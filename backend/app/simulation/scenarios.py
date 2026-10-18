"""Synthetic scenarios: visible evidence and hidden truth, kept in separate files.

- `data/scenarios/<id>.json`          VISIBLE: observations, calls, deployments. Loaded into the graph.
- `data/eval/scenario_truth.json`     HIDDEN: root cause, fault, expected affected services, action effects.
                                      Read only by the simulator oracle and the evaluation runner.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.graph.client import GraphClient

REQUIRED_VISIBLE = {"incident_id", "detected_at", "observations"}
REQUIRED_OBS = {"kind", "service", "signal", "score", "direction"}


class ScenarioError(ValueError):
    pass


def scenario_dir(data_dir: Path) -> Path:
    return data_dir / "scenarios"


def validate_visible(sc: dict, name: str = "?") -> dict:
    missing = REQUIRED_VISIBLE - set(sc)
    if missing:
        raise ScenarioError(f"scenario {name}: missing fields {sorted(missing)}")
    if not str(sc["incident_id"]).startswith("SYN-"):
        raise ScenarioError(f"scenario {name}: synthetic incident ids must start with 'SYN-'")
    forbidden = {"root_cause", "root_cause_service", "fault", "hidden", "truth"} & set(sc)
    if forbidden:
        raise ScenarioError(f"scenario {name}: visible file contains hidden fields {sorted(forbidden)}")
    for i, o in enumerate(sc["observations"]):
        miss = REQUIRED_OBS - set(o)
        if miss:
            raise ScenarioError(f"scenario {name}: observation {i} missing {sorted(miss)}")
        o.setdefault("anomalous", float(o["score"]) >= 3.0)
        o.setdefault("id", f"{sc['incident_id']}:{o['kind']}:{o['service']}:{o['signal']}")
        o["source"] = "synthetic"
    sc.setdefault("source", "synthetic")
    sc.setdefault("system", "online-boutique")
    sc.setdefault("dataset", "synthetic")
    sc.setdefault("telemetry", {"metrics": True, "logs": False, "traces": False})
    sc.setdefault("calls", [])
    sc.setdefault("deployments", [])
    return sc


def load_visible(data_dir: Path) -> list[dict]:
    out = []
    for f in sorted(scenario_dir(data_dir).glob("SYN-*.json")):
        out.append(validate_visible(json.loads(f.read_text(encoding="utf-8")), f.name))
    return out


def load_truth(data_dir: Path) -> dict:
    p = data_dir / "eval" / "scenario_truth.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_scenarios_into_graph(client: GraphClient, data_dir: Path) -> list[dict]:
    from app.graph.loader import load_incident

    return [load_incident(client, sc) for sc in load_visible(data_dir)]
