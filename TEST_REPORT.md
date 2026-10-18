# Test Report

Commands as run, with observed results (2026-10-16, Windows 11, Python 3.13.7, FalkorDB v4.22.0 in Docker).

## Final state

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && pytest -q` | **58 passed** (89.7 s), integration tests against real FalkorDB |
| Frontend | `cd frontend && npm run build` | tsc strict + vite build OK (chunk-size warning only) |
| Evaluation | `python scripts/evaluate.py` | exit 0; 0 leakage issues; integrity ok; rerun gave identical metrics |
| E2E phase 1 | `python scripts/e2e_check.py --phase 1` | 8/8 PASS |
| Restart | kill uvicorn; `docker compose stop falkordb` + `start`; start uvicorn | DB ready in 1.5 s; both memories present |
| E2E phase 2 | `python scripts/e2e_check.py --phase 2` | 7/7 PASS (memory reuse, failed repair not reused, look-alike rejected, rollback chosen) |
| Graph removal | `docker compose stop falkordb`; `e2e_check.py --phase down` | 3/3 PASS (health 503, investigate 503 `graph_unavailable`, list 503); recovered to 200 after restart |
| Manual UI | Chrome on http://localhost:5173 | investigate, evidence panel, 403 without approval, simulate → resolved + memory, memory reuse on SYN-redis-mem-2, evaluation/memory views, no console errors |

## Test files

| File | Covers |
|---|---|
| `test_stage1_env.py` | settings validation, secret not in repr, DB-down 503, parameterized hostile string |
| `test_stage2_ingestion.py` | opaque IDs, metric parsing, anomaly detection on fixtures, missing telemetry, invalid inputs, log sanitizing, real processed data has no labels + has provenance |
| `test_stage3_graph.py` | constraints enforced, idempotent full load, real records queryable, unknown service reported not invented |
| `test_stage4_tools.py` | multi-hop, upstream, no fabricated paths, validation, blast radius, change data absent/present, related incidents, memory reuse/reject/failed, action preconditions, evidence paths, DB down |
| `test_stage5_investigator.py` | coverage beats victim, caller fan-out, fault class, narrative validation, determinism, abstention, persistence traceability, LLM timeout/invented IDs/ok, real benchmark incident |
| `test_stage6_7_sim_memory.py` | correct vs incorrect interventions, approval, real labels in simulator, visible/hidden separation, memory Tests A/B/C in fresh sessions, contradiction preserved + idempotent |
| `test_stage9_api.py` | incident list/detail, DB-backed graph payload, investigate→evidence→simulate→memory→timeline, validation errors, outage 503 |
| `test_stage10_adversarial.py` | static ground-truth import check, hostile text inert, contradictory evidence, graph removal → 404, malformed requests, missing benchmark data, bad selection |

## Failures encountered and how they were resolved

| Stage | Failure | Class | Resolution |
|---|---|---|---|
| 0 | venv pip upgrade `WinError 32` | environment | venv recreated at repo root |
| 1 | raw `redis.TimeoutError` when DB down | application defect | FalkorDB ctor connects eagerly → lazy connect wrapped in `GraphUnavailableError` |
| 4 | look-alike memory not retrieved (KeyError) | application defect | memory candidates also via source-incident similarity |
| 5 | B misranked a victim with socket ↓ | application defect (history split) | resource decreases treated as symptoms |
| 8 | v1: memory worsened cpu actions; hub fan-out misses | application defect (found on rep 2) | max-based memory effect, fan-out restriction; rep 2 → validation, rep 3 added as test |
| 10 | static leak test flagged `graph/schema.py` | test defect | file only lists forbidden names (the guard) → allow-listed with comment |
| 10 | FalkorDB segfault replaying AOF after restart | dependency defect (reproduced in isolation) | `EFFECTS_THRESHOLD` tried: replay ETA > 2 h, abandoned; switched to RDB snapshots; restart verified |
| 10 | e2e phase 2 ran while DB was loading | test defect | script waits for health |

## Earlier stage logs (abridged)
- Stage 0 probe: variable-length paths, MERGE idempotency, `GRAPH.CONSTRAINT` required, `algo.*` available.
- Stage 2: `scripts/ingest.py --mode full --reps 1 2 3 --skip-download` → 90 selected, 90 loaded, 132 s.
- Stage 3: load → 0 integrity problems; 9 CALLS all in architecture; 7 architecture edges never traced.
