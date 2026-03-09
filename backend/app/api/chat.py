import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import ChatMessage, Team, User
from app.schemas.schemas import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])
chat_service = ChatService()


@router.post("/", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Non-streaming chat endpoint."""
    session_id = payload.session_id or str(uuid.uuid4())

    # Load history (last 10 turns)
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == session_id,
        )
        .order_by(desc(ChatMessage.created_at))
        .limit(20)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [{"role": r.role, "content": r.content} for r in history_rows]

    # Verify team exists if provided
    if payload.team_id:
        team_result = await db.execute(select(Team).where(Team.id == payload.team_id))
        if not team_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Team not found")

    reply = await chat_service.chat(
        db=db,
        user_id=current_user.id,
        message=payload.message,
        team_id=payload.team_id,
        session_id=session_id,
        history=history,
    )

    return ChatResponse(
        session_id=session_id,
        message=reply,
        team_id=payload.team_id,
        sources_used=["jira"] if payload.team_id else [],
        created_at=datetime.now(timezone.utc),
    )


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Server-Sent Events streaming chat endpoint."""
    session_id = payload.session_id or str(uuid.uuid4())

    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == session_id,
        )
        .order_by(desc(ChatMessage.created_at))
        .limit(20)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [{"role": r.role, "content": r.content} for r in history_rows]

    async def event_generator():
        yield f"data: {{\"session_id\": \"{session_id}\"}}\n\n"
        async for chunk in chat_service.stream_chat(
            db=db,
            user_id=current_user.id,
            message=payload.message,
            team_id=payload.team_id,
            session_id=session_id,
            history=history,
        ):
            # Escape for SSE
            chunk_escaped = chunk.replace("\n", "\\n")
            yield f"data: {{\"text\": \"{chunk_escaped}\"}}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Session-ID": session_id},
    )


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.session_id == session_id,
        )
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in messages]
