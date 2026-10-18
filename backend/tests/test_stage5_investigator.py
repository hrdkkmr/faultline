import json

import pytest

from app.agents import ranking
from app.agents.investigator import Investigator
from app.agents.llm import AnthropicNarrator, validate_narrative
from app.agents.tools import GraphTools
from app.config import Settings
from app.graph.loader import load_all, load_architecture, load_incident
from app.graph.schema import ensure_schema

T = 1_700_000_000


def _o(svc, sig, score, direction="up"):
    return {"kind": "metric", "service": svc, "signal": sig, "score": score, "direction": direction,
            "anomalous": score >= 3, "linked_service": svc, "id": f"x:{svc}:{sig}"}


# ---- pure ranking (no DB) ----------------------------------------------------------------

def test_coverage_prefers_downstream_cause_over_victim():
    # productcatalog delay: recommendation (its caller) shows equally extreme latency
    obs = [_o("productcatalogservice", "latency-90", 1000), _o("recommendationservice", "latency-90", 1000),
           _o("frontend", "latency-90", 200)]
    paths = [
        {"caller": "recommendationservice", "callee": "productcatalogservice", "depth": 1, "path": [], "rel_types": [], "rel_sources": []},
        {"caller": "frontend", "callee": "productcatalogservice", "depth": 1, "path": [], "rel_types": [], "rel_sources": []},
        {"caller": "frontend", "callee": "recommendationservice", "depth": 1, "path": [], "rel_types": [], "rel_sources": []},
    ]
    a = ranking.rank(ranking.build_candidates(obs), "A_incident_only")
    c = ranking.build_candidates(obs)
    ranking.apply_coverage(c, paths)
    b = ranking.rank(c, "B_graph")
    assert b[0].service == "productcatalogservice"
    assert a[0].total == pytest.approx(next(x.total for x in a if x.service == "recommendationservice"))


def test_caller_fanout_explains_slow_callees():
    obs = [_o("emailservice", "latency-90", 1000), _o("shippingservice", "latency-90", 1000),
           _o("checkoutservice", "latency-90", 300)]
    paths = [{"caller": "checkoutservice", "callee": s, "depth": 1, "path": [], "rel_types": [], "rel_sources": []}
             for s in ("emailservice", "shippingservice")]
    c = ranking.build_candidates(obs)
    ranking.apply_coverage(c, paths)
    assert ranking.rank(c, "B_graph")[0].service == "checkoutservice"


def test_fault_class_rules():
    c = ranking.build_candidates([_o("x", "diskio", 50), _o("x", "mem", 500)])["x"]
    assert ranking.fault_class(c)[0] == "disk"
    c = ranking.build_candidates([_o("x", "cpu", 300), _o("x", "latency-90", 50)])["x"]
    assert ranking.fault_class(c)[0] == "cpu"
    c = ranking.build_candidates([_o("x", "latency-90", 900), _o("x", "socket", 4)])["x"]
    assert ranking.fault_class(c)[0] == "network"


def test_narrative_validation():
    allowed = {"INC-1", "INC-1:metric:redis:mem"}
    assert validate_narrative("redis is the likely cause [INC-1:metric:redis:mem]", allowed) is None
    assert "unknown" in validate_narrative("cause [INC-1:metric:ghost:cpu]", allowed)
    assert "no evidence" in validate_narrative("redis is the cause", allowed)
    assert "overclaims" in validate_narrative("confirmed root cause [INC-1]", allowed)


# ---- integration --------------------------------------------------------------------------

pytestmark_i = pytest.mark.integration


@pytest.fixture
def seeded(graph):
    ensure_schema(graph)
    load_architecture(graph)

    def inc(iid, obs):
        for o in obs:
            o.pop("linked_service", None)
            o["id"] = f"{iid}:metric:{o['service']}:{o['signal']}"
        load_incident(graph, {"incident_id": iid, "source": "synthetic", "detected_at": T, "observations": obs})

    inc("SYN-redis", [_o("redis", "mem", 400), _o("cartservice", "latency-90", 60), _o("frontend", "latency-90", 20)])
    inc("SYN-weak", [_o("adservice", "latency-90", 3.5)])
    inc("SYN-none", [_o("adservice", "cpu", 0.3)])
    return graph


