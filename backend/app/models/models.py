import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    admin = "admin"
    coach = "coach"
    viewer = "viewer"


class InsightSource(str, PyEnum):
    jira = "jira"
    slack = "slack"
    transcript = "transcript"


class InsightType(str, PyEnum):
    blocker = "blocker"
    decision = "decision"
    risk = "risk"
    sentiment = "sentiment"
    dependency = "dependency"
    scope_change = "scope_change"


class Severity(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    surname: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.viewer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # External identity links
    jira_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # OAuth tokens (encrypted in production)
    jira_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    team_memberships: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="user")
    chat_messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    jira_project_key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    jira_board_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jira_cloud_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slack_channel_ids: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Risk scoring weights (must sum to 1.0)
    weight_wip_aging: Mapped[float] = mapped_column(Float, default=0.20)
    weight_dependencies: Mapped[float] = mapped_column(Float, default=0.20)
    weight_velocity_trend: Mapped[float] = mapped_column(Float, default=0.15)
    weight_pbi_readiness: Mapped[float] = mapped_column(Float, default=0.15)
    weight_slack_blockers: Mapped[float] = mapped_column(Float, default=0.15)
    weight_sentiment: Mapped[float] = mapped_column(Float, default=0.10)
    weight_meeting_alignment: Mapped[float] = mapped_column(Float, default=0.05)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_jira_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    members: Mapped[list["TeamMember"]] = relationship("TeamMember", back_populates="team")
    risk_snapshots: Mapped[list["RiskSnapshot"]] = relationship("RiskSnapshot", back_populates="team", order_by="RiskSnapshot.snapshot_at.desc()")
    insights: Mapped[list["Insight"]] = relationship("Insight", back_populates="team")
    jira_issues: Mapped[list["JiraIssue"]] = relationship("JiraIssue", back_populates="team")
    sprints: Mapped[list["Sprint"]] = relationship("Sprint", back_populates="team")
    transcripts: Mapped[list["Transcript"]] = relationship("Transcript", back_populates="team")
    healthchecks: Mapped[list["BacklogHealthcheck"]] = relationship("BacklogHealthcheck", back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="team_memberships")


class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    jira_sprint_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)  # active | closed | future
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    complete_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Velocity metrics
    committed_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    velocity: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped["Team"] = relationship("Team", back_populates="sprints")
    issues: Mapped[list["JiraIssue"]] = relationship("JiraIssue", back_populates="sprint")

    __table_args__ = (
        UniqueConstraint("team_id", "jira_sprint_id"),
        Index("ix_sprints_team_state", "team_id", "state"),
    )


class JiraIssue(Base):
    __tablename__ = "jira_issues"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    sprint_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("sprints.id"), nullable=True, index=True)

    jira_issue_id: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Story, Bug, Task, Epic
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    status_category: Mapped[str] = mapped_column(String(50), nullable=False)  # To Do, In Progress, Done
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assignee_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assignee_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    story_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    labels: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)

    # Dates
    created_at_jira: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_jira: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Computed risk fields
    time_in_status_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocker_count: Mapped[int] = mapped_column(Integer, default=0)
    has_acceptance_criteria: Mapped[bool] = mapped_column(Boolean, default=False)
    dependency_depth: Mapped[int] = mapped_column(Integer, default=0)

    # Links (blocked-by / blocks / relates-to)
    issue_links: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped["Team"] = relationship("Team", back_populates="jira_issues")
    sprint: Mapped["Sprint | None"] = relationship("Sprint", back_populates="issues")
    transitions: Mapped[list["IssueTransition"]] = relationship("IssueTransition", back_populates="issue")

    __table_args__ = (
        UniqueConstraint("team_id", "jira_issue_id"),
        Index("ix_jira_issues_status", "team_id", "status_category"),
    )


class IssueTransition(Base):
    """Stores the history of status changes for an issue."""
    __tablename__ = "issue_transitions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    issue_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("jira_issues.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_status: Mapped[str] = mapped_column(String(100), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    author_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    issue: Mapped["JiraIssue"] = relationship("JiraIssue", back_populates="transitions")


class RiskSnapshot(Base):
    """Point-in-time risk scores for a team. Stored as time-series for trend analysis."""
    __tablename__ = "risk_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # Individual signal scores (0–100, higher = more risk)
    wip_aging_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    dependency_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    velocity_trend_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    pbi_readiness_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    slack_blocker_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    sentiment_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    meeting_alignment_score: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Weighted composite (0–100)
    composite_score: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Full signal detail for drill-down
    raw_signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    team: Mapped["Team"] = relationship("Team", back_populates="risk_snapshots")

    __table_args__ = (
        Index("ix_risk_snapshots_team_time", "team_id", "snapshot_at"),
    )


class Transcript(Base):
    """Meeting transcript ingested manually or from Google Drive."""
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)          # "manual" | "google_drive"
    google_doc_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped["Team"] = relationship("Team", back_populates="transcripts")
    insights: Mapped[list["Insight"]] = relationship("Insight", back_populates="transcript")

    __table_args__ = (
        Index("ix_transcripts_team_date", "team_id", "meeting_date"),
    )


class Insight(Base):
    """Individual insights extracted from any source."""
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    transcript_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("transcripts.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.medium)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    team: Mapped["Team"] = relationship("Team", back_populates="insights")
    transcript: Mapped["Transcript | None"] = relationship("Transcript", back_populates="insights")

    __table_args__ = (
        Index("ix_insights_team_source_time", "team_id", "source", "captured_at"),
    )


class BacklogHealthcheck(Base):
    """Stores a generated PBL healthcheck report for a team."""
    __tablename__ = "backlog_healthchecks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|running|complete|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_days: Mapped[int] = mapped_column(Integer, default=180)
    total_items: Mapped[int] = mapped_column(Integer, default=0)

    # Populated when status=complete
    lead_times: Mapped[dict | None] = mapped_column(JSONB, nullable=True)          # {avg, story, bug, task}
    item_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)         # {issue_key: {criterion: "good"|"medium"|"critical"}}
    item_groups: Mapped[dict | None] = mapped_column(JSONB, nullable=True)         # {completed_last_month:[keys], ...}
    column_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)        # {group: {criterion: {good:%, medium:%, critical:%}}}
    ai_insights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)         # {completed_last_month:"...", ...}
    top_issues: Mapped[list | None] = mapped_column(JSONB, nullable=True)          # [{key, summary, root_cause}]
    concrete_actions: Mapped[list | None] = mapped_column(JSONB, nullable=True)    # ["action 1", ...]

    team: Mapped["Team"] = relationship("Team", back_populates="healthchecks")

    __table_args__ = (
        Index("ix_backlog_healthchecks_team_generated", "team_id", "generated_at"),
    )


class ChatMessage(Base):
    """Persisted chat history per user per session."""
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("teams.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="chat_messages")
