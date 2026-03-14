from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import BacklogHealthcheck, Team, User
from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.pipelines.healthcheck_analyzer import run_healthcheck

router = APIRouter(prefix="/healthcheck", tags=["healthcheck"])


# ── Background task ───────────────────────────────────────────────────────────

async def _run_healthcheck_task(healthcheck_id: str, team_id: str, project_key: str) -> None:
    """Background task: run healthcheck pipeline and persist results."""
    async with AsyncSessionLocal() as db:
        try:
            # Mark as running
            result = await db.execute(
                select(BacklogHealthcheck).where(BacklogHealthcheck.id == healthcheck_id)
            )
            hc = result.scalar_one_or_none()
            if not hc:
                return
            hc.status = "running"
            await db.commit()

            # Run the pipeline
            data = await run_healthcheck(team_id=team_id, project_key=project_key)

            # Persist results
            result = await db.execute(
                select(BacklogHealthcheck).where(BacklogHealthcheck.id == healthcheck_id)
            )
            hc = result.scalar_one_or_none()
            if not hc:
                return
            hc.status = "complete"
            hc.total_items = data["total_items"]
            hc.lead_times = data["lead_times"]
            hc.item_scores = data["item_scores"]
            hc.item_groups = data["item_groups"]
            hc.column_stats = data["column_stats"]
            hc.ai_insights = data["ai_insights"]
            hc.top_issues = data["top_issues"]
            hc.concrete_actions = data["concrete_actions"]
            await db.commit()
            logger.info("healthcheck.saved", id=healthcheck_id)

        except Exception as exc:
            logger.error("healthcheck.task_failed", id=healthcheck_id, error=str(exc))
            try:
                async with AsyncSessionLocal() as db2:
                    result = await db2.execute(
                        select(BacklogHealthcheck).where(BacklogHealthcheck.id == healthcheck_id)
                    )
                    hc = result.scalar_one_or_none()
                    if hc:
                        hc.status = "failed"
                        hc.error = str(exc)[:1000]
                        await db2.commit()
            except Exception:
                pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/teams/{team_id}/generate", status_code=202)
async def generate_healthcheck(
    team_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kick off a new backlog healthcheck analysis (runs in background)."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Create the record in pending state
    import uuid
    hc = BacklogHealthcheck(
        id=str(uuid.uuid4()),
        team_id=team_id,
        status="pending",
        generated_at=datetime.now(timezone.utc),
    )
    db.add(hc)
    await db.commit()
    await db.refresh(hc)

    background_tasks.add_task(
        _run_healthcheck_task,
        healthcheck_id=hc.id,
        team_id=team_id,
        project_key=team.jira_project_key,
    )

    return {
        "id": hc.id,
        "status": hc.status,
        "generated_at": hc.generated_at.isoformat(),
    }


@router.get("/teams/{team_id}/latest")
async def get_latest_healthcheck(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent complete healthcheck report."""
    result = await db.execute(
        select(BacklogHealthcheck)
        .where(
            BacklogHealthcheck.team_id == team_id,
            BacklogHealthcheck.status == "complete",
        )
        .order_by(desc(BacklogHealthcheck.generated_at))
        .limit(1)
    )
    hc = result.scalar_one_or_none()
    if not hc:
        raise HTTPException(status_code=404, detail="No completed healthcheck found.")

    return {
        "id": hc.id,
        "team_id": hc.team_id,
        "generated_at": hc.generated_at.isoformat(),
        "status": hc.status,
        "period_days": hc.period_days,
        "total_items": hc.total_items,
        "lead_times": hc.lead_times,
        "item_scores": hc.item_scores,
        "item_groups": hc.item_groups,
        "column_stats": hc.column_stats,
        "ai_insights": hc.ai_insights,
        "top_issues": hc.top_issues,
        "concrete_actions": hc.concrete_actions,
    }


@router.get("/teams/{team_id}/status")
async def get_healthcheck_status(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return status of the latest healthcheck (for polling)."""
    result = await db.execute(
        select(BacklogHealthcheck)
        .where(BacklogHealthcheck.team_id == team_id)
        .order_by(desc(BacklogHealthcheck.generated_at))
        .limit(1)
    )
    hc = result.scalar_one_or_none()
    if not hc:
        return {"status": "none"}

    return {
        "id": hc.id,
        "status": hc.status,
        "generated_at": hc.generated_at.isoformat(),
        "total_items": hc.total_items,
        "error": hc.error,
    }
