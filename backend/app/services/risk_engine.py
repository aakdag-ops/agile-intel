"""
Risk Scoring Engine.

Computes individual signal scores (0–100) for a team based on
synced Jira data. Higher score = more risk.

Scores are stored as RiskSnapshot records for trend analysis.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.models import (
    Insight, InsightSource, InsightType, JiraIssue,
    RiskSnapshot, Severity, Sprint, Team, Transcript
)


# ── Thresholds ────────────────────────────────────────────────────────────────

# Hours in status before WIP aging triggers (per issue type)
WIP_AGING_THRESHOLDS = {
    "Story": 48,
    "Bug": 24,
    "Task": 36,
    "Epic": 120,
    "default": 48,
}

# Sprint completion % at which we start flagging velocity risk
VELOCITY_RISK_THRESHOLD_PCT = 0.70  # below 70% completion = high risk


def _score_to_severity(score: int) -> str:
    if score >= 75:
        return Severity.critical
    if score >= 50:
        return Severity.high
    if score >= 25:
        return Severity.medium
    return Severity.low


def _clamp(value: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, value)))


# ── Individual Signal Scorers ─────────────────────────────────────────────────

def score_wip_aging(issues: list[JiraIssue]) -> tuple[int, list[dict]]:
    """
    Score based on issues that have been In Progress too long.
    Returns (score, detail_list).
    """
    in_progress = [i for i in issues if i.status_category == "In Progress"]
    if not in_progress:
        return 0, []

    aged = []
    for issue in in_progress:
        threshold = WIP_AGING_THRESHOLDS.get(issue.issue_type, WIP_AGING_THRESHOLDS["default"])
        hours = issue.time_in_status_hours or 0
        if hours > threshold:
            overage_pct = ((hours - threshold) / threshold) * 100
            aged.append({
                "issue_key": issue.issue_key,
                "summary": issue.summary[:80],
                "hours_in_status": hours,
                "threshold_hours": threshold,
                "overage_pct": round(overage_pct, 1),
                "assignee": issue.assignee_name,
            })

    if not aged:
        return 0, []

    # Score = % of in-progress issues that are aged, amplified by severity
    pct_aged = len(aged) / len(in_progress)
    avg_overage = sum(a["overage_pct"] for a in aged) / len(aged)
    score = _clamp(pct_aged * 60 + min(avg_overage / 2, 40))
    return score, aged


def score_dependencies(issues: list[JiraIssue]) -> tuple[int, list[dict]]:
    """
    Score based on blocked issues and dependency depth.
    """
    blocked = [i for i in issues if i.is_blocked]
    if not issues:
        return 0, []

    detail = []
    for issue in blocked:
        links = issue.issue_links or {}
        detail.append({
            "issue_key": issue.issue_key,
            "summary": issue.summary[:80],
            "blocked_by": links.get("blocked_by", []),
            "dependency_depth": issue.dependency_depth,
            "status": issue.status,
        })

    pct_blocked = len(blocked) / max(len(issues), 1)
    # Weight critical blockers (in-progress blocked items) more heavily
    in_progress_blocked = [i for i in blocked if i.status_category == "In Progress"]
    critical_weight = len(in_progress_blocked) * 10

    score = _clamp(pct_blocked * 70 + critical_weight)
    return score, detail


def score_pbi_readiness(issues: list[JiraIssue]) -> tuple[int, list[dict]]:
    """
    Score based on stories missing acceptance criteria, assignees, or story points.
    Only checks To Do items (they should be ready before sprint starts).
    """
    todo_stories = [
        i for i in issues
        if i.issue_type in ("Story", "Task") and i.status_category == "To Do"
    ]
    if not todo_stories:
        return 0, []

    not_ready = []
    for issue in todo_stories:
        problems = []
        if not issue.has_acceptance_criteria:
            problems.append("missing acceptance criteria")
        if not issue.assignee_account_id:
            problems.append("unassigned")
        if not issue.story_points:
            problems.append("no story points")

        if problems:
            not_ready.append({
                "issue_key": issue.issue_key,
                "summary": issue.summary[:80],
                "problems": problems,
            })

    if not not_ready:
        return 0, []

    pct_not_ready = len(not_ready) / len(todo_stories)
    score = _clamp(pct_not_ready * 80)
    return score, not_ready


async def score_velocity_trend(
    db: AsyncSession, team: Team
) -> tuple[int, dict]:
    """
    Compare last 3 sprint velocities. Declining trend = higher risk.
    """
    result = await db.execute(
        select(Sprint)
        .where(Sprint.team_id == team.id, Sprint.state == "closed")
        .order_by(Sprint.complete_date.desc())
        .limit(4)
    )
    closed_sprints = result.scalars().all()

    if len(closed_sprints) < 2:
        return 0, {"reason": "insufficient_history"}

    velocities = [s.velocity for s in closed_sprints if s.velocity is not None]
    if len(velocities) < 2:
        return 0, {"reason": "no_velocity_data"}

    # Trend: compare most recent to rolling average of prior sprints
    recent = velocities[0]
    prior_avg = sum(velocities[1:]) / len(velocities[1:])

    if prior_avg == 0:
        return 0, {"reason": "zero_prior_velocity"}

    pct_change = (recent - prior_avg) / prior_avg  # negative = declining

    detail = {
        "recent_velocity": recent,
        "prior_average": round(prior_avg, 1),
        "pct_change": round(pct_change * 100, 1),
        "sprints_analyzed": len(velocities),
    }

    if pct_change >= 0:
        return 0, detail  # improving or stable

    # Declining: score proportional to decline severity
    score = _clamp(abs(pct_change) * 100)
    return score, detail


async def score_sprint_completion(
    db: AsyncSession, team: Team
) -> tuple[int, dict]:
    """
    For the active sprint: what % of committed points are done?
    Low completion near sprint end = high risk.
    """
    result = await db.execute(
        select(Sprint).where(
            Sprint.team_id == team.id,
            Sprint.state == "active"
        ).limit(1)
    )
    active_sprint = result.scalar_one_or_none()
    if not active_sprint:
        return 0, {"reason": "no_active_sprint"}

    now = datetime.now(timezone.utc)
    if not active_sprint.end_date or not active_sprint.start_date:
        return 0, {"reason": "sprint_dates_missing"}

    total_duration = (active_sprint.end_date - active_sprint.start_date).total_seconds()
    elapsed = (now - active_sprint.start_date).total_seconds()
    sprint_pct_elapsed = elapsed / max(total_duration, 1)

    # Get points from issues
    result2 = await db.execute(
        select(JiraIssue).where(
            JiraIssue.sprint_id == active_sprint.id,
            JiraIssue.team_id == team.id,
        )
    )
    issues = result2.scalars().all()
    total_points = sum(i.story_points or 0 for i in issues)
    done_points = sum(
        (i.story_points or 0) for i in issues if i.status_category == "Done"
    )
    completion_pct = done_points / max(total_points, 1)

    detail = {
        "sprint_name": active_sprint.name,
        "sprint_pct_elapsed": round(sprint_pct_elapsed * 100, 1),
        "total_points": total_points,
        "done_points": done_points,
        "completion_pct": round(completion_pct * 100, 1),
    }

    # Risk = behind pace relative to time elapsed
    pace_gap = sprint_pct_elapsed - completion_pct
    if pace_gap <= 0:
        return 0, detail

    score = _clamp(pace_gap * 100)
    return score, detail


async def score_meeting_alignment(
    db: AsyncSession, team: Team
) -> tuple[int, dict]:
    """
    Score based on unresolved signals from recent meeting transcripts.
    - Unresolved blockers from transcripts: +15 each
    - Action items with no Jira ref (likely untracked): +10 each
    - Scope changes: +20 each
    Cap at 100.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(Insight).where(
            Insight.team_id == team.id,
            Insight.source == "transcript",
            Insight.is_resolved == False,
            Insight.captured_at >= cutoff,
        )
    )
    insights = result.scalars().all()

    if not insights:
        return 0, {"reason": "no_transcript_insights"}

    score = 0
    detail = {"blockers": 0, "untracked_action_items": 0, "scope_changes": 0}

    for insight in insights:
        extra = insight.extra_data or {}
        transcript_type = extra.get("transcript_type", "")
        jira_refs = extra.get("jira_refs", [])

        if transcript_type == "blocker":
            score += 15
            detail["blockers"] += 1
        elif transcript_type == "action_item" and not jira_refs:
            score += 10
            detail["untracked_action_items"] += 1
        elif transcript_type == "scope_change":
            score += 20
            detail["scope_changes"] += 1

    return _clamp(score), detail


