"""
AI synthesis service.
Uses Claude to generate natural-language project status answers
from Jira, Slack insights, meeting transcripts, and backlog healthcheck.
"""
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import AsyncGenerator

import anthropic
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.models import (
    BacklogHealthcheck, Insight, JiraIssue, RiskSnapshot,
    Sprint, Team, ChatMessage, Transcript,
)


RISK_LEVEL_MAP = {
    (0, 25): ("low", "🟢"),
    (25, 50): ("medium", "🟡"),
    (50, 75): ("high", "🟠"),
    (75, 101): ("critical", "🔴"),
}


def _risk_level(score: int) -> tuple[str, str]:
    for (lo, hi), val in RISK_LEVEL_MAP.items():
        if lo <= score < hi:
            return val
    return ("critical", "🔴")


def WIP_THRESHOLD(issue_type: str) -> float:
    from app.services.risk_engine import WIP_AGING_THRESHOLDS
    return WIP_AGING_THRESHOLDS.get(issue_type, WIP_AGING_THRESHOLDS["default"])


# ── Analytics helpers ──────────────────────────────────────────────────────────

def _compute_cycle_times(done_issues: list) -> dict:
    """Compute median cycle time in days by issue type (created → resolved)."""
    by_type: dict[str, list[float]] = {}
    all_times: list[float] = []
    for i in done_issues:
        if i.created_at_jira and i.status_changed_at:
            days = (i.status_changed_at - i.created_at_jira).days
            if 0 < days < 365:  # sanity filter
                itype = (i.issue_type or "Other").lower()
                by_type.setdefault(itype, []).append(days)
                all_times.append(days)
    result: dict = {}
    if all_times:
        result["overall"] = round(median(all_times), 1)
    for itype, times in by_type.items():
        if times:
            result[itype] = round(median(times), 1)
    return result


def _compute_throughput(done_issues: list) -> dict:
    """Compute throughput — issues/week and pts/week for last 30 and 90 days."""
    now = datetime.now(timezone.utc)
    last_30 = [i for i in done_issues
               if i.status_changed_at and i.status_changed_at >= now - timedelta(days=30)]
    last_90 = [i for i in done_issues
               if i.status_changed_at and i.status_changed_at >= now - timedelta(days=90)]

    def _stats(issues: list, weeks: float) -> dict:
        pts = sum(i.story_points or 0 for i in issues)
        return {
            "issues": len(issues),
            "issues_per_week": round(len(issues) / weeks, 1) if issues else 0,
            "points": round(pts),
            "pts_per_week": round(pts / weeks, 1) if issues else 0,
        }

    return {
        "last_30_days": _stats(last_30, 4.3),
        "last_90_days": _stats(last_90, 12.9),
    }


def _estimate_completion_date(issue, cycle_times: dict) -> str | None:
    """
    Estimate when an in-progress issue might complete based on:
    - Median cycle time for this issue type
    - Age of the issue (already-spent time)
    - Risk multipliers: blocked=2×, WIP-aged=1.5×, dependencies=1.3×
    Returns a human-readable string like '~Mar 25' or '~Mar 25 → ~Apr 8 (risk-adj, blocked)'
    """
    now = datetime.now(timezone.utc)
    itype = (issue.issue_type or "Story").lower()
    median_days = cycle_times.get(itype) or cycle_times.get("overall")
    if not median_days:
        return None

    # Remaining time = median cycle - age already spent (floor at 1d)
    age_days = (now - issue.created_at_jira).days if issue.created_at_jira else 0
    remaining_days = max(1.0, median_days - age_days)

    # Risk multipliers
    multiplier = 1.0
    risk_factors: list[str] = []
    if issue.is_blocked:
        multiplier = max(multiplier, 2.0)
        risk_factors.append("blocked")
    if issue.time_in_status_hours and issue.time_in_status_hours > WIP_THRESHOLD(issue.issue_type):
        multiplier = max(multiplier, 1.5)
        risk_factors.append(f"WIP-aged {issue.time_in_status_hours:.0f}h")
    dep_links = (issue.issue_links or {}).get("blocked_by", []) or []
    if dep_links and not issue.is_blocked:
        multiplier = max(multiplier, 1.3)
        risk_factors.append("has-dependencies")

    jira_date = (now + timedelta(days=remaining_days)).strftime("%b %d")
    adjusted_days = remaining_days * multiplier
    adj_date = (now + timedelta(days=adjusted_days)).strftime("%b %d")

    if multiplier > 1.0:
        return f"~{jira_date} (Jira est.) → ~{adj_date} (risk-adj: {', '.join(risk_factors)})"
    return f"~{jira_date}"


