"""REST API. Every graph-backed endpoint queries FalkorDB; nothing is served from static fixtures."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.agents.investigator import Investigator
from app.agents.llm import make_narrator
from app.agents.tools import GraphTools, NotFoundError, ToolInputError, validate_incident_id
from app.graph import queries as Q
from app.memory.service import execute_simulated_action, list_memories
from app.schemas.models import ActionSpec
from app.simulation.simulator import ApprovalRequired, Simulator, UnknownTruth

router = APIRouter(prefix="/api")


def _tools(req: Request) -> GraphTools:
    return GraphTools(req.app.state.graph)


def _wrap(fn):
    try:
        return fn()
    except ToolInputError as e:
        raise HTTPException(422, str(e)) from e
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ApprovalRequired as e:
        raise HTTPException(403, str(e)) from e
    except UnknownTruth as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


class InvestigateRequest(BaseModel):
    mode: Literal["A_incident_only", "B_graph", "C_graph_memory"] = "C_graph_memory"
    persist: bool = True
    narrate: bool = True


class ActionRequest(BaseModel):
    type: str = Field(pattern=r"^[a-z_]{1,40}$")
    target: str = Field(default="", max_length=41)
    approved: bool = False
    idempotency_key: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]*$")


@router.get("/incidents")
def incidents(req: Request):
    return req.app.state.graph.ro_query(Q.LIST_INCIDENTS)


@router.get("/incidents/{incident_id}")
def incident(incident_id: str, req: Request):
    return _wrap(lambda: _tools(req).inspect_incident(incident_id).model_dump())


@router.post("/incidents/{incident_id}/investigate")
def investigate(incident_id: str, body: InvestigateRequest, req: Request):
    s = req.app.state.graph.settings
    inv = Investigator(_tools(req), narrator=make_narrator(s))
    return _wrap(lambda: inv.investigate(incident_id, body.mode, persist=body.persist,
                                         narrate=body.narrate).model_dump())


@router.get("/incidents/{incident_id}/investigations")
def investigations(incident_id: str, req: Request):
    _wrap(lambda: validate_incident_id(incident_id))
    return req.app.state.graph.ro_query(
        "MATCH (v:Investigation)-[:INVESTIGATED]->(:Incident {id: $id}) "
        "RETURN v.id AS id, v.mode AS mode, v.created_at AS created_at, v.conclusion AS conclusion, "
        "v.top_service AS top_service, v.fault_class AS fault_class, v.confidence AS confidence "
        "ORDER BY created_at DESC", {"id": incident_id})


@router.get("/investigations/{investigation_id}")
def investigation(investigation_id: str, req: Request):
    rows = req.app.state.graph.ro_query("MATCH (v:Investigation {id: $id}) RETURN v.report AS report",
                                        {"id": investigation_id})
    if not rows:
        raise HTTPException(404, f"unknown investigation {investigation_id}")
    return json.loads(rows[0]["report"])


@router.get("/incidents/{incident_id}/graph")
def incident_graph(incident_id: str, req: Request):
    """Topology annotated with this incident's anomalies (for the dependency graph view)."""
    t = _tools(req)
    view = _wrap(lambda: t.inspect_incident(incident_id, only_anomalous=True))
    g = req.app.state.graph
    services = g.ro_query(Q.LIST_SERVICES)
    edges = g.ro_query("MATCH (a:Service)-[r:DEPENDS_ON|CALLS]->(b:Service) RETURN a.name AS source, "
                       "b.name AS target, type(r) AS type, r.source AS provenance, r.evidence AS evidence, "
                       "r.observed_in AS observed_in")
    per = {}
    for o in view.observations:
        if o.linked_service:
            p = per.setdefault(o.linked_service, {"max_score": 0.0, "observations": []})
            p["max_score"] = max(p["max_score"], o.score)
            p["observations"].append(o.id)
    return {"incident_id": incident_id,
            "nodes": [{**s, "anomalous": s["name"] in per, **per.get(s["name"], {"max_score": 0.0, "observations": []})}
                      for s in services],
            "edges": edges}


@router.get("/topology")
def topology(req: Request):
    g = req.app.state.graph
    return {"services": g.ro_query(Q.LIST_SERVICES),
            "edges": g.ro_query("MATCH (a:Service)-[r:DEPENDS_ON|CALLS]->(b:Service) RETURN a.name AS source, "
                                "b.name AS target, type(r) AS type, r.source AS provenance, r.evidence AS evidence, "
                                "r.observed_in AS observed_in")}


@router.get("/services/{service}/dependencies")
def dependencies(service: str, req: Request, depth: int = Query(3, ge=1, le=10),
                 direction: Literal["downstream", "upstream"] = "downstream"):
    return _wrap(lambda: _tools(req).trace_dependencies(service, depth, direction).model_dump())


