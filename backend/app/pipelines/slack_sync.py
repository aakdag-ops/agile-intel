"""
Slack sync pipeline.
Orchestrates: fetch messages → extract signals → store insights.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.models import Team, Insight
from app.core.config import settings
from app.pipelines.slack_client import SlackClient
from app.pipelines.slack_extractor import extract_signals, signals_to_insights

logger = logging.getLogger(__name__)


async def sync_slack_for_team(
    team_id: str,
    db: Optional[AsyncSession] = None,
    lookback_hours: int = 168,
) -> dict:
    """Full Slack sync for a single team."""
    close_db = db is None
    if db is None:
        db = AsyncSessionLocal()

    try:
        result = await db.execute(select(Team).where(Team.id == team_id))
        team = result.scalar_one_or_none()
        if not team:
            return {"error": "team_not_found"}

        if not team.slack_channel_ids:
            return {"skipped": True, "reason": "no_channels_configured"}

        if not settings.slack_bot_token:
            return {"error": "no_bot_token"}

        client = SlackClient(settings.slack_bot_token)
        try:
            await client.verify()
        except Exception as e:
            return {"error": f"slack_auth_failed: {e}"}

        all_channels = await client.list_channels(include_private=True)
        channel_map = {ch["id"]: ch["name"] for ch in all_channels}

        oldest_ts = (
            datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        ).timestamp()

        total_messages = 0
        total_insights = 0
        errors = []

        for channel_id in team.slack_channel_ids:
            channel_name = channel_map.get(channel_id, channel_id)
            try:
                messages = await client.fetch_messages(
                    channel_id=channel_id,
                    oldest=oldest_ts,
                    limit=200,
                )
                total_messages += len(messages)
                if not messages:
                    continue

                signals = await extract_signals(
                    messages=messages,
                    channel_name=channel_name,
                    team_jira_key=team.jira_project_key,
                )

                insight_dicts = signals_to_insights(
                    signals=signals,
                    team_id=str(team.id),
                    channel_name=channel_name,
                    channel_id=channel_id,
                )

                for ins_data in insight_dicts:
                    insight = Insight(
                        id=uuid.uuid4(),
                        team_id=ins_data["team_id"],
                        source=ins_data["source"],
                        insight_type=ins_data["insight_type"],
                        severity=ins_data["severity"],
                        content=ins_data["content"],
                        extra_data=ins_data["extra_data"],
                    )
                    db.add(insight)
                    total_insights += 1

            except Exception as e:
                logger.error(f"Error syncing #{channel_name}: {e}")
                errors.append({"channel": channel_name, "error": str(e)})

        await db.commit()
        summary = {
            "team": team.name,
            "channels_synced": len(team.slack_channel_ids),
            "messages_processed": total_messages,
            "insights_stored": total_insights,
            "errors": errors,
        }
        logger.info(f"Slack sync complete: {summary}")
        return summary

    except Exception as e:
        logger.exception(f"Slack sync failed for team {team_id}: {e}")
        await db.rollback()
        return {"error": str(e)}
    finally:
        if close_db:
            await db.close()


async def sync_slack_all_teams() -> list[dict]:
    """Sync Slack for all active teams with channels configured. Called by scheduler."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Team).where(Team.is_active == True)
        )
        teams = result.scalars().all()

    results = []
    for team in teams:
        if team.slack_channel_ids:
            result = await sync_slack_for_team(str(team.id))
            results.append(result)
    return results
