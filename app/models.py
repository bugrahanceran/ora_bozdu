from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    venues: Mapped[list["Venue"]] = relationship(back_populates="region")


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (
        UniqueConstraint("region_id", "slug", name="uq_venue_region_slug"),
        UniqueConstraint(
            "provider", "provider_place_id", name="uq_venue_provider_place_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    slug: Mapped[str] = mapped_column(String(180))
    display_name: Mapped[str] = mapped_column(String(240), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="places_api")
    provider_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    region: Mapped[Region] = relationship(back_populates="venues")
    snapshots: Mapped[list["PlaceSnapshot"]] = relationship(back_populates="venue")


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    cadence: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running")
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    warning_summary: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)


class PlaceSnapshot(Base):
    __tablename__ = "place_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "cadence",
            "period_start",
            name="uq_snapshot_venue_cadence_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    fetch_run_id: Mapped[int] = mapped_column(ForeignKey("fetch_runs.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    cadence: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    provider_name: Mapped[str] = mapped_column(String(240))
    formatted_address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[float | None] = mapped_column(Float)
    user_ratings_total: Mapped[int | None] = mapped_column(Integer)
    price_level: Mapped[int | None] = mapped_column(Integer)
    business_status: Mapped[str | None] = mapped_column(String(40))
    types: Mapped[list[str] | None] = mapped_column(JSON)
    website: Mapped[str | None] = mapped_column(String(1000))
    google_maps_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    venue: Mapped[Venue] = relationship(back_populates="snapshots")
    payloads: Mapped[list["SnapshotPayload"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["SnapshotReview"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class SnapshotPayload(Base):
    __tablename__ = "snapshot_payloads"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "provider", "request_variant", name="uq_payload_variant"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("place_snapshots.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    request_variant: Mapped[str] = mapped_column(String(80))
    review_sort: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))

    snapshot: Mapped[PlaceSnapshot] = relationship(back_populates="payloads")


class SnapshotReview(Base):
    __tablename__ = "snapshot_reviews"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "dedup_key", name="uq_snapshot_review_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("place_snapshots.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(40), default="places_api")
    provider_review_id: Mapped[str | None] = mapped_column(String(255))
    dedup_key: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(255))
    author_url: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(20))
    original_language: Mapped[str | None] = mapped_column(String(20))
    translated: Mapped[bool | None] = mapped_column(Boolean)
    raw_review: Mapped[dict[str, Any]] = mapped_column(JSON)

    snapshot: Mapped[PlaceSnapshot] = relationship(back_populates="reviews")
    appearances: Mapped[list["SnapshotReviewAppearance"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class SnapshotReviewAppearance(Base):
    __tablename__ = "snapshot_review_appearances"
    __table_args__ = (
        UniqueConstraint("snapshot_review_id", "review_sort", name="uq_review_sort"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_review_id: Mapped[int] = mapped_column(
        ForeignKey("snapshot_reviews.id", ondelete="CASCADE"), index=True
    )
    snapshot_payload_id: Mapped[int] = mapped_column(
        ForeignKey("snapshot_payloads.id", ondelete="CASCADE"), index=True
    )
    review_sort: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(Integer)

    review: Mapped[SnapshotReview] = relationship(back_populates="appearances")


class FetchRunWarning(Base):
    __tablename__ = "fetch_run_warnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    fetch_run_id: Mapped[int] = mapped_column(
        ForeignKey("fetch_runs.id", ondelete="CASCADE"), index=True
    )
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("place_snapshots.id", ondelete="SET NULL"), index=True
    )
    warning_code: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ScoreResult(Base):
    __tablename__ = "score_results"
    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "as_of_snapshot_id",
            "score_version",
            name="uq_score_venue_snapshot_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    as_of_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("place_snapshots.id"), index=True
    )
    score_version: Mapped[str] = mapped_column(String(40), index=True)
    change_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(32))
    stability_state: Mapped[str] = mapped_column(String(32))
    signal_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_story: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