@router.get("/services/{service}/blast-radius")
def blast_radius(service: str, req: Request, incident_id: str | None = None):
    return _wrap(lambda: _tools(req).calculate_blast_radius(service, incident_id).model_dump())


@router.get("/observations/{observation_id}")
def observation(observation_id: str, req: Request):
    if len(observation_id) > 200:
        raise HTTPException(422, "observation id too long")
    rows = req.app.state.graph.ro_query(
        "MATCH (i:Incident)-[:HAS_OBSERVATION]->(o:Observation {id: $id}) OPTIONAL MATCH (o)-[:OBSERVED_ON]->(s:Service) "
        "OPTIONAL MATCH (o)-[:OF_SIGNAL]->(g:Signal) RETURN o AS observation, i.id AS incident_id, s.name AS service, "
        "g.key AS signal_key", {"id": observation_id})
    if not rows:
        raise HTTPException(404, f"unknown observation {observation_id}")
    return rows[0]


@router.get("/hypotheses/{hypothesis_id}/evidence")
def hypothesis_evidence(hypothesis_id: str, req: Request):
    return _wrap(lambda: _tools(req).retrieve_evidence_paths(hypothesis_id).model_dump())


@router.get("/incidents/{incident_id}/related")
def related(incident_id: str, req: Request):
    return _wrap(lambda: _tools(req).retrieve_related_incidents(incident_id).model_dump())


@router.get("/incidents/{incident_id}/memories")
def incident_memories(incident_id: str, req: Request):
    return _wrap(lambda: _tools(req).retrieve_applicable_memories(incident_id).model_dump())


@router.get("/incidents/{incident_id}/changes")
def changes(incident_id: str, req: Request, window_s: int = Query(3600, ge=60, le=2592000)):
    t = _tools(req)
    view = _wrap(lambda: t.inspect_incident(incident_id, only_anomalous=True))
    svcs = view.anomalous_services or ["frontend"]
    return _wrap(lambda: t.find_recent_changes(svcs, view.detected_at or 0, window_s).model_dump())


@router.get("/memories")
def memories(req: Request, limit: int = Query(100, ge=1, le=500)):
    return list_memories(_tools(req), limit)


@router.post("/incidents/{incident_id}/actions/evaluate")
def evaluate_action(incident_id: str, body: ActionRequest, req: Request):
    t = _tools(req)

    def go():
        mem = t.retrieve_applicable_memories(incident_id)
        return t.evaluate_candidate_action(ActionSpec(type=body.type, target=body.target), incident_id, mem).model_dump()
    return _wrap(go)


@router.post("/incidents/{incident_id}/actions/simulate")
def simulate_action(incident_id: str, body: ActionRequest, req: Request):
    t = _tools(req)
    sim = Simulator(req.app.state.graph.settings.data_path)
    return _wrap(lambda: execute_simulated_action(t, sim, incident_id, ActionSpec(type=body.type, target=body.target),
                                                  approved=body.approved, idempotency_key=body.idempotency_key))


@router.get("/timeline")
def timeline(req: Request):
    """Memory timeline: incidents with their investigations, executed actions and outcomes, in time order."""
    return req.app.state.graph.ro_query(
        """
        MATCH (i:Incident)
        WHERE (i)<-[:INVESTIGATED]-() OR (i)-[:ATTEMPTED]->()
        OPTIONAL MATCH (i)-[:ATTEMPTED]->(a:Action)-[:PRODUCED]->(o:Outcome)
        OPTIONAL MATCH (m:Memory)-[:DERIVED_FROM]->(o)
        WITH i, collect(CASE WHEN a IS NULL THEN NULL ELSE {action: a.type, target: a.target, at: a.executed_at,
             outcome: o.result, memory: m.id, side_effects: o.side_effects} END) AS actions
        OPTIONAL MATCH (v:Investigation)-[:INVESTIGATED]->(i)
        RETURN i.id AS incident_id, i.title AS title, i.source AS source, i.status AS status,
               i.detected_at AS detected_at, actions, count(v) AS investigations
        ORDER BY detected_at
        """)


@router.get("/evaluation")
def evaluation(req: Request):
    """Evaluation results. Ground truth labels appear ONLY here, after predictions were made."""
    p = req.app.state.graph.settings.data_path / "eval" / "results" / "ablation_results.json"
    if not p.exists():
        raise HTTPException(404, "no evaluation results yet; run `python scripts/evaluate.py`")
    res = json.loads(p.read_text(encoding="utf-8"))
    res.pop("memory_phase", None)
    return res


@router.get("/stats")
def stats(req: Request):
    g = req.app.state.graph
    return {"labels": {r["l"]: r["n"] for r in g.ro_query("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS n")},
            "relationships": {r["t"]: r["n"] for r in g.ro_query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n")}}
