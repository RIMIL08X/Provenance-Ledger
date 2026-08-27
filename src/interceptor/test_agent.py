"""Data science agent implementation with Gemini Cloud LLM integration."""

import math
import os
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import scipy
from scipy import stats
import sklearn

from src.interceptor.capture import AgentClaimPayload
from src.interceptor.gemini_client import GeminiClient


class MinimalDataScienceAgent:
    """Agent that dynamically generates and executes analytical code on arbitrary DataFrames via Gemini."""

    def __init__(
        self,
        model_name: str = "gemini-3.6-flash",
        model_version: str = "3.6",
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

        cleaned_lines = []
        for line in code.split("\n"):
            if re.match(r"^\s*df\s*=\s*pd\.DataFrame\(", line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _find_matching_columns(self, prompt: str, df: pd.DataFrame) -> List[str]:
        """Find columns from df mentioned in prompt."""
        prompt_lower = prompt.lower()
        matched = []
        # Sort by length descending to match full names first
        for col in sorted(df.columns, key=lambda x: len(str(x)), reverse=True):
            col_name = str(col).strip()
            if col_name and col_name.lower() in prompt_lower:
                if col_name not in matched:
                    matched.append(col_name)
        return matched

    def _generate_code_mock(self, prompt: str, df: pd.DataFrame) -> str:
        """Intelligent fallback code generator targeting the exact columns requested in the prompt."""
        prompt_lower = prompt.lower()
        matched_cols = self._find_matching_columns(prompt, df)
        num_cols = list(df.select_dtypes(include=["number"]).columns)
        all_cols = list(df.columns)

        # Correlation or relationship requested
        if any(w in prompt_lower for w in ["corr", "predict", "relationship", "versus", "vs", "associated"]):
            if len(matched_cols) >= 2:
                c1, c2 = matched_cols[0], matched_cols[1]
            elif len(matched_cols) == 1 and num_cols:
                c1 = matched_cols[0]
                c2 = next((c for c in num_cols if c != c1), all_cols[0])
            elif len(num_cols) >= 2:
                c1, c2 = num_cols[0], num_cols[1]
            else:
                c1, c2 = all_cols[0], (all_cols[1] if len(all_cols) > 1 else all_cols[0])

            # Check if columns are numeric or categorical
            is_c1_num = pd.api.types.is_numeric_dtype(df[c1])
            is_c2_num = pd.api.types.is_numeric_dtype(df[c2])

            if is_c1_num and is_c2_num:
                return (
                    f"corr = float(df['{c1}'].corr(df['{c2}']))\n"
                    f"result = {{'r': round(corr, 2), 'claim': f'Correlation between {c1} and {c2} is {{round(corr, 2)}}'}}"
                )
            else:
                return (
                    f"s1, _ = pd.factorize(df['{c1}'])\n"
                    f"s2, _ = pd.factorize(df['{c2}'])\n"
                    f"corr = float(pd.Series(s1).corr(pd.Series(s2)))\n"
                    f"result = {{'r': round(corr, 2), 'claim': f'Factorized correlation between categorical columns {c1} and {c2} is {{round(corr, 2)}}'}}"
                )

        elif any(w in prompt_lower for w in ["mean", "avg", "average"]):
            target = matched_cols[0] if matched_cols else (num_cols[0] if num_cols else all_cols[0])
            if pd.api.types.is_numeric_dtype(df[target]):
                return (
                    f"val = float(df['{target}'].mean())\n"
                    f"result = {{'value': round(val, 2), 'claim': f'The average {target} is {{round(val, 2)}}'}}"
                )
            else:
                return (
                    f"top_val = df['{target}'].mode().iloc[0] if not df['{target}'].empty else 'N/A'\n"
                    f"result = {{'value': str(top_val), 'claim': f'Most common value in {target} is {{top_val}}'}}"
                )

        elif any(w in prompt_lower for w in ["max", "highest", "maximum"]):
            target = matched_cols[0] if matched_cols else (num_cols[0] if num_cols else all_cols[0])
            if pd.api.types.is_numeric_dtype(df[target]):
                return (
                    f"val = float(df['{target}'].max())\n"
                    f"result = {{'value': round(val, 2), 'claim': f'The maximum {target} is {{round(val, 2)}}'}}"
                )
            else:
                return (
                    f"val = df['{target}'].dropna().astype(str).max()\n"
                    f"result = {{'value': str(val), 'claim': f'Maximum entry in {target} is {{val}}'}}"
                )

        elif any(w in prompt_lower for w in ["count", "rows", "size", "length"]):
            return f"cnt = int(len(df))\ncols = int(len(df.columns))\nresult = {{'rows': cnt, 'columns': cols, 'claim': f'Dataset contains {{cnt}} rows and {{cols}} columns'}}"

        else:
            target = matched_cols[0] if matched_cols else (num_cols[0] if num_cols else all_cols[0])
            if pd.api.types.is_numeric_dtype(df[target]):
                return (
                    f"val = float(df['{target}'].mean())\n"
                    f"result = {{'value': round(val, 2), 'claim': f'Calculated mean for {target}: {{round(val, 2)}}'}}"
                )
            else:
                return (
                    f"cnt = int(df['{target}'].nunique())\n"
                    f"result = {{'unique_count': cnt, 'claim': f'Column {target} contains {{cnt}} unique categories'}}"
                )

    def _generate_code(self, prompt: str, df: pd.DataFrame, seed: Optional[int]) -> str:
        """Generate analysis code from Gemini or fallback with token-safe schema formatting."""
        if self.gemini.is_available():
            total_cols = len(df.columns)
            total_rows = len(df)
            num_cols = list(df.select_dtypes(include=["number"]).columns)

            if total_cols > 50:
                schema_description = (
                    f"Dataset Shape: {total_rows} rows x {total_cols} columns (Wide Dataset)\n"
                    f"All Column Names (sample): {list(df.columns[:50])}\n"
                    f"Total Numeric Columns: {len(num_cols)}\n"
                    f"Data Preview (first 3 rows):\n{df.iloc[:3, :min(15, total_cols)].to_string()}"
                )
            else:
                schema_info = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
                schema_description = (
                    f"Dataset Schema: {schema_info}\n"
                    f"Dataset Shape: {total_rows} rows x {total_cols} columns\n"
                    f"Data Preview:\n{df.head(3).to_string()}"
                )

            system_instruction = (
                "You are an expert, meticulous data science agent.\n"
                "A pandas DataFrame variable named `df` is ALREADY loaded in memory.\n"
                "Available packages: pandas (as pd), numpy (as np), scipy, scipy.stats (as stats), sklearn, math.\n"
                f"{schema_description}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. ALWAYS analyze the EXACT columns requested in the user's prompt (e.g. If the prompt mentions 'Activity' and 'Location', analyze `df['Activity']` and `df['Location']`).\n"
                "2. If the user asks for correlation between categorical / string columns, compute factorized Pearson correlation (`pd.factorize()`) or Cramér's V / contingency Chi-squared.\n"
                "3. DO NOT recreate or redefine `df`. Operate directly on `df`.\n"
                "4. Write Python code to compute the exact answer to the user's question.\n"
                "5. You MUST assign the final structured dictionary to the variable `result`.\n"
                "6. `result` MUST have a 'claim' key with a concise, clear natural-language summary answering the user's question.\n"
                "7. `result` SHOULD also include relevant numeric keys (e.g. 'r', 'value', 'mean', 'max', 'count').\n"
                "8. Wrap ONLY executable Python code in ```python ``` fences."
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
            except Exception as e:
                import traceback
                print(f"[Gemini Agent Error] {e}")
                traceback.print_exc()

        return self._generate_code_mock(prompt, df)

    def analyze(
        self,
        df: pd.DataFrame,
        prompt: str,
        seed: Optional[int] = 17,
    ) -> AgentClaimPayload:
        """Execute agent analysis on df and return structured claim payload."""
        generated_code = self._generate_code(prompt, df, seed)

        env_context = {
            "df": df,
            "pd": pd,
            "np": np,
            "scipy": scipy,
            "stats": stats,
            "sklearn": sklearn,
            "math": math,
        }
        local_scope: Dict[str, Any] = env_context.copy()
        try:
            exec(generated_code, env_context, local_scope)
            res = local_scope.get("result")
        except Exception as e:
            res = {"error": f"Execution error: {str(e)}", "claim": f"Analysis execution failed: {str(e)}"}

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
