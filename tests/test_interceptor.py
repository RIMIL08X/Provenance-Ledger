"""Unit tests for the Provenance Interceptor and Minimal Test Agent against PostgreSQL."""

import pandas as pd
import pytest

from src.interceptor.capture import (
    AgentClaimPayload,
    ProvenanceCaptureContext,
    provenance_intercept,
)
from src.interceptor.test_agent import MinimalDataScienceAgent
from src.store.database import get_session, init_db
from src.store.models import Claim
from src.store.repository import ProvenanceStore


@pytest.fixture(autouse=True)
def ensure_db():
    """Ensure database schema is created."""
    init_db()


def test_minimal_test_agent_execution():
    """Verify MinimalDataScienceAgent executes basic analysis on a DataFrame."""
    df = pd.DataFrame({"sales": [10.0, 20.0, 30.0], "region": ["A", "B", "C"]})
    agent = MinimalDataScienceAgent()

    payload = agent.analyze(df=df, prompt="Calculate the mean of sales", seed=42)

    assert isinstance(payload, AgentClaimPayload)
    assert payload.generated_code != ""
    assert isinstance(payload.result, dict)


def test_interceptor_decorator_with_store():
    """Verify @provenance_intercept records a claim row in PostgreSQL."""
    with get_session() as session:
        store = ProvenanceStore(session)

        @provenance_intercept(prompt_arg="prompt", df_arg="df", store=store)
        def run_agent_task(prompt: str, df: pd.DataFrame):
            return AgentClaimPayload(
                prompt=prompt,
                model_name="mock-model",
                model_version="1.0",
                generated_code="result = {'value': float(df['value'].sum())}",
                result={"value": float(df["value"].sum())},
                seed=123,
                input_dataframe=df,
            )

        test_df = pd.DataFrame({"value": [100.0, 200.0, 300.0]})
        result = run_agent_task(prompt="Calculate the sum of value", df=test_df)

    assert result.result["value"] == 600.0
    assert result.claim_id is not None

    with get_session() as session:
        store = ProvenanceStore(session)
        claim = store.get_claim(result.claim_id)
        assert claim is not None
        assert claim.prompt == "Calculate the sum of value"
        assert claim.seed == 123
        assert claim.original_result["value"] == 600.0
        assert len(claim.data_snapshot_hash) == 64
        assert len(claim.env_hash) == 64


def test_provenance_capture_context():
    """Verify ProvenanceCaptureContext manually logs execution details."""
    df = pd.DataFrame({"col": [1, 2, 3]})

    with get_session() as session:
        store = ProvenanceStore(session)
        with ProvenanceCaptureContext(
            prompt="Find maximum",
            model_name="custom-model",
            model_version="2.0",
            seed=77,
            dataframe=df,
            store=store,
        ) as ctx:
            claim = ctx.record(
                generated_code="result = {'value': float(df['col'].max())}",
                result={"value": 3.0},
            )

    assert claim is not None
    assert claim.prompt == "Find maximum"
    assert claim.model_name == "custom-model"
    assert claim.original_result["value"] == 3.0
