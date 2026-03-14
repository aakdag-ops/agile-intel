"""add transcripts table and transcript_id to insights

Revision ID: 002
Revises: 001
Create Date: 2025-01-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'transcripts',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('google_doc_id', sa.String(200), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('meeting_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('participants', postgresql.JSONB(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_doc_id'),
    )
    op.create_index('ix_transcripts_team_date', 'transcripts', ['team_id', 'meeting_date'])

    op.add_column(
        'insights',
        sa.Column('transcript_id', postgresql.UUID(as_uuid=False), nullable=True)
    )
    op.create_foreign_key(
        'fk_insights_transcript_id',
        'insights', 'transcripts',
        ['transcript_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_insights_transcript_id', 'insights', ['transcript_id'])


def downgrade() -> None:
    op.drop_index('ix_insights_transcript_id', table_name='insights')
    op.drop_constraint('fk_insights_transcript_id', 'insights', type_='foreignkey')
    op.drop_column('insights', 'transcript_id')
    op.drop_index('ix_transcripts_team_date', table_name='transcripts')
    op.drop_table('transcripts')
