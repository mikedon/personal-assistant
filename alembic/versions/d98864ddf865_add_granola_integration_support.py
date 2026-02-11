"""Add Granola integration support

Revision ID: d98864ddf865
Revises: 7cc4fcff7603
Create Date: 2026-02-11 09:40:38.670848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd98864ddf865'
down_revision: Union[str, Sequence[str], None] = '7cc4fcff7603'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create processed_granola_notes table for tracking which Granola notes have been processed
    op.create_table(
        'processed_granola_notes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('note_id', sa.String(length=200), nullable=False),
        sa.Column('workspace_id', sa.String(length=200), nullable=False),
        sa.Column('account_id', sa.String(length=100), nullable=False),
        sa.Column('note_title', sa.String(length=500), nullable=False),
        sa.Column('note_created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tasks_created_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('note_id', 'account_id', name='uix_note_account')
    )

    # Create indexes for efficient querying
    op.create_index(
        op.f('ix_processed_granola_notes_account_id'),
        'processed_granola_notes',
        ['account_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_processed_granola_notes_note_id'),
        'processed_granola_notes',
        ['note_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop processed_granola_notes table and indexes
    op.drop_index(op.f('ix_processed_granola_notes_note_id'), table_name='processed_granola_notes')
    op.drop_index(op.f('ix_processed_granola_notes_account_id'), table_name='processed_granola_notes')
    op.drop_table('processed_granola_notes')
