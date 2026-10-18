"""Ingest RCAEval RE2-OB cases (and synthetic scenarios) into Faultline.

Usage (from repo root, venv active):
  python scripts/ingest.py --mode sample            # 6 cases, ~70 MB download
  python scripts/ingest.py --mode full --reps 1 2   # 60 cases, ~650 MB download (default eval set)
  python scripts/ingest.py --mode full --skip-download --load-graph
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.ingestion import pipeline, rcaeval  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["sample", "full"], default="sample")
    ap.add_argument("--reps", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--skip-download", action="store_true", help="use already-downloaded raw files only")
    ap.add_argument("--skip-features", action="store_true", help="reuse data/processed (no raw files needed)")
    ap.add_argument("--load-graph", action="store_true", help="load processed evidence into FalkorDB")
    ap.add_argument("--reset-graph", action="store_true", help="delete the graph before loading")
    args = ap.parse_args()

    s = get_settings()
    configure_logging(s.log_level)
    if not args.skip_features:
        rep = pipeline.run(s.data_path, rcaeval.Selection(args.mode, args.reps), download=not args.skip_download)
        print(json.dumps({k: rep[k] for k in ("selection", "cases_selected", "cases_loaded",
                                              "telemetry_available", "elapsed_s")}, indent=2))
        if rep["cases_rejected"]:
            print("REJECTED:", json.dumps(rep["cases_rejected"], indent=2))
        if rep["cases_loaded"] == 0:
            print("ERROR: no cases loaded", file=sys.stderr)
            return 2
    if args.load_graph:
        from app.graph.loader import load_all

        summary = load_all(s, reset=args.reset_graph)
        print(json.dumps(summary, indent=2))
        if summary.get("integrity", {}).get("problems"):
            print("INTEGRITY PROBLEMS:", summary["integrity"]["problems"], file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
