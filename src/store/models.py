"""PostgreSQL SQLAlchemy models for Provenance Ledger according to mechanics.md Section 2."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Claim(Base):
    """One row per agent-generated claim."""

    __tablename__ = "claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
    original_result: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    data_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    env_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, default="unverified", nullable=False
    )  # 'unverified' | 'reproduced' | 'failed'

    # Relationships
    reexecutions: Mapped[list["ReexecutionResult"]] = relationship(
        "ReexecutionResult", back_populates="claim", cascade="all, delete-orphan"
    )


class EnvironmentSnapshot(Base):
    """One row per environment fingerprint (dedup — many claims can share one env)."""

    __tablename__ = "environment_snapshots"

    env_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    library_versions: Mapped[Dict[str, str]] = mapped_column(JSONB, nullable=False)


class ReexecutionResult(Base):
    """One row per re-execution attempt (a claim can be re-tried multiple times over its life)."""

    __tablename__ = "reexecution_results"

    reexecution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.claim_id", ondelete="CASCADE"), nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    new_result: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="reexecutions")
    diagnoses: Mapped[list["DriftDiagnosis"]] = relationship(
        "DriftDiagnosis", back_populates="reexecution", cascade="all, delete-orphan"
    )


class DriftDiagnosis(Base):
    """One row per detected mismatch, with a diagnosed cause."""

    __tablename__ = "drift_diagnoses"

    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reexecution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reexecution_results.reexecution_id", ondelete="CASCADE"),
        nullable=False,
    )
    cause: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # 'model_version_change' | 'library_version_change' | 'data_change' | 'stochastic_variation' | 'unknown'
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    reexecution: Mapped["ReexecutionResult"] = relationship(
        "ReexecutionResult", back_populates="diagnoses"
    )
