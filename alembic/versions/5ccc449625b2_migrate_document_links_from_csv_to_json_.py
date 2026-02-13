"""migrate document_links from csv to json and increase size

Revision ID: 5ccc449625b2
Revises: fb0591259fd8
Create Date: 2026-02-10 23:40:48.796224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ccc449625b2'
down_revision: Union[str, Sequence[str], None] = 'fb0591259fd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: increase column size and convert CSV to JSON.

    This migration:
    1. Increases document_links column from VARCHAR(1000) to VARCHAR(5000)
    2. Converts existing CSV data to JSON format
    """
    # Step 1: Increase column size
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('document_links',
                              existing_type=sa.String(length=1000),
                              type_=sa.String(length=5000),
                              existing_nullable=True)

    # Step 2: Convert existing CSV data to JSON
    # Using Python to handle CSV -> JSON conversion safely
    import json
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    bind = op.get_bind()
    session = Session(bind=bind)

    # Fetch all tasks with document_links
    result = session.execute(text(
        "SELECT id, document_links FROM tasks WHERE document_links IS NOT NULL AND document_links != ''"
    ))

    for row in result:
        task_id, csv_links = row

        # Skip if already JSON format
        try:
            json.loads(csv_links)
            continue  # Already JSON, skip
        except (json.JSONDecodeError, ValueError):
            pass

        # Convert CSV to JSON
        links = [link.strip() for link in csv_links.split(",") if link.strip()]
        json_links = json.dumps(links)

        # Update the row
        session.execute(
            text("UPDATE tasks SET document_links = :json_links WHERE id = :task_id"),
            {"json_links": json_links, "task_id": task_id}
        )

    session.commit()


def downgrade() -> None:
    """Downgrade schema: reduce column size and convert JSON to CSV.

    WARNING: This operation may lose data if URLs exceed 1000 character limit
    or if JSON arrays cannot be properly converted to CSV.
    """
    # Step 1: Convert JSON back to CSV
    import json
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    bind = op.get_bind()
    session = Session(bind=bind)

    # Fetch all tasks with document_links
    result = session.execute(text(
        "SELECT id, document_links FROM tasks WHERE document_links IS NOT NULL AND document_links != ''"
    ))

    for row in result:
        task_id, json_links = row

        # Skip if already CSV format
        try:
            links = json.loads(json_links)
            if not isinstance(links, list):
                continue  # Invalid format, skip
        except (json.JSONDecodeError, ValueError):
            continue  # Already CSV or invalid, skip

        # Convert JSON to CSV
        csv_links = ",".join(links) if links else None

        # Update the row (may truncate if over 1000 chars)
        session.execute(
            text("UPDATE tasks SET document_links = :csv_links WHERE id = :task_id"),
            {"csv_links": csv_links, "task_id": task_id}
        )

    session.commit()

    # Step 2: Reduce column size
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('document_links',
                              existing_type=sa.String(length=5000),
                              type_=sa.String(length=1000),
                              existing_nullable=True)