async def score_slack_signals(
    db: AsyncSession, team: Team
) -> tuple[int, dict]:
    """
    Score based on recent Slack-sourced insights (blockers, risks, customer escalations).
    Each insight contributes points weighted by type and severity.
    Cap at 100.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(Insight).where(
            Insight.team_id == team.id,
            Insight.source == InsightSource.slack,
            Insight.insight_type.in_([
                InsightType.blocker, InsightType.risk, InsightType.dependency
            ]),
            Insight.is_resolved == False,
            Insight.captured_at >= cutoff,
        )
    )
    insights = result.scalars().all()

    if not insights:
        return 0, {"reason": "no_slack_insights", "blockers": 0, "risks": 0, "top_items": []}

    # Points per severity tier — blockers weighted heavier than generic risks
    BLOCKER_PTS = {Severity.critical: 25, Severity.high: 15, Severity.medium: 10, Severity.low: 5}
    RISK_PTS    = {Severity.critical: 20, Severity.high: 12, Severity.medium:  6, Severity.low: 2}

    score = 0
    detail: dict = {"blockers": 0, "risks": 0, "top_items": []}

    for ins in insights:
        sev = ins.severity
        extra = ins.extra_data or {}

        if ins.insight_type in (InsightType.blocker,):
            score += BLOCKER_PTS.get(sev, 5)
            detail["blockers"] += 1
        else:
            score += RISK_PTS.get(sev, 2)
            detail["risks"] += 1

        if len(detail["top_items"]) < 5:
            detail["top_items"].append({
                "content": ins.content[:120],
                "severity": sev,
                "type": ins.insight_type,
                "channel": extra.get("channel", ""),
                "slack_type": extra.get("slack_type", ""),
            })

    return _clamp(score), detail


async def score_sentiment(
    db: AsyncSession, team: Team
) -> tuple[int, dict]:
    """
    Score based on negative vs positive sentiment signals from BOTH Slack and transcripts.
    Negative sentiment (frustration, morale issues) increases risk score.
    Positive sentiment (confidence, progress) reduces it slightly.
    Cap at 100, floor at 0.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(Insight).where(
            Insight.team_id == team.id,
            Insight.source.in_([InsightSource.slack, InsightSource.transcript]),
            Insight.insight_type == InsightType.sentiment,
            Insight.captured_at >= cutoff,
        )
    )
    insights = result.scalars().all()

    if not insights:
        return 0, {"reason": "no_sentiment_insights", "negative": 0, "positive": 0}

    NEGATIVE_PTS = {Severity.critical: 25, Severity.high: 15, Severity.medium: 8, Severity.low: 4}
    POSITIVE_REDUCTION = 3  # each positive signal reduces score by this amount

    score = 0
    detail: dict = {"negative": 0, "positive": 0, "sources": {"slack": 0, "transcript": 0}}

    for ins in insights:
        extra = ins.extra_data or {}
        slack_type = extra.get("slack_type", "")
        transcript_type = extra.get("transcript_type", "")
        is_negative = "negative" in slack_type or "negative" in transcript_type

        if is_negative:
            score += NEGATIVE_PTS.get(ins.severity, 4)
            detail["negative"] += 1
        else:
            score -= POSITIVE_REDUCTION
            detail["positive"] += 1

        src = ins.source if ins.source in detail["sources"] else "slack"
        detail["sources"][src] = detail["sources"].get(src, 0) + 1

    return _clamp(score), detail


