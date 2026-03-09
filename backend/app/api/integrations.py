"""
Integrations API — Jira + Slack endpoints.
"""
import logging
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.models import Team, User
from app.pipelines.jira_client import JiraClient
from app.pipelines.jira_sync import JiraSyncPipeline
from app.pipelines.slack_client import SlackClient
from app.pipelines.slack_sync import sync_slack_for_team

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations")


# ── Jira ─────────────────────────────────────────────────────────────────────

@router.get("/jira/verify")
async def verify_jira(current_user: User = Depends(get_current_user)):
    try:
        client = JiraClient(
            base_url=settings.jira_base_url,
            email=settings.jira_service_email,
            api_token=settings.jira_service_api_token,
        )
        info = await client.get_myself()
        return {"ok": True, "user": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jira/sync/{team_id}")
async def sync_jira(
    team_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    background_tasks.add_task(_run_jira_sync, team)
    return {"message": "Jira sync scheduled", "team_id": team_id}


@router.get("/jira/boards/{project_key}")
async def get_jira_boards(
    project_key: str,
    current_user: User = Depends(get_current_user),
):
    try:
        client = JiraClient(
            base_url=settings.jira_base_url,
            email=settings.jira_service_email,
            api_token=settings.jira_service_api_token,
        )
        boards = await client.get_boards(project_key)
        return {"boards": boards}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Slack ─────────────────────────────────────────────────────────────────────

@router.get("/slack/verify")
async def verify_slack(current_user: User = Depends(get_current_user)):
    """Verify the configured Slack bot token."""
    if not settings.slack_bot_token:
        raise HTTPException(status_code=400, detail="SLACK_BOT_TOKEN not configured")
    try:
        client = SlackClient(settings.slack_bot_token)
        info = await client.verify()
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/slack/channels")
async def list_slack_channels(current_user: User = Depends(get_current_user)):
    """List all channels the bot has access to."""
    if not settings.slack_bot_token:
        raise HTTPException(status_code=400, detail="SLACK_BOT_TOKEN not configured")
    try:
        client = SlackClient(settings.slack_bot_token)
        channels = await client.list_channels(include_private=True)
        return {"channels": channels}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SetChannelsRequest(BaseModel):
    channel_ids: List[str]


@router.post("/slack/teams/{team_id}/channels")
async def set_team_channels(
    team_id: str,
    body: SetChannelsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set which Slack channels to monitor for a team."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.slack_channel_ids = body.channel_ids
    await db.commit()
    return {
        "team_id": team_id,
        "slack_channel_ids": team.slack_channel_ids,
        "message": f"Configured {len(body.channel_ids)} channel(s)",
    }


@router.post("/slack/sync/{team_id}")
async def sync_slack(
    team_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Trigger an on-demand Slack sync for a team."""
    background_tasks.add_task(sync_slack_for_team, team_id)
    return {"message": "Slack sync scheduled", "team_id": team_id}
