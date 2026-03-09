from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.models import RiskSnapshot, Sprint, Team, TeamMember, User
from app.schemas.schemas import TeamCreate, TeamDetailResponse, TeamResponse, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=list[TeamDetailResponse])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Team).where(Team.is_active == True))
    teams = result.scalars().all()
    out = []
    for team in teams:
        # Member count
        mc_result = await db.execute(
            select(func.count()).where(TeamMember.team_id == team.id)
        )
        member_count = mc_result.scalar() or 0

        # Latest risk score
        rs_result = await db.execute(
            select(RiskSnapshot.composite_score)
            .where(RiskSnapshot.team_id == team.id)
            .order_by(RiskSnapshot.snapshot_at.desc())
            .limit(1)
        )
        latest_score = rs_result.scalar()

        # Active sprint name
        sp_result = await db.execute(
            select(Sprint.name).where(Sprint.team_id == team.id, Sprint.state == "active")
        )
        sprint_name = sp_result.scalar()

        out.append(TeamDetailResponse(
            **TeamResponse.model_validate(team).model_dump(),
            member_count=member_count,
            latest_risk_score=latest_score,
            active_sprint_name=sprint_name,
        ))
    return out


@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    exists = await db.execute(
        select(Team).where(Team.jira_project_key == payload.jira_project_key)
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Team with this Jira project key already exists")

    team = Team(**payload.model_dump())
    db.add(team)
    await db.flush()
    await db.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    mc_result = await db.execute(
        select(func.count()).where(TeamMember.team_id == team.id)
    )
    member_count = mc_result.scalar() or 0

    rs_result = await db.execute(
        select(RiskSnapshot.composite_score)
        .where(RiskSnapshot.team_id == team.id)
        .order_by(RiskSnapshot.snapshot_at.desc())
        .limit(1)
    )
    latest_score = rs_result.scalar()

    sp_result = await db.execute(
        select(Sprint.name).where(Sprint.team_id == team.id, Sprint.state == "active")
    )
    sprint_name = sp_result.scalar()

    return TeamDetailResponse(
        **TeamResponse.model_validate(team).model_dump(),
        member_count=member_count,
        latest_risk_score=latest_score,
        active_sprint_name=sprint_name,
    )


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    payload: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(team, field, value)
    await db.flush()
    await db.refresh(team)
    return team


@router.post("/{team_id}/members/{user_id}", status_code=204)
async def add_team_member(
    team_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    exists = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id
        )
    )
    if exists.scalar_one_or_none():
        return  # Already a member
    db.add(TeamMember(team_id=team_id, user_id=user_id))


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    team_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member:
        await db.delete(member)
