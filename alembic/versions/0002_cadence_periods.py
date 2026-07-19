"""Add cadence-aware snapshot periods.

Revision ID: 0002_cadence_periods
Revises: 0001_initial_schema
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_cadence_periods"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fetch_runs", sa.Column("cadence", sa.String(length=16), nullable=True)
    )
    op.add_column("fetch_runs", sa.Column("period_start", sa.Date(), nullable=True))
    op.add_column(
        "place_snapshots", sa.Column("cadence", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "place_snapshots", sa.Column("period_start", sa.Date(), nullable=True)
    )

    connection = op.get_bind()
    fetch_runs = sa.table(
        "fetch_runs",
        sa.column("id", sa.Integer),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("cadence", sa.String),
        sa.column("period_start", sa.Date),
    )
    for row in connection.execute(sa.select(fetch_runs.c.id, fetch_runs.c.started_at)):
        connection.execute(
            fetch_runs.update()
            .where(fetch_runs.c.id == row.id)
            .values(cadence="daily", period_start=row.started_at.date())
        )

    snapshots = sa.table(
        "place_snapshots",
        sa.column("id", sa.Integer),
        sa.column("snapshot_date", sa.Date),
        sa.column("cadence", sa.String),
        sa.column("period_start", sa.Date),
    )
    connection.execute(
        snapshots.update().values(
            cadence="daily",
            period_start=snapshots.c.snapshot_date,
        )
    )

    with op.batch_alter_table("fetch_runs") as batch_op:
        batch_op.alter_column("cadence", nullable=False)
        batch_op.alter_column("period_start", nullable=False)
        batch_op.create_index("ix_fetch_runs_period_start", ["period_start"])

    with op.batch_alter_table("place_snapshots") as batch_op:
        batch_op.drop_constraint("uq_snapshot_venue_date", type_="unique")
        batch_op.alter_column("cadence", nullable=False)
        batch_op.alter_column("period_start", nullable=False)
        batch_op.create_index("ix_place_snapshots_period_start", ["period_start"])
        batch_op.create_unique_constraint(
            "uq_snapshot_venue_cadence_period",
            ["venue_id", "cadence", "period_start"],
        )

    with op.batch_alter_table("venues") as batch_op:
        batch_op.drop_column("seed_query")


def downgrade() -> None:
    with op.batch_alter_table("venues") as batch_op:
        batch_op.add_column(
            sa.Column("seed_query", sa.String(length=500), nullable=True)
        )

    with op.batch_alter_table("place_snapshots") as batch_op:
        batch_op.drop_constraint("uq_snapshot_venue_cadence_period", type_="unique")
        batch_op.drop_index("ix_place_snapshots_period_start")
        batch_op.drop_column("period_start")
        batch_op.drop_column("cadence")
        batch_op.create_unique_constraint(
            "uq_snapshot_venue_date", ["venue_id", "snapshot_date"]
        )

    with op.batch_alter_table("fetch_runs") as batch_op:
        batch_op.drop_index("ix_fetch_runs_period_start")
        batch_op.drop_column("period_start")
        batch_op.drop_column("cadence")
