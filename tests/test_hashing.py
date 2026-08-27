"""Tests for data snapshot and environment hashing."""

import pandas as pd
import pytest

from src.interceptor.hashing import (
    canonical_serialize_dataframe,
    compute_data_snapshot_hash,
    compute_env_hash,
    get_environment_packages,
)


def test_dataframe_hash_invariance_to_column_order():
    """DataFrame hashing must yield identical hashes regardless of column order."""
    df1 = pd.DataFrame({"col_a": [1.0, 2.5, 3.0], "col_b": [10, 20, 30]})
    df2 = pd.DataFrame({"col_b": [10, 20, 30], "col_a": [1.0, 2.5, 3.0]})

    hash1 = compute_data_snapshot_hash(df1)
    hash2 = compute_data_snapshot_hash(df2)

    assert hash1 == hash2, "DataFrame hashes should match regardless of column ordering"
    assert len(hash1) == 64  # SHA-256 length


def test_dataframe_hash_sensitivity_to_data_changes():
    """DataFrame hashing must yield different hashes when values change."""
    df1 = pd.DataFrame({"col_a": [1.0, 2.0, 3.0]})
    df2 = pd.DataFrame({"col_a": [1.0, 2.0, 3.0001]})

    hash1 = compute_data_snapshot_hash(df1)
    hash2 = compute_data_snapshot_hash(df2)

    assert hash1 != hash2, "DataFrame hashes should differ when cell values differ"


def test_dataframe_hash_empty_and_none():
    """Verify handling of empty or None DataFrame."""
    assert compute_data_snapshot_hash(None) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # sha256("")


def test_environment_hash_determinism():
    """Environment hashing must be deterministic for identical package dictionaries."""
    packages_a = {"pandas": "2.2.0", "numpy": "1.26.0", "scikit-learn": "1.5.0"}
    packages_b = {"scikit-learn": "1.5.0", "pandas": "2.2.0", "numpy": "1.26.0"}

    hash_a, _ = compute_env_hash(packages_a)
    hash_b, _ = compute_env_hash(packages_b)

    assert hash_a == hash_b, "Env hashes must be identical regardless of dictionary key insertion order"
    assert len(hash_a) == 64


def test_get_environment_packages_live():
    """Live environment package extraction returns non-empty sorted dictionary."""
    pkgs = get_environment_packages()
    assert isinstance(pkgs, dict)
    assert len(pkgs) > 0
    assert "pandas" in pkgs or "sqlalchemy" in pkgs

    env_hash, live_pkgs = compute_env_hash()
    assert len(env_hash) == 64
    assert live_pkgs == pkgs