# ── Process Adherence ─────────────────────────────────────────────────────────

def score_process_adherence(issues: list[JiraIssue]) -> tuple[int, list[dict]]:
    """
    Detect issues that jumped directly to Done without passing through In Progress.
    """
    suspicious = []
    done_issues = [i for i in issues if i.status_category == "Done"]

    for issue in done_issues:
        transitions = getattr(issue, "transitions", [])
        statuses_visited = {t.to_status for t in transitions}
        has_in_progress = any(
            "progress" in s.lower() or "doing" in s.lower() or "development" in s.lower()
            for s in statuses_visited
        )
        if not has_in_progress and transitions:
            suspicious.append({
                "issue_key": issue.issue_key,
                "summary": issue.summary[:80],
                "statuses_visited": list(statuses_visited),
            })

    if not done_issues:
        return 0, []

    pct_suspicious = len(suspicious) / len(done_issues)
    score = _clamp(pct_suspicious * 60)
    return score, suspicious


# ── Master Scorer ─────────────────────────────────────────────────────────────

async def compute_risk_snapshot(team_id: str) -> RiskSnapshot | None:
    """
    Full risk computation for a team.
    Fetches current data, scores all signals, persists snapshot and insights.
    """
    async with AsyncSessionLocal() as db:
        # Load team
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            return None

        # Load active sprint issues
        result2 = await db.execute(
            select(Sprint).where(Sprint.team_id == team_id, Sprint.state == "active")
        )
        active_sprint = result2.scalar_one_or_none()

        if active_sprint:
            result3 = await db.execute(
                select(JiraIssue).where(
                    JiraIssue.sprint_id == active_sprint.id,
                    JiraIssue.team_id == team_id,
                )
            )
        else:
            result3 = await db.execute(
                select(JiraIssue).where(
                    JiraIssue.team_id == team_id,
                    JiraIssue.status_category != "Done",
                )
            )
        issues = result3.scalars().all()

        # ── Run all scorers ───────────────────────────────────────────────
        wip_score, wip_detail = score_wip_aging(issues)
        dep_score, dep_detail = score_dependencies(issues)
        pbi_score, pbi_detail = score_pbi_readiness(issues)
        vel_score, vel_detail = await score_velocity_trend(db, team)
        completion_score, completion_detail = await score_sprint_completion(db, team)
        meeting_score, meeting_detail = await score_meeting_alignment(db, team)

        # Velocity trend is a blend of velocity decline + sprint completion
        velocity_trend_score = _clamp((vel_score + completion_score) / 2)

        # Slack and sentiment scores — derived from stored Insight records
        slack_score, slack_detail = await score_slack_signals(db, team)
        sentiment_score, sentiment_detail = await score_sentiment(db, team)

        # ── Composite weighted score ──────────────────────────────────────
        composite = _clamp(
            wip_score * team.weight_wip_aging
            + dep_score * team.weight_dependencies
            + velocity_trend_score * team.weight_velocity_trend
            + pbi_score * team.weight_pbi_readiness
            + slack_score * team.weight_slack_blockers
            + sentiment_score * team.weight_sentiment
            + meeting_score * team.weight_meeting_alignment
        )

        raw_signals = {
            "wip_aging": {"score": wip_score, "detail": wip_detail[:10]},
            "dependencies": {"score": dep_score, "detail": dep_detail[:10]},
            "pbi_readiness": {"score": pbi_score, "detail": pbi_detail[:10]},
            "velocity_trend": {"score": velocity_trend_score, "vel_detail": vel_detail, "completion_detail": completion_detail},
            "slack_blockers": {"score": slack_score, "detail": slack_detail},
            "sentiment": {"score": sentiment_score, "detail": sentiment_detail},
            "meeting_alignment": {"score": meeting_score, "detail": meeting_detail},
            "issue_count": len(issues),
            "active_sprint": active_sprint.name if active_sprint else None,
        }

        snapshot = RiskSnapshot(
            team_id=team_id,
            wip_aging_score=wip_score,
            dependency_score=dep_score,
            velocity_trend_score=velocity_trend_score,
            pbi_readiness_score=pbi_score,
            slack_blocker_score=slack_score,
            sentiment_score=sentiment_score,
            meeting_alignment_score=meeting_score,
            composite_score=composite,
            raw_signals=raw_signals,
        )
        db.add(snapshot)

        # ── Generate insights from high-scoring signals ───────────────────
        await _generate_insights(db, team, snapshot, raw_signals)

        await db.commit()
        await db.refresh(snapshot)

        logger.info(
            "risk_score.computed",
            team=team.jira_project_key,
            composite=composite,
            wip=wip_score,
            deps=dep_score,
            pbi=pbi_score,
            slack=slack_score,
            sentiment=sentiment_score,
            meeting=meeting_score,
        )
        return snapshot


