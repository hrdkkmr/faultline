import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.graph.client import GraphClient
from app.graph.loader import load_architecture
from app.graph.schema import ensure_schema
from app.main import create_app
from app.simulation.scenarios import load_scenarios_into_graph

pytestmark = pytest.mark.integration


@pytest.fixture
def api(graph):
    ensure_schema(graph)
    load_architecture(graph)
    load_scenarios_into_graph(graph, get_settings().data_path)
    with TestClient(create_app(graph)) as c:
        yield c


def test_incident_list_and_detail(api):
    inc = api.get("/api/incidents").json()
    assert {i["id"] for i in inc} >= {"SYN-redis-mem-1", "SYN-cart-deploy"}
    d = api.get("/api/incidents/SYN-redis-mem-1").json()
    assert "redis" in d["anomalous_services"]
    assert api.get("/api/incidents/SYN-nope").status_code == 404
    assert api.get("/api/incidents/bad%20id").status_code == 422


def test_graph_payload_comes_from_db(api):
    g = api.get("/api/incidents/SYN-redis-mem-1/graph").json()
    names = {n["name"] for n in g["nodes"]}
    assert len(names) == 12 and {"redis", "frontend"} <= names
    assert next(n for n in g["nodes"] if n["name"] == "redis")["anomalous"]
    assert any(e["source"] == "cartservice" and e["target"] == "redis" and e["type"] == "DEPENDS_ON" for e in g["edges"])


def test_investigate_evidence_and_simulate_flow(api):
    r = api.post("/api/incidents/SYN-redis-mem-1/investigate", json={"mode": "C_graph_memory"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["suspected_root_cause"] == "redis" and rep["narrative"]
    hid = rep["hypotheses"][0]["id"]
    ev = api.get(f"/api/hypotheses/{hid}/evidence").json()
    assert ev["supporting"] and any(p["path"][-1] == "redis" for p in ev["symptom_paths"])
    obs_id = ev["supporting"][0]["observation"]
    assert api.get(f"/api/observations/{obs_id}").json()["service"] == "redis"
    hist = api.get("/api/incidents/SYN-redis-mem-1/investigations").json()
    assert hist[0]["id"] == rep["investigation_id"]
    assert api.get(f"/api/investigations/{rep['investigation_id']}").json()["incident_id"] == "SYN-redis-mem-1"

    denied = api.post("/api/incidents/SYN-redis-mem-1/actions/simulate", json={"type": "restart_service", "target": "redis"})
    assert denied.status_code == 403
    ok = api.post("/api/incidents/SYN-redis-mem-1/actions/simulate",
                  json={"type": "restart_service", "target": "redis", "approved": True}).json()
    assert ok["outcome"]["result"] == "resolved" and ok["outcome"]["source"] == "simulator"
    again = api.post("/api/incidents/SYN-redis-mem-1/actions/simulate",
                     json={"type": "restart_service", "target": "redis", "approved": True}).json()
    assert again["duplicate"] is True
    mems = api.get("/api/memories").json()
    assert len(mems) == 1 and mems[0]["outcome"] == "resolved"
    tl = api.get("/api/timeline").json()
    assert any(t["incident_id"] == "SYN-redis-mem-1" and t["actions"] for t in tl)
    applicable = api.get("/api/incidents/SYN-redis-mem-2/memories").json()["matches"]
    assert applicable[0]["verdict"] == "applicable"


def test_input_validation(api):
    assert api.post("/api/incidents/SYN-redis-mem-1/investigate", json={"mode": "Z"}).status_code == 422
    assert api.post("/api/incidents/SYN-redis-mem-1/actions/simulate",
                    json={"type": "DROP; --", "target": "redis"}).status_code == 422
    assert api.post("/api/incidents/SYN-redis-mem-1/actions/evaluate",
                    json={"type": "launch_missiles", "target": "redis"}).status_code == 422
    assert api.get("/api/services/redis/dependencies?depth=99").status_code == 422
    assert api.get("/api/services/ghost/dependencies").status_code == 404
    up = api.get("/api/services/redis/dependencies?depth=3&direction=upstream").json()
    assert "frontend" in up["reachable"]


def test_api_reports_db_outage(down_settings):
    with TestClient(create_app(GraphClient(down_settings))) as c:
        r = c.get("/api/incidents")
        assert r.status_code == 503 and r.json()["error"] == "graph_unavailable"
        assert c.post("/api/incidents/SYN-redis-mem-1/investigate", json={}).status_code == 503
