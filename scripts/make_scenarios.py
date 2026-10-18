"""Generate the synthetic, clearly labeled scenario files.

VISIBLE evidence -> data/scenarios/SYN-*.json   (loaded into the graph)
HIDDEN truth     -> data/eval/scenario_truth.json (simulator + evaluation only)

Every scenario uses the Online Boutique topology. Observation scores are robust-z-like values on
the same scale as the RCAEval features. These are hand-designed controlled cases, not measurements.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"
BASE = 1_788_000_000  # 2026-08-29, ordering only


def o(svc, sig, score, direction="up", kind="metric", samples=None):
    d = {"kind": kind, "service": svc, "signal": sig, "score": score, "direction": direction}
    if samples:
        d["samples"] = samples
    return d


SCENARIOS = [
    {
        "visible": {
            "incident_id": "SYN-redis-mem-1", "detected_at": BASE,
            "title": "[synthetic] Cart and storefront latency rising",
            "description": "Controlled scenario: memory pressure in the cart datastore propagates to callers.",
            "observations": [o("redis", "mem", 420), o("redis", "latency-90", 40), o("cartservice", "latency-90", 180),
                             o("frontend", "latency-90", 60), o("checkoutservice", "latency-90", 25),
                             o("cartservice", "log_errors", 12, kind="log",
                               samples=["Can't access cart storage. StackExchange.Redis.RedisTimeoutException"]),
                             o("cartservice", "cpu", 1.1), o("frontend", "cpu", 0.8)],
        },
        "truth": {"root_cause_service": "redis", "fault": "mem", "expected_affected": ["cartservice", "frontend", "checkoutservice", "frontend-external"],
                  "purpose": "Seed for memory Test A; restarting the victim cartservice must not resolve it."},
    },
    {
        "visible": {
            "incident_id": "SYN-redis-mem-2", "detected_at": BASE + 86400 * 3,
            "title": "[synthetic] Cart latency rising again",
            "description": "Controlled scenario: same failure signature as SYN-redis-mem-1, a few days later.",
            "observations": [o("redis", "mem", 380), o("redis", "latency-90", 33), o("cartservice", "latency-90", 150),
                             o("frontend", "latency-90", 48), o("checkoutservice", "latency-90", 20),
                             o("cartservice", "log_errors", 9, kind="log",
                               samples=["Can't access cart storage. StackExchange.Redis.RedisTimeoutException"])],
        },
        "truth": {"root_cause_service": "redis", "fault": "mem", "expected_affected": ["cartservice", "frontend", "checkoutservice", "frontend-external"],
                  "purpose": "Memory Test A: the earlier successful repair should be retrieved and is applicable."},
    },
    {
        "visible": {
            "incident_id": "SYN-cart-deploy", "detected_at": BASE + 86400 * 5,
            "title": "[synthetic] Cart and storefront latency rising",
            "description": "Controlled scenario: looks like the redis incidents from the storefront, different cause.",
            "observations": [o("cartservice", "latency-90", 170), o("frontend", "latency-90", 55),
                             o("checkoutservice", "latency-90", 22), o("cartservice", "error", 40),
                             o("cartservice", "log_errors", 30, kind="log",
                               samples=["NullReferenceException in CartStore.GetCartAsync (v2.4.0)"]),
                             o("redis", "mem", 0.6), o("redis", "latency-90", 0.4)],
            "deployments": [{"id": "DEP-cart-2.4.0", "service": "cartservice", "version": "2.4.0",
                             "previous_version": "2.3.7", "at": BASE + 86400 * 5 - 600, "change_type": "release",
                             "description": "[synthetic] cart release 2.4.0", "source": "synthetic"}],
        },
        "truth": {"root_cause_service": "cartservice", "fault": "deployment_regression",
                  "expected_affected": ["frontend", "checkoutservice", "frontend-external"],
                  "purpose": "Memory Test B: similar symptoms to the redis incidents, but redis is healthy; the old redis repair must be rejected."},
    },
    {
        "visible": {
            "incident_id": "SYN-payment-unrelated-deploy", "detected_at": BASE + 86400 * 7,
            "title": "[synthetic] Checkout latency rising",
            "description": "Controlled scenario: a recent cart deployment coincides with a checkout slowdown.",
            "observations": [o("paymentservice", "cpu", 260), o("paymentservice", "latency-90", 120),
                             o("checkoutservice", "latency-90", 90), o("frontend", "latency-90", 30),
                             o("cartservice", "latency-90", 0.7), o("cartservice", "cpu", 0.5)],
            "deployments": [{"id": "DEP-cart-2.4.1", "service": "cartservice", "version": "2.4.1",
                             "previous_version": "2.4.0", "at": BASE + 86400 * 7 - 900, "change_type": "release",
                             "description": "[synthetic] cart release 2.4.1", "source": "synthetic"}],
        },
        "truth": {"root_cause_service": "paymentservice", "fault": "cpu",
                  "expected_affected": ["checkoutservice", "frontend", "frontend-external"],
                  "purpose": "Rolling back an unrelated deployment (cart) must not resolve it; scaling payment does."},
    },
    {
        "visible": {
            "incident_id": "SYN-catalog-shared", "detected_at": BASE + 86400 * 9,
            "title": "[synthetic] Storefront, recommendations and checkout slow",
            "description": "Controlled scenario: a shared dependency saturates.",
            "observations": [o("productcatalogservice", "cpu", 310), o("productcatalogservice", "latency-90", 200),
                             o("recommendationservice", "latency-90", 220), o("frontend", "latency-90", 140),
                             o("checkoutservice", "latency-90", 80), o("frontend", "workload", 3.2),
                             o("recommendationservice", "cpu", 0.9)],
        },
        "truth": {"root_cause_service": "productcatalogservice", "fault": "cpu",
                  "expected_affected": ["frontend", "recommendationservice", "checkoutservice", "frontend-external"],
                  "purpose": "Scaling a caller (frontend/recommendation) does not help when the shared dependency is the bottleneck."},
    },
    {
        "visible": {
            "incident_id": "SYN-checkout-socket-1", "detected_at": BASE + 86400 * 11,
            "title": "[synthetic] Checkout errors and latency",
            "description": "Controlled scenario: connection exhaustion in checkout.",
            "observations": [o("checkoutservice", "socket", 240), o("checkoutservice", "cpu", 45),
                             o("checkoutservice", "latency-90", 110), o("frontend", "latency-90", 35),
                             o("frontend", "error", 14)],
        },
        "truth": {"root_cause_service": "checkoutservice", "fault": "socket",
                  "expected_affected": ["frontend", "frontend-external"],
                  "purpose": "Memory Test C seed: an operator scales checkout out (fails); the failure is remembered."},
    },
    {
        "visible": {
            "incident_id": "SYN-checkout-socket-2", "detected_at": BASE + 86400 * 13,
            "title": "[synthetic] Checkout errors and latency again",
            "description": "Controlled scenario: same signature as SYN-checkout-socket-1.",
            "observations": [o("checkoutservice", "socket", 210), o("checkoutservice", "cpu", 40),
                             o("checkoutservice", "latency-90", 95), o("frontend", "latency-90", 30),
                             o("frontend", "error", 11)],
        },
        "truth": {"root_cause_service": "checkoutservice", "fault": "socket",
                  "expected_affected": ["frontend", "frontend-external"],
                  "purpose": "Memory Test C: the failed scale_out must not be treated as a working procedure."},
    },
]


def main() -> None:
    (ROOT / "scenarios").mkdir(parents=True, exist_ok=True)
    (ROOT / "eval").mkdir(parents=True, exist_ok=True)
    truth = {}
    for sc in SCENARIOS:
        v = dict(sc["visible"], source="synthetic", dataset="synthetic")
        (ROOT / "scenarios" / f"{v['incident_id']}.json").write_text(json.dumps(v, indent=2), encoding="utf-8")
        truth[v["incident_id"]] = dict(sc["truth"], source="synthetic scenario definition")
    (ROOT / "eval" / "scenario_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"wrote {len(SCENARIOS)} scenarios")


if __name__ == "__main__":
    main()
