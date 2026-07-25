"""Add venues.is_tracked for the dynamic top-N tracked-venue selection.

Revision ID: 0004_add_venue_is_tracked
Revises: 0003_drop_unused_snapshot_fields
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_venue_is_tracked"
down_revision: str | None = "0003_drop_unused_snapshot_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venues") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_tracked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("venues") as batch_op:
        batch_op.drop_column("is_tracked")
