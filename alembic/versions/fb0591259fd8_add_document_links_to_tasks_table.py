"""add document_links to tasks table

Revision ID: fb0591259fd8
Revises: 7cc4fcff7603
Create Date: 2026-02-10 16:37:30.314387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb0591259fd8'
down_revision: Union[str, Sequence[str], None] = '7cc4fcff7603'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add document_links column to tasks table
    op.add_column('tasks', sa.Column('document_links', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove document_links column from tasks table
    op.drop_column('tasks', 'document_links')
