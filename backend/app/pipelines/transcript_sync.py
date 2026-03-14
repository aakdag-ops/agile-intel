"""
Google Drive transcript sync pipeline.
Polls Google Drive for Meet transcripts, extracts signals, and stores insights.
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.models import Insight, Team, Transcript, User, utcnow
from app.pipelines.transcript_extractor import extract_signals, signals_to_insights

logger = logging.getLogger(__name__)

DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Google Drive mimeType for Google Docs (Meet transcripts are saved as Docs)
GDOC_MIME = "application/vnd.google-apps.document"


async def _refresh_google_token(user: User) -> str | None:
    """Refresh the Google access token using the stored refresh token."""
    if not user.google_refresh_token:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": user.google_refresh_token,
            "grant_type": "refresh_token",
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
        logger.error(f"Google token refresh failed: {resp.text}")
        return None


async def _list_transcript_docs(
    access_token: str,
    since: datetime | None = None,
    all_drives: bool = False,
    days_back: int = 30,
) -> list[dict]:
    """
    List Google Docs that look like Meet transcripts from Drive.
    If all_drives=True, searches Shared Drives too (company-wide).
    """
    from datetime import timedelta

    if since is None and all_drives:
        # For company-wide sync with no prior anchor, look back N days
        since = datetime.now(timezone.utc) - timedelta(days=days_back)

    query_parts = [
        f"mimeType='{GDOC_MIME}'",
        "trashed=false",
    ]

    if not all_drives:
        # Narrow title filter for personal drive sync
        query_parts.append(
            "(name contains 'transcript' or name contains 'Transcript' "
            "or name contains 'Meet' or name contains 'standup' "
            "or name contains 'Standup' or name contains 'retro' "
            "or name contains 'Retro' or name contains 'planning')"
        )
    # For all_drives we skip the title filter — any recent Doc could be a meeting note

    if since:
        ts = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        query_parts.append(f"modifiedTime > '{ts}'")

    query = " and ".join(query_parts)
    params = {
        "q": query,
        "fields": "files(id,name,modifiedTime,createdTime,driveId,parents)",
        "orderBy": "modifiedTime desc",
        "pageSize": 100,
    }
    if all_drives:
        params["corpora"] = "allDrives"
        params["includeItemsFromAllDrives"] = "true"
        params["supportsAllDrives"] = "true"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API}/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if resp.status_code != 200:
            logger.error(f"Drive list error: {resp.status_code} {resp.text}")
            return []
        return resp.json().get("files", [])


def _match_team(raw_text: str, title: str, teams: list) -> "Team | None":
    """
    Try to match a transcript to a team by looking for Jira project keys
    in the document text or title. Returns the first matching team or None.
    """
    import re
    combined = f"{title}\n{raw_text[:3000]}"  # only scan start for performance
    for team in teams:
        key = team.jira_project_key
        if key and re.search(rf'\b{re.escape(key)}\b', combined, re.IGNORECASE):
            return team
    return None


async def _export_doc_as_text(access_token: str, doc_id: str) -> str | None:
    """Export a Google Doc as plain text."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DRIVE_API}/files/{doc_id}/export",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"mimeType": "text/plain"},
        )
        if resp.status_code == 200:
            return resp.text
        logger.error(f"Drive export error for {doc_id}: {resp.status_code}")
        return None


async def process_transcript(
    db: AsyncSession,
    transcript: Transcript,
    team_jira_key: str,
) -> int:
    """Run extraction on a transcript and store insights. Returns insight count."""
    signals = await extract_signals(
        transcript_text=transcript.raw_text,
        title=transcript.title,
        team_jira_key=team_jira_key,
        participants=transcript.participants or [],
    )

    insight_dicts = signals_to_insights(
        signals=signals,
        team_id=transcript.team_id,
        transcript_id=transcript.id,
        title=transcript.title,
    )

    now = utcnow()
    for d in insight_dicts:
        db.add(Insight(
            team_id=d["team_id"],
            transcript_id=d["transcript_id"],
            source=d["source"],
            insight_type=d["insight_type"],
            severity=d["severity"],
            content=d["content"],
            captured_at=now,
            extra_data=d["extra_data"],
        ))

    transcript.processed_at = now
    await db.commit()
    return len(insight_dicts)


