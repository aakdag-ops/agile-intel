"""004_agents

Revision ID: 004
Revises: 003
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_configs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('request_board_id', sa.Integer(), nullable=True),
        sa.Column('request_jql', sa.Text(), nullable=True),
        sa.Column('target_project_key', sa.String(50), nullable=True),
        sa.Column('github_repo_url', sa.String(500), nullable=True),
        sa.Column('github_token', sa.Text(), nullable=True),
        sa.Column('enable_solution_architect', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enable_pbi_generator', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enable_dependency_agent', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enable_backlog_dispatcher', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_create_jira_issues', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('poll_interval_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('last_polled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_processed_issue_key', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id'),
    )
    op.create_index('ix_agent_configs_team_id', 'agent_configs', ['team_id'])

    op.create_table(
        'agent_pipelines',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('trigger_issue_key', sa.String(50), nullable=False),
        sa.Column('trigger_issue_summary', sa.Text(), nullable=False),
        sa.Column('trigger_issue_data', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_pipelines_team_id', 'agent_pipelines', ['team_id'])
    op.create_index('ix_agent_pipelines_team_created', 'agent_pipelines', ['team_id', 'created_at'])

    op.create_table(
        'agent_step_results',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('pipeline_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('agent_label', sa.String(200), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('output', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['pipeline_id'], ['agent_pipelines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_step_results_pipeline', 'agent_step_results', ['pipeline_id'])
    op.create_index('ix_agent_step_results_pipeline_order', 'agent_step_results', ['pipeline_id', 'step_order'])


def downgrade():
    op.drop_table('agent_step_results')
    op.drop_table('agent_pipelines')
    op.drop_table('agent_configs')
