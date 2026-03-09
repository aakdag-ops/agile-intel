from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import Insight, JiraIssue, RiskSnapshot, Sprint, Team, User
from app.schemas.schemas import (
    InsightResponse, ProjectStatusResponse, RiskSnapshotResponse,
    RiskTrendResponse, SprintResponse
)
from app.services.risk_engine import compute_risk_snapshot

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/teams/{team_id}/snapshot", response_model=RiskSnapshotResponse)
async def get_latest_snapshot(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.team_id == team_id)
        .order_by(desc(RiskSnapshot.snapshot_at))
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No risk data yet. Run a Jira sync first.")
    return snapshot


@router.get("/teams/{team_id}/trend", response_model=RiskTrendResponse)
async def get_risk_trend(
    team_id: str,
    days: int = Query(default=14, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.team_id == team_id, RiskSnapshot.snapshot_at >= since)
        .order_by(desc(RiskSnapshot.snapshot_at))
        .limit(100)
    )
    snapshots = result.scalars().all()

    trend_direction = "stable"
    delta_7d = None
    if len(snapshots) >= 2:
        recent = snapshots[0].composite_score
        # Find snapshot closest to 7 days ago
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        older = min(snapshots, key=lambda s: abs((s.snapshot_at - week_ago).total_seconds()))
        delta_7d = recent - older.composite_score
        if delta_7d > 5:
            trend_direction = "worsening"
        elif delta_7d < -5:
            trend_direction = "improving"

    return RiskTrendResponse(
        team_id=team_id,
        snapshots=[RiskSnapshotResponse.model_validate(s) for s in snapshots],
        trend_direction=trend_direction,
        delta_7d=delta_7d,
    )


@router.get("/teams/{team_id}/insights", response_model=list[InsightResponse])
async def get_insights(
    team_id: str,
    days: int = Query(default=7, ge=1, le=30),
    source: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(Insight).where(
        Insight.team_id == team_id,
        Insight.captured_at >= since,
    )
    if source:
        query = query.where(Insight.source == source)
    if severity:
        query = query.where(Insight.severity == severity)
    query = query.order_by(desc(Insight.captured_at)).limit(50)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/teams/{team_id}/refresh", status_code=202)
async def trigger_risk_refresh(
    team_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger risk re-scoring (background)."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    background_tasks.add_task(compute_risk_snapshot, team_id)
    return {"message": "Risk refresh scheduled", "team_id": team_id}


@router.get("/teams/{team_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rich project status endpoint — all signals combined."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Latest snapshot
    rs_result = await db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.team_id == team_id)
        .order_by(desc(RiskSnapshot.snapshot_at))
        .limit(1)
    )
    snapshot = rs_result.scalar_one_or_none()

    # Active sprint
    sp_result = await db.execute(
        select(Sprint).where(Sprint.team_id == team_id, Sprint.state == "active")
    )
    active_sprint = sp_result.scalar_one_or_none()

    # Top risks from insights
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    ins_result = await db.execute(
        select(Insight)
        .where(Insight.team_id == team_id, Insight.captured_at >= week_ago)
        .order_by(desc(Insight.captured_at))
        .limit(10)
    )
    recent_insights = ins_result.scalars().all()

    composite = snapshot.composite_score if snapshot else 0
    level_map = [(75, "critical"), (50, "high"), (25, "medium"), (0, "low")]
    risk_level = next(label for threshold, label in level_map if composite >= threshold)

    # Trend
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    prev_result = await db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.team_id == team_id, RiskSnapshot.snapshot_at < two_days_ago)
        .order_by(desc(RiskSnapshot.snapshot_at))
        .limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    delta = (snapshot.composite_score - prev.composite_score) if (snapshot and prev) else 0
    trend = "worsening" if delta > 5 else ("improving" if delta < -5 else "stable")

    # Top risks as dicts
    top_risks = []
    if snapshot and snapshot.raw_signals:
        raw = snapshot.raw_signals
        signals = [
            ("WIP Aging", raw.get("wip_aging", {}).get("score", 0), raw.get("wip_aging", {}).get("detail", [])),
            ("Hidden Dependencies", raw.get("dependencies", {}).get("score", 0), raw.get("dependencies", {}).get("detail", [])),
            ("PBI Readiness", raw.get("pbi_readiness", {}).get("score", 0), raw.get("pbi_readiness", {}).get("detail", [])),
            ("Velocity Trend", raw.get("velocity_trend", {}).get("score", 0), [raw.get("velocity_trend", {}).get("vel_detail", {})]),
        ]
        for name, score, detail in sorted(signals, key=lambda x: x[1], reverse=True):
            if score > 0:
                top_risks.append({"signal": name, "score": score, "detail": detail[:3]})

    return ProjectStatusResponse(
        team_id=team_id,
        team_name=team.name,
        as_of=datetime.now(timezone.utc),
        composite_risk_score=composite,
        risk_level=risk_level,
        active_sprint=SprintResponse.model_validate(active_sprint) if active_sprint else None,
        top_risks=top_risks,
        recent_insights=[InsightResponse.model_validate(i) for i in recent_insights],
        signal_breakdown={
            "wip_aging": snapshot.wip_aging_score if snapshot else 0,
            "dependencies": snapshot.dependency_score if snapshot else 0,
            "velocity_trend": snapshot.velocity_trend_score if snapshot else 0,
            "pbi_readiness": snapshot.pbi_readiness_score if snapshot else 0,
            "slack_blockers": snapshot.slack_blocker_score if snapshot else 0,
            "sentiment": snapshot.sentiment_score if snapshot else 0,
        },
        trend_direction=trend,
        summary="",  # Filled by the chat service when needed
    )
