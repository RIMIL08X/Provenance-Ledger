"""Re-execution engine implementing mechanics.md Section 4 with agent re-invocation & stress testing."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
import pandas as pd
from pydantic import BaseModel

from src.comparator.comparator import ResultComparator
from src.diagnoser.diagnoser import DiagnosisResult, DriftDiagnoser
from src.interceptor.capture import AgentClaimPayload
from src.interceptor.hashing import compute_data_snapshot_hash, compute_env_hash
from src.interceptor.test_agent import MinimalDataScienceAgent
from src.store.database import get_session
from src.store.models import Claim, EnvironmentSnapshot, ReexecutionResult, DriftDiagnosis
from src.store.repository import ProvenanceStore


class TrialOutcome(BaseModel):
    trial_index: int
    matched: bool
    result: Dict[str, Any]
    generated_code: Optional[str] = None
    diff_summary: str


class MultiTrialReport(BaseModel):
    total_trials: int
    matched_trials: int
    reproducibility_score: float  # 0.0 to 1.0
    status: str  # 'reproduced' | 'partial_drift' | 'failed'
    trials: List[TrialOutcome]


class ReexecutionReport(BaseModel):
    """Full execution report from re-verifying a claim."""

    claim_id: str
    matched: bool
    status: str  # 'reproduced' | 'failed'
    original_result: Dict[str, Any]
    new_result: Dict[str, Any]
    diff_summary: str
    diagnosis: Optional[DiagnosisResult] = None
    multi_trial_summary: Optional[MultiTrialReport] = None
    executed_at: datetime


class ClaimReexecutor:
    """Orchestrates loading recorded claims, re-executing them, comparing results, and diagnosing drift."""

    def __init__(
        self,
        store: Optional[ProvenanceStore] = None,
        comparator: Optional[ResultComparator] = None,
        diagnoser: Optional[DriftDiagnoser] = None,
    ) -> None:
        self.store = store
        self.comparator = comparator or ResultComparator()
        self.diagnoser = diagnoser or DriftDiagnoser()

    def _execute_code(self, code: str, df: pd.DataFrame) -> Dict[str, Any]:
        """Execute python code snippet in controlled namespace with DataFrame."""
        local_scope: Dict[str, Any] = {"df": df, "pd": pd}
        try:
            exec(code, {"pd": pd}, local_scope)
            res = local_scope.get("result")
        except Exception as e:
            res = {"error": f"Re-execution error: {str(e)}", "claim": f"Failed: {str(e)}"}

        if isinstance(res, (int, float)):
            return {"value": float(res), "claim": str(res)}
        elif isinstance(res, dict):
            return res
        return {"claim": str(res)}

    def reverify(
        self,
        claim_id: Union[uuid.UUID, str],
        df: pd.DataFrame,
        mode: str = "code_rerun",  # 'code_rerun' | 'agent_reinvocation' | 'stress_test'
        current_model_name: Optional[str] = None,
        current_model_version: Optional[str] = None,
        temperature: float = 0.0,
        num_trials: int = 1,
        override_env_packages: Optional[Dict[str, str]] = None,
    ) -> ReexecutionReport:
        """Re-verify a claim given its ID and input dataframe snapshot.

        Modes:
        - 'code_rerun': Deterministic re-run of stored code on dataframe.
        - 'agent_reinvocation': Re-invoke the LLM agent from scratch with same prompt & seed.
        - 'stress_test': Run multi-trial stochastic repetition (N trials) to compute reproducibility score.
        """
        uid = uuid.UUID(str(claim_id)) if isinstance(claim_id, str) else claim_id

        with get_session() as session:
            repo = ProvenanceStore(session)
            claim = repo.get_claim(uid)
            if not claim:
                raise ValueError(f"Claim with ID {claim_id} not found in store.")

            # Load original environment snapshot
            orig_snapshot = session.get(EnvironmentSnapshot, claim.env_hash)
            orig_packages = orig_snapshot.library_versions if orig_snapshot else {}

            # Current environment
            if override_env_packages is not None:
                curr_env_hash, curr_packages = compute_env_hash(override_env_packages)
            else:
                curr_env_hash, curr_packages = compute_env_hash()

            curr_data_hash = compute_data_snapshot_hash(df)
            curr_model_name = current_model_name or claim.model_name
            curr_model_version = current_model_version or claim.model_version

            multi_trial_report = None

            # -------------------------------------------------------------
            # Execution Strategy
            # -------------------------------------------------------------
            if mode == "agent_reinvocation":
                # Re-invoke agent from scratch
                agent = MinimalDataScienceAgent(model_name=curr_model_name, model_version=curr_model_version)
                payload = agent.analyze(df=df, prompt=claim.prompt, seed=claim.seed)
                new_result = payload.result
                matched, diff_summary = self.comparator.compare(claim.original_result, new_result)

            elif mode == "stress_test":
                # Multi-trial stochastic repetition
                agent = MinimalDataScienceAgent(model_name=curr_model_name, model_version=curr_model_version)
                trials: List[TrialOutcome] = []
                matched_count = 0

                for i in range(num_trials):
                    trial_seed = (claim.seed or 17) + i if temperature > 0 else (claim.seed or 17)
                    payload = agent.analyze(df=df, prompt=claim.prompt, seed=trial_seed)
                    t_matched, t_diff = self.comparator.compare(claim.original_result, payload.result)
                    if t_matched:
                        matched_count += 1
                    trials.append(TrialOutcome(
                        trial_index=i + 1,
                        matched=t_matched,
                        result=payload.result,
                        generated_code=payload.generated_code,
                        diff_summary=t_diff,
                    ))

                score = matched_count / num_trials if num_trials > 0 else 0.0
                multi_trial_report = MultiTrialReport(
                    total_trials=num_trials,
                    matched_trials=matched_count,
                    reproducibility_score=score,
                    status="reproduced" if score == 1.0 else ("partial_drift" if score > 0 else "failed"),
                    trials=trials,
                )
                matched = score >= 0.8
                new_result = trials[0].result
                diff_summary = f"Reproducibility Score: {score * 100:.0f}% ({matched_count}/{num_trials} trials matched baseline)"

            else:
                # Default 'code_rerun': re-run stored code directly
                new_result = self._execute_code(claim.generated_code, df)
                matched, diff_summary = self.comparator.compare(claim.original_result, new_result)

            # -------------------------------------------------------------
            # Diagnosis
            # -------------------------------------------------------------
            diagnosis_res: Optional[DiagnosisResult] = None
            if not matched:
                diagnosis_res = self.diagnoser.diagnose(
                    orig_model_name=claim.model_name,
                    orig_model_version=claim.model_version,
                    curr_model_name=curr_model_name,
                    curr_model_version=curr_model_version,
                    orig_env_hash=claim.env_hash,
                    orig_packages=orig_packages,
                    curr_env_hash=curr_env_hash,
                    curr_packages=curr_packages,
                    orig_data_hash=claim.data_snapshot_hash,
                    curr_data_hash=curr_data_hash,
                )
                if diagnosis_res:
                    diff_summary = f"{diff_summary}. Cause: {diagnosis_res.human_readable_cause}"

            # -------------------------------------------------------------
            # Persistence
            # -------------------------------------------------------------
            now = datetime.now(timezone.utc)
            reexec = repo.record_reexecution(
                claim_id=claim.claim_id,
                new_result=new_result,
                matched=matched,
                diff_summary=diff_summary,
                executed_at=now,
            )

            if diagnosis_res:
                repo.record_drift_diagnosis(
                    reexecution_id=reexec.reexecution_id,
                    cause=diagnosis_res.cause,
                    confidence=diagnosis_res.confidence,
                    evidence=diagnosis_res.evidence,
                )

            claim.status = "reproduced" if matched else "failed"
            session.flush()

            return ReexecutionReport(
                claim_id=str(claim.claim_id),
                matched=matched,
                status=claim.status,
                original_result=claim.original_result,
                new_result=new_result,
                diff_summary=diff_summary,
                diagnosis=diagnosis_res,
                multi_trial_summary=multi_trial_report,
                executed_at=now,
            )
