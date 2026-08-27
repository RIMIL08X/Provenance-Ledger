"""Unit tests for PostgreSQL database models and ProvenanceStore DAL."""

import uuid
import pytest
from src.store.database import get_session, init_db
from src.store.models import Claim, EnvironmentSnapshot, ReexecutionResult, DriftDiagnosis
from src.store.repository import ProvenanceStore


@pytest.fixture(autouse=True)
def ensure_db():
    """Ensure database schema is created."""
    init_db()


@pytest.fixture
def db_session():
    """Provide a real PostgreSQL session."""
    with get_session() as session:
        yield session


def test_record_claim_and_environment_snapshot(db_session):
    """Verify recording a claim creates the claim row and upserts the environment snapshot."""
    store = ProvenanceStore(db_session)
    env_h = f"env_{uuid.uuid4().hex[:12]}"

    claim = store.record_claim(
        prompt="Calculate average revenue by region",
        model_name="mock-model",
        model_version="1.0.0",
        seed=42,
        generated_code="result = df.groupby('region')['revenue'].mean().to_dict()",
        original_result={"North": 100.5, "South": 200.0},
        data_snapshot_hash="dummy_data_hash_123",
        env_hash=env_h,
        library_versions={"pandas": "2.2.0", "numpy": "1.26.0"},
    )
    db_session.flush()

    assert claim.claim_id is not None
    assert claim.prompt == "Calculate average revenue by region"
    assert claim.status == "unverified"
    assert claim.original_result == {"North": 100.5, "South": 200.0}

    # Verify retrieval
    retrieved = store.get_claim(claim.claim_id)
    assert retrieved is not None
    assert retrieved.model_name == "mock-model"

    # Verify environment snapshot upsert
    snapshot = db_session.get(EnvironmentSnapshot, env_h)
    assert snapshot is not None
    assert snapshot.library_versions["pandas"] == "2.2.0"


def test_environment_snapshot_deduplication(db_session):
    """Verify duplicate environment hashes do not create duplicate rows."""
    store = ProvenanceStore(db_session)
    env_h = f"dedup_env_{uuid.uuid4().hex[:12]}"

    store.upsert_environment_snapshot(
        env_hash=env_h,
        library_versions={"pandas": "2.2.0"},
    )
    db_session.flush()

    # Second upsert with identical env_hash
    store.upsert_environment_snapshot(
        env_hash=env_h,
        library_versions={"pandas": "2.2.0"},
    )
    db_session.flush()

    snapshots = db_session.query(EnvironmentSnapshot).filter_by(env_hash=env_h).all()
    assert len(snapshots) == 1


def test_record_reexecution_and_drift_diagnosis(db_session):
    """Verify linking reexecution results and drift diagnosis to a claim in Postgres."""
    store = ProvenanceStore(db_session)
    env_h = f"env_{uuid.uuid4().hex[:12]}"

    claim = store.record_claim(
        prompt="Sum of sales",
        model_name="mock-model",
        model_version="1.0.0",
        generated_code="result = float(df['sales'].sum())",
        original_result={"value": 500.0},
        data_snapshot_hash="data_hash_abc",
        env_hash=env_h,
    )
    db_session.flush()

    reexec = store.record_reexecution(
        claim_id=claim.claim_id,
        new_result={"value": 520.0},
        matched=False,
        diff_summary="Value drifted from 500.0 to 520.0 (+4.0%)",
    )
    db_session.flush()

    assert reexec.reexecution_id is not None
    assert reexec.matched is False

    diagnosis = store.record_drift_diagnosis(
        reexecution_id=reexec.reexecution_id,
        cause="data_change",
        confidence=0.95,
        evidence={"old_hash": "data_hash_abc", "new_hash": "data_hash_modified"},
    )
    db_session.flush()

    assert diagnosis.diagnosis_id is not None
    assert diagnosis.cause == "data_change"
    assert diagnosis.confidence == 0.95
