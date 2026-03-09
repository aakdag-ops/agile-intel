"""
AI synthesis service.
Uses Claude to generate natural-language project status answers
from Jira snapshots, risk scores, and insights.
"""
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import anthropic
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.models import (
    Insight, JiraIssue, RiskSnapshot, Sprint, Team, ChatMessage
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


def _build_system_prompt() -> str:
    return """You are an expert Agile Coach and Risk Intelligence assistant embedded in a project management platform.

Your role is to help engineering managers and agile coaches understand the TRUE state of their teams and projects — not just what Jira says, but what the signals reveal.

When answering questions about project status or team health, you:
1. Lead with an honest, concise assessment (2-3 sentences)
2. Identify the top 3-5 specific risks with their source (Jira/Slack/Transcript)
3. Highlight the gap between what the board shows and what the signals say
4. Give concrete, actionable recommendations (not generic agile advice)
5. Flag trend changes — is the situation improving or worsening?

Your tone is direct, analytical, and coaching-oriented. You speak like a seasoned Scrum Master who has seen these patterns before. You do not sugarcoat risks, but you frame them constructively.

Always cite specific issue keys, sprint names, or channel names when available.
Format your responses with clear sections using markdown headers.
"""


def _build_context_block(
    team: Team,
    snapshot: RiskSnapshot | None,
    active_sprint: Sprint | None,
    recent_insights: list[Insight],
    active_issues: list[JiraIssue],
    prev_snapshot: RiskSnapshot | None,
) -> str:
    """Build the structured context block injected into the user prompt."""
    now = datetime.now(timezone.utc)
    lines = []

    lines.append(f"## Team: {team.name} ({team.jira_project_key})")
    lines.append(f"Data as of: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if team.last_jira_sync:
        lines.append(f"Last Jira sync: {team.last_jira_sync.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Risk scores
    if snapshot:
        level, emoji = _risk_level(snapshot.composite_score)
        lines.append(f"### Risk Score: {snapshot.composite_score}/100 {emoji} ({level.upper()})")
        if prev_snapshot:
            delta = snapshot.composite_score - prev_snapshot.composite_score
            trend = "↑ worsening" if delta > 5 else ("↓ improving" if delta < -5 else "→ stable")
            lines.append(f"Trend vs 24h ago: {trend} (delta: {delta:+d})")
        lines.append("")
        lines.append("**Signal breakdown:**")
        raw = snapshot.raw_signals or {}
        lines.append(f"- WIP Aging: {snapshot.wip_aging_score}/100")
        lines.append(f"- Hidden Dependencies: {snapshot.dependency_score}/100")
        lines.append(f"- Velocity Trend: {snapshot.velocity_trend_score}/100")
        lines.append(f"- PBI Readiness: {snapshot.pbi_readiness_score}/100")
        lines.append(f"- Slack Signals: {snapshot.slack_blocker_score}/100 (not yet active)")
        lines.append(f"- Team Sentiment: {snapshot.sentiment_score}/100 (not yet active)")
        lines.append("")

        # Velocity detail
        vel = raw.get("velocity_trend", {})
        if isinstance(vel.get("vel_detail"), dict) and "recent_velocity" in vel["vel_detail"]:
            vd = vel["vel_detail"]
            lines.append(f"**Velocity:** {vd['recent_velocity']} pts (recent) vs {vd['prior_average']} pts (avg of prior {vd.get('sprints_analyzed',2)-1} sprints), change: {vd.get('pct_change',0):+.0f}%")
            lines.append("")

    # Active sprint
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
                lines.append(f"Points done/total: {cd.get('done_points',0)}/{cd.get('total_points',0)} ({cd.get('completion_pct',0):.0f}%) | Sprint {cd.get('sprint_pct_elapsed',0):.0f}% elapsed")
        lines.append("")

    # Issue summary
    if active_issues:
        by_status = {}
        for issue in active_issues:
            by_status[issue.status_category] = by_status.get(issue.status_category, 0) + 1
        lines.append("### Issue Status Distribution")
        for status, count in sorted(by_status.items()):
            lines.append(f"- {status}: {count}")
        lines.append("")

        blocked = [i for i in active_issues if i.is_blocked]
        if blocked:
            lines.append(f"**BLOCKED ISSUES ({len(blocked)}):**")
            for i in blocked[:5]:
                links = (i.issue_links or {}).get("blocked_by", [])
                lines.append(f"- {i.issue_key}: {i.summary[:60]} — blocked by: {', '.join(links)}")
            lines.append("")

        aged = [i for i in active_issues if
                i.time_in_status_hours and i.time_in_status_hours > WIP_THRESHOLD(i.issue_type)]
        if aged:
            lines.append(f"**AGED WIP ({len(aged)} issues in status > threshold):**")
            for i in aged[:5]:
                lines.append(f"- {i.issue_key} [{i.status}]: {i.summary[:60]} — {i.time_in_status_hours:.0f}h in status, assigned to {i.assignee_name or 'nobody'}")
            lines.append("")

    # Recent insights
    if recent_insights:
        lines.append(f"### Recent Insights (last 7 days)")
        for ins in recent_insights[:8]:
            severity_emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🔶", "critical": "🚨"}.get(ins.severity, "•")
            lines.append(f"{severity_emoji} [{ins.source.upper()}] {ins.insight_type}: {ins.content}")
        lines.append("")

    return "\n".join(lines)


def WIP_THRESHOLD(issue_type: str) -> float:
    from app.services.risk_engine import WIP_AGING_THRESHOLDS
    return WIP_AGING_THRESHOLDS.get(issue_type, WIP_AGING_THRESHOLDS["default"])


class ChatService:

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def get_project_context(
        self, db: AsyncSession, team_id: str
    ) -> dict:
        """Load all context needed for a project status answer."""
        # Team
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            return {}

        # Latest risk snapshot
        result2 = await db.execute(
            select(RiskSnapshot)
            .where(RiskSnapshot.team_id == team_id)
            .order_by(desc(RiskSnapshot.snapshot_at))
            .limit(1)
        )
        snapshot = result2.scalar_one_or_none()

        # Previous snapshot (for trend)
        prev_snapshot = None
        if snapshot:
            result3 = await db.execute(
                select(RiskSnapshot)
                .where(
                    RiskSnapshot.team_id == team_id,
                    RiskSnapshot.snapshot_at < snapshot.snapshot_at
                )
                .order_by(desc(RiskSnapshot.snapshot_at))
                .limit(1)
            )
            prev_snapshot = result3.scalar_one_or_none()

        # Active sprint
        result4 = await db.execute(
            select(Sprint).where(Sprint.team_id == team_id, Sprint.state == "active")
        )
        active_sprint = result4.scalar_one_or_none()

        # Active issues
        query = select(JiraIssue).where(
            JiraIssue.team_id == team_id,
            JiraIssue.status_category != "Done"
        )
        if active_sprint:
            query = query.where(JiraIssue.sprint_id == active_sprint.id)
        result5 = await db.execute(query)
        active_issues = result5.scalars().all()

        # Recent insights
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        result6 = await db.execute(
            select(Insight)
            .where(Insight.team_id == team_id, Insight.captured_at >= week_ago)
            .order_by(desc(Insight.captured_at))
            .limit(20)
        )
        recent_insights = result6.scalars().all()

        return {
            "team": team,
            "snapshot": snapshot,
            "prev_snapshot": prev_snapshot,
            "active_sprint": active_sprint,
            "active_issues": list(active_issues),
            "recent_insights": list(recent_insights),
        }

    async def chat(
        self,
        db: AsyncSession,
        user_id: str,
        message: str,
        team_id: str | None,
        session_id: str,
        history: list[dict],
    ) -> str:
        """
        Generate a response to a chat message.
        If team_id is provided, inject full project context.
        """
        # Save user message
        db.add(ChatMessage(
            user_id=user_id,
            team_id=team_id,
            session_id=session_id,
            role="user",
            content=message,
        ))
        await db.flush()

        # Build context
        context_block = ""
        if team_id:
            ctx = await self.get_project_context(db, team_id)
            if ctx:
                context_block = _build_context_block(
                    team=ctx["team"],
                    snapshot=ctx["snapshot"],
                    active_sprint=ctx["active_sprint"],
                    recent_insights=ctx["recent_insights"],
                    active_issues=ctx["active_issues"],
                    prev_snapshot=ctx["prev_snapshot"],
                )

        # Build messages
        messages = list(history)  # prior turns
        user_content = message
        if context_block:
            user_content = (
                f"**LIVE PROJECT DATA:**\n\n{context_block}\n\n"
                f"---\n\n**My question:** {message}"
            )
        messages.append({"role": "user", "content": user_content})

        # Call Claude
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=_build_system_prompt(),
            messages=messages,
        )
        reply = response.content[0].text

        # Save assistant response
        db.add(ChatMessage(
            user_id=user_id,
            team_id=team_id,
            session_id=session_id,
            role="assistant",
            content=reply,
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
        """Streaming version — for WebSocket / SSE."""
        context_block = ""
        if team_id:
            ctx = await self.get_project_context(db, team_id)
            if ctx:
                context_block = _build_context_block(
                    team=ctx["team"],
                    snapshot=ctx["snapshot"],
                    active_sprint=ctx["active_sprint"],
                    recent_insights=ctx["recent_insights"],
                    active_issues=ctx["active_issues"],
                    prev_snapshot=ctx["prev_snapshot"],
                )

        messages = list(history)
        user_content = message
        if context_block:
            user_content = (
                f"**LIVE PROJECT DATA:**\n\n{context_block}\n\n"
                f"---\n\n**My question:** {message}"
            )
        messages.append({"role": "user", "content": user_content})

        full_reply = ""
        with self.client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=_build_system_prompt(),
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_reply += text
                yield text

        # Persist after stream completes
        db.add(ChatMessage(user_id=user_id, team_id=team_id, session_id=session_id, role="user", content=message))
        db.add(ChatMessage(user_id=user_id, team_id=team_id, session_id=session_id, role="assistant", content=full_reply))
        await db.commit()
