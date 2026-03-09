"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('surname', sa.String(100), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='viewer'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('jira_account_id', sa.String(100), nullable=True),
        sa.Column('slack_user_id', sa.String(50), nullable=True),
        sa.Column('jira_access_token', sa.Text(), nullable=True),
        sa.Column('jira_refresh_token', sa.Text(), nullable=True),
        sa.Column('google_access_token', sa.Text(), nullable=True),
        sa.Column('google_refresh_token', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('jira_project_key', sa.String(50), nullable=False),
        sa.Column('jira_board_id', sa.Integer(), nullable=True),
        sa.Column('jira_cloud_id', sa.String(100), nullable=True),
        sa.Column('slack_channel_ids', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('weight_wip_aging', sa.Float(), nullable=False, server_default='0.20'),
        sa.Column('weight_dependencies', sa.Float(), nullable=False, server_default='0.20'),
        sa.Column('weight_velocity_trend', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('weight_pbi_readiness', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('weight_slack_blockers', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('weight_sentiment', sa.Float(), nullable=False, server_default='0.10'),
        sa.Column('weight_meeting_alignment', sa.Float(), nullable=False, server_default='0.05'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_jira_sync', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jira_project_key'),
    )
    op.create_index('ix_teams_jira_project_key', 'teams', ['jira_project_key'])

    op.create_table(
        'team_members',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('is_lead', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'user_id'),
    )

    op.create_table(
        'sprints',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('jira_sprint_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('complete_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('committed_points', sa.Float(), nullable=True),
        sa.Column('completed_points', sa.Float(), nullable=True),
        sa.Column('velocity', sa.Float(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'jira_sprint_id'),
    )
    op.create_index('ix_sprints_team_state', 'sprints', ['team_id', 'state'])

    op.create_table(
        'jira_issues',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('sprint_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('jira_issue_id', sa.String(50), nullable=False),
        sa.Column('issue_key', sa.String(50), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('issue_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(100), nullable=False),
        sa.Column('status_category', sa.String(50), nullable=False),
        sa.Column('priority', sa.String(50), nullable=True),
        sa.Column('assignee_account_id', sa.String(100), nullable=True),
        sa.Column('assignee_name', sa.String(200), nullable=True),
        sa.Column('story_points', sa.Float(), nullable=True),
        sa.Column('labels', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('created_at_jira', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at_jira', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('time_in_status_hours', sa.Float(), nullable=True),
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('blocker_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('has_acceptance_criteria', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('dependency_depth', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('issue_links', postgresql.JSONB(), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sprint_id'], ['sprints.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'jira_issue_id'),
    )
    op.create_index('ix_jira_issues_status', 'jira_issues', ['team_id', 'status_category'])
    op.create_index('ix_jira_issues_key', 'jira_issues', ['issue_key'])

    op.create_table(
        'issue_transitions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('issue_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('from_status', sa.String(100), nullable=True),
        sa.Column('to_status', sa.String(100), nullable=False),
        sa.Column('transitioned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('author_account_id', sa.String(100), nullable=True),
        sa.Column('author_name', sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(['issue_id'], ['jira_issues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_issue_transitions_issue', 'issue_transitions', ['issue_id'])

    op.create_table(
        'risk_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('wip_aging_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('dependency_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('velocity_trend_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('pbi_readiness_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('slack_blocker_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('sentiment_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('meeting_alignment_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('composite_score', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('raw_signals', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_risk_snapshots_team_time', 'risk_snapshots', ['team_id', 'snapshot_at'])

    op.create_table(
        'insights',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('insight_type', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_insights_team_source_time', 'insights', ['team_id', 'source', 'captured_at'])

    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('session_id', sa.String(100), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chat_messages_user_session', 'chat_messages', ['user_id', 'session_id'])


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('insights')
    op.drop_table('risk_snapshots')
    op.drop_table('issue_transitions')
    op.drop_table('jira_issues')
    op.drop_table('sprints')
    op.drop_table('team_members')
    op.drop_table('teams')
    op.drop_table('users')
