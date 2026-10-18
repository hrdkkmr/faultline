"""Act -> observe -> remember.

`execute_simulated_action` applies an action to the simulator (never to a real system), then writes
the executed Action, its Outcome, and a Memory episode into FalkorDB via `record_incident_outcome`.
Memory is append-only: a contradicting outcome creates a new Memory linked by CONTRADICTS; nothing
is overwritten.
"""

from __future__ import annotations

from app.agents.tools import GraphTools
from app.schemas.models import ActionSpec
from app.simulation.simulator import Simulator


def execute_simulated_action(tools: GraphTools, simulator: Simulator, incident_id: str, action: ActionSpec,
                             approved: bool = False, idempotency_key: str | None = None) -> dict:
    tools._require_incident(incident_id)
    tools._require_service(action.target)
    outcome = simulator.simulate(incident_id, action, approved=approved)
    rec = tools.record_incident_outcome(incident_id, action, outcome, idempotency_key=idempotency_key)
    return {"incident_id": incident_id, "action": action.model_dump(), "outcome": outcome.model_dump(), **rec}


def list_memories(tools: GraphTools, limit: int = 100) -> list[dict]:
    return tools.g.ro_query(
        """
        MATCH (m:Memory)
        OPTIONAL MATCH (m)-[:APPLIES_UNDER]->(g:Signal)
        OPTIONAL MATCH (m)-[:CONTRADICTS]-(o:Memory)
        RETURN m.id AS id, m.derived_from AS derived_from, m.service AS service, m.action_type AS action_type,
               m.outcome AS outcome, m.lesson AS lesson, m.created_at AS created_at, m.source AS source,
               m.incident_source AS incident_source, collect(DISTINCT g.key) AS conditions,
               collect(DISTINCT o.id) AS contradicts
        ORDER BY created_at DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )
