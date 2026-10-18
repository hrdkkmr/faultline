# Data Provenance

Every graph record carries a `source` property set to one of the categories below.

| Category | `source` value | Origin | License |
|---|---|---|---|
| Observed benchmark data | `rcaeval` | RCAEval RE2-OB, HF parquet mirror `phamquiluan/RCAEval` | MIT (dataset) |
| Architecture-derived relationships | `architecture` | Online Boutique `release/kubernetes-manifests.yaml` (`*_SERVICE_ADDR`, `REDIS_ADDR` env vars) | Apache-2.0 |
| Trace-observed relationships | `trace` | parent/child spans in RCAEval `traces.parquet`, per incident | MIT |
| Synthetic scenario data | `synthetic` | `data/scenarios/*.json`, written for this project | project license |
| Simulated intervention outcomes | `simulator` | `backend/app/simulation`, deterministic rules | project license |
| Evaluation ground truth | *(not in graph)* | `cases.parquet` `root_cause_service`, `fault` → `data/eval/` | MIT |

## Data actually used
- RCAEval RE2-OB repetitions 1, 2, 3 (90 cases, all 5 root-cause services × 6 faults × 3) at HF revision
  `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e`. File sha256 prefixes per case: `data/manifests/rcaeval_manifest.json`.
- Splits: rep 1 history, rep 2 validation, rep 3 test (see `docs/evaluation.md`).
- 7 synthetic scenarios (`scripts/make_scenarios.py`), all IDs prefixed `SYN-` and titles prefixed `[synthetic]`.

## RCAEval (verified by inspection, 2026-10-16)

- `cases.parquet` (735 rows) has the columns `case, dataset, suite, system, system_name,
  root_cause_service, fault, fault_description, repetition, inject_time, n_metrics,
  n_timesteps, time_start, time_end, duration_minutes, normal_timesteps, faulty_timesteps,
  has_logs, n_logs, has_traces, n_traces, has_root_cause_file`.
- RE2-OB case `re2ob_checkoutservice_cpu_1` has:
  - `metrics.parquet`: 1441 rows × 73 columns; `time` + `{service}_{metric}` where
    metric ∈ cpu, mem, diskio, socket, workload, error, latency-50, latency-90.
    `diskio` exists only for adservice, emailservice, recommendationservice and redis.
    `error` exists only for currencyservice, frontend, frontend-external and productcatalogservice.
  - `logs.parquet`: `timestamp` (int64 s), `container_name`, `message`.
  - `traces.parquet`: `time, traceID, spanID, serviceName, methodName, operationName,
    parentSpanID, startTimeMillis, startTime (µs), duration (µs), statusCode`.
    `serviceName` covers only frontendservice, productcatalogservice, currencyservice,
    recommendationservice, checkoutservice, emailservice and paymentservice. Cart, ad,
    shipping and redis have **no spans**. All observed `statusCode` values were 0.
  - `inject_time.txt`: fault injection unix time. The 720 one-second steps before it are "normal".
- **What RCAEval does not provide**: deployments, alerts, remediation actions, repair outcomes,
  affected-service labels. Faultline does not claim any of these come from RCAEval.
- **Label leakage hazard**: case directory names encode `{service}_{fault}`. Faultline assigns
  opaque incident IDs (`INC-` + sha1 prefix). The case name exists only in `data/eval/` and the
  ingestion manifest, never in the graph or in agent inputs.
- `inject_time` is used as the anomaly-detection timestamp, as in RCAEval's own baselines
  (e.g. BARO's `anomaly_detected_timestamp`). It marks *when*, not *where* or *what*.

## Architecture reference

- RCAEval OB uses Google's Online Boutique (service names such as `checkoutservice`, `redis`).
- The OpenTelemetry Astronomy Shop is a later fork with different names (`checkout`, `valkey-cart`,
  plus Kafka, flagd, quote, accounting and fraud-detection). It is a cross-reference only.
  Faultline uses Online Boutique identifiers. The mapping is in `docs/architecture.md`.
