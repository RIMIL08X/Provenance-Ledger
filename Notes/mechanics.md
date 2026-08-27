# Provenance Ledger — Mechanics

This document specifies how the system actually works, at the level a coding agent (or future-you) needs to implement it. Pair with `PROMPT.md` to bootstrap the repo.

---

## 1. System overview

Five components, in call order:

```
Agent (test subject) 
  → Interceptor (captures provenance at claim time)
    → Provenance Store (Postgres — durable record)
       → Scheduler (periodically samples stored claims)
          → Re-executor (reruns a sampled claim under recorded conditions)
             → Comparator + Drift Diagnoser (did it match? if not, why?)
                → Dashboard (reproducibility score over time)
```

The Interceptor is a wrapper, not a modification to the agent. Nothing about the agent's internals should need to change for this system to work — that's what makes it agent-agnostic.

---

## 2. Data model (Postgres)

```sql
-- One row per agent-generated claim
CREATE TABLE claims (
    claim_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    prompt TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    seed INTEGER,
    generated_code TEXT NOT NULL,
    original_result JSONB NOT NULL,       -- the claim/output itself
    data_snapshot_hash TEXT NOT NULL,     -- sha256 of the input data used
    env_hash TEXT NOT NULL,               -- sha256 of `pip freeze` output
    status TEXT DEFAULT 'unverified'      -- unverified | reproduced | failed
);

-- One row per environment fingerprint (dedup — many claims can share one env)
CREATE TABLE environment_snapshots (
    env_hash TEXT PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL,
    library_versions JSONB NOT NULL       -- {"pandas": "2.2.0", "scikit-learn": "1.5.0", ...}
);

-- One row per re-execution attempt (a claim can be re-tried multiple times over its life)
CREATE TABLE reexecution_results (
    reexecution_id UUID PRIMARY KEY,
    claim_id UUID REFERENCES claims(claim_id),
    executed_at TIMESTAMPTZ NOT NULL,
    new_result JSONB NOT NULL,
    matched BOOLEAN NOT NULL,
    diff_summary TEXT                     -- human-readable description of what differed, if anything
);

-- One row per detected mismatch, with a diagnosed cause
CREATE TABLE drift_diagnoses (
    diagnosis_id UUID PRIMARY KEY,
    reexecution_id UUID REFERENCES reexecution_results(reexecution_id),
    cause TEXT NOT NULL,                  -- 'model_version_change' | 'library_version_change' | 'data_change' | 'stochastic_variation' | 'unknown'
    confidence FLOAT,                     -- 0.0-1.0, how sure the diagnosis logic is
    evidence JSONB                        -- whatever supported the diagnosis (e.g. old vs new env_hash diff)
);
```

---

## 3. Provenance capture mechanics

The interceptor wraps the agent's "produce a claim" call. On every call it captures:

- `prompt` — verbatim input to the agent.
- `model_name` / `model_version` — from the agent's config or API response metadata.
- `seed` — explicitly set before the call; if the agent framework doesn't expose a seed parameter, note this as a known limitation rather than faking one.
- `generated_code` — the exact code the agent produced and executed.
- `original_result` — the structured claim/output (numbers, and/or a short natural-language conclusion).
- `data_snapshot_hash` — `sha256(canonical_serialization(input_dataframe))`. Canonicalize before hashing (sort columns, fix float precision) so identical data always hashes identically regardless of in-memory ordering.
- `env_hash` — `sha256(sorted(pip freeze output))`.

Write one row to `claims`, and upsert into `environment_snapshots` if `env_hash` is new.

---

## 4. Re-execution mechanics

Given a `claim_id`:

1. Load the row: prompt, seed, generated_code, data_snapshot_hash, env_hash.
2. **Cheap version (build this first):** re-run the stored `generated_code` directly against a data snapshot matching `data_snapshot_hash`. This tests "does the same code on the same data still give the same answer" — isolates code/data/environment drift from agent stochasticity.
3. **Full version (build second):** re-invoke the agent itself with the same `prompt` and `seed`, let it regenerate code from scratch, and compare that new code's result too. This tests agent-level reproducibility, not just code-level — the harder and more interesting case, since it can diverge even when step 2 doesn't.
4. Record the outcome as a new row in `reexecution_results`.

---

## 5. Comparator logic

- Numeric results: match if `abs(new - original) / abs(original) < tolerance` (default tolerance 1%, make configurable — some analyses are legitimately more sensitive than others).
- Categorical/text conclusions: exact match first; if not exact, use a simple embedding-similarity threshold rather than requiring identical wording (a rephrased but equivalent conclusion should still count as reproduced).
- Always store `diff_summary` — even on a match, a one-line "identical" is useful; on a mismatch, describe what changed in plain terms.

---

## 6. Drift diagnosis (decision logic)

When `matched = false`, walk this in order and stop at the first cause found:

1. Compare `model_version` at original time vs. current model version available → if different: `model_version_change`.
2. Compare `env_hash` at original time vs. current environment's hash → if different: `library_version_change`. Store the specific package diffs as `evidence`.
3. Compare `data_snapshot_hash` at original time vs. the data snapshot used in re-execution → if different: `data_change`.
4. If none of the above differ (everything is provably identical) → `stochastic_variation`. This is the most important case to isolate cleanly, since it means the agent itself is inherently unstable, not that anything external changed.
5. If inputs can't be fully verified identical for some reason → `unknown`, with `evidence` explaining what couldn't be checked.

---

## 7. Scheduler mechanics

- Sample a configurable percentage of `claims` with `status = 'unverified'` or claims older than N days since last re-execution, on a cron schedule (start daily; tune based on run cost).
- Prioritize sampling: claims with high business importance (however you tag that) or claims that haven't been re-checked recently.
- Each sampled claim goes through the full re-execution → comparison → diagnosis pipeline, then updates `claims.status`.

---

## 8. Reproducibility score

Per claim: `1.0` if last re-execution matched, `0.0` if not, decaying confidence if it's been a long time since last check (a claim that hasn't been re-verified in 6 months shouldn't show the same confidence as one checked yesterday).

Per agent (aggregate): rolling average of per-claim scores over a trailing window (e.g. last 30 days of re-executions), reported alongside a breakdown of diagnosed causes — this breakdown is what makes the dashboard useful, not just the single number.

---

## 9. Fault-injection experiment design (for your demo/validation)

Deliberately break one variable at a time between an original run and a re-execution, and confirm the diagnosis logic correctly attributes it:

- Swap one library's version in the environment → expect `library_version_change`.
- Swap the model version/endpoint used → expect `model_version_change`.
- Mutate one column in the input data → expect `data_change`.
- Change nothing, just re-run with fresh sampling → expect `stochastic_variation` (or a match, depending on the agent's actual determinism).

Report a confusion matrix: injected cause vs. diagnosed cause, across enough trials to be a real result, not an anecdote.
