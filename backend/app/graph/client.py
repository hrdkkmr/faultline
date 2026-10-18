"""Thin, explicit wrapper around the FalkorDB client.

Every graph operation in Faultline goes through `GraphClient.query` / `GraphClient.ro_query`, which
- only accepts parameterized Cypher (values travel in `params`, never via string interpolation),
- converts connection failures into `GraphUnavailableError` (no silent fallback),
- returns rows as plain dicts keyed by the RETURN aliases.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.exceptions
from falkordb import FalkorDB
from falkordb.edge import Edge
from falkordb.node import Node
from falkordb.path import Path as FPath

from app.config import Settings, get_settings

log = logging.getLogger("faultline.graph")


class GraphUnavailableError(RuntimeError):
    """FalkorDB cannot be reached. Graph-dependent features must fail, never fall back."""


class GraphQueryError(RuntimeError):
    """FalkorDB was reached but rejected or failed the query."""


def _convert(v: Any) -> Any:
    if isinstance(v, Node):
        return {"_id": v.id, "_labels": list(v.labels or []), **(v.properties or {})}
    if isinstance(v, Edge):
        return {
            "_id": v.id,
            "_type": v.relation,
            "_src": v.src_node,
            "_dst": v.dest_node,
            **(v.properties or {}),
        }
    if isinstance(v, FPath):
        return {"nodes": [_convert(n) for n in v.nodes()], "edges": [_convert(e) for e in v.edges()]}
    if isinstance(v, list):
        return [_convert(x) for x in v]
    if isinstance(v, dict):
        return {k: _convert(x) for k, x in v.items()}
    return v


class GraphClient:
    def __init__(self, settings: Settings | None = None, graph_name: str | None = None):
        self.settings = settings or get_settings()
        self.graph_name = graph_name or self.settings.graph_name
        self._db_obj: FalkorDB | None = None
        self._graph_obj = None

    # The FalkorDB constructor connects eagerly (cluster-mode probe), so connect lazily and
    # translate failures into GraphUnavailableError.
    @property
    def _db(self) -> FalkorDB:
        if self._db_obj is None:
            try:
                self._db_obj = FalkorDB(
                    host=self.settings.falkordb_host,
                    port=self.settings.falkordb_port,
                    username=self.settings.falkordb_user,
                    password=self.settings.falkordb_password,
                    socket_timeout=max(2.0, self.settings.query_timeout_ms / 1000 + 2),
                    socket_connect_timeout=2.0,
                )
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError) as e:
                raise GraphUnavailableError(
                    f"FalkorDB unreachable at {self.settings.falkordb_host}:{self.settings.falkordb_port}: {e}"
                ) from e
        return self._db_obj

    @property
    def _graph(self):
        if self._graph_obj is None:
            self._graph_obj = self._db.select_graph(self.graph_name)
        return self._graph_obj

    # -- connectivity -------------------------------------------------------------------------
    def ping(self) -> float:
        """Round-trip a real command. Returns latency in ms or raises GraphUnavailableError."""
        t0 = time.perf_counter()
        try:
            self._db.connection.ping()
            # Also prove the graph module is loaded and answers Cypher.
            self._db.select_graph("__faultline_health__").ro_query("RETURN 1")
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError) as e:
            raise GraphUnavailableError(
                f"FalkorDB unreachable at {self.settings.falkordb_host}:{self.settings.falkordb_port}: {e}"
            ) from e
        except redis.exceptions.ResponseError as e:
            # "Invalid graph operation on empty key" is fine for a read-only probe of a missing graph.
            if "empty key" not in str(e):
                raise GraphQueryError(f"FalkorDB responded but Cypher probe failed: {e}") from e
        return (time.perf_counter() - t0) * 1000

    # -- queries ------------------------------------------------------------------------------
    def _run(self, fn, cypher: str, params: dict[str, Any] | None) -> list[dict[str, Any]]:
        t0 = time.perf_counter()
        try:
            res = fn(cypher, params or {}, timeout=self.settings.query_timeout_ms)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError) as e:
            raise GraphUnavailableError(f"FalkorDB unavailable: {e}") from e
        except redis.exceptions.ResponseError as e:
            if "empty key" in str(e):
                return []  # graph does not exist yet: a genuine empty result, not an error
            raise GraphQueryError(f"{e} | query={cypher.strip()[:200]}") from e
        cols = [h[1] if isinstance(h, (list, tuple)) else h for h in (res.header or [])]
        rows = [dict(zip(cols, (_convert(v) for v in row))) for row in (res.result_set or [])]
        log.debug(
            "cypher", extra={"ms": round((time.perf_counter() - t0) * 1000, 2), "rows": len(rows),
                             "q": " ".join(cypher.split())[:120]}
        )
        return rows

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._run(self._graph.query, cypher, params)

    def ro_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._run(self._graph.ro_query, cypher, params)

    def execute_command(self, *args: Any) -> Any:
        try:
            return self._db.connection.execute_command(*args)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError) as e:
            raise GraphUnavailableError(f"FalkorDB unavailable: {e}") from e

    def delete_graph(self) -> None:
        try:
            self._graph.delete()
        except redis.exceptions.ResponseError as e:
            if "empty key" not in str(e) and "Invalid graph" not in str(e):
                raise
        except (redis.exceptions.ConnectionError, OSError) as e:
            raise GraphUnavailableError(str(e)) from e

    def close(self) -> None:
        if self._db_obj is None:
            return
        try:
            self._db_obj.connection.close()
        except Exception:  # noqa: BLE001 - best effort on shutdown
            pass
