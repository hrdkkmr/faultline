import pytest

from app.graph.integrity import check_integrity
from app.graph.loader import load_all, load_architecture, load_incident
from app.graph.schema import ensure_schema, list_constraints

pytestmark = pytest.mark.integration


def _counts(g):
    return {r["l"]: r["n"] for r in g.ro_query("MATCH (n) RETURN labels(n)[0] AS l, count(n) AS n")}


def _rels(g):
    return {r["t"]: r["n"] for r in g.ro_query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n")}


def test_schema_constraints_enforced(graph):
    ensure_schema(graph)
    ensure_schema(graph)  # idempotent
    cons = list_constraints(graph)
    assert {"Service", "Incident", "Observation", "Memory"} <= {c["label"] for c in cons}
    graph.query("CREATE (:Service {name: 'dup'})")
    with pytest.raises(Exception):
        graph.query("CREATE (:Service {name: 'dup'})")


def test_full_load_is_idempotent_and_clean(graph, test_settings):
    test_settings.data_dir = test_settings.data_path  # same data as the app
    s1 = load_all(test_settings, client=graph)
    c1, r1 = _counts(graph), _rels(graph)
    s2 = load_all(test_settings, client=graph)
    assert _counts(graph) == c1 and _rels(graph) == r1, "re-ingestion duplicated entities"
    assert s1["integrity"]["ok"], s1["integrity"]["problems"]
    assert s2["integrity"]["ok"]
    assert c1["Service"] == 12 and r1["DEPENDS_ON"] == 16
    assert s1["rcaeval_incidents"] >= 1


def test_real_benchmark_records_queryable(graph, test_settings):
    test_settings.data_dir = test_settings.data_path
    load_all(test_settings, client=graph, include_scenarios=False)
    rows = graph.ro_query(
        "MATCH (i:Incident {source:'rcaeval'})-[:HAS_OBSERVATION]->(o:Observation {anomalous:true})"
        "-[:OBSERVED_ON]->(s:Service) RETURN i.id AS inc, s.name AS svc, o.signal AS sig, o.score AS score "
        "ORDER BY score DESC LIMIT 5")
    assert rows and all(r["inc"].startswith("INC-") for r in rows)
    calls = graph.ro_query("MATCH (a:Service)-[c:CALLS]->(b:Service) RETURN a.name AS a, b.name AS b, "
                           "c.source AS src, c.observed_in AS n")
    assert calls and all(c["src"] == "trace" and c["n"] >= 1 for c in calls)
    assert ("frontend", "checkoutservice") in {(c["a"], c["b"]) for c in calls}


def test_unknown_service_is_reported_not_invented(graph):
    ensure_schema(graph)
    load_architecture(graph)
    ev = {"incident_id": "INC-bad", "source": "rcaeval", "detected_at": 1_700_000_000,
          "observations": [{"id": "INC-bad:metric:ghostservice:cpu", "kind": "metric", "service": "ghostservice",
                            "signal": "cpu", "score": 9.0, "direction": "up", "anomalous": True}],
          "calls": [{"caller": "frontend", "callee": "ghostservice", "calls_before": 50, "calls_after": 50,
                     "p90_us_before": 1.0, "p90_us_after": 1.0}]}
    res = load_incident(graph, ev)
    assert res["unlinked_services"] == ["ghostservice"]
    assert not graph.ro_query("MATCH (s:Service {name:'ghostservice'}) RETURN s")
    integ = check_integrity(graph)
    assert not integ["ok"] and any("without OBSERVED_ON" in p for p in integ["problems"])
