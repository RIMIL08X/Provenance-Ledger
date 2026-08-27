"""FastAPI backend service supporting multi-format data ingestion, Gemini reasoning, and rich audit modes."""

from contextlib import asynccontextmanager
import os
import sys
from typing import Any, Dict, List, Optional
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.interceptor.capture import provenance_intercept
from src.interceptor.gemini_client import GeminiClient
from src.interceptor.hashing import compute_env_hash
from src.interceptor.test_agent import MinimalDataScienceAgent
from src.parser.data_parser import DataIngestionEngine
from src.reexecutor.reexecutor import ClaimReexecutor, ReexecutionReport
from src.store.database import get_database_url, get_engine, get_session, init_db
from src.store.models import EnvironmentSnapshot
from src.store.repository import ProvenanceStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database schema is initialized on server start."""
    init_db()
    yield


app = FastAPI(title="Provenance Ledger API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for active session datasets
ACTIVE_DATASETS: Dict[str, pd.DataFrame] = {}


class AnalyzeRequest(BaseModel):
    prompt: str
    model_name: str = "gemini-1.5-flash"
    seed: int = 17
    data_hash: str


class ReverifyRequest(BaseModel):
    claim_id: str
    audit_mode: str = "exact_code_rerun"


@app.get("/api/models")
def get_available_models():
    """List available Gemini Cloud models and check API key status."""
    client = GeminiClient()
    return {
        "models": client.AVAILABLE_MODELS,
        "active_provider": "Google Gemini",
        "is_configured": client.is_available(),
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and parse arbitrary data files (.csv, .xlsx, .pdf, .docx, .json, .parquet)."""
    try:
        content = await file.read()
        df, summary, data_hash = DataIngestionEngine.parse_file(content, file.filename)
        ACTIVE_DATASETS[data_hash] = df
        return {
            "success": True,
            "data_hash": data_hash,
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File parsing error: {str(e)}")


@app.get("/api/dataset")
def get_dataset(data_hash: Optional[str] = None):
    """Return dataset preview by hash."""
    if not data_hash:
        return {"columns": [], "records": [], "total_rows": 0}

    if data_hash in ACTIVE_DATASETS:
        df = ACTIVE_DATASETS[data_hash]
    else:
        df = DataIngestionEngine.load_snapshot(data_hash)
        if df is None:
            raise HTTPException(status_code=404, detail="Dataset snapshot not found")

    return {
        "columns": list(df.columns),
        "records": df.head(15).to_dict(orient="records"),
        "total_rows": len(df),
    }


@app.post("/api/analyze")
def run_analysis(req: AnalyzeRequest):
    """Run data science agent on uploaded dataset with provenance interception."""
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    if not req.data_hash:
        raise HTTPException(status_code=400, detail="No dataset provided. Please upload a dataset or document first.")

    if req.data_hash in ACTIVE_DATASETS:
        target_df = ACTIVE_DATASETS[req.data_hash]
    else:
        target_df = DataIngestionEngine.load_snapshot(req.data_hash)
        if target_df is None:
            raise HTTPException(status_code=400, detail="Dataset snapshot not found. Please upload your file first.")

    agent = MinimalDataScienceAgent(
        model_name=req.model_name,
        model_version="1.5",
    )

    with get_session() as session:
        store = ProvenanceStore(session)

        @provenance_intercept(prompt_arg="prompt", df_arg="df", store=store)
        def _execute(prompt: str, df: pd.DataFrame, seed: int):
            return agent.analyze(df=df, prompt=prompt, seed=seed)

        payload = _execute(prompt=req.prompt, df=target_df, seed=req.seed)
        session.commit()

        claim = store.get_claim(payload.claim_id)
        if not claim:
            raise HTTPException(status_code=500, detail="Failed to persist claim in database")

        return {
            "claim_id": str(claim.claim_id),
            "prompt": claim.prompt,
            "model_name": claim.model_name,
            "seed": claim.seed,
            "generated_code": claim.generated_code,
            "original_result": claim.original_result,
            "data_snapshot_hash": claim.data_snapshot_hash,
            "env_hash": claim.env_hash,
            "status": claim.status,
            "created_at": claim.created_at.isoformat(),
        }


@app.post("/api/reverify")
def reverify_claim(req: ReverifyRequest):
    """Re-verify a recorded claim under various real-world audit conditions."""
    reexecutor = ClaimReexecutor()

    with get_session() as session:
        store = ProvenanceStore(session)
        claim = store.get_claim(req.claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found in ledger")

        # Load exact historical data snapshot
        loaded_df = DataIngestionEngine.load_snapshot(claim.data_snapshot_hash)
        if loaded_df is None:
            raise HTTPException(status_code=404, detail="Original data snapshot not found on disk")

        target_df = loaded_df.copy()
        override_env_packages = None
        target_model = claim.model_name
        exec_mode = "code_rerun"
        num_trials = 1
        temperature = 0.0

        # Process Audit Mode
        if req.audit_mode == "exact_code_rerun":
            exec_mode = "code_rerun"

        elif req.audit_mode == "agent_reinvocation_same_seed":
            exec_mode = "agent_reinvocation"

        elif req.audit_mode == "cross_model_gemini_2_flash":
            exec_mode = "agent_reinvocation"
            target_model = "gemini-2.0-flash"

        elif req.audit_mode == "cross_model_gemini_pro":
            exec_mode = "agent_reinvocation"
            target_model = "gemini-1.5-pro"

        elif req.audit_mode == "batch_consistency_test":
            exec_mode = "stress_test"
            num_trials = 5
            temperature = 0.2

        elif req.audit_mode == "simulated_library_drift":
            orig_env = {"pandas": "2.1.0", "numpy": "1.26.4", "scikit-learn": "1.4.0"}
            orig_hash, _ = compute_env_hash(orig_env)

            claim.env_hash = orig_hash
            snap = session.get(EnvironmentSnapshot, orig_hash)
            if not snap:
                snap = EnvironmentSnapshot(
                    env_hash=orig_hash,
                    captured_at=claim.created_at,
                    library_versions=orig_env,
                )
                session.add(snap)
            session.commit()

            override_env_packages = {"pandas": "2.2.0", "numpy": "1.26.4", "scikit-learn": "1.4.0"}
            num_cols = list(target_df.select_dtypes(include=["number"]).columns)
            for col in num_cols:
                target_df[col] = target_df[col].astype(float)

            if num_cols:
                target_df[num_cols[0]] = target_df[num_cols[0]].iloc[::-1].values
                if len(num_cols) > 1:
                    target_df.loc[0, num_cols[1]] = float(target_df[num_cols[1]].max() * 3.5 + 20.0)

        elif req.audit_mode == "simulated_data_drift":
            num_cols = list(target_df.select_dtypes(include=["number"]).columns)
            for col in num_cols:
                target_df[col] = target_df[col].astype(float)
            if num_cols:
                target_df[num_cols[0]] = target_df[num_cols[0]].iloc[::-1].values

        try:
            report: ReexecutionReport = reexecutor.reverify(
                claim_id=claim.claim_id,
                df=target_df,
                mode=exec_mode,
                current_model_name=target_model,
                temperature=temperature,
                num_trials=num_trials,
                override_env_packages=override_env_packages,
            )
            return {
                "claim_id": report.claim_id,
                "matched": report.matched,
                "status": report.status,
                "original_result": report.original_result,
                "new_result": report.new_result,
                "diff_summary": report.diff_summary,
                "diagnosis": report.diagnosis.model_dump() if report.diagnosis else None,
                "multi_trial_summary": report.multi_trial_summary.model_dump() if report.multi_trial_summary else None,
                "executed_at": report.executed_at.isoformat(),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Re-verification error: {str(e)}")


@app.get("/api/claims")
def list_claims():
    """List historical claims in the ledger."""
    with get_session() as session:
        store = ProvenanceStore(session)
        claims = store.list_claims(limit=50)
        return {
            "claims": [
                {
                    "claim_id": str(c.claim_id),
                    "prompt": c.prompt,
                    "model_name": c.model_name,
                    "seed": c.seed,
                    "original_result": c.original_result,
                    "data_snapshot_hash": c.data_snapshot_hash,
                    "env_hash": c.env_hash,
                    "status": c.status,
                    "created_at": c.created_at.isoformat(),
                }
                for c in claims
            ]
        }


# Serve React Single-Page Application
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """Serve frontend index.html."""
    index_file = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>Frontend loading...</h1>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