# ── Prompt builders ────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return """You are an expert Agile Coach and Risk Intelligence assistant embedded in a project management platform.

Your role is to help engineering managers and agile coaches understand the TRUE state of their teams and projects — not just what Jira says, but what all the signals reveal.

You have access to a rich, multi-source context: Jira sprint data, risk scores, Slack-derived insights, meeting transcripts, backlog healthcheck data, historical delivery metrics (cycle times, throughput), and AI-generated completion estimates for in-progress work. Use ALL of them when answering.

When answering questions:
1. Lead with an honest, concise assessment (2-3 sentences)
2. Cross-reference signals across sources — if a blocker appeared in Jira AND was discussed in a transcript, flag that
3. Highlight the gap between what the board shows and what the broader signals say
4. Give concrete, actionable recommendations (not generic agile advice)
5. Flag trend changes — is the situation improving or worsening?
6. When meeting transcripts are available, cite specific decisions, action items, or concerns raised
7. For completion date questions, use the "Completion Estimates" section which already accounts for risk factors (blocked issues get 2× multiplier, WIP-aged get 1.5×, dependency issues 1.3×). Always cite both the Jira estimate and the risk-adjusted estimate.
8. For historical questions ("what did we do last month?", "how has velocity changed?"), use the "Historical Delivery" section with throughput, cycle times, and the completed issues list.

Your tone is direct, analytical, and coaching-oriented. You speak like a seasoned Scrum Master who has seen these patterns before. You do not sugarcoat risks, but you frame them constructively.

