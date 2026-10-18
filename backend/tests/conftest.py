"""Shared fixtures.

Integration tests talk to a REAL FalkorDB (docker compose up -d falkordb) using an isolated
graph name so they never touch the `faultline` application graph. If FalkorDB is down,
integration tests FAIL (they are not skipped), so that a green run proves real connectivity.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.config import Settings
from app.graph.client import GraphClient


def _settings(**overrides) -> Settings:
    base = dict(FAULTLINE_GRAPH=f"faultline_test_{uuid.uuid4().hex[:8]}")
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def test_settings() -> Settings:
    return _settings()


@pytest.fixture
def graph(test_settings) -> GraphClient:
    client = GraphClient(test_settings)
    client.ping()  # raises GraphUnavailableError -> test error, never a skip
    yield client
    client.delete_graph()
    client.close()


@pytest.fixture
def down_settings() -> Settings:
    """Settings pointing at a port where nothing listens."""
    return _settings(falkordb_port=int(os.environ.get("FAULTLINE_DEAD_PORT", "6399")))
