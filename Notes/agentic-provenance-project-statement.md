# The Gap

LLM agents are now doing real data science work end-to-end — cleaning data, running analysis, writing conclusions — with almost no human in the loop. The problem: these agents don't reliably produce the same answer twice, and right now nobody is keeping a permanent record that would let you check.

Two things are true at once in the current research:
- Even under maximally controlled settings, agent-generated analysis still shows unexplained variation run to run — the determinism you'd expect from "just set the temperature to zero" doesn't actually hold in practice.
- On real scientific coding tasks, benchmarks show these agents get the analysis outright wrong close to two-thirds of the time.

The one serious attempt to measure this (AIRepr, 2025) is a **benchmark** — it scores a batch of agents on a fixed set of test tasks, once. It does not sit underneath a live, deployed agent and keep watching whether the claims it made last month still hold up today. That's the piece nobody has built: a permanent, checkable paper trail for AI-generated analysis, running continuously in production rather than scored once in a lab.

---

# Project Statement — Working Title: **Provenance Ledger**
### A Continuous Provenance & Reproducibility Auditing Layer for Agentic Data Science

## Goal

**Build a system that sits underneath any data-science agent, records a full, verifiable chain of custody for every claim it makes, and continuously re-checks those claims — so that at any point you can ask "does this conclusion still reproduce" and get a real, tested answer instead of a guess.**

Success criteria:
1. A working provenance capture layer that records, for every agent-generated claim: the prompt, model + version, generated code, environment/library versions, data snapshot hash, and random seed.
2. An automatic re-execution scheduler that samples past claims and reruns them against the recorded provenance, flagging any that no longer reproduce.
3. A live **reproducibility score** per claim and per agent over time, not a one-time benchmark number.
4. Automatic drift diagnosis — distinguishing whether a failed reproduction was caused by a model version change, a library update, a data change, or genuine stochastic variation.
5. A benchmark comparing your continuous system's detection rate against a static one-time evaluation (like AIRepr's approach), to demonstrate what continuous monitoring catches that a single benchmark run misses.

## One-line resume bullet

> Built **Provenance Ledger**, a continuous reproducibility-auditing layer for LLM data science agents — capturing full provenance per claim and automatically re-verifying past agent conclusions in production, rather than one-time benchmark scoring.

## Short statement (resume / portfolio, ~90 words)

Data science agents increasingly generate real analytical conclusions with no reliable guarantee they'll produce the same answer twice — and the field's current fix is a one-time benchmark, not a running check. I built Provenance Ledger, a system that captures a full chain of custody (prompt, model version, code, data snapshot, seed) for every agent-generated claim, then continuously re-executes a sample of past claims to compute a live reproducibility score and diagnose why a claim stopped reproducing — a model update, a library change, a data shift, or genuine randomness.

## Extended statement (SOP / essay draft, ~260 words)

As LLM agents take on more of the data science workflow — cleaning data, selecting models, generating and interpreting analysis — a quiet reliability problem has emerged alongside their growing autonomy. Even in tightly controlled settings, agent-generated outputs show variation across runs that current evaluation methods don't reliably catch, and accuracy on real scientific coding tasks remains far from trustworthy. The one rigorous attempt to measure this treats reproducibility as something you score once, against a fixed benchmark — useful for comparing models, but silent on whether a specific conclusion an agent produced last month still holds today.

I built Provenance Ledger to close that gap: a layer that sits underneath a deployed data-science agent and keeps a permanent, verifiable record of every claim it makes — not just the conclusion, but everything needed to regenerate it: the exact prompt, model version, generated code, environment, data snapshot, and seed. On a schedule, the system samples past claims and re-executes them against that recorded provenance, comparing the new result to the original and computing a live reproducibility score per claim and per agent over time.

The part I consider the real contribution is diagnosis, not just detection: when a claim fails to reproduce, the system distinguishes whether that's because the underlying model changed, a library was updated, the data shifted, or the failure is genuine stochastic noise inherent to the agent itself. That distinction is what turns "this didn't reproduce" from a red flag into an actionable finding — and it's the piece a static, one-time benchmark structurally cannot provide, because it never runs again after the paper is published.

## Notes for next steps
- "Provenance Ledger" is a working title — swap it for whatever you want to ship under.
- This reuses the lineage/audit-trail architecture from your lakehouse-eraser side project, applied to AI-generated claims instead of personal data — worth naming that connection explicitly in an SOP, since it shows a consistent research thread rather than two unrelated projects.
- Say the word if you want the same goal-and-scaffold treatment (repo structure + stubbed modules) you got for lakehouse-eraser.
