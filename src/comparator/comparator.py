"""Result comparison engine implementing mechanics.md Section 5."""

import math
from typing import Any, Dict, Tuple


class ResultComparator:
    """Compares original claim results against newly re-executed results."""

    def __init__(self, numeric_tolerance: float = 0.01) -> None:
        """Args:

        numeric_tolerance: Maximum allowable relative difference (default 1% /
        0.01).
        """
        self.numeric_tolerance = numeric_tolerance

    def _compare_numbers(self, orig_val: float, new_val: float) -> Tuple[bool, str]:
        """Compare two numbers under relative tolerance."""
        if math.isnan(orig_val) and math.isnan(new_val):
            return True, "Both values are NaN"

        if orig_val == 0.0:
            abs_diff = abs(new_val - orig_val)
            matched = abs_diff <= self.numeric_tolerance
            diff_pct = abs_diff * 100
        else:
            rel_diff = abs(new_val - orig_val) / abs(orig_val)
            matched = rel_diff <= self.numeric_tolerance
            diff_pct = rel_diff * 100

        if matched:
            return True, f"Numeric values matched within tolerance (drift: {diff_pct:.2f}%)"
        else:
            return False, f"Value drifted from {orig_val:.4g} to {new_val:.4g} (diff: {diff_pct:.1f}%)"

    def compare(
        self,
        original_result: Dict[str, Any],
        new_result: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Compare original claim result with newly re-executed result.

        Returns:
            (matched: bool, diff_summary: str)
        """
        if original_result == new_result:
            return True, "Identical results"

        # Check for correlation 'r'
        if "r" in original_result and "r" in new_result:
            try:
                orig_r = float(original_result["r"])
                new_r = float(new_result["r"])
                matched, _ = self._compare_numbers(orig_r, new_r)
                if matched:
                    return True, f"Correlation matched (r = {new_r})"
                else:
                    return False, f"New result: r = {new_r:.2f}"
            except (ValueError, TypeError):
                pass

        # Check for numeric 'value'
        if "value" in original_result and "value" in new_result:
            try:
                orig_v = float(original_result["value"])
                new_v = float(new_result["value"])
                matched, num_summary = self._compare_numbers(orig_v, new_v)
                if matched:
                    return True, num_summary
                else:
                    return False, f"New result: {new_v:.4g}. {num_summary}"
            except (ValueError, TypeError):
                pass

        # Check top-level numeric scalar dicts
        for key in original_result:
            if key in new_result:
                val_orig = original_result[key]
                val_new = new_result[key]
                if isinstance(val_orig, (int, float)) and isinstance(val_new, (int, float)):
                    matched, num_summary = self._compare_numbers(float(val_orig), float(val_new))
                    if not matched:
                        return False, f"New result: {key} = {val_new:.4g}. {num_summary}"

        # Text conclusion comparison
        orig_claim = str(original_result.get("claim", original_result.get("conclusion", ""))).strip()
        new_claim = str(new_result.get("claim", new_result.get("conclusion", ""))).strip()

        if orig_claim and new_claim:
            if orig_claim == new_claim:
                return True, "Conclusions identical"
            return False, f"New conclusion: '{new_claim}' (was: '{orig_claim}')"

        return False, f"New result: {new_result} (was: {original_result})"
