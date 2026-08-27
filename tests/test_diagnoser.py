"""Unit tests for the DriftDiagnoser decision logic."""

import pytest
from src.diagnoser.diagnoser import DriftDiagnoser


def test_diagnose_model_version_change():
    diagnoser = DriftDiagnoser()
    res = diagnoser.diagnose(
        orig_model_name="llama3.2:1b",
        orig_model_version="1.0",
        curr_model_name="llama3.2:3b",
        curr_model_version="1.0",
        orig_env_hash="env1",
        orig_packages={"pandas": "2.2.0"},
        curr_env_hash="env1",
        curr_packages={"pandas": "2.2.0"},
        orig_data_hash="data1",
        curr_data_hash="data1",
    )
    assert res.cause == "model_version_change"
    assert "llama3.2:3b" in res.human_readable_cause


def test_diagnose_library_version_change():
    diagnoser = DriftDiagnoser()
    res = diagnoser.diagnose(
        orig_model_name="llama3.2:1b",
        orig_model_version="1.0",
        curr_model_name="llama3.2:1b",
        curr_model_version="1.0",
        orig_env_hash="env_old",
        orig_packages={"pandas": "2.1.0"},
        curr_env_hash="env_new",
        curr_packages={"pandas": "2.2.0"},
        orig_data_hash="data1",
        curr_data_hash="data1",
    )
    assert res.cause == "library_version_change"
    assert "pandas 2.1.0 to 2.2.0" in res.human_readable_cause


def test_diagnose_data_change():
    diagnoser = DriftDiagnoser()
    res = diagnoser.diagnose(
        orig_model_name="llama3.2:1b",
        orig_model_version="1.0",
        curr_model_name="llama3.2:1b",
        curr_model_version="1.0",
        orig_env_hash="env1",
        orig_packages={"pandas": "2.2.0"},
        curr_env_hash="env1",
        curr_packages={"pandas": "2.2.0"},
        orig_data_hash="data_hash_old",
        curr_data_hash="data_hash_new",
    )
    assert res.cause == "data_change"


def test_diagnose_stochastic_variation():
    diagnoser = DriftDiagnoser()
    res = diagnoser.diagnose(
        orig_model_name="llama3.2:1b",
        orig_model_version="1.0",
        curr_model_name="llama3.2:1b",
        curr_model_version="1.0",
        orig_env_hash="env1",
        orig_packages={"pandas": "2.2.0"},
        curr_env_hash="env1",
        curr_packages={"pandas": "2.2.0"},
        orig_data_hash="data1",
        curr_data_hash="data1",
    )
    assert res.cause == "stochastic_variation"
