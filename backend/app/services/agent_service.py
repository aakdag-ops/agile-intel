"""
Agent Pipeline Service
-----------------------
Orchestrates the 4-agent pipeline:
  1. Solution Architect Agent
  2. PBI Generator Agent
  3. Dependency Agent
  4. Backlog Dispatcher & Follow-up Agent

Each step writes results to AgentStepResult in the DB, allowing the frontend
to poll/stream progress in real-time.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.models.models import AgentConfig, AgentPipeline, AgentStepResult, JiraIssue, Team
from app.pipelines import (
    backlog_dispatcher,
    dependency_analyzer,
    pbi_generator,
    solution_architect,
)
from app.pipelines.jira_client import JiraClient

AGENT_STEPS = [
    (1, "solution_architect", "Solution Architect"),
    (2, "pbi_generator", "PBI Generator"),
    (3, "dependency_agent", "Dependency Analyzer"),
    (4, "backlog_dispatcher", "Backlog Dispatcher & Follow-up"),
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _update_step(db: AsyncSession, step: AgentStepResult, **kwargs) -> None:
    for k, v in kwargs.items():
        setattr(step, k, v)
    await db.flush()


async def _update_pipeline(db: AsyncSession, pipeline: AgentPipeline, **kwargs) -> None:
    for k, v in kwargs.items():
        setattr(pipeline, k, v)
    await db.flush()


async def run_pipeline(pipeline_id: str) -> None:
    """Run the full 4-step agent pipeline. Called as a background task."""
    async with AsyncSessionLocal() as db:
        pipeline = await db.get(AgentPipeline, pipeline_id)
        if not pipeline:
            logger.error("agent_pipeline.not_found", pipeline_id=pipeline_id)
            return

        # Load config
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.team_id == pipeline.team_id)
        )
        config = result.scalar_one_or_none()

        # Load existing issues for context
        issues_result = await db.execute(
            select(JiraIssue)
            .where(JiraIssue.team_id == pipeline.team_id)
            .order_by(JiraIssue.updated_at_jira.desc())
            .limit(100)
        )
        existing_issues_orm = issues_result.scalars().all()
        existing_issues = [
            {
                "issue_key": i.issue_key,
                "summary": i.summary,
                "issue_type": i.issue_type,
                "status": i.status,
                "status_category": i.status_category,
                "assignee_name": i.assignee_name,
                "story_points": i.story_points,
                "is_blocked": i.is_blocked,
            }
            for i in existing_issues_orm
        ]

        await _update_pipeline(db, pipeline, status="running", started_at=utcnow())
        await db.commit()

        # Initialise step records
        steps: dict[int, AgentStepResult] = {}
        for order, name, label in AGENT_STEPS:
            skip = not getattr(config, f"enable_{name}", True) if config else False
            step = AgentStepResult(
                pipeline_id=pipeline_id,
                step_order=order,
                agent_name=name,
                agent_label=label,
                status="skipped" if skip else "pending",
            )
            db.add(step)
            steps[order] = step

        await db.commit()

        # Refresh steps to get IDs
        for step in steps.values():
            await db.refresh(step)

        # ── Step 1: Solution Architect ────────────────────────────────────────
        arch_result: dict = {}
        step1 = steps[1]
        if step1.status != "skipped":
            t0 = time.monotonic()
            await _update_step(db, step1, status="running", started_at=utcnow())
            await db.commit()
            try:
                issue_data = pipeline.trigger_issue_data or {}
                arch_result = await solution_architect.run(
                    issue_key=pipeline.trigger_issue_key,
                    issue_summary=pipeline.trigger_issue_summary,
                    issue_description=issue_data.get("description", ""),
                    existing_issues=existing_issues,
                    github_repo_url=config.github_repo_url if config else None,
                    github_token=config.github_token if config else None,
                )
                await _update_step(
                    db, step1,
                    status="completed",
                    completed_at=utcnow(),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    output=arch_result,
                )
            except Exception as e:
                logger.error("agent_step.failed", step="solution_architect", error=str(e))
                await _update_step(db, step1, status="failed", error=str(e), completed_at=utcnow())
                await _update_pipeline(db, pipeline, status="failed", error=f"Step 1 failed: {e}", completed_at=utcnow())
                await db.commit()
                return
            await db.commit()

        # ── Step 2: PBI Generator ─────────────────────────────────────────────
        pbi_result: dict = {}
        step2 = steps[2]
        if step2.status != "skipped":
            t0 = time.monotonic()
            await _update_step(db, step2, status="running", started_at=utcnow())
            await db.commit()
            try:
                pbi_result = await pbi_generator.run(
                    issue_key=pipeline.trigger_issue_key,
                    issue_summary=pipeline.trigger_issue_summary,
                    architecture_proposal=arch_result.get("architecture_proposal", ""),
                    affected_components=arch_result.get("affected_components", []),
                    new_components=arch_result.get("new_components", []),
                    complexity=arch_result.get("complexity", "medium"),
                    technical_approach=arch_result.get("technical_approach", ""),
                )
                await _update_step(
                    db, step2,
                    status="completed",
                    completed_at=utcnow(),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    output=pbi_result,
                )
            except Exception as e:
                logger.error("agent_step.failed", step="pbi_generator", error=str(e))
                await _update_step(db, step2, status="failed", error=str(e), completed_at=utcnow())
                await _update_pipeline(db, pipeline, status="failed", error=f"Step 2 failed: {e}", completed_at=utcnow())
                await db.commit()
                return
            await db.commit()

        # ── Step 3: Dependency Analyzer ───────────────────────────────────────
        dep_result: dict = {}
        step3 = steps[3]
        if step3.status != "skipped":
            t0 = time.monotonic()
            await _update_step(db, step3, status="running", started_at=utcnow())
            await db.commit()
            try:
                dep_result = await dependency_analyzer.run(
                    issue_key=pipeline.trigger_issue_key,
                    epics=pbi_result.get("epics", []),
                    existing_issues=existing_issues,
                )
                await _update_step(
                    db, step3,
                    status="completed",
                    completed_at=utcnow(),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    output=dep_result,
                )
            except Exception as e:
                logger.error("agent_step.failed", step="dependency_analyzer", error=str(e))
                await _update_step(db, step3, status="failed", error=str(e), completed_at=utcnow())
                await _update_pipeline(db, pipeline, status="failed", error=f"Step 3 failed: {e}", completed_at=utcnow())
                await db.commit()
                return
            await db.commit()

        # ── Step 4: Backlog Dispatcher ────────────────────────────────────────
        step4 = steps[4]
        if step4.status != "skipped":
            t0 = time.monotonic()
            await _update_step(db, step4, status="running", started_at=utcnow())
            await db.commit()
            try:
                jira_client = JiraClient() if (config and config.auto_create_jira_issues) else None
                dispatch_result = await backlog_dispatcher.run(
                    issue_key=pipeline.trigger_issue_key,
                    issue_summary=pipeline.trigger_issue_summary,
                    epics=pbi_result.get("epics", []),
                    dependency_result=dep_result,
                    auto_create=bool(config and config.auto_create_jira_issues),
                    target_project_key=config.target_project_key if config else None,
                    jira_client=jira_client,
                )
                await _update_step(
                    db, step4,
                    status="completed",
                    completed_at=utcnow(),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    output=dispatch_result,
                )
            except Exception as e:
                logger.error("agent_step.failed", step="backlog_dispatcher", error=str(e))
                await _update_step(db, step4, status="failed", error=str(e), completed_at=utcnow())
                await _update_pipeline(db, pipeline, status="failed", error=f"Step 4 failed: {e}", completed_at=utcnow())
                await db.commit()
                return
            await db.commit()

        await _update_pipeline(db, pipeline, status="completed", completed_at=utcnow())
        await db.commit()
        logger.info("agent_pipeline.completed", pipeline_id=pipeline_id)


async def poll_request_board(team_id: str) -> list[str]:
    """
    Poll the configured Jira request board for new issues and spawn pipelines.
    Returns list of triggered pipeline IDs.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentConfig).where(AgentConfig.team_id == team_id)
        )
        config = result.scalar_one_or_none()
        if not config or not config.request_board_id:
            return []

        jira = JiraClient()
        try:
            issues = await jira.get_issues_for_board(
                config.request_board_id,
                config.request_jql,
            )
        except Exception as e:
            logger.error("agent_poll.jira_failed", team_id=team_id, error=str(e))
            return []

        # Filter new issues (not yet processed)
        triggered = []
        for issue in issues:
            issue_key = issue.get("key", "")
            if not issue_key:
                continue
            fields = issue.get("fields", {})

            # Skip if already processed (use limit(1) — duplicate manual triggers are allowed)
            existing = await db.execute(
                select(AgentPipeline).where(
                    AgentPipeline.team_id == team_id,
                    AgentPipeline.trigger_issue_key == issue_key,
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue

            summary = fields.get("summary", "")
            description = ""
            desc_field = fields.get("description")
            if desc_field and isinstance(desc_field, dict):
                # Jira ADF format
                for block in desc_field.get("content", []):
                    for inline in block.get("content", []):
                        description += inline.get("text", "") + " "
            elif isinstance(desc_field, str):
                description = desc_field

            pipeline = AgentPipeline(
                team_id=team_id,
                trigger_issue_key=issue_key,
                trigger_issue_summary=summary,
                trigger_issue_data={"description": description.strip(), "raw": fields},
                status="pending",
            )
            db.add(pipeline)
            await db.flush()
            await db.refresh(pipeline)
            triggered.append(pipeline.id)

        # Update watermark
        config.last_polled_at = utcnow()
        await db.commit()

        # Kick off pipelines in background
        for pid in triggered:
            asyncio.create_task(run_pipeline(pid))

        logger.info("agent_poll.done", team_id=team_id, triggered=len(triggered))
        return triggered


async def poll_all_teams() -> None:
    """Poll request boards for all teams that have agent config. Called by scheduler."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentConfig))
        configs = result.scalars().all()

    for config in configs:
        try:
            await poll_request_board(config.team_id)
        except Exception as e:
            logger.error("agent_poll_all.failed", team_id=config.team_id, error=str(e))
