"""RCAEval case selection, download and manifest generation.

Ground truth handling: `cases.parquet` contains the label columns `root_cause_service` and
`fault`, and case directory names encode them too. This module is the ONLY place that reads
those columns. It writes them to `data/eval/` (evaluation-side) and gives every case an opaque
incident ID. Nothing downstream that the agent can read receives the case name or the labels.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("faultline.ingest.rcaeval")

HF_REPO = "phamquiluan/RCAEval"
HF_REVISION = "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e"  # dataset commit inspected 2026-10-16
DATASET = "RE2-OB"
REQUIRED_FILES = ("metrics.parquet", "inject_time.txt")
OPTIONAL_FILES = ("logs.parquet", "traces.parquet")

# Sample mode: one case per fault type, spread over all five root-cause services (repetition 1).
SAMPLE_CASES = [
    "re2ob_checkoutservice_cpu_1",
    "re2ob_currencyservice_mem_1",
    "re2ob_emailservice_disk_1",
    "re2ob_productcatalogservice_delay_1",
    "re2ob_recommendationservice_loss_1",
    "re2ob_checkoutservice_socket_1",
]


# Repetition -> evaluation split. rep 1: history (memory seeding, weight development);
# rep 2: validation (failure analysis allowed); rep 3: test (untouched until final evaluation).
SPLITS = {1: "history", 2: "validation", 3: "test"}


class IngestionError(RuntimeError):
    pass


def incident_id_for(case: str) -> str:
    """Stable, opaque, label-free identifier."""
    return "INC-" + hashlib.sha1(f"rcaeval:{case}".encode()).hexdigest()[:10]


@dataclass
class Selection:
    mode: str  # "sample" | "full"
    repetitions: list[int] = field(default_factory=lambda: [1, 2, 3])

    def describe(self) -> str:
        return "sample(6 cases)" if self.mode == "sample" else f"full(RE2-OB reps={self.repetitions})"


def load_case_index(cache_dir: Path) -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    p = hf_hub_download(HF_REPO, "cases.parquet", repo_type="dataset", revision=HF_REVISION,
                        local_dir=str(cache_dir))
    idx = pd.read_parquet(p)
    needed = {"case", "dataset", "root_cause_service", "fault", "repetition", "inject_time",
              "has_logs", "has_traces"}
    missing = needed - set(idx.columns)
    if missing:
        raise IngestionError(f"cases.parquet schema changed; missing columns {sorted(missing)}")
    return idx


def select_cases(idx: pd.DataFrame, sel: Selection) -> pd.DataFrame:
    sub = idx[idx.dataset == DATASET]
    if sel.mode == "sample":
        sub = sub[sub.case.isin(SAMPLE_CASES)]
        if len(sub) != len(SAMPLE_CASES):
            raise IngestionError("sample cases not all present in cases.parquet")
    elif sel.mode == "full":
        sub = sub[sub.repetition.isin(sel.repetitions)]
    else:
        raise IngestionError(f"unknown selection mode {sel.mode!r}")
    return sub.sort_values("case").reset_index(drop=True)


def download_cases(cases: list[str], raw_dir: Path) -> None:
    from huggingface_hub import snapshot_download

    todo = [c for c in cases if not (raw_dir / c / "metrics.parquet").exists()]
    if not todo:
        return
    log.info("downloading cases", extra={"n": len(todo)})
    snapshot_download(HF_REPO, repo_type="dataset", revision=HF_REVISION,
                      allow_patterns=[f"{c}/*" for c in todo], local_dir=str(raw_dir), max_workers=4)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(sub: pd.DataFrame, raw_dir: Path, sel: Selection) -> tuple[dict, dict]:
    """Returns (manifest, labels). The manifest is evaluation-side (it holds case names)."""
    entries, labels = [], {}
    for row in sub.itertuples(index=False):
        inc = incident_id_for(row.case)
        d = raw_dir / row.case
        files = {}
        for fn in REQUIRED_FILES + OPTIONAL_FILES:
            p = d / fn
            if p.exists():
                files[fn] = {"bytes": p.stat().st_size, "sha256": _sha256(p)}
        entries.append({
            "incident_id": inc,
            "case": row.case,
            "dataset": DATASET,
            "repetition": int(row.repetition),
            "split": SPLITS.get(int(row.repetition), "extra"),
            "files": files,
            "index_has_logs": bool(row.has_logs),
            "index_has_traces": bool(row.has_traces),
        })
        labels[inc] = {
            "root_cause_service": row.root_cause_service,
            "fault": row.fault,
            "fault_description": getattr(row, "fault_description", None),
            "dataset": DATASET,
            "repetition": int(row.repetition),
            "source": "rcaeval cases.parquet",
        }
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"hf_repo": HF_REPO, "revision": HF_REVISION, "dataset": DATASET,
                   "license": "MIT (RCAEval datasets)"},
        "selection": sel.describe(),
        "cases": entries,
    }
    return manifest, labels


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False, default=str), encoding="utf-8")
