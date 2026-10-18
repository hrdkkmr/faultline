import pytest

from app.agents.investigator import Investigator
from app.agents.tools import GraphTools
from app.config import get_settings
from app.graph.client import GraphClient
from app.graph.loader import load_architecture
from app.graph.schema import ensure_schema
from app.memory.service import execute_simulated_action
from app.schemas.models import ActionSpec
from app.simulation.scenarios import ScenarioError, load_scenarios_into_graph, validate_visible
from app.simulation.simulator import ApprovalRequired, Simulator, UnknownTruth

DATA = get_settings().data_path
SIM = Simulator(DATA)


# ---- simulator (no DB) ----

def test_correct_vs_incorrect_interventions():
    ok = SIM.simulate("SYN-redis-mem-1", ActionSpec(type="restart_service", target="redis"), approved=True)
    assert ok.result == "resolved"
    victim = SIM.simulate("SYN-redis-mem-1", ActionSpec(type="restart_service", target="cartservice"), approved=True)
    assert victim.result == "worsened" and victim.side_effects
    wrong_type = SIM.simulate("SYN-redis-mem-1", ActionSpec(type="scale_out", target="redis"))
    assert wrong_type.result == "not_resolved"
    assert SIM.simulate("SYN-payment-unrelated-deploy",
                        ActionSpec(type="rollback_deployment", target="cartservice"), approved=True).result != "resolved"
    assert SIM.simulate("SYN-payment-unrelated-deploy", ActionSpec(type="scale_out", target="paymentservice")).result == "resolved"
    assert SIM.simulate("SYN-catalog-shared", ActionSpec(type="scale_out", target="frontend")).result == "not_resolved"
    assert SIM.simulate("SYN-catalog-shared", ActionSpec(type="scale_out", target="productcatalogservice")).result == "resolved"
    assert SIM.simulate("SYN-cart-deploy", ActionSpec(type="rollback_deployment", target="cartservice"),
                        approved=True).result == "resolved"


def test_disruptive_actions_require_approval_and_truth_required():
    with pytest.raises(ApprovalRequired):
        SIM.simulate("SYN-redis-mem-1", ActionSpec(type="restart_service", target="redis"))
    with pytest.raises(UnknownTruth):
        SIM.simulate("SYN-nope", ActionSpec(type="scale_out", target="redis"))
    with pytest.raises(ValueError):
        SIM.simulate("SYN-redis-mem-1", ActionSpec(type="gather_more_evidence"))


def test_simulator_uses_real_rcaeval_labels():
    import json
    labels = json.loads((DATA / "eval" / "rcaeval_labels.json").read_text())
    iid, lab = next((k, v) for k, v in labels.items() if v["fault"] == "cpu")
    assert SIM.simulate(iid, ActionSpec(type="scale_out", target=lab["root_cause_service"])).result == "resolved"
    assert SIM.simulate(iid, ActionSpec(type="scale_out", target="adservice")).result == "not_resolved"


def test_visible_scenarios_cannot_contain_truth():
    with pytest.raises(ScenarioError):
        validate_visible({"incident_id": "SYN-x", "detected_at": 1, "observations": [], "root_cause_service": "redis"})
    with pytest.raises(ScenarioError):
        validate_visible({"incident_id": "INC-x", "detected_at": 1, "observations": []})


# ---- memory tests A/B/C (real FalkorDB, fresh sessions) ----

@pytest.fixture
def scen_graph(graph):
    ensure_schema(graph)
    load_architecture(graph)
    load_scenarios_into_graph(graph, DATA)
    return graph


def _fresh(test_settings):
    """A new client/tools/investigator: simulates a separate session (nothing shared in-process)."""
    tools = GraphTools(GraphClient(test_settings))
    return tools, Investigator(tools)


