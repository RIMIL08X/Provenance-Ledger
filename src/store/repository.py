"""Data Access Layer for Provenance Ledger strictly with PostgreSQL."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid
import numpy as np
import pandas as pd

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.store.models import Claim, DriftDiagnosis, EnvironmentSnapshot, ReexecutionResult


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert numpy/pandas types to native Python JSON-serializable types."""
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return [sanitize_for_json(x) for x in obj.tolist()]
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, (datetime,)):
        return obj.isoformat()
    elif pd.isna(obj):
        return None
    return obj


class ProvenanceStore:
    """Repository class for persisting and querying provenance data in PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_environment_snapshot(
        self,
        env_hash: str,
        library_versions: Dict[str, str],
        captured_at: Optional[datetime] = None,
    ) -> EnvironmentSnapshot:
        """Upsert an environment snapshot if env_hash is not present."""
        existing = self.session.get(EnvironmentSnapshot, env_hash)
        if existing:
            return existing

        snapshot = EnvironmentSnapshot(
            env_hash=env_hash,
            captured_at=captured_at or datetime.now(timezone.utc),
            library_versions=sanitize_for_json(library_versions),
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def record_claim(
        self,
        prompt: str,
        model_name: str,
        model_version: str,
        generated_code: str,
        original_result: Dict[str, Any],
        data_snapshot_hash: str,
        env_hash: str,
        seed: Optional[int] = None,
        claim_id: Optional[Union[uuid.UUID, str]] = None,
        created_at: Optional[datetime] = None,
        status: str = "unverified",
        library_versions: Optional[Dict[str, str]] = None,
    ) -> Claim:
        """Record a newly captured claim and ensure its environment snapshot exists in PostgreSQL."""
        if library_versions is not None:
            self.upsert_environment_snapshot(
                env_hash=env_hash,
                library_versions=library_versions,
                captured_at=created_at,
            )

        if isinstance(claim_id, str):
            cid = uuid.UUID(claim_id)
        elif isinstance(claim_id, uuid.UUID):
            cid = claim_id
        else:
            cid = uuid.uuid4()

        claim = Claim(
            claim_id=cid,
            created_at=created_at or datetime.now(timezone.utc),
            prompt=prompt,
            model_name=model_name,
            model_version=model_version,
            seed=seed,
            generated_code=generated_code,
            original_result=sanitize_for_json(original_result),
            data_snapshot_hash=data_snapshot_hash,
            env_hash=env_hash,
            status=status,
        )
        self.session.add(claim)
        self.session.flush()
        return claim

    def get_claim(self, claim_id: Union[uuid.UUID, str]) -> Optional[Claim]:
        """Fetch a claim by UUID or string ID."""
        uid = uuid.UUID(str(claim_id)) if isinstance(claim_id, str) else claim_id
        return self.session.get(Claim, uid)

    def list_claims(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Claim]:
        """List claims with optional status filtering."""
        stmt = select(Claim).order_by(Claim.created_at.desc())
        if status:
            stmt = stmt.where(Claim.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def record_reexecution(
        self,
        claim_id: Union[uuid.UUID, str],
        new_result: Dict[str, Any],
        matched: bool,
        diff_summary: Optional[str] = None,
        reexecution_id: Optional[Union[uuid.UUID, str]] = None,
        executed_at: Optional[datetime] = None,
    ) -> ReexecutionResult:
        """Record a re-execution attempt for a claim."""
        cid = uuid.UUID(str(claim_id)) if isinstance(claim_id, str) else claim_id
        rid = uuid.UUID(str(reexecution_id)) if isinstance(reexecution_id, str) else (reexecution_id or uuid.uuid4())

        result = ReexecutionResult(
            reexecution_id=rid,
            claim_id=cid,
            executed_at=executed_at or datetime.now(timezone.utc),
            new_result=sanitize_for_json(new_result),
            matched=matched,
            diff_summary=diff_summary,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def record_drift_diagnosis(
        self,
        reexecution_id: Union[uuid.UUID, str],
        cause: str,
        confidence: Optional[float] = None,
        evidence: Optional[Dict[str, Any]] = None,
        diagnosis_id: Optional[Union[uuid.UUID, str]] = None,
    ) -> DriftDiagnosis:
        """Record a drift diagnosis for a mismatched re-execution."""
        rid = uuid.UUID(str(reexecution_id)) if isinstance(reexecution_id, str) else reexecution_id
        did = uuid.UUID(str(diagnosis_id)) if isinstance(diagnosis_id, str) else (diagnosis_id or uuid.uuid4())

        diagnosis = DriftDiagnosis(
            diagnosis_id=did,
            reexecution_id=rid,
            cause=cause,
            confidence=confidence,
            evidence=sanitize_for_json(evidence) if evidence else None,
        )
        self.session.add(diagnosis)
        self.session.flush()
        return diagnosis
