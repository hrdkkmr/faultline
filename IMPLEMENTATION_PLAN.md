# Faultline — Implementation Plan

Faultline is a graph-native incident investigation agent. FalkorDB holds the service
topology, benchmark-derived incident evidence, investigation episodes, simulated action
outcomes and context-conditioned memory. All investigation reasoning runs through
parameterized Cypher.

## Environment (verified in Stage 0, 2026-10-16)

| Item | Value |
|---|---|
| OS | Windows 11, Git Bash + PowerShell |
| Python | 3.13.7 (venv at `.venv/`) |
| Node / npm | 24.14.1 / 11.11.0 |
| Docker | 29.6.1, Compose v5.2.0 (Docker Desktop, 8 GB, 18 CPU) |
| FalkorDB | `falkordb/falkordb:v4.22.0` (released 2026-09-30) |
| FalkorDB Python client | `falkordb==1.8.0` (uses `redis==8.1.0`) |

Probed on v4.22.0: parameterized queries, variable-length paths `[:R*1..3]`, `MERGE`,
`CREATE INDEX`, unique constraints via `GRAPH.CONSTRAINT CREATE` (not Cypher),
`algo.BFS`, `algo.pageRank`, `algo.WCC`, full-text indexes.

## Architecture

```
React/TS/Vite UI  ──HTTP──>  FastAPI backend  ──Cypher──>  FalkorDB (Docker, persistent volume)
                                │
                                ├─ ingestion/   RCAEval parquet -> features -> graph
                                ├─ agents/      typed graph tools + deterministic investigator (+ optional LLM narrator)
                                ├─ memory/      episode write + context-conditioned retrieval (Cypher)
                                ├─ simulation/  scenario-driven repair simulator (oracle hidden from agent)
                                └─ evaluation/  ablation harness A/B/C, metrics, leakage checks
```

Ground truth lives only in `data/eval/` files read by the simulator oracle and the
evaluation runner. Agent modules never import it, and the graph never stores it.

## Data

- **Real**: RCAEval RE2-OB (Online Boutique; metrics + logs + traces) from the Hugging Face
  parquet mirror. 5 root-cause services × 6 faults × 3 repetitions = 90 cases, all used.
  Repetition 1 = history (weight development, memory), 2 = validation, 3 = untouched test
  (revised after the v1 evaluation, see DECISIONS D11–D13). Sample mode: 6 cases.
- **Architecture**: Online Boutique Kubernetes manifests (service `*_ADDR` env vars), cross-referenced
  with the OpenTelemetry Astronomy Shop architecture diagram.
- **Synthetic**: hand-written, explicitly labeled scenarios that add deployments, prior repairs
  and look-alike incidents, none of which RCAEval provides.

## Stages and first end-to-end milestone

0. Inspection & feasibility — this document.
1. Environment: compose, config, health endpoint with real DB check.
2. Ingestion: case manifest, fetch subset, feature extraction, quality report, idempotency.
3. Graph model: schema, constraints, idempotent loader, integrity checks, docs.
4. Graph tools (9 typed tools) + unit/integration tests.
5. Investigator (deterministic) + optional LLM narrator with evidence-ID validation.
6. Repair simulator + action catalog + synthetic contrasting scenarios.
7. Persistent memory + tests A/B/C.
8. Evaluation harness + ablation A/B/C + report.
9. Frontend + API.
10. E2E and adversarial tests.
11. Documentation & submission readiness.

**First end-to-end milestone**: one real RE2-OB case ingested into FalkorDB → `investigate`
returns a ranked root-cause hypothesis with evidence IDs and dependency paths from Cypher.
