"""Graph integrity checks. Problems are reported, never auto-repaired."""

from __future__ import annotations

from app.graph.client import GraphClient
from app.graph.schema import FORBIDDEN_PROPERTIES, UNIQUE_KEYS


def check_integrity(client: GraphClient) -> dict:
    problems: list[str] = []
    info: dict = {}

    for label, key in UNIQUE_KEYS.items():
        r = client.ro_query(f"MATCH (n:{label}) RETURN count(n) AS total, count(DISTINCT n.{key}) AS uniq, "
                            f"sum(CASE WHEN n.{key} IS NULL THEN 1 ELSE 0 END) AS nulls")
        total, uniq, nulls = r[0]["total"], r[0]["uniq"], r[0]["nulls"]
        info[label] = total
        if total != uniq + nulls or nulls:
            problems.append(f"{label}: {total} nodes but {uniq} distinct {key} ({nulls} null)")

    r = client.ro_query("MATCH (o:Observation) WHERE NOT (o)-[:OBSERVED_ON]->(:Service) "
                        "RETURN collect(o.id)[0..10] AS ids, count(o) AS n")
    if r and r[0]["n"]:
        problems.append(f"{r[0]['n']} observations without OBSERVED_ON service, e.g. {r[0]['ids']}")

    r = client.ro_query("MATCH (o:Observation) WHERE NOT (:Incident)-[:HAS_OBSERVATION]->(o) RETURN count(o) AS n")
    if r and r[0]["n"]:
        problems.append(f"{r[0]['n']} orphan observations (no incident)")

    r = client.ro_query("MATCH (i:Incident) WHERE NOT (i)-[:HAS_OBSERVATION]->() RETURN collect(i.id) AS ids")
    if r and r[0]["ids"]:
        problems.append(f"incidents without observations: {r[0]['ids']}")

    r = client.ro_query("MATCH (s:Service) WHERE NOT (:System)-[:CONTAINS]->(s) RETURN collect(s.name) AS names")
    if r and r[0]["names"]:
        problems.append(f"services not attached to a System: {r[0]['names']}")

    keys = client.ro_query("CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS keys")
    leaked = sorted(set(keys[0]["keys"]) & FORBIDDEN_PROPERTIES) if keys else []
    if leaked:
        problems.append(f"ground-truth-like property keys present in graph: {leaked}")

    # Informational: where trace observations and architecture disagree.
    r = client.ro_query("MATCH (a:Service)-[c:CALLS]->(b:Service) WHERE NOT (a)-[:DEPENDS_ON]->(b) "
                        "RETURN collect(a.name + '->' + b.name) AS e")
    info["calls_not_in_architecture"] = r[0]["e"] if r else []
    r = client.ro_query("MATCH (a:Service)-[d:DEPENDS_ON]->(b:Service) WHERE NOT (a)-[:CALLS]->(b) "
                        "RETURN collect(a.name + '->' + b.name) AS e")
    info["architecture_edges_never_traced"] = r[0]["e"] if r else []
    rels = client.ro_query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY t")
    info["relationships"] = {x["t"]: x["n"] for x in rels}
    return {"ok": not problems, "problems": problems, "counts": info}