async def sync_google_drive_for_team(team_id: str, user_id: str) -> dict:
    """
    Sync Google Drive transcripts for a team using a specific user's OAuth tokens.
    Returns a summary dict.
    """
    async with AsyncSessionLocal() as db:
        team_result = await db.execute(select(Team).where(Team.id == team_id))
        team = team_result.scalar_one_or_none()
        if not team:
            return {"error": "Team not found"}

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.google_refresh_token:
            return {"error": "No Google OAuth token for user"}

        access_token = await _refresh_google_token(user)
        if not access_token:
            return {"error": "Failed to refresh Google token"}

        # Find newest existing transcript to use as since-filter
        existing = await db.execute(
            select(Transcript.created_at)
            .where(Transcript.team_id == team_id, Transcript.source == "google_drive")
            .order_by(Transcript.created_at.desc())
            .limit(1)
        )
        since = existing.scalar_one_or_none()

        docs = await _list_transcript_docs(access_token, since=since)
        if not docs:
            return {"fetched": 0, "processed": 0, "skipped": 0}

        fetched = skipped = total_insights = 0
        for doc in docs:
            doc_id = doc["id"]

            # Skip already processed
            dup = await db.execute(
                select(Transcript).where(Transcript.google_doc_id == doc_id)
            )
            if dup.scalar_one_or_none():
                skipped += 1
                continue

            raw_text = await _export_doc_as_text(access_token, doc_id)
            if not raw_text or len(raw_text.strip()) < 100:
                skipped += 1
                continue

            transcript = Transcript(
                team_id=team_id,
                title=doc["name"],
                source="google_drive",
                google_doc_id=doc_id,
                raw_text=raw_text,
                meeting_date=datetime.fromisoformat(
                    doc["createdTime"].replace("Z", "+00:00")
                ) if doc.get("createdTime") else None,
            )
            try:
                db.add(transcript)
                await db.flush()  # get transcript.id
            except IntegrityError:
                await db.rollback()
                skipped += 1
                continue

            count = await process_transcript(db, transcript, team.jira_project_key)
            total_insights += count
            fetched += 1

        logger.info(
            "transcript_sync.google_drive",
            team=team.jira_project_key,
            fetched=fetched,
            skipped=skipped,
            insights=total_insights,
        )
        return {"fetched": fetched, "skipped": skipped, "insights": total_insights}


async def sync_transcripts_all_teams() -> None:
    """Scheduler entry point — syncs Drive transcripts for all teams with OAuth tokens."""
    async with AsyncSessionLocal() as db:
        # Find users with Google tokens and their team memberships
        result = await db.execute(
            select(User).where(User.google_refresh_token.isnot(None))
        )
        users = result.scalars().all()

    for user in users:
        for membership in user.team_memberships:
            try:
                await sync_google_drive_for_team(
                    team_id=str(membership.team_id),
                    user_id=str(user.id),
                )
            except Exception as e:
                logger.error(
                    "transcript_sync.failed",
                    user=user.email,
                    team=membership.team_id,
                    error=str(e),
                )


async def sync_all_company_transcripts(user_id: str, days_back: int = 30) -> dict:
    """
    Admin-only: scan ALL drives (personal + shared) for the last N days,
    auto-assign each doc to the best-matching team by Jira project key,
    fall back to first active team if no match found.
    Returns a summary dict.
    """
    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.google_refresh_token:
            return {"error": "No Google OAuth token for user"}

        # Load all active teams for matching
        teams_result = await db.execute(
            select(Team).where(Team.is_active == True).order_by(Team.name)
        )
        teams = teams_result.scalars().all()
        if not teams:
            return {"error": "No active teams found"}

        access_token = await _refresh_google_token(user)
        if not access_token:
            return {"error": "Failed to refresh Google token"}

        docs = await _list_transcript_docs(
            access_token, all_drives=True, days_back=days_back
        )
        if not docs:
            return {"fetched": 0, "processed": 0, "skipped": 0, "no_match": 0}

        fetched = skipped = total_insights = no_match = 0

        for doc in docs:
            doc_id = doc["id"]

            # Skip already processed
            dup = await db.execute(
                select(Transcript).where(Transcript.google_doc_id == doc_id)
            )
            if dup.scalar_one_or_none():
                skipped += 1
                continue

            raw_text = await _export_doc_as_text(access_token, doc_id)
            if not raw_text or len(raw_text.strip()) < 50:
                skipped += 1
                continue

            # Try to match to a team by Jira key; fall back to first team
            matched_team = _match_team(raw_text, doc["name"], teams)
            if matched_team is None:
                no_match += 1
                matched_team = teams[0]  # default to first team

            transcript = Transcript(
                team_id=matched_team.id,
                title=doc["name"],
                source="google_drive",
                google_doc_id=doc_id,
                raw_text=raw_text,
                meeting_date=datetime.fromisoformat(
                    doc["createdTime"].replace("Z", "+00:00")
                ) if doc.get("createdTime") else None,
            )
            try:
                db.add(transcript)
                await db.flush()
            except IntegrityError:
                await db.rollback()
                skipped += 1
                continue

            count = await process_transcript(db, transcript, matched_team.jira_project_key)
            total_insights += count
            fetched += 1

        logger.info(
            "transcript_sync.company_wide",
            user=user.email,
            fetched=fetched,
            skipped=skipped,
            no_match=no_match,
            insights=total_insights,
        )
        return {
            "fetched": fetched,
            "skipped": skipped,
            "no_match": no_match,
            "insights": total_insights,
        }
