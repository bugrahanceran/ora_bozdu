"""Add venue_reviews for the scraped historical review backfill corpus.

Revision ID: 0005_add_venue_reviews
Revises: 0004_add_venue_is_tracked
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_venue_reviews"
down_revision: str | None = "0004_add_venue_is_tracked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("provider_review_id", sa.String(length=255), nullable=True),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("sub_ratings", sa.JSON(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "dedup_key", name="uq_venue_review_key"),
    )
    op.create_index("ix_venue_reviews_venue_id", "venue_reviews", ["venue_id"])
    op.create_index("ix_venue_reviews_published_at", "venue_reviews", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_venue_reviews_published_at", table_name="venue_reviews")
    op.drop_index("ix_venue_reviews_venue_id", table_name="venue_reviews")
    op.drop_table("venue_reviews")
