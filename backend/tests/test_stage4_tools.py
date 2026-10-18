import pytest

from app.agents.tools import GraphTools, NotFoundError, ToolInputError
from app.graph.client import GraphClient, GraphUnavailableError
from app.graph.loader import load_architecture, load_deployment, load_incident
from app.graph.schema import ensure_schema
from app.schemas.models import ActionSpec, OutcomeRecord

T = 1_700_000_000


def _o(svc, sig, score, direction="up", kind="metric"):
    return {"kind": kind, "service": svc, "signal": sig, "score": score, "direction": direction,
            "anomalous": score >= 3}


def _inc(iid, obs, detected=T):
    for o in obs:
        o["id"] = f"{iid}:{o['kind']}:{o['service']}:{o['signal']}"
    return {"incident_id": iid, "source": "synthetic", "detected_at": detected, "observations": obs}


@pytest.fixture
def tools(graph):
    ensure_schema(graph)
    load_architecture(graph)
    # redis memory pressure propagating up to cartservice and frontend
    load_incident(graph, _inc("SYN-t1", [_o("redis", "mem", 40), _o("cartservice", "latency-90", 12),
                                         _o("frontend", "latency-90", 6), _o("checkoutservice", "cpu", 0.5)]))
    # look-alike: same cart/frontend latency, but redis is healthy
    load_incident(graph, _inc("SYN-t2", [_o("redis", "mem", 0.4), _o("cartservice", "latency-90", 11),
                                         _o("frontend", "latency-90", 5)], detected=T + 7200))
    # a third, same signature as t1
    load_incident(graph, _inc("SYN-t3", [_o("redis", "mem", 35), _o("cartservice", "latency-90", 9),
                                         _o("frontend", "latency-90", 4)], detected=T + 9000))
    return GraphTools(graph)


pytestmark = pytest.mark.integration


def test_multi_hop_downstream(tools):
    tr = tools.trace_dependencies("frontend", max_depth=2)
    redis = [p for p in tr.paths if p.service == "redis"]
    assert redis and redis[0].depth == 2 and redis[0].path == ["frontend", "cartservice", "redis"]
    assert set(redis[0].rel_types) == {"DEPENDS_ON"} and set(redis[0].rel_sources) == {"architecture"}
    assert "redis" not in tools.trace_dependencies("frontend", max_depth=1).reachable


def test_upstream_and_no_fabricated_paths(tools):
    up = tools.trace_dependencies("redis", max_depth=3, direction="upstream")
    assert {"cartservice", "frontend", "checkoutservice", "frontend-external"} <= set(up.reachable)
    leaf = tools.trace_dependencies("redis", max_depth=3, direction="downstream")
    assert leaf.paths == [] and leaf.reachable == []


def test_input_validation(tools):
    for bad in (0, 11, "3", True):
        with pytest.raises((ToolInputError, ValueError)):
            tools.trace_dependencies("frontend", max_depth=bad)
    with pytest.raises(ToolInputError):
        tools.trace_dependencies("frontend'}) DETACH DELETE n //")
    with pytest.raises(NotFoundError):
        tools.trace_dependencies("ghostservice")
    with pytest.raises(NotFoundError):
        tools.inspect_incident("INC-doesnotexist")
    with pytest.raises(ToolInputError):
        tools.inspect_incident("not an id")


def test_blast_radius_from_graph(tools):
    br = tools.calculate_blast_radius("redis", incident_id="SYN-t1")
    depth = {e.service: e.depth for e in br.entries}
    assert depth["cartservice"] == 1 and depth["frontend"] == 2 and depth["checkoutservice"] == 2
    assert depth["frontend-external"] == 3
    assert set(br.observed) == {"cartservice", "frontend"}  # checkout cpu=0.5 is not anomalous


def test_inspect_incident_returns_stored_records(tools):
    v = tools.inspect_incident("SYN-t1")
    assert v.anomalous_services == ["cartservice", "frontend", "redis"]
    assert {o.id for o in v.observations} >= {"SYN-t1:metric:redis:mem"}


def test_recent_changes_explicit_when_absent(tools, graph):
    rc = tools.find_recent_changes(["cartservice"], until_ts=T, time_window_s=3600)
    assert rc.changes == [] and rc.data_available is False and "No Deployment" in rc.note
    load_deployment(graph, {"id": "DEP-1", "service": "cartservice", "version": "v2", "at": T - 600})
    rc = tools.find_recent_changes(["cartservice"], until_ts=T, time_window_s=3600)
    assert [c.id for c in rc.changes] == ["DEP-1"] and rc.data_available


