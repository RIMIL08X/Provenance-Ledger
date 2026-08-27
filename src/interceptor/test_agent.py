"""Data science agent implementation with Gemini Cloud LLM integration."""

import os
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from src.interceptor.capture import AgentClaimPayload
from src.interceptor.gemini_client import GeminiClient


class MinimalDataScienceAgent:
    """Agent that dynamically generates and executes analytical code on arbitrary DataFrames via Gemini."""

    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        model_version: str = "1.5",
        gemini_client: Optional[GeminiClient] = None,
    ) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self.gemini = gemini_client or GeminiClient()

    def get_available_models(self) -> List[str]:
        """Return list of available Gemini cloud models."""
        return self.gemini.AVAILABLE_MODELS

    def _extract_code(self, raw_text: str) -> str:
        """Extract clean python code block from model output."""
        match = re.search(r"```(?:python)?\s*([\s\S]*?)```", raw_text)
        if match:
            code = match.group(1).strip()
        else:
            lines = [line for line in raw_text.strip().split("\n") if not line.startswith("#") and not line.startswith("Here")]
            code = "\n".join(lines).strip()

        # Remove any accidental local df definitions so it runs against real in-memory df
        cleaned_lines = []
        for line in code.split("\n"):
            if re.match(r"^\s*df\s*=\s*pd\.DataFrame\(", line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _generate_code_mock(self, prompt: str, df: pd.DataFrame) -> str:
        """Deterministic fallback code generator when offline."""
        prompt_lower = prompt.lower()
        cols = list(df.columns)
        num_cols = list(df.select_dtypes(include=["number"]).columns)

        if "tenure" in prompt_lower and "churn" in prompt_lower and "tenure" in cols and "churn" in cols:
            return (
                "corr = float(df['tenure'].corr(df['churn']))\n"
                "result = {'r': round(corr, 2), 'claim': f'Tenure is negatively correlated with churn (r = {round(corr, 2)})' if corr < 0 else f'Tenure is positively correlated with churn (r = {round(corr, 2)})'}"
            )
        elif len(num_cols) >= 2 and any(w in prompt_lower for w in ["corr", "predict", "relationship", "versus", "vs"]):
            c1, c2 = num_cols[0], num_cols[1]
            return (
                f"corr = float(df['{c1}'].corr(df['{c2}']))\n"
                f"result = {{'r': round(corr, 2), 'claim': f'Correlation between {c1} and {c2} is {{round(corr, 2)}}'}}"
            )
        elif any(w in prompt_lower for w in ["mean", "avg", "average"]):
            target = next((c for c in cols if c.lower() in prompt_lower), num_cols[0] if num_cols else cols[0])
            return (
                f"val = float(df['{target}'].mean())\n"
                f"result = {{'value': round(val, 2), 'claim': f'The average {target} is {{round(val, 2)}}'}}"
            )
        elif any(w in prompt_lower for w in ["max", "highest", "maximum"]):
            target = next((c for c in cols if c.lower() in prompt_lower), num_cols[0] if num_cols else cols[0])
            return (
                f"val = float(df['{target}'].max())\n"
                f"result = {{'value': round(val, 2), 'claim': f'The maximum {target} is {{round(val, 2)}}'}}"
            )
        elif any(w in prompt_lower for w in ["sum", "total"]):
            target = next((c for c in cols if c.lower() in prompt_lower), num_cols[0] if num_cols else cols[0])
            return (
                f"val = float(df['{target}'].sum())\n"
                f"result = {{'value': round(val, 2), 'claim': f'The total {target} is {{round(val, 2)}}'}}"
            )
        elif any(w in prompt_lower for w in ["count", "rows", "size"]):
            return "cnt = int(len(df))\nresult = {'value': cnt, 'claim': f'Dataset contains {cnt} total rows'}"
        else:
            first_col = num_cols[0] if num_cols else cols[0]
            return (
                f"val = float(df['{first_col}'].mean())\n"
                f"result = {{'value': round(val, 2), 'claim': f'Calculated mean for {first_col}: {{round(val, 2)}}'}}"
            )

    def _generate_code(self, prompt: str, df: pd.DataFrame, seed: Optional[int]) -> str:
        """Generate analysis code from Gemini or fallback."""
        if self.gemini.is_available():
            schema_info = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
            sample_preview = df.head(3).to_string()

            system_instruction = (
                "You are an expert, meticulous data science agent.\n"
                "A pandas DataFrame variable named `df` is ALREADY loaded in memory.\n"
                f"Dataset Schema: {schema_info}\n"
                f"Dataset Shape: {len(df)} rows x {len(df.columns)} columns\n"
                f"Data Preview:\n{sample_preview}\n\n"
                "RULES:\n"
                "1. DO NOT recreate, mock, or redefine `df`. Operate directly on `df`.\n"
                "2. Write Python code to compute the exact answer to the user's question.\n"
                "3. You MUST assign the final structured dictionary to the variable `result`.\n"
                "4. `result` MUST have a 'claim' key with a concise, clear natural-language summary (e.g. 'Tenure is negatively correlated with churn (r = -0.42)' or 'The average salary is $105,200.00').\n"
                "5. `result` SHOULD also include relevant numeric keys (e.g. 'r', 'value', 'mean', 'max', 'count').\n"
                "6. Wrap ONLY executable Python code in ```python ``` fences."
            )

            try:
                raw_output = self.gemini.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=self.model_name,
                    temperature=0.0,
                    seed=seed,
                )
                code = self._extract_code(raw_output)
                if code and "result" in code:
                    return code
            except Exception:
                pass

        return self._generate_code_mock(prompt, df)

    def analyze(
        self,
        df: pd.DataFrame,
        prompt: str,
        seed: Optional[int] = 17,
    ) -> AgentClaimPayload:
        """Execute agent analysis on df and return structured claim payload."""
        # 1. Generate code
        generated_code = self._generate_code(prompt, df, seed)

        # 2. Execute code in controlled scope
        local_scope: Dict[str, Any] = {"df": df, "pd": pd, "np": np}
        try:
            exec(generated_code, {"pd": pd, "np": np}, local_scope)
            res = local_scope.get("result")
        except Exception as e:
            res = {"error": f"Execution error: {str(e)}", "claim": f"Analysis execution failed: {str(e)}"}

        # 3. Format structured output
        if isinstance(res, (int, float, np.number)):
            structured_result = {"value": float(res), "claim": str(res)}
        elif isinstance(res, dict):
            structured_result = res
        else:
            structured_result = {"claim": str(res)}

        return AgentClaimPayload(
            prompt=prompt,
            model_name=self.model_name,
            model_version=self.model_version,
            generated_code=generated_code,
            result=structured_result,
            seed=seed,
            input_dataframe=df,
        )
