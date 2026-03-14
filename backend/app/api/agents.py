"""
Agent Pipeline API
------------------
Endpoints for managing agent configurations and pipeline runs.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import AgentConfig, AgentPipeline, AgentStepResult, User
from app.schemas.schemas import (
    AgentConfigResponse,
    AgentConfigUpdate,
    AgentPipelineResponse,
    TriggerPipelineRequest,
)
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Config ───────────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.team_id == team_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Agent config not found. Create one first.")
    return config


@router.put("/teams/{team_id}/config", response_model=AgentConfigResponse)
async def upsert_agent_config(
    team_id: str,
    payload: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.team_id == team_id)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = AgentConfig(team_id=team_id)
        db.add(config)

    update_data = payload.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(config, k, v)

    await db.commit()
    await db.refresh(config)
    return config


# ── Pipelines ────────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/pipelines", response_model=list[AgentPipelineResponse])
async def list_pipelines(
    team_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentPipeline)
        .where(AgentPipeline.team_id == team_id)
        .options(selectinload(AgentPipeline.steps))
        .order_by(desc(AgentPipeline.created_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/teams/{team_id}/pipelines/{pipeline_id}", response_model=AgentPipelineResponse)
async def get_pipeline(
    team_id: str,
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentPipeline)
        .where(AgentPipeline.id == pipeline_id, AgentPipeline.team_id == team_id)
        .options(selectinload(AgentPipeline.steps))
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline


@router.post("/teams/{team_id}/trigger", response_model=AgentPipelineResponse, status_code=201)
async def trigger_pipeline(
    team_id: str,
    payload: TriggerPipelineRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a pipeline for a specific Jira issue."""
    pipeline = AgentPipeline(
        team_id=team_id,
        trigger_issue_key=payload.issue_key,
        trigger_issue_summary=payload.issue_summary,
        trigger_issue_data=payload.issue_data,
        status="pending",
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)

    background_tasks.add_task(agent_service.run_pipeline, pipeline.id)

    # Return Pydantic model directly to avoid lazy-loading the steps relationship
    return AgentPipelineResponse(
        id=pipeline.id,
        team_id=pipeline.team_id,
        trigger_issue_key=pipeline.trigger_issue_key,
        trigger_issue_summary=pipeline.trigger_issue_summary,
        trigger_issue_data=pipeline.trigger_issue_data,
        status=pipeline.status,
        started_at=pipeline.started_at,
        completed_at=pipeline.completed_at,
        error=pipeline.error,
        created_at=pipeline.created_at,
        steps=[],
    )


@router.post("/teams/{team_id}/poll")
async def poll_request_board(
    team_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a poll of the configured Jira request board."""
    triggered = await agent_service.poll_request_board(team_id)
    return {"triggered_pipelines": len(triggered), "pipeline_ids": triggered}


@router.delete("/teams/{team_id}/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(
    team_id: str,
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentPipeline)
        .where(AgentPipeline.id == pipeline_id, AgentPipeline.team_id == team_id)
    )
    pipeline = result.scalar_one_or_none()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await db.delete(pipeline)
    await db.commit()
