# Progress

| Stage | Status | Notes |
|---|---|---|
| 0 Inspection & feasibility | PASS | Empty repo. Python 3.13, Node 24, Docker OK. FalkorDB v4.22.0 probed. RCAEval HF layout inspected on a real case. |
| 1 Environment | PASS | Compose, pydantic settings, JSON logging, `/health` (200 vs 503 with a real Cypher probe), recovery after DB restart. |
| 2 Data ingestion | PASS | 90/90 RE2-OB cases (reps 1–3) loaded via pinned HF revision; manifest, labels separated, quality report, sample mode, stale-file cleanup. |
| 3 Graph model | PASS | 11 labels, 25 relationship types, unique constraints, idempotent MERGE loader, integrity checks (0 problems). |
| 4 Graph tools | PASS | 9 typed tools; input validation; no fabricated paths; visible failure without DB. |
| 5 Investigator | PASS | Deterministic A/B/C modes, abstention, persistence, evidence traceable. LLM narrator validated with a fake provider only (no key). |
| 6 Simulator | PASS | Deterministic effect model, approval gate, 7 contrasting synthetic scenarios with hidden truth in a separate file. |
| 7 Memory | PASS | Tests A/B/C pass in fresh sessions; append-only with CONTRADICTS; survives backend + DB restart (verified live). |
| 8 Evaluation | PASS | History/validation/test protocol, frozen config, reproducible (2 identical runs), 0 leakage issues. v1 archived. |
| 9 Frontend/API | PASS | React/TS/Cytoscape UI on the real API; build passes; manually verified in Chrome. |
| 10 E2E/adversarial | PASS | `e2e_check.py` phases 1/2/down pass across restarts; adversarial suite passes. Found and worked around a FalkorDB AOF crash (RDB persistence). |
| 9b Frontend refactor | PASS | Graph-first workbench: incident list + 4 tabs, rebuilt Cytoscape graph (icons, data-derived layout, controls, drawer), Memory & Timeline and Evaluation pages. Build + manual Chrome verification; see TEST_REPORT. |
| 9c Visual redesign + guide | PASS | Design system based on the Refero/Runey reference, rail navigation, stat tiles + Investigation tile, restyled graph, in-app guide (A–H) with real screenshots, printable one-pager (1 A4 page verified). See TEST_REPORT. |
| 11 Docs | PASS | README, docs/*.md, status files. Video not recorded; no public deployment; LICENSE to be chosen by the owner. |
