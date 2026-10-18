"""End-to-end RCAEval ingestion: select -> download -> manifest -> features -> report.

Outputs (paths relative to the data dir):
  manifests/rcaeval_manifest.json   evaluation-side manifest (case names, hashes, revision)
  eval/rcaeval_labels.json          ground truth, keyed by opaque incident ID (never loaded into the graph)
  processed/rcaeval/<id>.json       label-free evidence per incident (input to the graph loader)
  manifests/ingestion_report.json   discovered / loaded / rejected, telemetry coverage, quality
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from pathlib import Path

from app.ingestion import rcaeval
from app.ingestion.features import extract_case

log = logging.getLogger("faultline.ingest")


def paths(data_dir: Path) -> dict[str, Path]:
    return {
        "raw": data_dir / "raw" / "rcaeval",
        "manifest": data_dir / "manifests" / "rcaeval_manifest.json",
        "labels": data_dir / "eval" / "rcaeval_labels.json",
        "processed": data_dir / "processed" / "rcaeval",
        "report": data_dir / "manifests" / "ingestion_report.json",
    }


def run(data_dir: Path, sel: rcaeval.Selection, download: bool = True) -> dict:
    p = paths(data_dir)
    p["raw"].mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    idx = rcaeval.load_case_index(p["raw"])
    sub = rcaeval.select_cases(idx, sel)
    if download:
        rcaeval.download_cases(list(sub.case), p["raw"])
    manifest, labels = rcaeval.build_manifest(sub, p["raw"], sel)

    loaded, rejected = [], []
    telemetry = Counter()
    warnings = Counter()
    p["processed"].mkdir(parents=True, exist_ok=True)
    for entry in manifest["cases"]:
        inc = entry["incident_id"]
        try:
            ev = extract_case(p["raw"] / entry["case"], inc)
        except (ValueError, OSError) as e:
            rejected.append({"incident_id": inc, "case": entry["case"], "reason": str(e)})
            log.warning("case rejected", extra={"incident_id": inc, "reason": str(e)})
            continue
        ev["provenance"] = {"source": "rcaeval", "hf_repo": rcaeval.HF_REPO, "revision": rcaeval.HF_REVISION,
                            "files": {k: v["sha256"][:16] for k, v in entry["files"].items()}}
        rcaeval.write_json(p["processed"] / f"{inc}.json", ev)
        for k in ("metrics", "logs", "traces"):
            telemetry[k] += int(ev["telemetry"][k])
        for w in ev["quality"]["warnings"]:
            warnings[w] += 1
        loaded.append({"incident_id": inc, "observations": len(ev["observations"]),
                       "anomalous": sum(o["anomalous"] for o in ev["observations"]),
                       "calls": len(ev["calls"]), "telemetry": ev["telemetry"],
                       "quality": ev["quality"]})

    # Only labels of loaded cases are kept; processed files from earlier selections are removed so that
    # processed evidence, labels and manifest always describe the same case set.
    keep = {x["incident_id"] for x in loaded}
    for f in p["processed"].glob("INC-*.json"):
        if f.stem not in keep:
            f.unlink()
    rcaeval.write_json(p["labels"], {k: v for k, v in labels.items() if k in keep})
    rcaeval.write_json(p["manifest"], manifest)

    report = {
        "generated_at": manifest["generated_at"],
        "source": manifest["source"],
        "selection": manifest["selection"],
        "cases_discovered_in_index": int((idx.dataset == rcaeval.DATASET).sum()),
        "cases_selected": len(manifest["cases"]),
        "cases_loaded": len(loaded),
        "cases_rejected": rejected,
        "telemetry_available": dict(telemetry),
        "ground_truth_fields": ["root_cause_service", "fault"],
        "ground_truth_location": "data/eval/rcaeval_labels.json (evaluation only; not in graph)",
        "recurring_warnings": dict(warnings),
        "per_case": loaded,
        "code_version": "faultline 0.1.0",
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    rcaeval.write_json(p["report"], report)
    return report


def load_processed(data_dir: Path) -> list[dict]:
    d = paths(data_dir)["processed"]
    if not d.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(d.glob("INC-*.json"))]