def test_related_incidents_by_shared_signals(tools):
    rel = tools.retrieve_related_incidents("SYN-t1")
    by = {r.incident_id: r for r in rel.related}
    assert by["SYN-t3"].jaccard == 1.0
    assert by["SYN-t2"].jaccard < 1.0 and "redis|mem|up" not in by["SYN-t2"].shared


def test_memory_reuse_reject_and_failed(tools):
    restart = ActionSpec(type="restart_service", target="redis")
    r = tools.record_incident_outcome("SYN-t1", restart, OutcomeRecord(result="resolved"))
    assert "redis|mem|up" in r["conditions"]
    dup = tools.record_incident_outcome("SYN-t1", restart, OutcomeRecord(result="resolved"))
    assert dup["duplicate"] is True

    m3 = {m.memory_id: m for m in tools.retrieve_applicable_memories("SYN-t3").matches}
    assert m3[r["memory_id"]].verdict == "applicable"
    m2 = {m.memory_id: m for m in tools.retrieve_applicable_memories("SYN-t2").matches}
    assert m2[r["memory_id"]].verdict == "rejected"
    assert any("redis" in x for x in m2[r["memory_id"]].reasons)

    ev = tools.evaluate_candidate_action(restart, "SYN-t3", tools.retrieve_applicable_memories("SYN-t3"))
    assert ev.verdict == "recommended" and ev.memory_effect > 0 and r["memory_id"] in ev.evidence

    # a failed attempt of a different action is remembered as failed, not as a procedure
    scale = ActionSpec(type="scale_out", target="cartservice")
    with pytest.raises(ToolInputError):  # paymentservice has no anomalous signal -> no conditions -> refused
        tools.record_incident_outcome("SYN-t1", ActionSpec(type="scale_out", target="paymentservice"),
                                      OutcomeRecord(result="not_resolved"))
    f = tools.record_incident_outcome("SYN-t1", scale, OutcomeRecord(result="not_resolved"))
    mem = tools.retrieve_applicable_memories("SYN-t3")
    failed = [m for m in mem.matches if m.memory_id == f["memory_id"]][0]
    assert failed.outcome == "not_resolved"
    ev = tools.evaluate_candidate_action(scale, "SYN-t3", mem)
    assert ev.verdict == "not_recommended"


def test_action_preconditions(tools):
    rb = tools.evaluate_candidate_action(ActionSpec(type="rollback_deployment", target="cartservice"), "SYN-t1")
    assert rb.verdict == "not_recommended" and any("no deployment" in b for b in rb.blockers)
    sc = tools.evaluate_candidate_action(ActionSpec(type="scale_out", target="cartservice"), "SYN-t1")
    assert sc.verdict == "not_recommended"
    healthy = tools.evaluate_candidate_action(ActionSpec(type="restart_service", target="paymentservice"), "SYN-t1")
    assert healthy.verdict == "not_recommended" and healthy.requires_approval
    with pytest.raises(ToolInputError):
        tools.evaluate_candidate_action(ActionSpec(type="rm_rf", target="redis"), "SYN-t1")


def test_evidence_paths_for_stored_hypothesis(tools, graph):
    graph.query(
        "MATCH (s:Service {name:'redis'}), (o:Observation {id:'SYN-t1:metric:redis:mem'}) "
        "CREATE (h:Hypothesis {id:'HYP-x', incident_id:'SYN-t1', service:'redis'})-[:ABOUT]->(s), "
        "(h)-[:SUPPORTED_BY {weight: 1.0}]->(o)")
    ep = tools.retrieve_evidence_paths("HYP-x")
    assert ep.supporting[0]["observation"] == "SYN-t1:metric:redis:mem"
    paths = {p.service: p.path for p in ep.symptom_paths}
    assert paths["frontend"] == ["frontend", "cartservice", "redis"]
    assert paths["cartservice"] == ["cartservice", "redis"]
    with pytest.raises(NotFoundError):
        tools.retrieve_evidence_paths("HYP-missing")


def test_tools_fail_visibly_without_db(down_settings):
    t = GraphTools(GraphClient(down_settings))
    with pytest.raises(GraphUnavailableError):
        t.trace_dependencies("frontend", 2)
    with pytest.raises(GraphUnavailableError):
        t.inspect_incident("INC-0000000000")
