"""Deterministic hashing utilities for data snapshots and execution environments."""

import hashlib
import importlib.metadata
import re
from typing import Dict, Tuple
import pandas as pd


def canonical_serialize_dataframe(df: pd.DataFrame) -> bytes:
    """Canonicalize and serialize a pandas DataFrame to bytes.

    Sorting column names and standardizing float precision ensures identical
    data produces identical bytes regardless of in-memory column ordering or
    platform float representation subtleties.
    """
    if df is None:
        return b""

    # Work on a shallow copy
    df_copy = df.copy()

    # Sort columns alphabetically by name
    sorted_cols = sorted(df_copy.columns, key=lambda col: str(col))
    df_sorted = df_copy[sorted_cols]

    # Convert to CSV representation with fixed float formatting
    csv_str = df_sorted.to_csv(
        index=False,
        float_format="%.8g",
        date_format="%Y-%m-%dT%H:%M:%SZ",
        lineterminator="\n",
    )
    return csv_str.encode("utf-8")


def compute_data_snapshot_hash(df: pd.DataFrame) -> str:
    """Compute SHA-256 hash of a canonicalized pandas DataFrame."""
    canonical_bytes = canonical_serialize_dataframe(df)
    return hashlib.sha256(canonical_bytes).hexdigest()


def get_environment_packages() -> Dict[str, str]:
    """Extract installed packages and their versions sorted by package name."""
    packages: Dict[str, str] = {}
    try:
        for dist in importlib.metadata.distributions():
            name = dist.metadata["Name"]
            version = dist.metadata["Version"]
            if name:
                packages[name.lower()] = version
    except Exception:
        # Fallback if metadata is unavailable
        pass
    return dict(sorted(packages.items()))


def compute_env_hash(
    packages: Dict[str, str] | None = None,
) -> Tuple[str, Dict[str, str]]:
    """Compute SHA-256 hash of sorted environment package fingerprints.

    Returns:
        (env_hash, library_versions_dict)
    """
    if packages is None:
        packages = get_environment_packages()

    # Sort lines deterministically: "package==version\n"
    sorted_lines = [f"{pkg}=={ver}\n" for pkg, ver in sorted(packages.items())]
    raw_env_str = "".join(sorted_lines)
    env_hash = hashlib.sha256(raw_env_str.encode("utf-8")).hexdigest()

    return env_hash, packages
