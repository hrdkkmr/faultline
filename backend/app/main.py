"""Faultline FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, routes
from app.config import get_settings
from app.graph.client import GraphClient, GraphQueryError, GraphUnavailableError
from app.logging_setup import configure_logging

log = logging.getLogger("faultline.app")


def create_app(graph: GraphClient | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.graph = graph or GraphClient(settings)
        try:
            ms = app.state.graph.ping()
            log.info("falkordb reachable", extra={"latency_ms": round(ms, 2), "graph": settings.graph_name})
        except (GraphUnavailableError, GraphQueryError) as e:
            # Start anyway so /health can report the outage; graph endpoints will return 503.
            log.error("falkordb NOT reachable at startup", extra={"error": str(e)})
        yield
        app.state.graph.close()

    app = FastAPI(title="Faultline", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GraphUnavailableError)
    async def _graph_down(_: Request, exc: GraphUnavailableError) -> JSONResponse:
        return JSONResponse({"error": "graph_unavailable", "detail": str(exc)}, status_code=503)

    @app.exception_handler(GraphQueryError)
    async def _graph_err(_: Request, exc: GraphQueryError) -> JSONResponse:
        log.error("graph query error", extra={"error": str(exc)})
        return JSONResponse({"error": "graph_query_error", "detail": str(exc)}, status_code=500)

    app.include_router(health.router)
    app.include_router(routes.router)
    return app


app = create_app()
