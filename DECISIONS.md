# Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Use RCAEval **RE2-OB** as the real dataset | Only OB suite with metrics + logs + traces; Online Boutique is the ancestor of the OTel Astronomy Shop, so the architecture references align. |
| D2 | Fetch from the HF parquet mirror per case, pinned to a dataset revision | Downloads about 11 MB per case instead of 4.2 GB RE2.zip; allows reproducible subset selection. |
| D3 | Opaque incident IDs; ground truth kept in `data/eval/` only | Case names encode labels. Prevents leakage into graph and agent context. |
| D4 | Store derived **Observations** (anomaly summaries), not raw time series, in the graph | Raw traces are about 400k spans per case. The graph holds evidence with references to raw files. |
| D5 | Two dependency edge types: `DEPENDS_ON` (architecture) and `CALLS` (trace-observed) | The prompt requires keeping architecture-derived and observed relationships separate. |
| D6 | Deterministic investigator is the core; LLM is an optional narrator whose cited evidence IDs are validated | Works without an API key; LLM cannot add evidence. |
| D7 | Repair outcomes for RCAEval incidents come from a **simulator oracle** keyed on hidden ground truth | RCAEval has no repair outcomes. Simulated, labeled as such. |
| D8 | Memory evaluation uses a temporal split (superseded by D11) | Memory may only come from earlier incidents. Weights are developed on rep 1. |
| D9 | FalkorDB `v4.22.0` pinned, not `latest` | Reproducibility; v4.22.1 was 1 day old at inspection. |
| D10 | Root `.venv` instead of `backend/.venv` | A Windows file lock (antivirus) broke the first venv under `backend/`. Purely environmental. |
| D11 | Three-way split: rep 1 history, rep 2 validation, rep 3 test | The v1 evaluation used rep 2 as held-out. Its failure analysis revealed a memory-weighting defect, so rep 2 became validation. Rep 3 was downloaded only after that point and is the untouched test split. The v1 results are archived in `data/eval/results/archive/`. |
| D12 | Changes made after looking at rep 2 (v1 → v2) | (a) Memory effect per action uses max(success) − max(failure) instead of a sum (frequency bias). (b) Caller fan-out credit is withheld for callees that have their own anomalous dependency. (c) `reschedule_pod` risk raised to high; `deployment_regression` fault class added (motivated by synthetic scenarios, not rep 2). |
| D13 | Ranking and memory configuration FROZEN on 2026-10-16 before the first rep-3 run | Rep-3 numbers are reported from a single run of that frozen configuration. |
| D14 | Optional LLM narrator: Anthropic SDK, `claude-opus-5-5`, effort low, server-side refusal fallback | Narration only; citations are validated against report IDs, otherwise the deterministic text is used. |
| D15 | FalkorDB persistence: RDB snapshots (`--appendonly no --save 60 1`) | AOF replay crashed v4.22.0 (reproduced). `EFFECTS_THRESHOLD` verbatim replication made replay take hours. RDB loads in 1.5 s; trade-off of ≤60 s loss on a hard crash is documented. |
| D16 | No code LICENSE file added | Choosing the license is the owner's decision; flagged in KNOWN_LIMITATIONS. |
