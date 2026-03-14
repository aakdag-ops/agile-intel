"""
Team Feed API.
Returns a paginated, Jira-enriched stream of insights from all sources
(Slack, transcripts, risk engine) for a given team.
"""
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import Insight, JiraIssue, Team, Transcript, User

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("/teams/{team_id}")
async def get_team_feed(
    team_id: str,
    source: str = Query("all", description="all | slack | transcript | jira"),
    severity: str = Query("all", description="all | critical | high | medium | low"),
    issue_key: str | None = Query(None, description="Filter to insights mentioning a specific issue key"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Paginated team feed: all insights enriched with live Jira issue data.
    Insights with jira_refs show issue pills; others show as plain signal cards.
    """
    # ── Build base query ───────────────────────────────────────────────────────
    q = select(Insight).where(Insight.team_id == team_id)

    if source != "all":
        q = q.where(Insight.source == source)

    if severity != "all":
        q = q.where(Insight.severity == severity)

    if issue_key:
        # PostgreSQL JSONB containment: extra_data->'jira_refs' @> '["ONB-123"]'
        q = q.where(
            text("metadata->'jira_refs' @> :key_json").bindparams(
                key_json=f'["{issue_key.upper()}"]'
            )
        )

    # ── Count total ────────────────────────────────────────────────────────────
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # ── Fetch page ─────────────────────────────────────────────────────────────
    offset = (page - 1) * limit
    q = q.order_by(desc(Insight.captured_at)).offset(offset).limit(limit)
    rows = list((await db.execute(q)).scalars().all())

    # ── Collect transcript titles ──────────────────────────────────────────────
    transcript_ids = [r.transcript_id for r in rows if r.transcript_id]
    transcript_map: dict[str, str] = {}
    if transcript_ids:
        tr = await db.execute(
            select(Transcript.id, Transcript.title).where(Transcript.id.in_(transcript_ids))
        )
        for tid, title in tr.all():
            transcript_map[tid] = title

    # ── Collect all jira_refs and enrich ──────────────────────────────────────
    # Slack/transcript insights: extra_data.jira_refs = ["ONB-123"]
    # Jira (risk engine) insights: extra_data.issue_key = "ONB-123"
    all_keys: set[str] = set()
    for r in rows:
        extra = r.extra_data or {}
        refs = extra.get("jira_refs", [])
        if isinstance(refs, list):
            all_keys.update(k.upper() for k in refs if k)
        single_key = extra.get("issue_key")
        if single_key:
            all_keys.add(single_key.upper())

    jira_map: dict[str, dict] = {}
    if all_keys:
        ji = await db.execute(
            select(
                JiraIssue.issue_key,
                JiraIssue.summary,
                JiraIssue.status,
                JiraIssue.status_category,
                JiraIssue.assignee_name,
                JiraIssue.issue_type,
                JiraIssue.story_points,
            ).where(
                JiraIssue.team_id == team_id,
                JiraIssue.issue_key.in_(all_keys),
            )
        )
        for row in ji.all():
            jira_map[row.issue_key] = {
                "summary": row.summary,
                "status": row.status,
                "status_category": row.status_category,
                "assignee": row.assignee_name,
                "issue_type": row.issue_type,
                "story_points": int(row.story_points) if row.story_points else None,
            }

    # ── Serialize ──────────────────────────────────────────────────────────────
    items: list[dict[str, Any]] = []
    for r in rows:
        extra = r.extra_data or {}
        refs = list(extra.get("jira_refs", []) or [])
        single_key = extra.get("issue_key")
        if single_key and single_key not in refs:
            refs.append(single_key)
        enriched_issues = {k.upper(): jira_map[k.upper()] for k in refs if k.upper() in jira_map}

        items.append({
            "id": r.id,
            "source": r.source,
            "insight_type": r.insight_type,
            "severity": r.severity,
            "content": r.content,
            "captured_at": r.captured_at.isoformat(),
            "is_resolved": r.is_resolved,
            "extra_data": extra,
            "jira_issues": enriched_issues,
            "transcript_title": transcript_map.get(r.transcript_id) if r.transcript_id else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": ceil(total / limit) if total else 1,
    }