@pytest.mark.integration
def test_investigation_uses_graph_and_is_deterministic(seeded):
    inv = Investigator(GraphTools(seeded))
    r1 = inv.investigate("SYN-redis", mode="B_graph")
    r2 = inv.investigate("SYN-redis", mode="B_graph")
    strip = lambda r: [(h.service, h.score.total, h.supporting_evidence) for h in r.hypotheses]  # noqa: E731
    assert strip(r1) == strip(r2)
    assert r1.suspected_root_cause == "redis" and r1.conclusion == "root_cause_hypothesis"
    tools_used = {c["tool"] for c in r1.tool_calls}
    assert {"inspect_incident", "anomaly_subgraph_paths", "find_recent_changes",
            "calculate_blast_radius", "evaluate_candidate_action"} <= tools_used
    h = r1.hypotheses[0]
    assert set(h.explained_services) == {"cartservice", "frontend"}
    assert any(p.path == ["frontend", "cartservice", "redis"] for p in h.graph_paths)
    # every cited evidence id exists in the graph
    ids = [i for hh in r1.hypotheses for i in hh.supporting_evidence + hh.contradicting_evidence]
    found = seeded.ro_query("MATCH (o:Observation) WHERE o.id IN $ids RETURN count(DISTINCT o) AS n", {"ids": ids})
    assert found[0]["n"] == len(set(ids))
    assert "cartservice" in r1.affected_services["observed"]
    rec = [m for m in r1.candidate_mitigations if m.verdict == "recommended"]
    assert rec and rec[0].action.target == "redis"


@pytest.mark.integration
def test_abstains_when_evidence_weak_or_absent(seeded):
    inv = Investigator(GraphTools(seeded))
    weak = inv.investigate("SYN-weak", mode="B_graph")
    assert weak.conclusion == "inconclusive" and weak.suspected_root_cause is None
    assert weak.candidate_mitigations[0].action.type == "gather_more_evidence"
    none = inv.investigate("SYN-none", mode="C_graph_memory")
    assert none.conclusion == "inconclusive" and not none.hypotheses


@pytest.mark.integration
def test_persisted_hypothesis_evidence_paths_traceable(seeded):
    tools = GraphTools(seeded)
    r = Investigator(tools).investigate("SYN-redis", mode="B_graph", persist=True)
    ep = tools.retrieve_evidence_paths(r.hypotheses[0].id)
    assert {s["observation"] for s in ep.supporting} == set(r.hypotheses[0].supporting_evidence)
    assert seeded.ro_query("MATCH (:Investigation {id:$id})-[:RECOMMENDED]->(a:Action {status:'proposed'}) "
                           "RETURN count(a) AS n", {"id": r.investigation_id})[0]["n"] >= 1


class _FakeLLM(AnthropicNarrator):
    def __init__(self, behaviour):
        super().__init__(Settings())
        self.behaviour = behaviour

    def complete(self, payload):
        if self.behaviour == "timeout":
            raise TimeoutError("simulated")
        if self.behaviour == "invent":
            return "The cause is the payment database [INC-made-up:metric:db:cpu]."
        hid = payload["hypotheses"][0]["supporting_evidence"][0]
        return f"Likely redis memory pressure (hypothesis) [{hid}]."


@pytest.mark.integration
def test_llm_failures_do_not_break_investigation(seeded):
    tools = GraphTools(seeded)
    for behaviour, src in (("timeout", "llm failed"), ("invent", "rejected"), ("ok", "citations validated")):
        r = Investigator(tools, narrator=_FakeLLM(behaviour)).investigate("SYN-redis", mode="B_graph", narrate=True)
        assert r.suspected_root_cause == "redis"
        assert src in r.narrative_source
        assert "made-up" not in (r.narrative or "")


@pytest.mark.integration
def test_real_benchmark_investigation(graph, test_settings):
    test_settings.data_dir = test_settings.data_path
    load_all(test_settings, client=graph, include_scenarios=False)
    inc = graph.ro_query("MATCH (i:Incident {source:'rcaeval'}) RETURN i.id AS id ORDER BY id LIMIT 1")[0]["id"]
    r = Investigator(GraphTools(graph)).investigate(inc, mode="C_graph_memory")
    assert r.hypotheses and r.hypotheses[0].supporting_evidence
    assert json.dumps(r.model_dump()).count("root_cause_service") == 0
