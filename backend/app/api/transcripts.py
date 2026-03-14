"""
Transcripts API.
Handles manual upload and Google Drive OAuth + sync.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_admin
from app.core.config import settings
from app.models.models import Insight, Team, Transcript, User, utcnow
from app.pipelines.transcript_extractor import extract_signals, signals_to_insights
from app.pipelines.transcript_sync import process_transcript, sync_google_drive_for_team, sync_all_company_transcripts

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TranscriptUpload(BaseModel):
    team_id: str
    title: str
    raw_text: str
    meeting_date: Optional[str] = None   # ISO date string
    participants: Optional[list[str]] = []


class TranscriptResponse(BaseModel):
    id: str
    team_id: str
    title: str
    source: str
    meeting_date: Optional[datetime]
    participants: list
    processed_at: Optional[datetime]
    created_at: datetime
    insight_count: int = 0

    class Config:
        from_attributes = True


class InsightResponse(BaseModel):
    id: str
    source: str
    insight_type: str
    severity: str
    content: str
    captured_at: datetime
    extra_data: Optional[dict]

    class Config:
        from_attributes = True


class TranscriptDetailResponse(TranscriptResponse):
    insights: list[InsightResponse] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_team_or_404(team_id: str, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=TranscriptDetailResponse, status_code=201)
async def upload_transcript(
    body: TranscriptUpload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a transcript manually and process it immediately."""
    team = await _get_team_or_404(body.team_id, db)

    meeting_date = None
    if body.meeting_date:
        try:
            meeting_date = datetime.fromisoformat(body.meeting_date)
            if meeting_date.tzinfo is None:
                meeting_date = meeting_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    transcript = Transcript(
        team_id=body.team_id,
        title=body.title,
        source="manual",
        raw_text=body.raw_text,
        meeting_date=meeting_date,
        participants=body.participants or [],
    )
    db.add(transcript)
    await db.flush()  # get transcript.id

    insight_count = await process_transcript(db, transcript, team.jira_project_key)
    await db.refresh(transcript)

    # Load linked insights for response
    ins_result = await db.execute(
        select(Insight).where(Insight.transcript_id == transcript.id)
    )
    insights = ins_result.scalars().all()

    return TranscriptDetailResponse(
        id=transcript.id,
        team_id=transcript.team_id,
        title=transcript.title,
        source=transcript.source,
        meeting_date=transcript.meeting_date,
        participants=transcript.participants or [],
        processed_at=transcript.processed_at,
        created_at=transcript.created_at,
        insight_count=len(insights),
        insights=[
            InsightResponse(
                id=i.id,
                source=i.source,
                insight_type=i.insight_type,
                severity=i.severity,
                content=i.content,
                captured_at=i.captured_at,
                extra_data=i.extra_data,
            ) for i in insights
        ],
    )


@router.get("/", response_model=list[TranscriptResponse])
async def list_transcripts(
    team_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List transcripts for a team with insight counts."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(Transcript)
        .where(Transcript.team_id == team_id, Transcript.created_at >= cutoff)
        .order_by(Transcript.created_at.desc())
    )
    transcripts = result.scalars().all()

    out = []
    for t in transcripts:
        count_result = await db.execute(
            select(Insight).where(Insight.transcript_id == t.id)
        )
        count = len(count_result.scalars().all())
        out.append(TranscriptResponse(
            id=t.id,
            team_id=t.team_id,
            title=t.title,
            source=t.source,
            meeting_date=t.meeting_date,
            participants=t.participants or [],
            processed_at=t.processed_at,
            created_at=t.created_at,
            insight_count=count,
        ))
    return out