@pytest.mark.integration
def test_memory_A_reuse_in_compatible_incident(scen_graph, test_settings):
    tools, inv = _fresh(test_settings)
    r1 = inv.investigate("SYN-redis-mem-1", "C_graph_memory", persist=True)
    assert r1.suspected_root_cause == "redis" and not r1.memories_considered
    res = execute_simulated_action(tools, SIM, "SYN-redis-mem-1",
                                   ActionSpec(type="restart_service", target="redis"), approved=True)
    assert res["outcome"]["result"] == "resolved"

    tools2, inv2 = _fresh(test_settings)  # new session
    r2 = inv2.investigate("SYN-redis-mem-2", "C_graph_memory", persist=True)
    mem = {m.memory_id: m for m in r2.memories_considered}
    assert mem[res["memory_id"]].verdict == "applicable"
    assert r2.hypotheses[0].memories == [res["memory_id"]] and r2.hypotheses[0].score.memory > 0
    top = next(m for m in r2.candidate_mitigations if m.verdict == "recommended")
    assert (top.action.type, top.action.target) == ("restart_service", "redis")
    assert res["memory_id"] in top.evidence
    # B-mode (no memory) on the same incident does not see it
    assert not inv2.investigate("SYN-redis-mem-2", "B_graph").memories_considered


@pytest.mark.integration
def test_memory_B_similar_symptoms_old_repair_rejected(scen_graph, test_settings):
    tools, _ = _fresh(test_settings)
    res = execute_simulated_action(tools, SIM, "SYN-redis-mem-1",
                                   ActionSpec(type="restart_service", target="redis"), approved=True)
    _, inv = _fresh(test_settings)
    r = inv.investigate("SYN-cart-deploy", "C_graph_memory")
    m = {x.memory_id: x for x in r.memories_considered}[res["memory_id"]]
    assert m.source_similarity > 0  # it does look similar...
    assert m.verdict == "rejected"  # ...but its conditions do not hold
    assert any("redis" in reason for reason in m.reasons)
    assert r.suspected_root_cause == "cartservice" and r.suspected_fault_class == "deployment_regression"
    top = next(x for x in r.candidate_mitigations if x.verdict == "recommended")
    assert (top.action.type, top.action.target) == ("rollback_deployment", "cartservice")
    assert not any(x.action.target == "redis" and x.verdict == "recommended" for x in r.candidate_mitigations)
    out = SIM.simulate("SYN-cart-deploy", top.action, approved=True)
    assert out.result == "resolved"


@pytest.mark.integration
def test_memory_C_failed_repair_not_reused(scen_graph, test_settings):
    tools, inv = _fresh(test_settings)
    before = inv.investigate("SYN-checkout-socket-2", "C_graph_memory")
    assert any(m.action.type == "scale_out" and m.verdict == "recommended" for m in before.candidate_mitigations)
    res = execute_simulated_action(tools, SIM, "SYN-checkout-socket-1", ActionSpec(type="scale_out", target="checkoutservice"))
    assert res["outcome"]["result"] == "not_resolved"
    _, inv2 = _fresh(test_settings)
    after = inv2.investigate("SYN-checkout-socket-2", "C_graph_memory")
    so = next(m for m in after.candidate_mitigations if m.action.type == "scale_out")
    assert so.verdict == "not_recommended" and so.memory_effect < 0 and res["memory_id"] in so.evidence
    assert after.hypotheses[0].score.memory == 0  # a failed repair is not support
    top = next(m for m in after.candidate_mitigations if m.verdict == "recommended")
    assert top.action.type == "restart_service"


@pytest.mark.integration
def test_contradicting_outcomes_preserved(scen_graph, test_settings):
    tools, _ = _fresh(test_settings)
    a = execute_simulated_action(tools, SIM, "SYN-checkout-socket-1", ActionSpec(type="restart_service", target="checkoutservice"),
                                 approved=True, idempotency_key="k1")
    # an operator-recorded failure of the same action under the same conditions on a later incident
    from app.schemas.models import OutcomeRecord
    b = tools.record_incident_outcome("SYN-checkout-socket-2", ActionSpec(type="restart_service", target="checkoutservice"),
                                      OutcomeRecord(result="not_resolved", source="operator"))
    assert a["memory_id"] in b["contradicts"]
    n = scen_graph.ro_query("MATCH (m:Memory) RETURN count(m) AS n")[0]["n"]
    assert n == 2  # both kept, nothing overwritten
    again = execute_simulated_action(tools, SIM, "SYN-checkout-socket-1", ActionSpec(type="restart_service", target="checkoutservice"),
                                     approved=True, idempotency_key="k1")
    assert again["duplicate"] and scen_graph.ro_query("MATCH (m:Memory) RETURN count(m) AS n")[0]["n"] == 2
