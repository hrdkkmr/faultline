"""Builders for small, synthetic RCAEval-shaped case directories (unit-test fixtures only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

T0 = 1_700_000_000


def make_case(dirpath: Path, *, hot_service: str = "checkoutservice", n: int = 240, with_logs=True,
              with_traces=True, inject_offset: int = 120) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    t = np.arange(T0, T0 + n)
    inject = T0 + inject_offset
    cols = {"time": t}
    for svc in ("checkoutservice", "currencyservice", "frontend", "productcatalogservice"):
        for sig, base in (("cpu", 1.0), ("mem", 100.0), ("latency-90", 10.0)):
            v = base + rng.normal(0, base * 0.02, n)
            if svc == hot_service and sig == "cpu":
                v[t >= inject] += base * 5
            cols[f"{svc}_{sig}"] = v
    pd.DataFrame(cols).to_parquet(dirpath / "metrics.parquet")
    (dirpath / "inject_time.txt").write_text(str(inject))
    if with_logs:
        rows = []
        for ts in t:
            rows.append((int(ts), "frontend", "request started"))
            if ts >= inject:
                rows.append((int(ts), hot_service, f"rpc error: code 14 timeout after {ts % 97} ms"))
        pd.DataFrame(rows, columns=["timestamp", "container_name", "message"]).to_parquet(dirpath / "logs.parquet")
    if with_traces:
        rows = []
        for k, ts in enumerate(t):
            dur_child = 100 + (900 if ts >= inject else 0)
            rows.append(dict(spanID=f"p{k}", parentSpanID=None, serviceName="frontendservice",
                             startTime=int(ts) * 1_000_000, duration=5000, statusCode=0))
            rows.append(dict(spanID=f"c{k}", parentSpanID=f"p{k}", serviceName=hot_service,
                             startTime=int(ts) * 1_000_000 + 10, duration=dur_child, statusCode=0))
        pd.DataFrame(rows).to_parquet(dirpath / "traces.parquet")
    return dirpath