Always cite specific issue keys, sprint names, transcript titles, or channel names when available.
Format your responses with clear sections using markdown headers.
"""


def _build_context_block(
    team: Team,
    snapshot: RiskSnapshot | None,
    active_sprint: Sprint | None,
    past_sprints: list[Sprint],
    recent_insights: list[Insight],
    sprint_issues: list[JiraIssue],
    prev_snapshot: RiskSnapshot | None,
    recent_transcripts: list[Transcript],
    latest_healthcheck: BacklogHealthcheck | None,
    done_issues: list[JiraIssue] | None = None,
    analytics: dict | None = None,
) -> str:
    """Build the structured context block injected into the user prompt."""
    now = datetime.now(timezone.utc)
    lines = []

    lines.append(f"## Team: {team.name} ({team.jira_project_key})")
    lines.append(f"Data as of: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if team.last_jira_sync:
        lines.append(f"Last Jira sync: {team.last_jira_sync.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # ── Risk scores ───────────────────────────────────────────────────────────
    if snapshot:
        level, emoji = _risk_level(snapshot.composite_score)
        lines.append(f"### Risk Score: {snapshot.composite_score}/100 {emoji} ({level.upper()})")
        if prev_snapshot:
            delta = snapshot.composite_score - prev_snapshot.composite_score
            trend = "↑ worsening" if delta > 5 else ("↓ improving" if delta < -5 else "→ stable")
            lines.append(f"Trend vs previous snapshot: {trend} (delta: {delta:+d})")
        lines.append("")
        lines.append("**Signal breakdown:**")
        raw = snapshot.raw_signals or {}
        lines.append(f"- WIP Aging: {snapshot.wip_aging_score}/100")
        lines.append(f"- Hidden Dependencies: {snapshot.dependency_score}/100")
        lines.append(f"- Velocity Trend: {snapshot.velocity_trend_score}/100")
        lines.append(f"- PBI Readiness: {snapshot.pbi_readiness_score}/100")
        lines.append(f"- Slack Signals: {snapshot.slack_blocker_score}/100")
        lines.append(f"- Team Sentiment: {snapshot.sentiment_score}/100")
        lines.append("")

        vel = raw.get("velocity_trend", {})
        if isinstance(vel.get("vel_detail"), dict) and "recent_velocity" in vel["vel_detail"]:
            vd = vel["vel_detail"]
            lines.append(
                f"**Velocity:** {vd['recent_velocity']} pts (recent sprint) vs "
                f"{vd['prior_average']} pts (avg of prior {vd.get('sprints_analyzed', 2) - 1} sprints), "
                f"change: {vd.get('pct_change', 0):+.0f}%"
            )
            lines.append("")

    # ── Active sprint ─────────────────────────────────────────────────────────
    if active_sprint:
        lines.append(f"### Active Sprint: {active_sprint.name}")
        if active_sprint.end_date:
            days_left = (active_sprint.end_date - now).days
            lines.append(f"Days remaining: {days_left}")
        if active_sprint.goal:
            lines.append(f"Sprint goal: {active_sprint.goal}")
        if snapshot and snapshot.raw_signals:
            cd = snapshot.raw_signals.get("velocity_trend", {}).get("completion_detail", {})
            if cd:
                lines.append(
                    f"Points done/total: {cd.get('done_points', 0)}/{cd.get('total_points', 0)} "
                    f"({cd.get('completion_pct', 0):.0f}%) | Sprint {cd.get('sprint_pct_elapsed', 0):.0f}% elapsed"
                )
        lines.append("")

    # ── Full sprint board ─────────────────────────────────────────────────────
    if sprint_issues:
        by_status: dict[str, list[JiraIssue]] = {}
        for issue in sprint_issues:
            by_status.setdefault(issue.status_category, []).append(issue)

        lines.append(f"### Sprint Board ({len(sprint_issues)} issues total)")
        status_order = ["In Progress", "To Do", "Done"]
        all_statuses = status_order + [s for s in by_status if s not in status_order]
        cycle_times = (analytics or {}).get("cycle_times", {})

        for status in all_statuses:
            group = by_status.get(status, [])
            if not group:
                continue
            lines.append(f"**{status} ({len(group)}):**")
            for i in group[:25]:
                sp = f" [{int(i.story_points)}sp]" if i.story_points else ""
                assignee = f" → {i.assignee_name}" if i.assignee_name else ""
                blocked_flag = " ⛔BLOCKED" if i.is_blocked else ""
                aged_flag = ""
                if i.time_in_status_hours and i.time_in_status_hours > WIP_THRESHOLD(i.issue_type):
                    aged_flag = f" ⏰{i.time_in_status_hours:.0f}h"
                # Append completion estimate for in-progress items
                est_flag = ""
                if status == "In Progress" and cycle_times:
                    est = _estimate_completion_date(i, cycle_times)
                    if est:
                        est_flag = f" 📅{est}"
                lines.append(f"  - {i.issue_key}{sp} [{i.issue_type}]{assignee}{blocked_flag}{aged_flag}{est_flag}: {i.summary[:70]}")
            if len(group) > 25:
                lines.append(f"  ... and {len(group) - 25} more")
        lines.append("")

        blocked = [i for i in sprint_issues if i.is_blocked]
        if blocked:
            lines.append(f"**BLOCKED ISSUES ({len(blocked)}):**")
            for i in blocked[:8]:
                links = (i.issue_links or {}).get("blocked_by", [])
                lines.append(f"  - {i.issue_key}: {i.summary[:60]} — blocked by: {', '.join(links)}")
            lines.append("")

    # ── Sprint history (up to 12 sprints) ─────────────────────────────────────
    if past_sprints:
        lines.append(f"### Sprint History (last {len(past_sprints)} closed sprints)")
        for s in past_sprints:
            committed = f"{s.committed_points:.0f}" if s.committed_points else "?"
            completed = f"{s.completed_points:.0f}" if s.completed_points else "?"
            velocity = f"{s.velocity:.0f}" if s.velocity else "?"
            completion_rate = ""
            if s.committed_points and s.committed_points > 0 and s.completed_points is not None:
                rate = round(s.completed_points / s.committed_points * 100)
                completion_rate = f", {rate}% delivered"
            date_range = ""
            if s.start_date and s.complete_date:
                date_range = f" ({s.start_date.strftime('%b %d')}–{s.complete_date.strftime('%b %d')})"
            lines.append(
                f"- {s.name}{date_range}: committed={committed}pts, completed={completed}pts, "
                f"velocity={velocity}pts{completion_rate}"
            )
            if s.goal:
                lines.append(f"  Goal: {s.goal}")
        lines.append("")

    # ── Historical delivery (cycle times + throughput + completed items) ───────
    if analytics:
        ct = analytics.get("cycle_times", {})
        tp = analytics.get("throughput", {})

        if ct or tp:
            lines.append("### Historical Delivery (last 6 months)")

        if ct:
            ct_parts = []
            if ct.get("overall"):
                ct_parts.append(f"Overall: {ct['overall']}d")
            for itype in ["story", "bug", "task"]:
                if ct.get(itype):
                    ct_parts.append(f"{itype.capitalize()}: {ct[itype]}d")
            if ct_parts:
                lines.append(f"**Cycle time (median, created→done):** {' | '.join(ct_parts)}")

        if tp:
            d30 = tp.get("last_30_days", {})
            d90 = tp.get("last_90_days", {})
            if d30.get("issues"):
                lines.append(
                    f"**Throughput last 30d:** {d30['issues']} issues ({d30['issues_per_week']}/wk), "
                    f"{d30['points']} pts ({d30['pts_per_week']} pts/wk)"
                )
            if d90.get("issues"):
                lines.append(
                    f"**Throughput last 90d:** {d90['issues']} issues ({d90['issues_per_week']}/wk), "
                    f"{d90['points']} pts ({d90['pts_per_week']} pts/wk)"
                )

        # Recently completed issues list
        if done_issues:
            recent_done = sorted(
                [i for i in done_issues if i.status_changed_at],
                key=lambda x: x.status_changed_at,
                reverse=True,
            )[:30]
            if recent_done:
                lines.append(f"**Recently completed ({len(recent_done)} shown, up to 30):**")
                for i in recent_done:
                    sp = f" [{int(i.story_points)}sp]" if i.story_points else ""
                    done_date = i.status_changed_at.strftime("%b %d") if i.status_changed_at else "?"
                    cycle = ""
                    if i.created_at_jira and i.status_changed_at:
                        d = (i.status_changed_at - i.created_at_jira).days
                        cycle = f" ({d}d cycle)"
                    assignee = f" → {i.assignee_name}" if i.assignee_name else ""
                    lines.append(f"  - {i.issue_key}{sp} [{i.issue_type}]{assignee} done {done_date}{cycle}: {i.summary[:65]}")
        lines.append("")

    # ── Recent insights (all sources) ────────────────────────────────────────
    if recent_insights:
        by_source: dict[str, list[Insight]] = {}
        for ins in recent_insights:
            by_source.setdefault(ins.source, []).append(ins)

        lines.append(f"### Recent Insights ({len(recent_insights)} from last 30 days)")
        source_order = ["transcript", "slack", "jira"]
        for src in source_order + [s for s in by_source if s not in source_order]:
            group = by_source.get(src, [])
            if not group:
                continue
            lines.append(f"**From {src.upper()}:**")
            for ins in group[:8]:
                sev_emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🔶", "critical": "🚨"}.get(ins.severity, "•")
                date_str = ins.captured_at.strftime("%b %d")
                lines.append(f"  {sev_emoji} [{date_str}] {ins.insight_type}: {ins.content}")
        lines.append("")

    # ── Meeting transcripts ───────────────────────────────────────────────────
    if recent_transcripts:
        lines.append(f"### Meeting Transcripts (last {len(recent_transcripts)})")
        for t in recent_transcripts:
            date_str = t.meeting_date.strftime("%Y-%m-%d") if t.meeting_date else t.created_at.strftime("%Y-%m-%d")
            participants = ", ".join(t.participants or []) if t.participants else "unknown"
            lines.append(f"**[{date_str}] {t.title}** (participants: {participants})")
            text = (t.raw_text or "").strip()
            if len(text) > 1200:
                text = text[:1200] + "... [truncated]"
            lines.append(text)
            lines.append("")

    # ── Backlog healthcheck ───────────────────────────────────────────────────
    if latest_healthcheck and latest_healthcheck.status == "complete":
        hc = latest_healthcheck
        gen_date = hc.generated_at.strftime("%Y-%m-%d")
        lines.append(f"### Backlog Healthcheck (generated {gen_date}, {hc.total_items} items analysed)")

        if hc.lead_times:
            lt = hc.lead_times
            lt_parts = []
            if lt.get("avg"):
                lt_parts.append(f"avg={lt['avg']}d")
            if lt.get("story"):
                lt_parts.append(f"story={lt['story']}d")
            if lt.get("bug"):
                lt_parts.append(f"bug={lt['bug']}d")
            if lt.get("task"):
                lt_parts.append(f"task={lt['task']}d")
            if lt_parts:
                lines.append(f"Lead times: {', '.join(lt_parts)}")

        group_labels = {
            "completed_last_month": "Completed Last Month",
            "planned_this_month": "Planned This Month",
            "next_month": "Next Month Backlog",
        }
        if hc.ai_insights:
            lines.append("**AI insights per group:**")
            for key, label in group_labels.items():
                insight_text = hc.ai_insights.get(key, "")
                if insight_text and insight_text != "No items found.":
                    lines.append(f"- {label}: {insight_text}")
            lines.append("")

        if hc.top_issues:
            lines.append("**Top backlog items needing attention:**")
            for item in hc.top_issues[:5]:
                lines.append(f"  - {item.get('key', '?')}: {item.get('summary', '')[:60]}")
                if item.get("root_cause"):
                    lines.append(f"    Root cause: {item['root_cause']}")
            lines.append("")

        if hc.concrete_actions:
            lines.append("**Recommended actions:**")
            for i, action in enumerate(hc.concrete_actions[:3], 1):
                lines.append(f"  {i}. {action}")
        lines.append("")

    return "\n".join(lines)


class ChatService:

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def get_project_context(self, db: AsyncSession, team_id: str) -> dict:
        """Load all context needed for a project status answer."""
        # Team
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            return {}

        # Latest risk snapshot
        r2 = await db.execute(
            select(RiskSnapshot)
            .where(RiskSnapshot.team_id == team_id)
            .order_by(desc(RiskSnapshot.snapshot_at))
            .limit(1)
        )
        snapshot = r2.scalar_one_or_none()

        # Previous snapshot (for trend)
        prev_snapshot = None
        if snapshot:
            r3 = await db.execute(
                select(RiskSnapshot)
                .where(RiskSnapshot.team_id == team_id, RiskSnapshot.snapshot_at < snapshot.snapshot_at)
                .order_by(desc(RiskSnapshot.snapshot_at))
                .limit(1)
            )
            prev_snapshot = r3.scalar_one_or_none()

        # Active sprint
        r4 = await db.execute(
            select(Sprint).where(Sprint.team_id == team_id, Sprint.state == "active")
        )
        active_sprint = r4.scalar_one_or_none()

        # Past 12 closed sprints (was 4 — extended for trend analysis)
        r5 = await db.execute(
            select(Sprint)
            .where(Sprint.team_id == team_id, Sprint.state == "closed")
            .order_by(desc(Sprint.complete_date))
            .limit(12)
        )
        past_sprints = list(r5.scalars().all())

        # All sprint issues (active sprint + any unresolved)
        issue_query = select(JiraIssue).where(JiraIssue.team_id == team_id)
        if active_sprint:
            issue_query = issue_query.where(JiraIssue.sprint_id == active_sprint.id)
        else:
            issue_query = issue_query.where(JiraIssue.status_category != "Done")
        r6 = await db.execute(issue_query)
        sprint_issues = list(r6.scalars().all())

        # Recent insights — 30 days, up to 40 items
        month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        r7 = await db.execute(
            select(Insight)
            .where(Insight.team_id == team_id, Insight.captured_at >= month_ago)
            .order_by(desc(Insight.captured_at))
            .limit(40)
        )
        recent_insights = list(r7.scalars().all())

        # Last 3 transcripts
        r8 = await db.execute(
            select(Transcript)
            .where(Transcript.team_id == team_id)
            .order_by(desc(Transcript.meeting_date))
            .limit(3)
        )
        recent_transcripts = list(r8.scalars().all())

        # Latest complete healthcheck
        r9 = await db.execute(
            select(BacklogHealthcheck)
            .where(BacklogHealthcheck.team_id == team_id, BacklogHealthcheck.status == "complete")
            .order_by(desc(BacklogHealthcheck.generated_at))
            .limit(1)
        )
        latest_healthcheck = r9.scalar_one_or_none()

        # Done issues from last 6 months — for cycle time, throughput, history
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
        r10 = await db.execute(
            select(JiraIssue)
            .where(
                JiraIssue.team_id == team_id,
                JiraIssue.status_category == "Done",
                JiraIssue.status_changed_at >= six_months_ago,
            )
            .order_by(desc(JiraIssue.status_changed_at))
            .limit(500)
        )
        done_issues = list(r10.scalars().all())

        # Compute analytics from done issues
        analytics = {
            "cycle_times": _compute_cycle_times(done_issues),
            "throughput": _compute_throughput(done_issues),
            "total_done_6mo": len(done_issues),
        }

        return {
            "team": team,
            "snapshot": snapshot,
            "prev_snapshot": prev_snapshot,
            "active_sprint": active_sprint,
            "past_sprints": past_sprints,
            "sprint_issues": sprint_issues,
            "recent_insights": recent_insights,
            "recent_transcripts": recent_transcripts,
            "latest_healthcheck": latest_healthcheck,
            "done_issues": done_issues,
            "analytics": analytics,
        }

    def _make_context_block(self, ctx: dict) -> str:
        return _build_context_block(
            team=ctx["team"],
            snapshot=ctx["snapshot"],
            prev_snapshot=ctx["prev_snapshot"],
            active_sprint=ctx["active_sprint"],
            past_sprints=ctx["past_sprints"],
            sprint_issues=ctx["sprint_issues"],
            recent_insights=ctx["recent_insights"],
            recent_transcripts=ctx["recent_transcripts"],
            latest_healthcheck=ctx["latest_healthcheck"],
            done_issues=ctx.get("done_issues"),
            analytics=ctx.get("analytics"),
        )

    async def chat(
        self,
        db: AsyncSession,
        user_id: str,
        message: str,
        team_id: str | None,
        session_id: str,
        history: list[dict],
    ) -> str:
        db.add(ChatMessage(
            user_id=user_id, team_id=team_id, session_id=session_id,
            role="user", content=message,
        ))
        await db.flush()

        context_block = ""
        if team_id:
            ctx = await self.get_project_context(db, team_id)
            if ctx:
                context_block = self._make_context_block(ctx)

        messages = list(history)
        user_content = message
        if context_block:
            user_content = (
                f"**LIVE PROJECT DATA:**\n\n{context_block}\n\n"
                f"---\n\n**My question:** {message}"
            )
        messages.append({"role": "user", "content": user_content})

        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=_build_system_prompt(),
            messages=messages,
        )
        reply = response.content[0].text

        db.add(ChatMessage(
            user_id=user_id, team_id=team_id, session_id=session_id,
            role="assistant", content=reply,
        ))
        await db.commit()
        return reply

    async def stream_chat(
        self,
        db: AsyncSession,
        user_id: str,
        message: str,
        team_id: str | None,
        session_id: str,
        history: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Streaming version — for SSE."""
        context_block = ""
        if team_id:
            ctx = await self.get_project_context(db, team_id)
            if ctx:
                context_block = self._make_context_block(ctx)

        messages = list(history)
        user_content = message
        if context_block:
            user_content = (
                f"**LIVE PROJECT DATA:**\n\n{context_block}\n\n"
                f"---\n\n**My question:** {message}"
            )
        messages.append({"role": "user", "content": user_content})

        full_reply = ""
        async with self.client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=_build_system_prompt(),
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_reply += text
                yield text

        db.add(ChatMessage(user_id=user_id, team_id=team_id, session_id=session_id, role="user", content=message))
        db.add(ChatMessage(user_id=user_id, team_id=team_id, session_id=session_id, role="assistant", content=full_reply))
        await db.commit()
