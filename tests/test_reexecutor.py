"""Integration tests for ClaimReexecutor, Comparator, and DriftDiagnoser."""

import pandas as pd
import pytest

from src.interceptor.capture import provenance_intercept
from src.interceptor.test_agent import MinimalDataScienceAgent
from src.reexecutor.reexecutor import ClaimReexecutor
from src.store.database import get_session, init_db
from src.store.repository import ProvenanceStore


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure schema is initialized before running tests."""
    init_db()


def test_reexecutor_reproduced():
    """Verify clean reproduction when data and environment are identical."""
    df = pd.DataFrame({"tenure": [1, 24, 60, 2, 48], "churn": [1, 0, 0, 1, 0]})
    agent = MinimalDataScienceAgent()

    with get_session() as session:
        store = ProvenanceStore(session)

        @provenance_intercept(prompt_arg="prompt", df_arg="df", store=store)
        def run_analysis(prompt: str, df: pd.DataFrame):
            return agent.analyze(df=df, prompt=prompt, seed=17)

        payload = run_analysis(prompt="Does tenure predict customer churn?", df=df)

    # Re-verify
    reexecutor = ClaimReexecutor()
    report = reexecutor.reverify(claim_id=payload.claim_id, df=df)

    assert report.matched is True
    assert report.status == "reproduced"
    assert report.diagnosis is None


def test_reexecutor_library_drift_diagnosis():
    """Verify drift diagnosis attributes cause to library_version_change."""
    df = pd.DataFrame({"tenure": [1, 24, 60, 2, 48], "churn": [1, 0, 0, 1, 0]})
    agent = MinimalDataScienceAgent()

    with get_session() as session:
        store = ProvenanceStore(session)

        @provenance_intercept(prompt_arg="prompt", df_arg="df", store=store)
        def run_analysis(prompt: str, df: pd.DataFrame):
            return agent.analyze(df=df, prompt=prompt, seed=17)

        payload = run_analysis(prompt="Does tenure predict customer churn?", df=df)

    # Modify data to cause numeric mismatch and override env packages to trigger library change diagnosis
    modified_df = df.copy()
    modified_df.loc[0, "tenure"] = 50

    reexecutor = ClaimReexecutor()
    report = reexecutor.reverify(
        claim_id=payload.claim_id,
        df=modified_df,
        override_env_packages={"pandas": "99.0.0", "numpy": "99.0.0"},
    )

    assert report.matched is False
    assert report.status == "failed"
    assert report.diagnosis is not None
    assert report.diagnosis.cause == "library_version_change"
    assert "pandas" in report.diagnosis.human_readable_cause
