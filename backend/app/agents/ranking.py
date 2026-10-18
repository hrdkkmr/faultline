"""Deterministic hypothesis scoring. Pure functions (no I/O) so they can be unit-tested.

Inputs are graph-derived facts gathered by the investigator through Cypher:
- anomalous observations per service (from the incident's Observation nodes),
- shortest dependency paths among anomalous services (DEPENDS_ON | CALLS),
- applicable memories (Memory-[:APPLIES_UNDER]->Signal matching).

Scores (documented in docs/architecture.md; weights fixed before evaluation on the history split):
  strength(o)   = w(signal) * min(1, ln(1+score) / ln(1+1000))
  local(s)      = max strength over s's anomalous observations + 0.05 * min(4, #distinct signals - 1)
                  (resource metrics going DOWN count at half weight as symptoms of reduced load)
  explains(s,t) = 1.0  if t transitively depends on s and t has no local resource anomaly
                  0.5  if t transitively depends on s but t also has a local resource anomaly
                  0.7  if s directly calls t and t shows latency/error symptoms only
                       (a fault on the caller side makes its outgoing calls look slow), and t has
                       no anomalous dependency of its own that could explain it
                  0    otherwise
  coverage(s)   = sum_t local(t) * explains(s,t) / sum_t local(t)       (t != s, anomalous)
  A (incident only)  = local(s)
  B (graph)          = 0.5 * local(s) + 0.5 * coverage(s)   [+0.15 if s was deployed <=1h before detection]
  C (graph + memory) = B + 0.3 * max(coverage of applicable resolved memories about s)
Temporal precedence and deployments are weak signals and never treated as proof of causation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.simulation.catalog import ERROR_SIGNALS, LATENCY_SIGNALS, RESOURCE_SIGNALS

SIGNAL_WEIGHTS = {
    "cpu": 1.0, "mem": 1.0, "diskio": 1.0, "socket": 1.0,
    "latency-50": 0.8, "latency-90": 0.8, "error": 0.8, "log_errors": 0.8, "span_errors": 0.8,
    "span_latency_p90": 0.7, "call_latency_p90": 0.6, "log_volume": 0.4, "workload": 0.3,
}
W_LOCAL, W_COVERAGE, W_DEPLOY, W_MEMORY = 0.5, 0.5, 0.15, 0.3
INCONCLUSIVE_BELOW = 0.25  # local evidence of the top candidate (≈ max robust z of 5 on a resource signal)


def strength(signal: str, score: float) -> float:
    return SIGNAL_WEIGHTS.get(signal, 0.5) * min(1.0, math.log1p(max(0.0, score)) / math.log1p(1000.0))


@dataclass
class Candidate:
    service: str
    observations: list[dict] = field(default_factory=list)  # anomalous observations on this service
    local: float = 0.0
    resource: float = 0.0
    symptom: float = 0.0
    coverage: float = 0.0
    deploy: float = 0.0
    memory: float = 0.0
    total: float = 0.0
    explained: list[str] = field(default_factory=list)
    explained_paths: list[dict] = field(default_factory=list)
    memories: list[str] = field(default_factory=list)


def build_candidates(observations: list[dict]) -> dict[str, Candidate]:
    cands: dict[str, Candidate] = {}
    for o in observations:
        if not o.get("anomalous") or not o.get("linked_service"):
            continue
        c = cands.setdefault(o["linked_service"], Candidate(o["linked_service"]))
        c.observations.append(o)
    for c in cands.values():
        # A resource metric going DOWN (fewer sockets, less CPU) reflects reduced incoming load, i.e. a
        # downstream effect of a problem elsewhere; only resource increases count as local saturation.
        st = []
        for o in c.observations:
            v = strength(o["signal"], o["score"])
            is_res = o["signal"] in RESOURCE_SIGNALS and o["direction"] == "up"
            st.append((o["signal"], v if is_res or o["signal"] not in RESOURCE_SIGNALS else 0.5 * v, is_res))
        c.resource = max([v for _, v, r in st if r] or [0.0])
        c.symptom = max([v for _, v, r in st if not r] or [0.0])
        n_sig = len({s for s, _, _ in st})
        c.local = max(v for _, v, _ in st) + 0.05 * min(4, n_sig - 1)
    return cands


def _symptom_only(c: Candidate) -> bool:
    """No local saturation; only latency/error symptoms or reduced-load (resource down) signals."""
    sigs = {o["signal"] for o in c.observations}
    reduced = any(o["signal"] in RESOURCE_SIGNALS and o["direction"] == "down" for o in c.observations)
    return c.resource == 0.0 and (bool(sigs & (LATENCY_SIGNALS | ERROR_SIGNALS)) or reduced)


def apply_coverage(cands: dict[str, Candidate], paths: list[dict]) -> None:
    """paths: rows of ANOMALY_SUBGRAPH_PATHS (caller, callee, depth, path, ...)."""
    reach = {(p["caller"], p["callee"]): p for p in paths}
    for s, cs in cands.items():
        num = den = 0.0
        for t, ct in cands.items():
            if t == s:
                continue
            den += ct.local
            e, why = 0.0, None
            if (t, s) in reach:  # t depends on s (s is downstream of t)
                e = 0.5 if ct.resource > 0 else 1.0
                why = reach[(t, s)]
            elif (s, t) in reach and reach[(s, t)]["depth"] == 1 and _symptom_only(ct) \
                    and not any((t, u) in reach for u in cands if u not in (s, t)):
                # caller fan-out: only for callees whose symptoms are not explainable by an anomalous
                # dependency of their own (avoid attributing one symptom to two causes)
                e = 0.7
                why = reach[(s, t)]
            if e > 0:
                num += ct.local * e
                cs.explained.append(t)
                cs.explained_paths.append({**why, "explains": t, "weight": e})
        cs.coverage = num / den if den > 0 else 0.0


def apply_deployments(cands: dict[str, Candidate], deployed_services: set[str]) -> None:
    for s, c in cands.items():
        c.deploy = W_DEPLOY if s in deployed_services else 0.0


def apply_memory(cands: dict[str, Candidate], matches: list) -> None:
    for c in cands.values():
        best = 0.0
        for m in matches:
            if m.service != c.service or m.outcome != "resolved" or m.verdict == "rejected":
                continue
            w = m.coverage * (0.5 if m.verdict == "partial" else 1.0)
            if w > 0:
                c.memories.append(m.memory_id)
            best = max(best, w)
        c.memory = W_MEMORY * best


def total(c: Candidate, mode: str, n_candidates: int) -> float:
    if mode == "A_incident_only":
        return c.local
    base = W_LOCAL * c.local + W_COVERAGE * c.coverage if n_candidates > 1 else c.local
    base += c.deploy
    if mode == "C_graph_memory":
        base += c.memory
    return base


def rank(cands: dict[str, Candidate], mode: str) -> list[Candidate]:
    n = len(cands)
    for c in cands.values():
        c.total = round(total(c, mode, n), 4)
    # Deterministic tie-break: total, then local evidence, then name.
    return sorted(cands.values(), key=lambda c: (-c.total, -c.local, c.service))


def fault_class(c: Candidate) -> tuple[str, str]:
    """Infer a fault class from the candidate's own anomalies. Returns (class, basis)."""
    by: dict[str, float] = {}
    for o in c.observations:
        by[o["signal"]] = max(by.get(o["signal"], 0.0), strength(o["signal"], o["score"]))
    if by.get("diskio", 0) > 0:
        return "disk", f"diskio anomalous (strength {by['diskio']:.2f})"
    res = {k: by.get(k, 0.0) for k in ("cpu", "mem", "socket")}
    top_res, v = max(res.items(), key=lambda kv: kv[1])
    lat = max([by.get(k, 0.0) for k in LATENCY_SIGNALS] or [0.0])
    err = max([by.get(k, 0.0) for k in ERROR_SIGNALS] or [0.0])
    if c.deploy and v < 0.5:
        return "deployment_regression", (f"deployed <=1h before detection and no dominant resource anomaly "
                                         f"(resource {v:.2f}); temporal coincidence only")
    if v >= 0.5 and v >= 0.8 * lat:
        return {"cpu": "cpu", "mem": "memory", "socket": "socket"}[top_res], \
            f"{top_res} is the dominant local resource anomaly (strength {v:.2f}, latency {lat:.2f})"
    if lat > 0 or err > 0:
        return "network", f"latency/error symptoms (latency {lat:.2f}, errors {err:.2f}) dominate local resources ({v:.2f})"
    if v > 0:
        return {"cpu": "cpu", "mem": "memory", "socket": "socket"}[top_res], f"weak {top_res} anomaly ({v:.2f})"
    return "unknown", "no characteristic signal"
