# Faultline

**A graph-native incident investigation and repair-intelligence agent on FalkorDB.**
Built for Graph Hacks 2026.

> Faultline uses a persistent knowledge graph to connect operational evidence, investigate failures across service
> dependencies, retrieve context-sensitive incident memory, and produce traceable mitigation recommendations.

**Tracks:** 1. *Agents That Act on Connected Data* (primary) · 2. *Agent Memory and Coordination* (secondary).

## Problem

When a microservice fails, the loudest symptom is often not the cause: a slow dependency makes every caller slow,
and a misbehaving caller makes its callees look slow. Responders also repeat yesterday's fix without checking whether
yesterday's conditions hold. Faultline addresses both problems with explicit graph structure: dependency paths explain
symptoms, and memories carry the conditions under which a repair worked.

## What it does

1. Ingests real failure cases from the public **RCAEval RE2-OB** benchmark (Online Boutique: metrics, logs, traces)
   and turns them into label-free observations in FalkorDB.
2. Links them to the Online Boutique topology (architecture-derived `DEPENDS_ON`) and to trace-observed `CALLS`
   edges, kept separate.
3. Investigates an incident with **9 typed, Cypher-backed tools**: multi-hop traversal, blast radius, related
   incidents, evidence paths, memory retrieval, and action precondition checks.
4. Ranks root-cause **hypotheses** by local evidence plus graph explanation coverage, cites the stored observation
   IDs, lists contradicting evidence, and abstains when evidence is weak.
5. Recommends mitigations, checks each against the incident's graph context, and applies them **only to a
   deterministic simulator** (approval required for disruptive actions).
6. Stores outcomes as **memory** conditioned on graph signals, then reuses, rejects or warns in later sessions.
7. Measures all of this against ablations (`docs/evaluation.md`).

## Results (measured; details and caveats in `docs/evaluation.md`)

Untouched TEST split: RCAEval RE2-OB repetition 3, n = 30, configuration frozen before the single run.