@router.get("/{transcript_id}", response_model=TranscriptDetailResponse)
async def get_transcript(
    transcript_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a transcript with all its extracted insights."""
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    ins_result = await db.execute(
        select(Insight).where(Insight.transcript_id == transcript_id)
        .order_by(Insight.captured_at.desc())
    )
    insights = ins_result.scalars().all()

    return TranscriptDetailResponse(
        id=transcript.id,
        team_id=transcript.team_id,
        title=transcript.title,
        source=transcript.source,
        meeting_date=transcript.meeting_date,
        participants=transcript.participants or [],
        processed_at=transcript.processed_at,
        created_at=transcript.created_at,
        insight_count=len(insights),
        insights=[
            InsightResponse(
                id=i.id,
                source=i.source,
                insight_type=i.insight_type,
                severity=i.severity,
                content=i.content,
                captured_at=i.captured_at,
                extra_data=i.extra_data,
            ) for i in insights
        ],
    )


@router.delete("/{transcript_id}", status_code=204)
async def delete_transcript(
    transcript_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a transcript and its linked insights."""
    result = await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    transcript = result.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    await db.execute(delete(Insight).where(Insight.transcript_id == transcript_id))
    await db.delete(transcript)
    await db.commit()


@router.post("/sync/all", status_code=202)
async def sync_all_company(
    background_tasks: BackgroundTasks,
    days_back: int = Query(30, ge=1, le=90),
    current_user: User = Depends(require_admin),
):
    """
    Admin only: scan all drives (personal + shared) for the last N days,
    auto-assign transcripts to teams by Jira key, fall back to first team.
    """
    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="No Google account connected. Connect via /transcripts/google/auth first."
        )
    background_tasks.add_task(
        sync_all_company_transcripts,
        user_id=current_user.id,
        days_back=days_back,
    )
    return {"status": "company_sync_started", "days_back": days_back}


@router.post("/sync/{team_id}", status_code=202)
async def sync_google_drive(
    team_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a Google Drive transcript sync for a team (background)."""
    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="No Google account connected. Connect via /transcripts/google/auth first."
        )
    background_tasks.add_task(
        sync_google_drive_for_team,
        team_id=team_id,
        user_id=current_user.id,
    )
    return {"status": "sync_started", "team_id": team_id}


@router.get("/google/auth")
async def google_auth_url(
    team_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Return the Google OAuth URL for Drive access."""
    import urllib.parse
    from datetime import timedelta
    from app.core.security import create_access_token

    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Embed a short-lived token in state so the callback can identify the user
    # without needing a Bearer header (Google redirects the browser, not the API client)
    state_token = create_access_token(
        f"oauth:{current_user.id}:{team_id}",
        expires_delta=timedelta(minutes=10),
    )

    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "openid",
        "email",
    ]
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={urllib.parse.quote(settings.google_client_id)}"
        f"&redirect_uri={urllib.parse.quote(settings.google_redirect_uri, safe='')}"
        "&response_type=code"
        f"&scope={urllib.parse.quote(' '.join(scopes))}"
        "&access_type=offline"
        "&prompt=consent"
        f"&state={urllib.parse.quote(state_token)}"
    )
    return {"auth_url": url}


@router.get("/google/callback")
async def google_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback — no Bearer auth; user is identified via state token."""
    import urllib.parse
    import httpx
    from fastapi.responses import RedirectResponse
    from app.core.security import verify_token

    # Decode the state token to get user_id and team_id
    raw_state = urllib.parse.unquote(state)
    sub = verify_token(raw_state)
    if not sub or not sub.startswith("oauth:"):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    parts = sub.split(":", 2)
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Malformed OAuth state")

    user_id, team_id = parts[1], parts[2]

    result = await db.execute(select(User).where(User.id == user_id))
    current_user = result.scalar_one_or_none()
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Exchange authorisation code for tokens
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Google OAuth failed: {resp.text}")

        tokens = resp.json()
        current_user.google_access_token = tokens.get("access_token")
        current_user.google_refresh_token = tokens.get(
            "refresh_token", current_user.google_refresh_token
        )
        await db.commit()

    # Redirect back to the Transcripts page in the frontend
    return RedirectResponse(
        url=f"http://localhost:5173/transcripts/{team_id}?google_connected=1"
    )


@router.get("/google/status")
async def google_connection_status(
    current_user: User = Depends(get_current_user),
):
    """Check if the current user has Google Drive connected."""
    return {
        "connected": bool(current_user.google_refresh_token),
        "has_access_token": bool(current_user.google_access_token),
    }
