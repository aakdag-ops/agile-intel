from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    surname: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    name: str | None = None
    surname: str | None = None
    role: str | None = None
    jira_account_id: str | None = None
    slack_user_id: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    surname: str
    role: str
    is_active: bool
    jira_account_id: str | None
    slack_user_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Team ─────────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str
    jira_project_key: str
    jira_board_id: int | None = None
    slack_channel_ids: list[str] = []
    description: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    slack_channel_ids: list[str] | None = None
    description: str | None = None
    weight_wip_aging: float | None = None
    weight_dependencies: float | None = None
    weight_velocity_trend: float | None = None
    weight_pbi_readiness: float | None = None
    weight_slack_blockers: float | None = None
    weight_sentiment: float | None = None
    weight_meeting_alignment: float | None = None


class TeamResponse(BaseModel):
    id: str
    name: str
    jira_project_key: str
    jira_board_id: int | None
    slack_channel_ids: list[str] | None
    description: str | None
    is_active: bool
    last_jira_sync: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamDetailResponse(TeamResponse):
    member_count: int = 0
    latest_risk_score: int | None = None
    active_sprint_name: str | None = None


# ── Risk ─────────────────────────────────────────────────────────────────────

class RiskSnapshotResponse(BaseModel):
    id: str
    team_id: str
    snapshot_at: datetime
    wip_aging_score: int
    dependency_score: int
    velocity_trend_score: int
    pbi_readiness_score: int
    slack_blocker_score: int
    sentiment_score: int
    meeting_alignment_score: int
    composite_score: int
    raw_signals: dict | None

    model_config = {"from_attributes": True}


class RiskTrendResponse(BaseModel):
    team_id: str
    snapshots: list[RiskSnapshotResponse]
    trend_direction: str  # improving | worsening | stable
    delta_7d: int | None  # composite score change over last 7 days


# ── Insight ──────────────────────────────────────────────────────────────────

class InsightResponse(BaseModel):
    id: str
    team_id: str
    source: str
    insight_type: str
    content: str
    severity: str
    captured_at: datetime
    is_resolved: bool
    extra_data: dict | None = None

    model_config = {"from_attributes": True}


# ── Sprint ───────────────────────────────────────────────────────────────────

class SprintResponse(BaseModel):
    id: str
    jira_sprint_id: int
    name: str
    state: str
    start_date: datetime | None
    end_date: datetime | None
    goal: str | None
    committed_points: float | None
    completed_points: float | None
    velocity: float | None

    model_config = {"from_attributes": True}


# ── Jira Issue ────────────────────────────────────────────────────────────────

class JiraIssueResponse(BaseModel):
    id: str
    issue_key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    priority: str | None
    assignee_name: str | None
    story_points: float | None
    time_in_status_hours: float | None
    is_blocked: bool
    blocker_count: int
    dependency_depth: int

    model_config = {"from_attributes": True}


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    team_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    team_id: str | None
    sources_used: list[str] = []  # jira | slack | transcript
    risk_score: int | None = None
    created_at: datetime


# ── Project Status (rich) ────────────────────────────────────────────────────

class ProjectStatusResponse(BaseModel):
    team_id: str
    team_name: str
    as_of: datetime
    composite_risk_score: int
    risk_level: str  # low | medium | high | critical
    active_sprint: SprintResponse | None
    top_risks: list[dict[str, Any]]
    recent_insights: list[InsightResponse]
    signal_breakdown: dict[str, int]
    trend_direction: str
    summary: str  # AI-generated
