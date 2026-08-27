"""Integration tests for the FastAPI service endpoints with multi-format uploads, Gemini, and rich audit modes."""

import io
import pytest
from starlette.testclient import TestClient
from src.api import app
from src.store.database import init_db


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_get_models_endpoint(client):
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert "gemini-1.5-flash" in data["models"]


def test_upload_file_endpoint(client):
    csv_bytes = b"user_id,revenue\n101,500.0\n102,750.0\n103,1200.0\n"
    files = {"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "data_hash" in data
    assert data["summary"]["total_rows"] == 3


def test_analyze_and_rich_audit_modes(client):
    # 0. Upload test dataset
    csv_bytes = b"tenure,churn\n1,1\n24,0\n60,0\n2,1\n48,0\n12,1\n70,0\n6,1\n"
    files = {"file": ("customer_churn.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post("/api/upload", files=files)
    assert upload_res.status_code == 200
    data_hash = upload_res.json()["data_hash"]

    # 1. Analyze
    analyze_res = client.post(
        "/api/analyze",
        json={
            "prompt": "What is the correlation between tenure and churn?",
            "model_name": "gemini-1.5-flash",
            "seed": 17,
            "data_hash": data_hash,
        },
    )
    assert analyze_res.status_code == 200
    claim_data = analyze_res.json()
    assert "claim_id" in claim_data
    claim_id = claim_data["claim_id"]

    # 2. Exact Code Rerun
    reverify_exact = client.post(
        "/api/reverify",
        json={"claim_id": claim_id, "audit_mode": "exact_code_rerun"},
    )
    assert reverify_exact.status_code == 200
    assert reverify_exact.json()["matched"] is True

    # 3. Model Re-invocation
    reverify_agent = client.post(
        "/api/reverify",
        json={"claim_id": claim_id, "audit_mode": "agent_reinvocation_same_seed"},
    )
    assert reverify_agent.status_code == 200

    # 4. Multi-Trial Stress Test
    reverify_stress = client.post(
        "/api/reverify",
        json={"claim_id": claim_id, "audit_mode": "batch_consistency_test"},
    )
    assert reverify_stress.status_code == 200
    stress_data = reverify_stress.json()
    assert "multi_trial_summary" in stress_data
    assert stress_data["multi_trial_summary"]["total_trials"] == 5

    # 5. Simulated Library Drift
    reverify_lib_drift = client.post(
        "/api/reverify",
        json={"claim_id": claim_id, "audit_mode": "simulated_library_drift"},
    )
    assert reverify_lib_drift.status_code == 200
    drift_data = reverify_lib_drift.json()
    assert drift_data["matched"] is False
    assert drift_data["diagnosis"]["cause"] == "library_version_change"


def test_serve_spa_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Provenance Ledger" in res.text
