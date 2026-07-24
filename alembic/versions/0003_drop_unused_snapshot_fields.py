"""Drop place_snapshots columns never populated by the minimal field mask.

Revision ID: 0003_drop_unused_snapshot_fields
Revises: 0002_cadence_periods
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_drop_unused_snapshot_fields"
down_revision: str | None = "0002_cadence_periods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("place_snapshots") as batch_op:
        batch_op.drop_column("formatted_address")
        batch_op.drop_column("latitude")
        batch_op.drop_column("longitude")
        batch_op.drop_column("types")
        batch_op.drop_column("website")
        batch_op.drop_column("google_maps_url")


def downgrade() -> None:
    with op.batch_alter_table("place_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("formatted_address", sa.String(length=500), nullable=True)
        )
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("types", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("website", sa.String(length=1000), nullable=True))
        batch_op.add_column(
            sa.Column("google_maps_url", sa.String(length=1000), nullable=True)
        )