| Mode | Top-1 | Avg@5 | Mitigation success (simulated) | Blast-radius P / R |
|---|---|---|---|---|
| A: incident only (no graph, no memory) | 0.933 | 0.973 | 0.667 | 0.53 / 0.53 |
| B: graph | 0.967 | 0.993 | 0.700 | 1.00 / 0.99 |
| C: graph + persistent memory | 0.967 | 0.993 | **0.767** | 1.00 / 0.99 |
| C-LOSO control (only other services' memories) | 0.867 | 0.960 | 0.483 | 1.00 / 0.94 |

The graph mainly improves blast-radius estimation and a minority of propagation cases. Memory mainly improves
action choice. Memories from unrelated services **hurt** (LOSO row), which is a known limitation. With n = 30,
one case is 3.3 points, and no significance testing was done. Evidence validity is 100% and leakage checks found 0
issues.

## Architecture

```
React + Cytoscape UI ──HTTP──> FastAPI ──parameterized Cypher──> FalkorDB v4.22.0 (Docker, persistent volume)
                                 │
     ingestion/ ── RCAEval parquet → features → graph       agents/ ── 9 tools + deterministic investigator (+ optional LLM narrator)
     memory/    ── outcome → Memory-[:APPLIES_UNDER]->Signal   simulation/ ── scenario-driven simulator (hidden truth)
     evaluation/ ── A/B/C ablation, leakage scan
```
Full diagram, scoring formulas, memory and simulator design: [`docs/architecture.md`](docs/architecture.md).
Schema, relationship semantics and Cypher: [`docs/graph-schema.md`](docs/graph-schema.md).
Data pipeline: [`docs/data-pipeline.md`](docs/data-pipeline.md). Demo: [`docs/demo-script.md`](docs/demo-script.md).

**Why FalkorDB is essential.** Ranking needs reachability among anomalous services. Blast radius is reverse
traversal. Related incidents and memory applicability are matches over shared `Signal` nodes. Evidence paths are
stored relationships. With FalkorDB stopped, every graph endpoint returns 503 and there is no fallback answer
(verified: `scripts/e2e_check.py --phase down`, `test_graph_removal_breaks_investigation`). With the graph deleted,
the same investigation returns 404.

## Setup

Prerequisites: Docker (Compose v2), Python ≥ 3.11 (tested on 3.13.7), Node ≥ 20 (tested on 24.14.1).

```bash
git clone <repo> faultline && cd faultline
cp .env.example .env                        # defaults work locally; no API key needed

docker compose up -d falkordb               # FalkorDB on :6379, FalkorDB Browser on :3000

python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"               # add ,llm for the optional narrator

# Load the graph from the committed processed data (no download needed):
python scripts/ingest.py --skip-features --load-graph
#   or re-derive everything from the public dataset:
#   python scripts/ingest.py --mode sample --load-graph             (6 cases, ~70 MB)
#   python scripts/ingest.py --mode full --reps 1 2 3 --load-graph   (90 cases, ~880 MB)

cd backend && uvicorn app.main:app --port 8000        # API: http://localhost:8000/docs
cd frontend && npm ci && npm run dev                   # UI:  http://localhost:5173
```

### Environment variables (`.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_PASSWORD` | localhost / 6379 / empty | database connection |
| `FAULTLINE_GRAPH` | faultline | graph name (validated `[A-Za-z0-9_-]`) |
| `FAULTLINE_MAX_DEPTH` | 6 | upper bound for traversal depth (1–10) |
| `FAULTLINE_QUERY_TIMEOUT_MS` | 5000 | per-query timeout |
| `FAULTLINE_DATA_DIR` | data | data root |
| `FAULTLINE_LOG_LEVEL` | INFO | JSON-lines logging |
| `FAULTLINE_LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `FAULTLINE_LLM_MODEL`, `FAULTLINE_LLM_TIMEOUT_S` | empty, empty, claude-opus-5-5, 20 | optional narrator |
| `VITE_API_BASE` | http://localhost:8000 | Vite dev-server proxy target |

## Tests and evaluation

```bash
cd backend && pytest                    # 58 tests; integration tests need FalkorDB running (they fail, not skip, without it)
pytest -m "not integration"             # unit tests only
python scripts/evaluate.py              # ablation on a fresh faultline_eval graph (~40 s)
python scripts/e2e_check.py --phase 1   # live end-to-end; see the script docstring for the restart sequence
cd frontend && npm run build            # strict TypeScript check + production build
```
Latest results: [`TEST_REPORT.md`](TEST_REPORT.md).

## Data sources and licenses

| Source | Use | License |
|---|---|---|
| [RCAEval](https://github.com/phamquiluan/RCAEval), HF `phamquiluan/RCAEval` @ `afeacb11` | 90 RE2-OB failure cases (observed telemetry; labels for evaluation only) | MIT |
| [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) manifests | architecture `DEPENDS_ON` edges | Apache-2.0 |
| [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) | architecture cross-reference (name mapping only) | Apache-2.0 |
| `data/scenarios/` | 7 hand-written synthetic scenarios (deployments, prior repairs, look-alikes) | this repository |

Provenance per record: [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md). Code license: choose one before publishing
(see `KNOWN_LIMITATIONS.md`).

## Troubleshooting

- `/health` returns 503 `database unavailable`: run `docker compose up -d falkordb`. "Redis is loading" clears
  after a few seconds.
- Integration tests error with `GraphUnavailableError`: FalkorDB isn't running on `FALKORDB_PORT`.
- UI shows "backend unreachable": start uvicorn on :8000, or set `VITE_API_BASE`.
- Windows: if pip fails with `WinError 32` inside the venv, recreate the venv (an antivirus file lock).

## Limitations

See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). In short: repair outcomes are simulated; deployments, prior
repairs and look-alike incidents exist only in synthetic scenarios; RCAEval has 5 root-cause services with repeated
faults (favourable for memory); cross-service memories can mislead; persistence uses RDB snapshots (up to 60 s loss
on a hard crash).

## AI coding assistant disclosure

This project was implemented with **Claude Code** (Anthropic, model Claude Opus 5.5). It wrote the code, tests and
documentation under the direction of the project owner, following a staged, test-driven plan
(`IMPLEMENTATION_PLAN.md`, `PROGRESS.md`). Every reported number comes from scripts in this repository that were
actually run (`TEST_REPORT.md`). The optional runtime narrator can also call Claude; it is off by default and
cannot add evidence.
