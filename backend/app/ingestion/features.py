"""Feature extraction: raw RCAEval case files -> label-free incident evidence.

Input: one case directory (metrics.parquet, inject_time.txt, optional logs/traces parquet).
Output: a JSON-serializable dict with Observations and trace-observed calls.

This module never reads ground-truth labels. The only time anchor is the detection timestamp
(`inject_time.txt`), used as RCAEval's own baselines do.

Scoring (all deterministic, documented in docs/data-pipeline.md):
- metric: robust z = (x - median_normal) / scale, scale = max(IQR, 1.4826*MAD, 1% |median|, 1e-6).
  score = |75th percentile of z over the post-detection window| (sustained shift, not a spike).
- log: per-service rate of all lines and of error-like lines, before vs after detection.
- trace: per-service span p90 duration before vs after; score = 3 * log2(p90_after / p90_before).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ANOMALY_THRESHOLD = 3.0
METRIC_SIGNALS = ("cpu", "mem", "diskio", "socket", "workload", "error", "latency-50", "latency-90")
RESOURCE_SIGNALS = {"cpu", "mem", "diskio", "socket"}

# Raw service names in RCAEval OB telemetry -> canonical Online Boutique service names.
SERVICE_ALIASES = {
    "frontendservice": "frontend",
    "redis-cart": "redis",
    "redis": "redis",
}
KNOWN_SERVICES = {
    "adservice", "cartservice", "checkoutservice", "currencyservice", "emailservice", "frontend",
    "frontend-external", "paymentservice", "productcatalogservice", "recommendationservice", "redis",
    "shippingservice",
}
_ERROR_RE = re.compile(r"\b(?:error|err|fail(?:ed|ure)?|exception|timeout|timed out|refused|unavailable|panic)\b",
                       re.IGNORECASE)
_NUM_RE = re.compile(r"\d+")
_MAX_MSG = 160


def canon(service: str) -> str:
    s = str(service).strip().lower()
    return SERVICE_ALIASES.get(s, s)


def _robust_scale(x: np.ndarray) -> tuple[float, float]:
    med = float(np.median(x))
    q75, q25 = np.percentile(x, [75, 25])
    mad = float(np.median(np.abs(x - med)))
    scale = max(float(q75 - q25), 1.4826 * mad, 0.01 * abs(med), 1e-6)
    return med, scale


def _sanitize_message(m: str) -> str:
    """Log text is untrusted: collapse whitespace, mask numbers, truncate. Never interpreted."""
    m = " ".join(str(m).split())
    m = _NUM_RE.sub("<n>", m)
    return m[:_MAX_MSG]


def split_metric_column(col: str) -> tuple[str, str] | None:
    for sig in sorted(METRIC_SIGNALS, key=len, reverse=True):
        suffix = "_" + sig
        if col.endswith(suffix):
            return canon(col[: -len(suffix)]), sig
    return None


def metric_observations(m: pd.DataFrame, t0: int, quality: dict) -> list[dict]:
    if "time" not in m.columns:
        raise ValueError("metrics.parquet has no 'time' column")
    m = m.loc[:, ~m.columns.duplicated()].sort_values("time")
    t = m["time"].to_numpy(dtype="int64")
    normal_mask, anom_mask = t < t0, t >= t0
    if normal_mask.sum() < 30 or anom_mask.sum() < 30:
        raise ValueError(f"insufficient metric coverage around detection time "
                         f"(normal={int(normal_mask.sum())}, after={int(anom_mask.sum())})")
    obs = []
    for col in m.columns:
        if col == "time":
            continue
        parsed = split_metric_column(col)
        if parsed is None:
            quality["unparsed_metric_columns"].append(col)
            continue
        svc, sig = parsed
        if svc not in KNOWN_SERVICES:
            quality["unknown_services"].add(svc)
        v = pd.to_numeric(m[col], errors="coerce").to_numpy(dtype="float64")
        vn, va, ta = v[normal_mask], v[anom_mask], t[anom_mask]
        okn, oka = ~np.isnan(vn), ~np.isnan(va)
        if okn.sum() < 10 or oka.sum() < 10:
            quality["sparse_metric_columns"].append(col)
            continue
        med, scale = _robust_scale(vn[okn])
        z = (va[oka] - med) / scale
        z = np.clip(z, -1e3, 1e3)
        q75 = float(np.percentile(z, 75))
        q25 = float(np.percentile(z, 25))
        signed = q75 if abs(q75) >= abs(q25) else q25
        score = abs(signed)
        onset = None
        if score >= ANOMALY_THRESHOLD:
            # first post-detection second where the 15-sample rolling median exceeds the threshold
            roll = pd.Series(np.abs(z)).rolling(15, min_periods=5).median().to_numpy()
            hits = np.nonzero(roll >= ANOMALY_THRESHOLD)[0]
            if hits.size:
                onset = int(ta[oka][hits[0]] - t0)
        obs.append({
            "kind": "metric", "service": svc, "signal": sig,
            "score": round(score, 3), "direction": "up" if signed > 0 else "down",
            "anomalous": score >= ANOMALY_THRESHOLD,
            "baseline": round(med, 6), "observed": round(float(np.median(va[oka])), 6),
            "onset_s": onset, "raw_ref": f"metrics.parquet#{col}",
        })
    return obs


def log_observations(logs: pd.DataFrame, t0: int, t_start: int, t_end: int) -> list[dict]:
    if not {"timestamp", "container_name", "message"} <= set(logs.columns):
        raise ValueError("logs.parquet missing required columns")
    logs = logs.dropna(subset=["timestamp", "container_name"])
    ts = logs["timestamp"].astype("int64").to_numpy()
    span_n = max(t0 - t_start, 1)
    span_a = max(t_end - t0 + 1, 1)
    is_err = logs["message"].fillna("").str.contains(_ERROR_RE)
    out = []
    for raw_svc, g_idx in logs.groupby("container_name").groups.items():
        svc = canon(raw_svc)
        g_ts = ts[logs.index.get_indexer(g_idx)]
        g_err = is_err.loc[g_idx].to_numpy()
        n_norm, n_anom = int((g_ts < t0).sum()), int((g_ts >= t0).sum())
        e_norm, e_anom = int(((g_ts < t0) & g_err).sum()), int(((g_ts >= t0) & g_err).sum())
        r_n, r_a = n_norm / span_n, n_anom / span_a
        er_n, er_a = e_norm / span_n, e_anom / span_a
        vol_ratio = (r_a + 0.05) / (r_n + 0.05)
        vol_score = round(3 * abs(float(np.log2(vol_ratio))), 3)
        err_ratio = (er_a + 0.01) / (er_n + 0.01)
        err_score = round(3 * max(0.0, float(np.log2(err_ratio))), 3) if e_anom >= 5 else 0.0
        samples = []
        if e_anom:
            msgs = logs.loc[g_idx][(g_ts >= t0) & g_err]["message"].map(_sanitize_message)
            samples = msgs.value_counts().head(3).index.tolist()
        out.append({
            "kind": "log", "service": svc, "signal": "log_volume", "score": vol_score,
            "direction": "up" if vol_ratio > 1 else "down", "anomalous": vol_score >= ANOMALY_THRESHOLD,
            "baseline": round(r_n, 4), "observed": round(r_a, 4), "onset_s": None,
            "raw_ref": f"logs.parquet#container_name={raw_svc}",
        })
        out.append({
            "kind": "log", "service": svc, "signal": "log_errors", "score": err_score,
            "direction": "up" if err_ratio > 1 else "down", "anomalous": err_score >= ANOMALY_THRESHOLD,
            "baseline": round(er_n, 4), "observed": round(er_a, 4), "onset_s": None,
            "samples": samples, "raw_ref": f"logs.parquet#container_name={raw_svc}&error_like",
        })
    return out


def trace_features(tr: pd.DataFrame, t0: int) -> tuple[list[dict], list[dict]]:
    need = {"spanID", "parentSpanID", "serviceName", "startTime", "duration"}
    if not need <= set(tr.columns):
        raise ValueError(f"traces.parquet missing columns {sorted(need - set(tr.columns))}")
    tr = tr.dropna(subset=["spanID", "serviceName", "startTime", "duration"]).copy()
    tr["svc"] = tr["serviceName"].map(canon)
    tr["sec"] = (tr["startTime"].astype("int64") // 1_000_000).astype("int64")
    tr["after"] = tr["sec"] >= t0
    status = tr["statusCode"] if "statusCode" in tr.columns else pd.Series(0, index=tr.index)
    tr["err"] = status.fillna(0).astype("int64") != 0

    obs = []
    for svc, g in tr.groupby("svc"):
        gn, ga = g[~g["after"]], g[g["after"]]
        if len(gn) < 20 or len(ga) < 20:
            continue
        p90n = float(np.percentile(gn["duration"], 90))
        p90a = float(np.percentile(ga["duration"], 90))
        ratio = (p90a + 1) / (p90n + 1)
        score = round(3 * abs(float(np.log2(ratio))), 3)
        obs.append({
            "kind": "trace", "service": svc, "signal": "span_latency_p90", "score": score,
            "direction": "up" if ratio > 1 else "down", "anomalous": score >= ANOMALY_THRESHOLD,
            "baseline": round(p90n, 1), "observed": round(p90a, 1), "onset_s": None,
            "raw_ref": f"traces.parquet#serviceName={svc}",
        })
        en, ea = float(gn["err"].mean()), float(ga["err"].mean())
        err_score = round(min(30.0, 100 * max(0.0, ea - en)), 3)
        obs.append({
            "kind": "trace", "service": svc, "signal": "span_errors", "score": err_score,
            "direction": "up" if ea > en else "down", "anomalous": err_score >= ANOMALY_THRESHOLD,
            "baseline": round(en, 5), "observed": round(ea, 5), "onset_s": None,
            "raw_ref": f"traces.parquet#serviceName={svc}&statusCode!=0",
        })

    parents = tr[["spanID", "svc"]].rename(columns={"spanID": "parentSpanID", "svc": "caller"})
    j = tr.dropna(subset=["parentSpanID"]).merge(parents.drop_duplicates("parentSpanID"),
                                                 on="parentSpanID", how="inner")
    j = j[j["caller"] != j["svc"]]
    calls = []
    for (caller, callee), g in j.groupby(["caller", "svc"]):
        gn, ga = g[~g["after"]], g[g["after"]]
        calls.append({
            "caller": caller, "callee": callee,
            "calls_before": int(len(gn)), "calls_after": int(len(ga)),
            "p90_us_before": round(float(np.percentile(gn["duration"], 90)), 1) if len(gn) else None,
            "p90_us_after": round(float(np.percentile(ga["duration"], 90)), 1) if len(ga) else None,
        })
    return obs, calls


def extract_case(case_dir: Path, incident_id: str) -> dict:
    """Build label-free evidence for one case. Raises ValueError on unusable input."""
    if not case_dir.is_dir():
        raise ValueError(f"case directory not found: {case_dir}")
    quality: dict = {"missing_files": [], "unparsed_metric_columns": [], "sparse_metric_columns": [],
                     "unknown_services": set(), "warnings": []}
    for fn in ("metrics.parquet", "inject_time.txt"):
        if not (case_dir / fn).exists():
            raise ValueError(f"required file missing: {fn}")
    try:
        t0 = int((case_dir / "inject_time.txt").read_text().strip())
    except ValueError as e:
        raise ValueError(f"inject_time.txt is not an integer unix timestamp: {e}") from e

    m = pd.read_parquet(case_dir / "metrics.parquet")
    t_start, t_end = int(m["time"].min()), int(m["time"].max())
    if not (t_start < t0 <= t_end):
        raise ValueError(f"detection time {t0} outside metric window [{t_start}, {t_end}]")
    observations = metric_observations(m, t0, quality)
    telemetry = {"metrics": True, "logs": False, "traces": False, "metric_columns": int(m.shape[1] - 1)}

    calls: list[dict] = []
    lp, tp = case_dir / "logs.parquet", case_dir / "traces.parquet"
    if lp.exists():
        observations += log_observations(pd.read_parquet(lp), t0, t_start, t_end)
        telemetry["logs"] = True
    else:
        quality["missing_files"].append("logs.parquet")
    if tp.exists():
        tobs, calls = trace_features(pd.read_parquet(tp), t0)
        observations += tobs
        telemetry["traces"] = True
        traced = sorted({o["service"] for o in tobs})
        untraced = sorted(KNOWN_SERVICES - set(traced) - {"frontend-external"})
        quality["warnings"].append(f"no spans for services: {', '.join(untraced)}")
    else:
        quality["missing_files"].append("traces.parquet")

    # Stable observation IDs: incident + kind + service + signal.
    for o in observations:
        o["id"] = f"{incident_id}:{o['kind']}:{o['service']}:{o['signal']}"
    seen = set()
    for o in observations:
        if o["id"] in seen:
            raise ValueError(f"duplicate observation id {o['id']}")
        seen.add(o["id"])

    quality["unknown_services"] = sorted(quality["unknown_services"])
    return {
        "incident_id": incident_id,
        "source": "rcaeval",
        "system": "online-boutique",
        "dataset": "RE2-OB",
        "detected_at": t0,
        "window": {"start": t_start, "end": t_end, "normal_seconds": t0 - t_start,
                   "after_seconds": t_end - t0 + 1},
        "telemetry": telemetry,
        "observations": observations,
        "calls": calls,
        "quality": quality,
    }
