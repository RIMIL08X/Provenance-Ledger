"""Unit tests for the ResultComparator."""

import pytest
from src.comparator.comparator import ResultComparator


def test_comparator_identical_results():
    comp = ResultComparator()
    orig = {"r": -0.42, "claim": "Tenure is negatively correlated with churn (r = -0.42)"}
    new_res = {"r": -0.42, "claim": "Tenure is negatively correlated with churn (r = -0.42)"}

    matched, diff_summary = comp.compare(orig, new_res)
    assert matched is True
    assert "Identical" in diff_summary or "matched" in diff_summary


def test_comparator_numeric_drift():
    comp = ResultComparator(numeric_tolerance=0.01)  # 1% tolerance
    orig = {"r": -0.42, "claim": "Tenure is negatively correlated with churn (r = -0.42)"}
    new_res = {"r": -0.31, "claim": "Tenure is negatively correlated with churn (r = -0.31)"}

    matched, diff_summary = comp.compare(orig, new_res)
    assert matched is False
    assert "-0.31" in diff_summary


def test_comparator_within_tolerance():
    comp = ResultComparator(numeric_tolerance=0.05)  # 5% tolerance
    orig = {"value": 100.0}
    new_res = {"value": 102.0}  # 2% difference

    matched, diff_summary = comp.compare(orig, new_res)
    assert matched is True
    assert "matched within tolerance" in diff_summary
