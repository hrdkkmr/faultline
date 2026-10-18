"""Idempotent graph loading: architecture topology + incident evidence.

All writes use MERGE on unique keys, so re-running ingestion never duplicates entities.
Service nodes come only from the architecture definition. Evidence that references an unknown
service is NOT silently given a new Service node: the missing link is reported.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.graph import architecture as arch
from app.graph.client import GraphClient
from app.graph.integrity import check_integrity
from app.graph.schema import ensure_schema

log = logging.getLogger("faultline.graph.loader")

_OBS_FIELDS = ("id", "incident_id", "kind", "service", "signal", "score", "direction", "anomalous",
               "baseline", "observed", "onset_s", "raw_ref", "samples", "caller", "source")


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """FalkorDB properties cannot be null/NaN; drop those keys explicitly."""
    out = {}
    for k, v in d.items():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        out[k] = v
    return out


def signal_key(service: str, signal: str, direction: str) -> str:
    return f"{service}|{signal}|{direction}"


def call_observations(ev: dict) -> list[dict]:
    """Per-incident caller->callee latency change, derived from the trace `calls` records."""
    out = []
    for c in ev.get("calls", []):
        b, a = c.get("p90_us_before"), c.get("p90_us_after")
        if b is None or a is None or c["calls_before"] < 20 or c["calls_after"] < 20:
            continue
        ratio = (a + 1) / (b + 1)
        score = round(3 * abs(math.log2(ratio)), 3)
        out.append({
            "id": f"{ev['incident_id']}:call:{c['caller']}->{c['callee']}:latency_p90",
            "kind": "call", "service": c["callee"], "caller": c["caller"], "signal": "call_latency_p90",
            "score": score, "direction": "up" if ratio > 1 else "down", "anomalous": score >= 3.0,
            "baseline": b, "observed": a, "raw_ref": f"traces.parquet#{c['caller']}->{c['callee']}",
        })
    return out


def load_architecture(client: GraphClient) -> dict:
    client.query(
        "MERGE (s:System {id: $id}) SET s.name = $name, s.source = 'architecture', s.ref = $ref",
        {"id": arch.SYSTEM_ID, "name": "Online Boutique", "ref": arch.MANIFEST_REF},
    )
    rows = [{"name": n, **meta} for n, meta in arch.SERVICES.items()]
    client.query(
        """
        UNWIND $rows AS r
        MERGE (s:Service {name: r.name})
        SET s.kind = r.kind, s.language = r.language, s.otel_counterpart = r.otel_counterpart,
            s.system = $sys, s.source = 'architecture'
        WITH s
        MATCH (sys:System {id: $sys})
        MERGE (sys)-[:CONTAINS]->(s)
        """,
        {"rows": rows, "sys": arch.SYSTEM_ID},
    )
    edges = [{"a": a, "b": b, "evidence": ev} for a, b, ev in arch.DEPENDS_ON]
    res = client.query(
        """
        UNWIND $edges AS e
        MATCH (a:Service {name: e.a}), (b:Service {name: e.b})
        MERGE (a)-[d:DEPENDS_ON]->(b)
        SET d.source = 'architecture', d.evidence = e.evidence, d.ref = $ref
        RETURN count(d) AS n
        """,
        {"edges": edges, "ref": arch.MANIFEST_REF},
    )
    return {"services": len(rows), "depends_on": res[0]["n"] if res else 0}


def load_incident(client: GraphClient, ev: dict) -> dict:
    inc = ev["incident_id"]
    source = ev.get("source", "rcaeval")
    detected = int(ev["detected_at"])
    props = _clean({
        "id": inc,
        "source": source,
        "system": ev.get("system", arch.SYSTEM_ID),
        "dataset": ev.get("dataset"),
        "detected_at": detected,
        "detected_at_iso": datetime.fromtimestamp(detected, tz=timezone.utc).isoformat(),
        "window_start": ev.get("window", {}).get("start"),
        "window_end": ev.get("window", {}).get("end"),
        "has_metrics": ev.get("telemetry", {}).get("metrics", False),
        "has_logs": ev.get("telemetry", {}).get("logs", False),
        "has_traces": ev.get("telemetry", {}).get("traces", False),
        "title": ev.get("title") or f"Anomaly in Online Boutique detected "
                                     f"{datetime.fromtimestamp(detected, tz=timezone.utc):%Y-%m-%d %H:%M} UTC",
        "description": ev.get("description"),
        "provenance": ev.get("provenance_note") or (
            f"RCAEval {ev.get('dataset')} via HF {ev.get('provenance', {}).get('hf_repo')}"
            f"@{str(ev.get('provenance', {}).get('revision', ''))[:12]}" if source == "rcaeval" else "synthetic scenario"
        ),
    })
    client.query(
        """
        MERGE (i:Incident {id: $id})
        ON CREATE SET i.status = 'open'
        SET i += $props
        WITH i
        MATCH (s:System {id: $sys})
        MERGE (i)-[:IN_SYSTEM]->(s)
        """,
        {"id": inc, "props": props, "sys": props["system"]},
    )

    obs = []
    for o in list(ev["observations"]) + call_observations(ev):
        row = {k: o.get(k) for k in _OBS_FIELDS}
        row["incident_id"] = inc
        row["source"] = o.get("source") or ("trace" if o["kind"] in ("trace", "call") else source)
        if row["source"] == "trace" and source == "synthetic":
            row["source"] = "synthetic"
        if row.get("samples") == []:
            row["samples"] = None
        obs.append(_clean(row))

    client.query(
        """
        UNWIND $rows AS r
        MERGE (o:Observation {id: r.id})
        SET o += r
        WITH o
        MATCH (i:Incident {id: $inc})
        MERGE (i)-[:HAS_OBSERVATION]->(o)
        """,
        {"rows": obs, "inc": inc},
    )
    linked = client.query(
        """
        UNWIND $rows AS r
        MATCH (o:Observation {id: r.id}), (s:Service {name: r.service})
        MERGE (o)-[:OBSERVED_ON]->(s)
        RETURN collect(DISTINCT r.id) AS ids
        """,
        {"rows": [{"id": o["id"], "service": o["service"]} for o in obs]},
    )
    linked_ids = set(linked[0]["ids"]) if linked else set()
    unlinked = sorted({o["service"] for o in obs if o["id"] not in linked_ids})

    client.query(
        """
        UNWIND $rows AS r
        MATCH (o:Observation {id: r.id}), (caller:Service {name: r.caller})
        MERGE (o)-[:FROM_CALLER]->(caller)
        """,
        {"rows": [{"id": o["id"], "caller": o["caller"]} for o in obs if o.get("caller")]},
    )

    anomalous = [
        {"id": o["id"], "key": signal_key(o["service"], o["signal"], o["direction"]),
         "service": o["service"], "signal": o["signal"], "direction": o["direction"]}
        for o in obs if o.get("anomalous") and o["id"] in linked_ids
    ]
    client.query(
        """
        UNWIND $rows AS r
        MERGE (g:Signal {key: r.key})
        SET g.service = r.service, g.signal = r.signal, g.direction = r.direction
        WITH g, r
        MATCH (o:Observation {id: r.id}), (s:Service {name: r.service})
        MERGE (o)-[:OF_SIGNAL]->(g)
        MERGE (g)-[:ON]->(s)
        """,
        {"rows": anomalous},
    )

    # Aggregated trace-observed call edges (distinct from architecture DEPENDS_ON).
    calls = [{"a": c["caller"], "b": c["callee"]} for c in ev.get("calls", [])]
    client.query(
        """
        UNWIND $rows AS r
        MATCH (a:Service {name: r.a}), (b:Service {name: r.b})
        MERGE (a)-[c:CALLS]->(b)
        ON CREATE SET c.incidents = [], c.source = $src
        SET c.incidents = CASE WHEN $inc IN c.incidents THEN c.incidents ELSE c.incidents + [$inc] END
        SET c.observed_in = size(c.incidents)
        """,
        {"rows": calls, "inc": inc, "src": "trace" if source == "rcaeval" else "synthetic"},
    )

    for d in ev.get("deployments", []):
        load_deployment(client, d)

    return {"incident_id": inc, "observations": len(obs), "anomalous": len(anomalous),
            "calls": len(calls), "unlinked_services": unlinked}


def load_deployment(client: GraphClient, d: dict) -> None:
    props = _clean({k: d.get(k) for k in ("id", "service", "version", "previous_version", "at",
                                         "description", "change_type")})
    props["source"] = d.get("source", "synthetic")
    client.query(
        """
        MERGE (d:Deployment {id: $id})
        SET d += $props
        WITH d
        MATCH (s:Service {name: $svc})
        MERGE (d)-[:CHANGED]->(s)
        """,
        {"id": d["id"], "props": props, "svc": d["service"]},
    )


def load_all(settings: Settings, reset: bool = False, client: GraphClient | None = None,
             include_scenarios: bool = True) -> dict:
    from app.ingestion.pipeline import load_processed

    client = client or GraphClient(settings)
    if reset:
        client.delete_graph()
    schema = ensure_schema(client)
    a = load_architecture(client)
    incidents = [load_incident(client, ev) for ev in load_processed(settings.data_path)]
    scen = []
    if include_scenarios:
        from app.simulation.scenarios import load_scenarios_into_graph

        scen = load_scenarios_into_graph(client, settings.data_path)
    integ = check_integrity(client)
    return {
        "graph": client.graph_name,
        "schema": schema,
        "architecture": a,
        "rcaeval_incidents": len(incidents),
        "synthetic_incidents": len(scen),
        "unlinked": {x["incident_id"]: x["unlinked_services"] for x in incidents + scen if x["unlinked_services"]},
        "integrity": integ,
    }
