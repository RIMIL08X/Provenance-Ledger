"""Provenance Interceptor: Wraps agent execution and captures audit metadata."""

from datetime import datetime, timezone
import functools
import inspect
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, Union
import uuid

import pandas as pd
from pydantic import BaseModel, Field

from src.interceptor.hashing import compute_data_snapshot_hash, compute_env_hash
from src.store.database import get_session
from src.store.models import Claim
from src.store.repository import ProvenanceStore, sanitize_for_json


class AgentClaimPayload(BaseModel):
    """Normalized payload produced by an agent execution."""

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    prompt: str
    model_name: str
    model_version: str
    generated_code: str
    result: Dict[str, Any]
    seed: Optional[int] = None
    input_dataframe: Optional[Any] = None
    claim_id: Optional[str] = None


class ProvenanceCaptureContext:
    """Context manager for capturing provenance metadata around an agent run."""

    def __init__(
        self,
        prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        seed: Optional[int] = None,
        dataframe: Optional[pd.DataFrame] = None,
        store: Optional[ProvenanceStore] = None,
    ) -> None:
        self.prompt = prompt
        self.model_name = model_name
        self.model_version = model_version
        self.seed = seed
        self.dataframe = dataframe
        self.store = store

        self.generated_code: Optional[str] = None
        self.original_result: Optional[Dict[str, Any]] = None
        self.recorded_claim: Optional[Claim] = None

    def __enter__(self) -> "ProvenanceCaptureContext":
        return self

    def record(
        self,
        prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        generated_code: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        dataframe: Optional[pd.DataFrame] = None,
    ) -> Claim:
        """Capture and commit provenance metadata to the store."""
        prompt = prompt or self.prompt or ""
        model_name = model_name or self.model_name or "unknown_model"
        model_version = model_version or self.model_version or "unknown_version"
        seed = seed if seed is not None else self.seed
        generated_code = generated_code or self.generated_code or ""
        result = sanitize_for_json(result or self.original_result or {})
        df = dataframe if dataframe is not None else self.dataframe

        # Compute data and environment fingerprints
        data_hash = compute_data_snapshot_hash(df) if df is not None else ""
        env_hash, packages = compute_env_hash()

        # TODO: adapt to actual agent framework (e.g. LangChain, CrewAI, AutoGen callback hooks)

        if self.store is not None:
            self.recorded_claim = self.store.record_claim(
                prompt=prompt,
                model_name=model_name,
                model_version=model_version,
                seed=seed,
                generated_code=generated_code,
                original_result=result,
                data_snapshot_hash=data_hash,
                env_hash=env_hash,
                library_versions=packages,
            )
        else:
            with get_session() as session:
                store = ProvenanceStore(session)
                self.recorded_claim = store.record_claim(
                    prompt=prompt,
                    model_name=model_name,
                    model_version=model_version,
                    seed=seed,
                    generated_code=generated_code,
                    original_result=result,
                    data_snapshot_hash=data_hash,
                    env_hash=env_hash,
                    library_versions=packages,
                )

        return self.recorded_claim

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


F = TypeVar("F", bound=Callable[..., Any])


def provenance_intercept(
    prompt_arg: str = "prompt",
    df_arg: str = "df",
    store: Optional[ProvenanceStore] = None,
) -> Callable[[F], F]:
    """Decorator to intercept agent claim-producing functions and log provenance.

    Expects the wrapped function to return either an `AgentClaimPayload` or a tuple/dict
    containing generated_code, result, model_name, model_version, and optional seed.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Bind arguments to extract input prompt and dataframe
            sig = inspect.signature(fn)
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            prompt_val = bound.arguments.get(prompt_arg, "")
            df_val = bound.arguments.get(df_arg, None)

            # If df wasn't found by name, scan positional args for DataFrame
            if df_val is None:
                for arg in args:
                    if isinstance(arg, pd.DataFrame):
                        df_val = arg
                        break

            # Execute agent call
            output = fn(*args, **kwargs)

            # TODO: adapt to actual agent framework
            # Extract metadata from agent return value
            if isinstance(output, AgentClaimPayload):
                p = output.prompt or prompt_val
                m_name = output.model_name
                m_ver = output.model_version
                g_code = output.generated_code
                res = sanitize_for_json(output.result)
                s = output.seed
                if output.input_dataframe is not None:
                    df_val = output.input_dataframe
            elif isinstance(output, dict):
                p = output.get("prompt", prompt_val)
                m_name = output.get("model_name", "agent-default")
                m_ver = output.get("model_version", "1.0")
                g_code = output.get("generated_code", "")
                res = sanitize_for_json(output.get("result", output))
                s = output.get("seed", None)
            else:
                # Basic fallback
                p = str(prompt_val)
                m_name = "custom-agent"
                m_ver = "1.0"
                g_code = getattr(output, "generated_code", "")
                res = {"output": str(output)}
                s = None

            # Calculate hashes
            data_hash = compute_data_snapshot_hash(df_val) if isinstance(df_val, pd.DataFrame) else ""
            env_hash, packages = compute_env_hash()

            claim_id_str: str = ""
            # Persist claim
            if store is not None:
                claim = store.record_claim(
                    prompt=p,
                    model_name=m_name,
                    model_version=m_ver,
                    seed=s,
                    generated_code=g_code,
                    original_result=res,
                    data_snapshot_hash=data_hash,
                    env_hash=env_hash,
                    library_versions=packages,
                )
                claim_id_str = str(claim.claim_id)
            else:
                with get_session() as session:
                    repo = ProvenanceStore(session)
                    claim = repo.record_claim(
                        prompt=p,
                        model_name=m_name,
                        model_version=m_ver,
                        seed=s,
                        generated_code=g_code,
                        original_result=res,
                        data_snapshot_hash=data_hash,
                        env_hash=env_hash,
                        library_versions=packages,
                    )
                    claim_id_str = str(claim.claim_id)

            # Attach recorded claim_id to output if it's a dict or object
            if isinstance(output, dict):
                output["claim_id"] = claim_id_str
            elif isinstance(output, AgentClaimPayload):
                output.claim_id = claim_id_str

            return output

        return wrapper  # type: ignore

    return decorator
