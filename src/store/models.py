"""SQLAlchemy models for Provenance Ledger supporting PostgreSQL native types with universal SQLite compatibility."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Claim(Base):
    """One row per agent-generated claim."""

    __tablename__ = "claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_code: Mapped[str] = mapped_column(Text, nullable=False)
    original_result: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    data_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    env_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, default="unverified", nullable=False
    )

    # Relationships
    reexecutions: Mapped[list["ReexecutionResult"]] = relationship(
        "ReexecutionResult", back_populates="claim", cascade="all, delete-orphan"
    )


class EnvironmentSnapshot(Base):
    """One row per environment fingerprint."""

    __tablename__ = "environment_snapshots"

    env_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    library_versions: Mapped[Dict[str, str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )


class ReexecutionResult(Base):
    """One row per re-execution attempt of a claim."""

    __tablename__ = "reexecution_results"

    reexecution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(UUID(as_uuid=True), "postgresql"),
        ForeignKey("claims.claim_id", ondelete="CASCADE"),
        nullable=False,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    new_result: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="reexecutions")
    drift_diagnosis: Mapped[Optional["DriftDiagnosis"]] = relationship(
        "DriftDiagnosis",
        back_populates="reexecution",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DriftDiagnosis(Base):
    """One row per non-reproducible run with diagnosed root cause."""

    __tablename__ = "drift_diagnoses"

    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    reexecution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid().with_variant(UUID(as_uuid=True), "postgresql"),
        ForeignKey("reexecution_results.reexecution_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    cause: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )

    # Relationships
    reexecution: Mapped["ReexecutionResult"] = relationship(
        "ReexecutionResult", back_populates="drift_diagnosis"
    )
