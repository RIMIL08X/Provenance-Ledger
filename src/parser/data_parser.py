"""Multi-format data parser and snapshot manager for tabular and unstructured documents."""

import io
import json
import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from pypdf import PdfReader
from docx import Document

from src.interceptor.hashing import compute_data_snapshot_hash

SNAPSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data_snapshots"))
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


class DataIngestionEngine:
    """Parses arbitrary file formats into structured DataFrames and manages immutable snapshots."""

    @staticmethod
    def parse_file(file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, Dict[str, Any], str]:
        """Parse raw file bytes into a DataFrame and return (dataframe, metadata_summary, data_hash)."""
        ext = os.path.splitext(filename)[1].lower()
        df = None

        if ext in (".csv", ".txt", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=delimiter, low_memory=False)
            except Exception:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python")

        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")

        elif ext == ".parquet":
            df = pd.read_parquet(io.BytesIO(file_bytes))

        elif ext == ".json":
            try:
                data = json.loads(file_bytes.decode("utf-8"))
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                elif isinstance(data, dict):
                    df = pd.DataFrame([data])
            except Exception:
                df = pd.read_json(io.BytesIO(file_bytes))

        elif ext == ".docx":
            doc = Document(io.BytesIO(file_bytes))
            rows_data = []
            if doc.tables:
                table = doc.tables[0]
                headers = [cell.text.strip() for cell in table.rows[0].cells]
                for row in table.rows[1:]:
                    vals = [cell.text.strip() for cell in row.cells]
                    rows_data.append(dict(zip(headers, vals)))
                df = pd.DataFrame(rows_data)
            else:
                paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                df = pd.DataFrame({"paragraph_id": range(1, len(paragraphs) + 1), "text": paragraphs})

        elif ext == ".pdf":
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append({"page_number": i + 1, "text": text.strip()})
            df = pd.DataFrame(pages_text) if pages_text else pd.DataFrame({"page_number": [1], "text": [""]})

        else:
            text = file_bytes.decode("utf-8", errors="replace")
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            df = pd.DataFrame({"line_number": range(1, len(lines) + 1), "text": lines})

        if df is None or df.empty:
            df = pd.DataFrame({"info": ["Empty dataset"]})

        df.columns = [str(c).strip() for c in df.columns]

        data_hash = compute_data_snapshot_hash(df)

        snapshot_path = os.path.join(SNAPSHOT_DIR, f"{data_hash}.parquet")
        try:
            df.to_parquet(snapshot_path, index=False)
        except Exception:
            df.to_csv(os.path.join(SNAPSHOT_DIR, f"{data_hash}.csv"), index=False)

        # Optimize preview & metadata payload for ultra-wide datasets (e.g. 25,000+ columns)
        num_cols = list(df.select_dtypes(include=["number"]).columns)
        total_cols = len(df.columns)
        
        # Take a slice of columns for frontend preview
        preview_col_limit = min(25, total_cols)
        preview_df = df.iloc[:10, :preview_col_limit]

        summary = {
            "filename": filename,
            "data_hash": data_hash,
            "total_rows": len(df),
            "total_columns": total_cols,
            "is_wide": total_cols > 100,
            "columns": list(df.columns[:50]),
            "preview_columns": list(preview_df.columns),
            "dtypes": {str(col): str(df[col].dtype) for col in preview_df.columns},
            "numeric_columns": num_cols[:20],
            "numeric_column_count": len(num_cols),
            "sample_records": preview_df.to_dict(orient="records"),
        }

        return df, summary, data_hash

    @staticmethod
    def load_snapshot(data_hash: str) -> Optional[pd.DataFrame]:
        """Load stored dataset snapshot by its sha256 hash."""
        parquet_path = os.path.join(SNAPSHOT_DIR, f"{data_hash}.parquet")
        if os.path.exists(parquet_path):
            return pd.read_parquet(parquet_path)
        csv_path = os.path.join(SNAPSHOT_DIR, f"{data_hash}.csv")
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        return None
