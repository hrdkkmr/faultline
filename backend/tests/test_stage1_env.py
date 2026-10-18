import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.graph.client import GraphClient, GraphUnavailableError
from app.main import create_app


def test_settings_reject_bad_values():
    with pytest.raises(ValidationError):
        Settings(falkordb_port=0)
    with pytest.raises(ValidationError):
        Settings(FAULTLINE_GRAPH="bad name; DROP")
    with pytest.raises(ValidationError):
        Settings(FAULTLINE_LLM_PROVIDER="mystery")
    with pytest.raises(ValidationError):
        Settings(FAULTLINE_MAX_DEPTH=50)


def test_api_key_not_in_repr():
    s = Settings(ANTHROPIC_API_KEY="sk-secret-value")
    assert "sk-secret-value" not in repr(s)


def test_unreachable_db_raises(down_settings):
    client = GraphClient(down_settings)
    with pytest.raises(GraphUnavailableError):
        client.ping()
    with pytest.raises(GraphUnavailableError):
        client.ro_query("MATCH (n) RETURN count(n) AS c")


def test_health_reports_db_down_with_503(down_settings):
    app = create_app(GraphClient(down_settings))
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["app"]["status"] == "ok"
    assert body["database"]["status"] == "unavailable"


@pytest.mark.integration
def test_health_ok_with_real_db(graph):
    graph.query("CREATE (:Probe {id: $id})", {"id": "x"})
    app = create_app(graph)
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200, r.text
    db = r.json()["database"]
    assert db["status"] == "ok" and db["nodes"] == 1 and db["latency_ms"] >= 0


@pytest.mark.integration
def test_parameterized_query_roundtrip(graph):
    hostile = "x'}) DETACH DELETE n //"
    graph.query("CREATE (:Probe {id: $id})", {"id": hostile})
    rows = graph.ro_query("MATCH (p:Probe) RETURN p.id AS id")
    assert rows == [{"id": hostile}]
