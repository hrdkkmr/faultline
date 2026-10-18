# data/

| Path | Content | In git |
|---|---|---|
| `raw/rcaeval/` | downloaded RCAEval parquet case folders + `cases.parquet` | no (re-fetch with `scripts/ingest.py`) |
| `processed/rcaeval/INC-*.json` | label-free evidence per incident (graph loader input) | yes |
| `manifests/rcaeval_manifest.json` | case → opaque ID, file hashes, split, dataset revision. **Contains case names (= labels); evaluation-side only** | yes |
| `manifests/ingestion_report.json` | discovered / loaded / rejected, telemetry coverage, quality warnings | yes |
| `scenarios/SYN-*.json` | visible synthetic scenario evidence | yes |
| `eval/rcaeval_labels.json`, `eval/scenario_truth.json` | ground truth, read only by the simulator and the evaluation runner | yes |
| `eval/results/` | ablation results (+ `archive/` for the superseded v1 run) | yes |

The agent reads only the graph. Nothing under `eval/` or `manifests/` is loaded into it.
