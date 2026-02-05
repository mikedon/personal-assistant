"""Add initiative_id to tasks table.

This migration was generated after the column was manually added via ALTER TABLE.
The column and foreign key constraint are already in place.

Revision ID: 7ae29958397f
Revises:
Create Date: 2026-02-04 14:10:38.372859
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ae29958397f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite requires batch mode for schema changes with foreign keys
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('initiative_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_tasks_initiative_id',
            'initiatives',
            ['initiative_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tasks_initiative_id', type_='foreignkey')
        batch_op.drop_column('initiative_id')
