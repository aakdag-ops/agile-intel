"""add backlog_healthchecks table

Revision ID: 003
Revises: 002
Create Date: 2026-03-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'backlog_healthchecks',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('period_days', sa.Integer(), server_default='180', nullable=False),
        sa.Column('total_items', sa.Integer(), server_default='0', nullable=False),
        sa.Column('lead_times', postgresql.JSONB(), nullable=True),
        sa.Column('item_scores', postgresql.JSONB(), nullable=True),
        sa.Column('item_groups', postgresql.JSONB(), nullable=True),
        sa.Column('column_stats', postgresql.JSONB(), nullable=True),
        sa.Column('ai_insights', postgresql.JSONB(), nullable=True),
        sa.Column('top_issues', postgresql.JSONB(), nullable=True),
        sa.Column('concrete_actions', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_backlog_healthchecks_team_generated',
        'backlog_healthchecks',
        ['team_id', 'generated_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_backlog_healthchecks_team_generated', table_name='backlog_healthchecks')
    op.drop_table('backlog_healthchecks')
