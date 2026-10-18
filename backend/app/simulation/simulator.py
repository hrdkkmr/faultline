"""Deterministic repair simulator. Nothing is executed against a real system.

The outcome of an action is decided ONLY by the hidden truth of the incident (RCAEval labels or
`data/eval/scenario_truth.json`) and the fixed effect model below - never by the agent or an LLM.

Environment model (a stylized assumption, documented in docs/architecture.md):
  fault                  modeled cause                         effective actions
  cpu                    sustained load above capacity         scale_out
  mem                    memory leak in the process            restart_service, increase_memory_limit, reschedule_pod
  socket                 socket/connection leak in process     restart_service, reschedule_pod
  disk                   noisy-neighbour disk I/O on the node  reschedule_pod
  delay / loss           degraded network path on the node     reschedule_pod
  deployment_regression  bad release                           rollback_deployment
Any action on a service other than the true root cause does not resolve the incident. Disruptive
actions on a healthy service on the request path are recorded as `worsened` (transient errors).
Scenario truth may override effects per action (`action_effects`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.schemas.models import ActionSpec, OutcomeRecord
from app.simulation.catalog import ACTIONS
from app.simulation.scenarios import load_truth

EFFECTIVE: dict[str, set[str]] = {
    "cpu": {"scale_out"},
    "mem": {"restart_service", "increase_memory_limit", "reschedule_pod"},
    "socket": {"restart_service", "reschedule_pod"},
    "disk": {"reschedule_pod"},
    "delay": {"reschedule_pod"},
    "loss": {"reschedule_pod"},
    "deployment_regression": {"rollback_deployment"},
}
DISRUPTIVE = {"restart_service", "reschedule_pod", "rollback_deployment"}
REQUEST_PATH = {"frontend", "checkoutservice", "cartservice", "redis", "productcatalogservice", "currencyservice"}


class ApprovalRequired(PermissionError):
    pass


class UnknownTruth(LookupError):
    pass


@dataclass
class Truth:
    root_cause_service: str
    fault: str
    action_effects: dict | None = None


class Simulator:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _truth(self, incident_id: str) -> Truth:
        if incident_id.startswith("SYN-"):
            t = load_truth(self.data_dir).get(incident_id)
        else:
            p = self.data_dir / "eval" / "rcaeval_labels.json"
            t = json.loads(p.read_text(encoding="utf-8")).get(incident_id) if p.exists() else None
        if not t:
            raise UnknownTruth(f"no simulator truth for {incident_id}")
        return Truth(t["root_cause_service"], t["fault"], t.get("action_effects"))

    def simulate(self, incident_id: str, action: ActionSpec, approved: bool = False) -> OutcomeRecord:
        if action.type not in ACTIONS or action.type == "gather_more_evidence":
            raise ValueError(f"action {action.type!r} cannot be simulated")
        if ACTIONS[action.type].requires_approval and not approved:
            raise ApprovalRequired(f"{action.type} requires explicit human approval")
        t = self._truth(incident_id)
        override = (t.action_effects or {}).get(f"{action.type}:{action.target}")
        if override:
            return OutcomeRecord(result=override["result"], detail=override.get("detail"), source="simulator",
                                 side_effects=override.get("side_effects", []))
        if action.target == t.root_cause_service and action.type in EFFECTIVE.get(t.fault, set()):
            return OutcomeRecord(result="resolved", source="simulator",
                                 detail=f"{action.type} on {action.target} removed the modeled cause")
        side = []
        result = "not_resolved"
        if action.target != t.root_cause_service:
            detail = f"{action.target} was not the cause; symptoms persist"
            if action.type in DISRUPTIVE and action.target in REQUEST_PATH:
                result = "worsened"
                side.append(f"unnecessary {action.type} on request-path service {action.target} caused transient errors")
        else:
            detail = f"{action.type} does not address the modeled cause on {action.target}"
        return OutcomeRecord(result=result, detail=detail, source="simulator", side_effects=side)
