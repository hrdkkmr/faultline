"""Run the A/B/C ablation on a fresh evaluation graph and write results.

  python scripts/evaluate.py            # writes data/eval/results/ablation_results.json + ablation_report.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.evaluation.runner import run  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402


def main() -> int:
    s = get_settings()
    configure_logging("WARNING")
    res = run(s, s.data_path / "eval" / "results")
    print(json.dumps({"test": res["test_summary"], "validation": res["validation_summary"], "synthetic": res["synthetic_summary"],
                      "leakage_issues": res["leakage_issues"], "integrity_ok": res["integrity_ok"],
                      "elapsed_s": res["elapsed_s"]}, indent=1))
    return 1 if res["leakage_issues"] or not res["integrity_ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