async def _generate_insights(
    db: AsyncSession,
    team: Team,
    snapshot: RiskSnapshot,
    raw_signals: dict,
) -> None:
    """Create Insight records for high-severity signals."""
    now = datetime.now(timezone.utc)

    # WIP aging insights
    for item in raw_signals.get("wip_aging", {}).get("detail", []):
        if item["overage_pct"] > 50:
            content = (
                f"{item['issue_key']} has been In Progress for {item['hours_in_status']:.0f}h "
                f"(threshold: {item['threshold_hours']}h). "
                f"Assigned to {item['assignee'] or 'nobody'}."
            )
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.jira,
                insight_type=InsightType.risk,
                content=content,
                severity=Severity.high if item["overage_pct"] > 100 else Severity.medium,
                captured_at=now,
                extra_data=item,
            ))

    # Blocked issue insights
    for item in raw_signals.get("dependencies", {}).get("detail", []):
        if item["status"] == "In Progress":
            content = (
                f"{item['issue_key']} is In Progress but blocked by: "
                f"{', '.join(item['blocked_by'])}."
            )
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.jira,
                insight_type=InsightType.blocker,
                content=content,
                severity=Severity.high,
                captured_at=now,
                extra_data=item,
            ))

    # PBI readiness insights
    if raw_signals.get("pbi_readiness", {}).get("score", 0) > 50:
        not_ready_count = len(raw_signals["pbi_readiness"].get("detail", []))
        content = (
            f"{not_ready_count} backlog items are not sprint-ready "
            f"(missing acceptance criteria, assignee, or story points)."
        )
        db.add(Insight(
            team_id=team.id,
            source=InsightSource.jira,
            insight_type=InsightType.risk,
            content=content,
            severity=_score_to_severity(raw_signals["pbi_readiness"]["score"]),
            captured_at=now,
            extra_data={"not_ready": raw_signals["pbi_readiness"]["detail"][:5]},
        ))

    # Velocity insights
    vel_detail = raw_signals.get("velocity_trend", {}).get("vel_detail", {})
    if isinstance(vel_detail, dict) and vel_detail.get("pct_change", 0) < -20:
        content = (
            f"Velocity declined {abs(vel_detail['pct_change']):.0f}% vs prior sprint average "
            f"({vel_detail['recent_velocity']} vs {vel_detail['prior_average']} points)."
        )
        db.add(Insight(
            team_id=team.id,
            source=InsightSource.jira,
            insight_type=InsightType.risk,
            content=content,
            severity=Severity.high if vel_detail["pct_change"] < -40 else Severity.medium,
            captured_at=now,
            extra_data=vel_detail,
        ))

    # Slack blocker insights — summarize when score is elevated
    slack_detail = raw_signals.get("slack_blockers", {}).get("detail", {})
    if isinstance(slack_detail, dict):
        blocker_count = slack_detail.get("blockers", 0)
        risk_count = slack_detail.get("risks", 0)
        slack_score_val = raw_signals.get("slack_blockers", {}).get("score", 0)
        if slack_score_val >= 25:
            parts = []
            if blocker_count:
                parts.append(f"{blocker_count} active blocker(s)")
            if risk_count:
                parts.append(f"{risk_count} risk signal(s)")
            content = (
                f"Slack signals indicate {' and '.join(parts)} in the last 7 days."
                if parts else f"Elevated Slack risk score ({slack_score_val})."
            )
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.slack,
                insight_type=InsightType.risk,
                content=content,
                severity=_score_to_severity(slack_score_val),
                captured_at=now,
                extra_data=slack_detail,
            ))

    # Sentiment insights — flag when team morale is low
    sentiment_detail = raw_signals.get("sentiment", {}).get("detail", {})
    if isinstance(sentiment_detail, dict):
        neg_count = sentiment_detail.get("negative", 0)
        sentiment_score_val = raw_signals.get("sentiment", {}).get("score", 0)
        if sentiment_score_val >= 20 and neg_count > 0:
            sources = sentiment_detail.get("sources", {})
            source_str = " and ".join(
                f"{count} from {src}" for src, count in sources.items() if count > 0
            ) or "multiple sources"
            content = (
                f"{neg_count} negative sentiment signal(s) detected "
                f"({source_str}) in the last 7 days."
            )
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.slack,
                insight_type=InsightType.sentiment,
                content=content,
                severity=_score_to_severity(sentiment_score_val),
                captured_at=now,
                extra_data=sentiment_detail,
            ))

    # Meeting alignment insights
    meeting_detail = raw_signals.get("meeting_alignment", {}).get("detail", {})
    if isinstance(meeting_detail, dict):
        if meeting_detail.get("scope_changes", 0) > 0:
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.transcript,
                insight_type=InsightType.scope_change,
                content=f"{meeting_detail['scope_changes']} scope change(s) detected in recent meeting transcripts.",
                severity=Severity.high,
                captured_at=now,
                extra_data=meeting_detail,
            ))
        if meeting_detail.get("untracked_action_items", 0) > 2:
            db.add(Insight(
                team_id=team.id,
                source=InsightSource.transcript,
                insight_type=InsightType.risk,
                content=f"{meeting_detail['untracked_action_items']} action items from meetings have no Jira reference.",
                severity=Severity.medium,
                captured_at=now,
                extra_data=meeting_detail,
            ))


async def run_risk_scoring_for_all_teams() -> None:
    """Entry point called by the scheduler."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Team).where(Team.is_active == True))
        teams = result.scalars().all()

    for team in teams:
        try:
            await compute_risk_snapshot(str(team.id))
        except Exception as e:
            logger.error("risk_score.failed", team=team.jira_project_key, error=str(e))
