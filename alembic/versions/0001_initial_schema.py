"""Create the initial snapshot and scoring schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regions_slug", "regions", ["slug"], unique=True)

    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_place_id", sa.String(length=255), nullable=True),
        sa.Column("seed_query", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_place_id", name="uq_venue_provider_place_id"
        ),
        sa.UniqueConstraint("region_id", "slug", name="uq_venue_region_slug"),
    )
    op.create_index("ix_venues_display_name", "venues", ["display_name"])
    op.create_index("ix_venues_region_id", "venues", ["region_id"])

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=True),
        sa.Column("warning_summary", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fetch_runs_region_id", "fetch_runs", ["region_id"])

    op.create_table(
        "place_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_name", sa.String(length=240), nullable=False),
        sa.Column("formatted_address", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("user_ratings_total", sa.Integer(), nullable=True),
        sa.Column("price_level", sa.Integer(), nullable=True),
        sa.Column("business_status", sa.String(length=40), nullable=True),
        sa.Column("types", sa.JSON(), nullable=True),
        sa.Column("website", sa.String(length=1000), nullable=True),
        sa.Column("google_maps_url", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fetch_run_id"], ["fetch_runs.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("venue_id", "snapshot_date", name="uq_snapshot_venue_date"),
    )
    op.create_index(
        "ix_place_snapshots_fetch_run_id", "place_snapshots", ["fetch_run_id"]
    )
    op.create_index(
        "ix_place_snapshots_snapshot_date", "place_snapshots", ["snapshot_date"]
    )
    op.create_index("ix_place_snapshots_venue_id", "place_snapshots", ["venue_id"])

    op.create_table(
        "snapshot_payloads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("request_variant", sa.String(length=80), nullable=False),
        sa.Column("review_sort", sa.String(length=32), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["place_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "provider",
            "request_variant",
            name="uq_payload_variant",
        ),
    )
    op.create_index(
        "ix_snapshot_payloads_snapshot_id", "snapshot_payloads", ["snapshot_id"]
    )

    op.create_table(
        "snapshot_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("provider_review_id", sa.String(length=255), nullable=True),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("author_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("original_language", sa.String(length=20), nullable=True),
        sa.Column("translated", sa.Boolean(), nullable=True),
        sa.Column("raw_review", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["place_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "dedup_key", name="uq_snapshot_review_key"),
    )
    op.create_index(
        "ix_snapshot_reviews_published_at", "snapshot_reviews", ["published_at"]
    )
    op.create_index(
        "ix_snapshot_reviews_snapshot_id", "snapshot_reviews", ["snapshot_id"]
    )

    op.create_table(
        "snapshot_review_appearances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_review_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_payload_id", sa.Integer(), nullable=False),
        sa.Column("review_sort", sa.String(length=32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_payload_id"], ["snapshot_payloads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_review_id"], ["snapshot_reviews.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_review_id", "review_sort", name="uq_review_sort"),
    )
    op.create_index(
        "ix_snapshot_review_appearances_snapshot_payload_id",
        "snapshot_review_appearances",
        ["snapshot_payload_id"],
    )
    op.create_index(
        "ix_snapshot_review_appearances_snapshot_review_id",
        "snapshot_review_appearances",
        ["snapshot_review_id"],
    )

    op.create_table(
        "fetch_run_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("warning_code", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fetch_run_id"], ["fetch_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["place_snapshots.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fetch_run_warnings_fetch_run_id", "fetch_run_warnings", ["fetch_run_id"]
    )
    op.create_index(
        "ix_fetch_run_warnings_snapshot_id", "fetch_run_warnings", ["snapshot_id"]
    )
    op.create_index(
        "ix_fetch_run_warnings_venue_id", "fetch_run_warnings", ["venue_id"]
    )

    op.create_table(
        "score_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("as_of_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("score_version", sa.String(length=40), nullable=False),
        sa.Column("change_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("stability_state", sa.String(length=32), nullable=False),
        sa.Column("signal_breakdown", sa.JSON(), nullable=False),
        sa.Column("change_story", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["as_of_snapshot_id"], ["place_snapshots.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "venue_id",
            "as_of_snapshot_id",
            "score_version",
            name="uq_score_venue_snapshot_version",
        ),
    )
    op.create_index(
        "ix_score_results_as_of_snapshot_id",
        "score_results",
        ["as_of_snapshot_id"],
    )
    op.create_index(
        "ix_score_results_score_version", "score_results", ["score_version"]
    )
    op.create_index("ix_score_results_venue_id", "score_results", ["venue_id"])


def downgrade() -> None:
    op.drop_index("ix_score_results_venue_id", table_name="score_results")
    op.drop_index("ix_score_results_score_version", table_name="score_results")
    op.drop_index("ix_score_results_as_of_snapshot_id", table_name="score_results")
    op.drop_table("score_results")
    op.drop_index("ix_fetch_run_warnings_venue_id", table_name="fetch_run_warnings")
    op.drop_index("ix_fetch_run_warnings_snapshot_id", table_name="fetch_run_warnings")
    op.drop_index("ix_fetch_run_warnings_fetch_run_id", table_name="fetch_run_warnings")
    op.drop_table("fetch_run_warnings")
    op.drop_index(
        "ix_snapshot_review_appearances_snapshot_review_id",
        table_name="snapshot_review_appearances",
    )
    op.drop_index(
        "ix_snapshot_review_appearances_snapshot_payload_id",
        table_name="snapshot_review_appearances",
    )
    op.drop_table("snapshot_review_appearances")
    op.drop_index("ix_snapshot_reviews_snapshot_id", table_name="snapshot_reviews")
    op.drop_index("ix_snapshot_reviews_published_at", table_name="snapshot_reviews")
    op.drop_table("snapshot_reviews")
    op.drop_index("ix_snapshot_payloads_snapshot_id", table_name="snapshot_payloads")
    op.drop_table("snapshot_payloads")
    op.drop_index("ix_place_snapshots_venue_id", table_name="place_snapshots")
    op.drop_index("ix_place_snapshots_snapshot_date", table_name="place_snapshots")
    op.drop_index("ix_place_snapshots_fetch_run_id", table_name="place_snapshots")
    op.drop_table("place_snapshots")
    op.drop_index("ix_fetch_runs_region_id", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("ix_venues_region_id", table_name="venues")
    op.drop_index("ix_venues_display_name", table_name="venues")
    op.drop_table("venues")
    op.drop_index("ix_regions_slug", table_name="regions")
    op.drop_table("regions")
