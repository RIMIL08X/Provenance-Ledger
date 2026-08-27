"""Drift diagnosis engine implementing mechanics.md Section 6."""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel


class DiagnosisResult(BaseModel):
    """Diagnosed root cause for a reproducibility failure."""

    cause: str  # 'model_version_change' | 'library_version_change' | 'data_change' | 'stochastic_variation' | 'unknown'
    confidence: float
    evidence: Dict[str, Any]
    human_readable_cause: str


class DriftDiagnoser:
    """Diagnoses the root cause of why a claim failed to reproduce."""

    def diagnose(
        self,
        orig_model_name: str,
        orig_model_version: str,
        curr_model_name: str,
        curr_model_version: str,
        orig_env_hash: str,
        orig_packages: Optional[Dict[str, str]],
        curr_env_hash: str,
        curr_packages: Optional[Dict[str, str]],
        orig_data_hash: str,
        curr_data_hash: str,
    ) -> DiagnosisResult:
        """Walks the decision tree in exact specification order and stops at the first cause found."""

        # 1. Model Version Change
        if (orig_model_name != curr_model_name) or (orig_model_version != curr_model_version):
            evidence = {
                "original_model": f"{orig_model_name}:{orig_model_version}",
                "current_model": f"{curr_model_name}:{curr_model_version}",
            }
            return DiagnosisResult(
                cause="model_version_change",
                confidence=1.0,
                evidence=evidence,
                human_readable_cause=f"model version change ({orig_model_name}:{orig_model_version} to {curr_model_name}:{curr_model_version})",
            )

        # 2. Library Version Change (Environment Drift)
        if orig_env_hash != curr_env_hash:
            pkg_diffs: Dict[str, Dict[str, str]] = {}
            p_orig = orig_packages or {}
            p_curr = curr_packages or {}

            all_pkgs = set(p_orig.keys()).union(set(p_curr.keys()))
            for pkg in sorted(all_pkgs):
                v_old = p_orig.get(pkg)
                v_new = p_curr.get(pkg)
                if v_old != v_new:
                    pkg_diffs[pkg] = {"original": v_old or "missing", "current": v_new or "missing"}

            # Build human readable summary for key data science packages
            key_diff_strings = []
            for pkg, diff in pkg_diffs.items():
                if pkg in ("pandas", "numpy", "scikit-learn", "scipy", "statsmodels", "torch", "transformers"):
                    key_diff_strings.append(f"{pkg} {diff['original']} to {diff['current']}")

            if not key_diff_strings and pkg_diffs:
                # Take first 2 packages as example
                sample_pkgs = list(pkg_diffs.items())[:2]
                key_diff_strings = [f"{p} {d['original']} to {d['current']}" for p, d in sample_pkgs]

            summary_str = ", ".join(key_diff_strings) if key_diff_strings else "dependencies changed"

            return DiagnosisResult(
                cause="library_version_change",
                confidence=0.95,
                evidence={"diffs": pkg_diffs, "orig_env_hash": orig_env_hash, "curr_env_hash": curr_env_hash},
                human_readable_cause=f"library version change ({summary_str})",
            )

        # 3. Data Change
        if orig_data_hash != curr_data_hash:
            evidence = {
                "original_data_hash": orig_data_hash,
                "current_data_hash": curr_data_hash,
            }
            return DiagnosisResult(
                cause="data_change",
                confidence=0.95,
                evidence=evidence,
                human_readable_cause=f"data change (snapshot hash altered from {orig_data_hash[:6]}... to {curr_data_hash[:6]}...)",
            )

        # 4. Stochastic Variation (Everything external is identical, but output diverged)
        if (
            orig_model_name == curr_model_name
            and orig_model_version == curr_model_version
            and orig_env_hash == curr_env_hash
            and orig_data_hash == curr_data_hash
        ):
            return DiagnosisResult(
                cause="stochastic_variation",
                confidence=0.90,
                evidence={"status": "all_inputs_and_environment_identical"},
                human_readable_cause="stochastic variation (inherent model non-determinism)",
            )

        # 5. Unknown
        return DiagnosisResult(
            cause="unknown",
            confidence=0.30,
            evidence={"reason": "unverifiable_or_unresolved_inputs"},
            human_readable_cause="unknown cause",
        )
