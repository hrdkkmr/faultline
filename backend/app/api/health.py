from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.graph.client import GraphQueryError, GraphUnavailableError

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """Application health and database availability are reported separately.

    HTTP 200 only when the database answered a real Cypher probe; 503 otherwise.
    """
    client = request.app.state.graph
    body: dict = {"app": {"status": "ok", "version": request.app.version}}
    try:
        latency = client.ping()
        counts = client.ro_query("MATCH (n) RETURN count(n) AS nodes")
        body["database"] = {
            "status": "ok",
            "latency_ms": round(latency, 2),
            "graph": client.graph_name,
            "nodes": counts[0]["nodes"] if counts else 0,
        }
        return JSONResponse(body, status_code=200)
    except (GraphUnavailableError, GraphQueryError) as e:
        body["database"] = {"status": "unavailable", "error": str(e), "graph": client.graph_name}
        return JSONResponse(body, status_code=503)
