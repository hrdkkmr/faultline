"""Graph schema: labels, unique keys, and constraint/index creation.

FalkorDB requires an exact-match index on the property before a unique constraint can be
created, and unique constraints are created with the `GRAPH.CONSTRAINT` command (not Cypher).
"""

from __future__ import annotations

import logging

import redis.exceptions

from app.graph.client import GraphClient

log = logging.getLogger("faultline.graph.schema")

# label -> unique key property
UNIQUE_KEYS: dict[str, str] = {
    "System": "id",
    "Service": "name",
    "Incident": "id",
    "Observation": "id",
    "Signal": "key",
    "Deployment": "id",
    "Investigation": "id",
    "Hypothesis": "id",
    "Action": "id",
    "Outcome": "id",
    "Memory": "id",
}

EXTRA_INDEXES: list[tuple[str, str]] = [
    ("Observation", "incident_id"),
    ("Incident", "source"),
    ("Deployment", "service"),
    ("Memory", "service"),
]

# Properties that must never appear on any node: they would leak evaluation ground truth.
FORBIDDEN_PROPERTIES = {"root_cause", "root_cause_service", "fault", "fault_type", "case", "case_name",
                        "ground_truth", "label"}


def ensure_schema(client: GraphClient) -> dict:
    created_idx, created_con = 0, 0
    # Ensure the graph key exists before issuing GRAPH.CONSTRAINT.
    client.query("MERGE (s:System {id: $id})", {"id": "__schema_probe__"})
    client.query("MATCH (s:System {id: $id}) DELETE s", {"id": "__schema_probe__"})
    for label, prop in list(UNIQUE_KEYS.items()) + EXTRA_INDEXES:
        try:
            client.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            created_idx += 1
        except Exception as e:  # noqa: BLE001
            if "already indexed" not in str(e).lower():
                raise
    for label, prop in UNIQUE_KEYS.items():
        try:
            client.execute_command("GRAPH.CONSTRAINT", "CREATE", client.graph_name, "UNIQUE", "NODE",
                                   label, "PROPERTIES", "1", prop)
            created_con += 1
        except redis.exceptions.ResponseError as e:
            if "already exists" not in str(e).lower():
                raise
    return {"indexes_created": created_idx, "constraints_created": created_con}


def list_constraints(client: GraphClient) -> list[dict]:
    return client.ro_query("CALL db.constraints() YIELD type, label, properties, status "
                           "RETURN type, label, properties, status")
