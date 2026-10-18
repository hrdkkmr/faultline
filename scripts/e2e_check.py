"""End-to-end check against a RUNNING backend (default http://localhost:8000).

  python scripts/e2e_check.py --phase 1     # investigate, inspect evidence, simulate a failing action
  (restart the backend and `docker compose restart falkordb`)
  python scripts/e2e_check.py --phase 2     # fresh session: memory retrieved, misleading memory rejected
  (stop FalkorDB)
  python scripts/e2e_check.py --phase down  # graph-dependent endpoints must fail with 503

Exits non-zero on the first failed check. State between phases is kept in the graph only.
"""

from __future__ import annotations

import argparse
import sys

import httpx

FAILED = False


def check(cond: bool, msg: str) -> None:
    global FAILED
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILED = True


def phase1(c: httpx.Client) -> None:
    h = c.get("/health")
    check(h.status_code == 200 and h.json()["database"]["status"] == "ok", f"health ok ({h.json()['database']})")
    n = len(c.get("/api/incidents").json())
    check(n >= 97, f"{n} incidents in graph (90 RCAEval + 7 synthetic expected)")
    rcaeval = [i for i in c.get("/api/incidents").json() if i["source"] == "rcaeval"][0]["id"]
    r = c.post(f"/api/incidents/{rcaeval}/investigate", json={"mode": "C_graph_memory"}, timeout=60).json()
    check(bool(r["hypotheses"]) and bool(r["hypotheses"][0]["supporting_evidence"]),
          f"real RCAEval incident {rcaeval} investigated -> {r['suspected_root_cause']}")
    r = c.post("/api/incidents/SYN-checkout-socket-1/investigate", json={"mode": "C_graph_memory"}).json()
    check(r["suspected_root_cause"] == "checkoutservice", "multi-hop investigation: checkoutservice suspected")
    ev = c.get(f"/api/hypotheses/{r['hypotheses'][0]['id']}/evidence").json()
    check(any(p["path"][-1] == "checkoutservice" for p in ev["symptom_paths"]),
          f"evidence path(s): {[' -> '.join(p['path']) for p in ev['symptom_paths']]}")
    check(any(m["verdict"] == "recommended" for m in r["candidate_mitigations"]), "candidate mitigations generated")
    s = c.post("/api/incidents/SYN-checkout-socket-1/actions/simulate",
               json={"type": "scale_out", "target": "checkoutservice", "idempotency_key": "e2e"}).json()
    check(s["outcome"]["result"] == "not_resolved", f"simulated scale_out -> {s['outcome']['result']} ({s['memory_id']})")
    s2 = c.post("/api/incidents/SYN-redis-mem-1/actions/simulate",
                json={"type": "restart_service", "target": "redis", "approved": True, "idempotency_key": "e2e"}).json()
    check(s2["outcome"]["result"] == "resolved", f"simulated restart redis -> {s2['outcome']['result']} ({s2['memory_id']})")


def wait_healthy(c: httpx.Client, seconds: int = 300) -> bool:
    import time
    for _ in range(seconds):
        try:
            if c.get("/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def phase2(c: httpx.Client) -> None:
    ok = wait_healthy(c)
    check(ok, "health ok after restarts")
    if not ok:
        return
    mems = c.get("/api/memories").json()
    check(any(m["action_type"] == "scale_out" and m["outcome"] == "not_resolved" for m in mems),
          f"failed-repair memory survived restart ({len(mems)} memories)")
    r = c.post("/api/incidents/SYN-checkout-socket-2/investigate", json={"mode": "C_graph_memory"}).json()
    so = next(m for m in r["candidate_mitigations"] if m["action"]["type"] == "scale_out")
    check(so["verdict"] == "not_recommended" and so["memory_effect"] < 0,
          "later incident: failed scale_out not reused (memory_effect %.2f)" % so["memory_effect"])
    r = c.post("/api/incidents/SYN-redis-mem-2/investigate", json={"mode": "C_graph_memory"}).json()
    check(any(m["verdict"] == "applicable" and m["outcome"] == "resolved" for m in r["memories_considered"]),
          "compatible incident: prior successful repair retrieved as applicable")
    r = c.post("/api/incidents/SYN-cart-deploy/investigate", json={"mode": "C_graph_memory"}).json()
    rej = [m for m in r["memories_considered"] if m["service"] == "redis"]
    check(bool(rej) and all(m["verdict"] == "rejected" for m in rej),
          f"look-alike incident: redis memory rejected ({rej[0]['reasons'] if rej else 'none'})")
    top = next(m for m in r["candidate_mitigations"] if m["verdict"] == "recommended")
    check((top["action"]["type"], top["action"]["target"]) == ("rollback_deployment", "cartservice"),
          f"look-alike incident: top action {top['action']}")
    ev = c.get("/api/evaluation")
    check(ev.status_code == 200 and not ev.json()["leakage_issues"], "evaluation results available, no leakage")


def phase_down(c: httpx.Client) -> None:
    h = c.get("/health")
    check(h.status_code == 503, f"health reports DB down ({h.json()['database']['status']})")
    r = c.post("/api/incidents/SYN-redis-mem-2/investigate", json={})
    check(r.status_code == 503, f"investigation fails visibly without FalkorDB ({r.status_code} {r.json().get('error')})")
    check(c.get("/api/incidents").status_code == 503, "incident list unavailable without FalkorDB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["1", "2", "down"], required=True)
    ap.add_argument("--base", default="http://localhost:8000")
    a = ap.parse_args()
    with httpx.Client(base_url=a.base, timeout=30) as c:
        {"1": phase1, "2": phase2, "down": phase_down}[a.phase](c)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
