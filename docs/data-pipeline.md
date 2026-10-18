# Data pipeline

```
scripts/ingest.py
  └─ app/ingestion/pipeline.run
       1. load cases.parquet (HF phamquiluan/RCAEval @ afeacb11…, pinned)       rcaeval.load_case_index
       2. select RE2-OB cases (sample: 6 | full: chosen repetitions)           rcaeval.select_cases
       3. download only those case folders (~11 MB each, skip if present)     rcaeval.download_cases
       4. manifest (case → opaque INC id, sha256 per file, split) + labels     rcaeval.build_manifest
       5. per case: extract_case → data/processed/rcaeval/INC-*.json            features.extract_case
       6. ingestion report → data/manifests/ingestion_report.json
  └─ --load-graph: app/graph/loader.load_all (schema, architecture, incidents, scenarios, integrity)
```

## Commands

```bash
python scripts/ingest.py --mode sample --load-graph              # 6 cases (~70 MB), quickest start
python scripts/ingest.py --mode full --reps 1 2 3 --load-graph    # 90 cases (~880 MB raw), used for evaluation
python scripts/ingest.py --skip-features --load-graph             # graph only, from committed data/processed
python scripts/make_scenarios.py                                  # regenerate synthetic scenario files
```

`data/processed/` (3.9 MB) and `data/eval/` are committed, so the graph and the evaluation can be rebuilt without
downloading raw telemetry. `data/raw/` is git-ignored.

## Observed results (full run, 2026-10-16)

- 90 RE2-OB cases selected (reps 1–3), 90 loaded, 0 rejected; metrics, logs and traces present in all 90.
- About 107 observations per case, about 14 anomalous on average.
- Recurring data-quality warning in all 90 cases: *no spans for adservice, cartservice, redis, shippingservice*.
- All 9 trace-observed caller→callee pairs exist in the architecture. 7 architecture edges are never traced; all
  involve the untraced services.

## Feature definitions (`features.py`)

| Kind | Signal | Score |
|---|---|---|
| metric | `cpu, mem, diskio, socket, workload, error, latency-50, latency-90` per service | robust z: `(x − median_normal)/scale`, scale = max(IQR, 1.4826·MAD, 1% median, 1e-6), clipped to ±1000; score = \|75th percentile of z after detection\|; onset = first second the 15-sample rolling median exceeds 3 |
| log | `log_volume`, `log_errors` per container | `3·\|log2(rate_after/rate_before)\|` (errors: one-sided, ≥5 lines) |
| trace | `span_latency_p90`, `span_errors` per service | `3·\|log2(p90_after/p90_before)\|`; errors: 100·Δ error rate |
| call | `call_latency_p90` per caller→callee (from parent/child spans; built in the loader) | `3·\|log2\|` of p90 ratio |

An observation is `anomalous` when score ≥ 3. Every observation is stored, including normal ones, so that
contradicting evidence ("resource metrics within baseline") refers to real records.

Service names are canonicalized (`frontendservice`→`frontend`). Unknown services are reported in the quality
report and are **not** created as graph nodes.

## Leakage controls

- Case names encode `{service}_{fault}`. Incidents get `INC-` + sha1 prefix IDs. Case names exist only in the
  manifest and `data/eval/`.
- `extract_case` never reads labels. `inject_time.txt` is used as the detection time, as in RCAEval's baselines.
- `tests/test_stage2_ingestion.py` asserts that no processed file contains its case name or label keys.
- The integrity check fails if label-like property keys reach the graph.
- Synthetic scenarios: visible evidence and hidden truth live in separate files (`data/scenarios/` vs
  `data/eval/scenario_truth.json`). The validator rejects visible files that contain truth fields.

## Splits

| Repetition | Split | Use |
|---|---|---|
| 1 | history | weight development; memory seeding |
| 2 | validation | failure analysis after the v1 evaluation (see `docs/evaluation.md`) |
| 3 | test | untouched until the frozen configuration was evaluated once |

## Idempotency and failure behaviour

- Re-running ingestion or loading MERGEs on unique keys. The test suite asserts identical node and relationship
  counts after a second load.
- Re-running with a different selection removes stale processed files, so processed data, labels and manifest
  always describe the same case set.
- Missing files, a non-integer `inject_time.txt`, a detection time outside the metric window, or too little coverage
  reject the case with a reason in the report. A changed `cases.parquet` schema raises `IngestionError`.
