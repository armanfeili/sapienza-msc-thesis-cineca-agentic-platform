"""
Memgraph adapter (gqlalchemy-based)

This module centralizes Memgraph access for the application:
- Connection factory with lazy singleton
- Health/readiness check
- Small, ergonomic helpers for queries and simple CRUD
- Safe degradation via custom exceptions

Typical usage:
    from src.adapters.db_memgraph import get_client, mg_health, query, execute

    mg = get_client()
    rows = query("MATCH (n) RETURN count(n) AS c")

Notes:
- Uses `gqlalchemy.Memgraph` (which wraps `mgclient` under the hood).
- Keeps a process-wide client; callers shouldn't hold on to it across forks.
"""

from __future__ import annotations

import contextlib
import time
import warnings
from collections.abc import Iterable
from typing import Any

from src.config import settings

# Logging (structlog if available; stdlib otherwise)
try:  # pragma: no cover - logging wiring varies
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Prometheus (optional)
try:  # pragma: no cover
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore

if Counter is not None:  # pragma: no cover
    DB_QUERIES = Counter(
        "db_memgraph_queries_total",
        "Number of Memgraph queries executed",
        labelnames=("status",),
    )
else:  # pragma: no cover
    DB_QUERIES = None  # type: ignore

if Histogram is not None:  # pragma: no cover
    DB_LATENCY = Histogram(
        "db_memgraph_query_latency_seconds",
        "Latency of Memgraph queries in seconds",
        buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, float("inf")),
    )
else:  # pragma: no cover
    DB_LATENCY = None  # type: ignore

# Quiet GQLAlchemy subclass warnings when working with generic nodes
with contextlib.suppress(Exception):
    from gqlalchemy.exceptions import GQLAlchemySubclassNotFoundWarning  # type: ignore

    warnings.filterwarnings("ignore", category=GQLAlchemySubclassNotFoundWarning)

# Try importing gqlalchemy only when needed to keep import cost low
_MEMGRAPH_CLASS = None
_CLIENT: Memgraph | None = None  # type: ignore[name-defined]


# ---------------- Exceptions ----------------
class DBError(RuntimeError):
    """Generic database error."""


class DBUnavailable(DBError):
    """Raised when a connection cannot be established."""


# ---------------- Internal helpers ----------------
def _import_memgraph_class():
    global _MEMGRAPH_CLASS
    if _MEMGRAPH_CLASS is not None:
        return _MEMGRAPH_CLASS
    try:
        from gqlalchemy import Memgraph  # type: ignore

        _MEMGRAPH_CLASS = Memgraph
        return Memgraph
    except Exception as exc:  # pragma: no cover
        raise DBUnavailable(f"gqlalchemy import failed: {exc}") from exc


def _build_client() -> Memgraph:  # type: ignore[name-defined]
    Memgraph = _import_memgraph_class()
    host, port, user, pwd = (
        settings.MG_HOST,
        settings.MG_PORT,
        settings.MG_USER,
        settings.MG_PASSWORD,
    )
    try:
        # Accept either 'user' or 'username' to be robust across call sites
        username = getattr(settings, "MG_USER", None) or getattr(settings, "MG_USERNAME", None) or user
        if username and pwd:
            return Memgraph(host=host, port=port, username=username, password=pwd)
        return Memgraph(host=host, port=port)
    except Exception as exc:
        raise DBUnavailable(f"could not connect to Memgraph at {host}:{port}: {exc}") from exc


def get_client() -> Memgraph:  # type: ignore[name-defined]
    """
    Return a process-wide Memgraph client. Raises DBUnavailable on failure.
    """
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = _build_client()
    return _CLIENT


def close_client() -> None:
    """Close and clear the process-wide client (useful for tests or shutdown)."""
    global _CLIENT
    if _CLIENT is not None:
        with contextlib.suppress(Exception):
            _CLIENT.close()
    _CLIENT = None


# ---------------- Health / readiness ----------------
def mg_health() -> dict[str, Any]:
    """
    Run a trivial query to verify connectivity. Returns a dict:
        {"ok": bool, "host": str, "port": int, "error": Optional[str]}
    """
    info: dict[str, Any] = {"ok": False, "host": settings.MG_HOST, "port": settings.MG_PORT}
    try:
        mg = get_client()
        # minimal query
        _ = list(mg.execute_and_fetch("RETURN 1 AS ok LIMIT 1"))
        info["ok"] = True
    except Exception as exc:
        info["error"] = str(exc)
    return info


# ---------------- Query helpers ----------------
def query(cypher: str, params: dict[str, Any] | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    """
    Execute a Cypher query and return a list of dict rows.
    Raises DBError on failure.
    """
    mg = get_client()
    t0 = time.perf_counter()
    try:
        rows = list(mg.execute_and_fetch(cypher, params or {}))
        if DB_QUERIES is not None:  # pragma: no cover
            DB_QUERIES.labels(status="ok").inc()
        return rows
    except Exception as exc:
        if DB_QUERIES is not None:  # pragma: no cover
            DB_QUERIES.labels(status="error").inc()
        raise DBError(str(exc)) from exc
    finally:
        if DB_LATENCY is not None:  # pragma: no cover
            DB_LATENCY.observe(time.perf_counter() - t0)


def query_one(cypher: str, params: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any] | None:
    """Return the first row or None."""
    rows = query(cypher, params, run_id=run_id)
    return rows[0] if rows else None


def execute(cypher: str, params: dict[str, Any] | None = None, run_id: str | None = None) -> int:
    """
    Execute a Cypher write query. Returns number of rows yielded (0 for pure writes).
    """
    result = query(cypher, params, run_id=run_id)
    return len(result)


# ---------------- Simple CRUD helpers ----------------
def ensure_index(label: str, prop: str) -> None:
    """
    Create an index on :Label(prop) if it doesn't already exist.
    Ignores 'already exists' errors.
    """
    try:
        execute(f"CREATE INDEX ON :`{label}`(`{prop}`)")
    except DBError as exc:
        # Memgraph returns a specific error if the index exists; ignore any such case
        if "already exists" not in str(exc).lower():
            raise


def upsert_node(labels: Iterable[str] | str, key: str, props: dict[str, Any]) -> None:
    """
    MERGE node on a stable key property, then SET remaining properties.

    Example:
        upsert_node(["User"], key="orig_id", props={"orig_id": "123", "name": "Ada"})
    """
    if isinstance(labels, str):
        labels = [labels]
    labels_cypher = ":".join(f"`{l}`" for l in labels)
    if key not in props:
        raise ValueError(f"props must include the key property '{key}'")
    params = {"kval": props[key], "props": props}
    execute(
        f"MERGE (n:{labels_cypher} {{{key}:$kval}}) " f"SET n += $props",
        params,
    )


def upsert_relationship(
    start_key: Any,
    rel_type: str,
    end_key: Any,
    *,
    start_key_name: str = "orig_id",
    end_key_name: str = "orig_id",
    props: dict[str, Any] | None = None,
    start_labels: Iterable[str] | str = (),
    end_labels: Iterable[str] | str = (),
) -> None:
    """
    MERGE a relationship by matching endpoints on key properties.

    Example:
        upsert_relationship("u-1", "RUNS", "t-1", start_labels=["User"], end_labels=["Task"])
    """
    if isinstance(start_labels, str):
        start_labels = [start_labels] if start_labels else []
    if isinstance(end_labels, str):
        end_labels = [end_labels] if end_labels else []

    a_labels = ":" + ":".join(f"`{l}`" for l in start_labels) if start_labels else ""
    b_labels = ":" + ":".join(f"`{l}`" for l in end_labels) if end_labels else ""

    params = {"a": start_key, "b": end_key, "props": props or {}}
    execute(
        f"MATCH (a{a_labels} {{{start_key_name}:$a}}), "
        f"      (b{b_labels} {{{end_key_name}:$b}}) "
        f"MERGE (a)-[r:`{rel_type}`]->(b) "
        f"SET r += $props",
        params,
    )


def wipe_all() -> None:
    """Dangerous: remove **all** nodes and relationships."""
    execute("MATCH (n) DETACH DELETE n")


__all__ = [
    "DBError",
    "DBUnavailable",
    "MemgraphAdapter",
    "close_client",
    "ensure_index",
    "execute",
    "get_client",
    "mg_health",
    "query",
    "query_one",
    "upsert_node",
    "upsert_relationship",
    "wipe_all",
]


# ---------------- Lightweight OO Adapter (for health checks & tools) ----------------
class MemgraphAdapter:
    """Thin OO wrapper around gqlalchemy.Memgraph used by health checks and tools.

    Provides a minimal surface:
      - ping() -> bool
      - info() -> Dict[str, Any]

    Parameters mirror common settings but all are optional; when omitted, values
    from src.config.settings are used.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> None:
        Memgraph = _import_memgraph_class()
        _host = host or getattr(settings, "MG_HOST", "memgraph")
        _port = port or int(getattr(settings, "MG_PORT", 7687))
        _user = username or getattr(settings, "MG_USER", None) or getattr(settings, "MG_USERNAME", None)
        _pwd = password or getattr(settings, "MG_PASSWORD", None)

        # gqlalchemy.Memgraph accepts username/password optionally
        if _user and _pwd:
            self._client = Memgraph(host=_host, port=_port, username=_user, password=_pwd)
        else:
            self._client = Memgraph(host=_host, port=_port)

        # Store basics for info()
        self._host = _host
        self._port = _port
        self._timeout = timeout or 3.0

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()

    def ping(self) -> bool:
        """Return True if a trivial query succeeds."""
        try:
            _ = list(self._client.execute_and_fetch("RETURN 1 AS ok LIMIT 1"))
            return True
        except Exception:
            return False

    def execute_and_fetch(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results (facade for health checks).
        
        This is a thin wrapper around the internal client's execute_and_fetch
        to support health check code that expects this method.
        
        Args:
            cypher: Cypher query string
            params: Optional query parameters
            
        Returns:
            List of result dictionaries
        """
        return self.query(cypher, params)

    def query(
        self, cypher: str, params: dict[str, Any] | None = None, run_id: str | None = None, timeout_ms: int | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts.

        Args:
            cypher: Cypher query string
            params: Optional query parameters
            timeout_ms: Optional timeout in milliseconds (currently ignored - gqlalchemy doesn't support per-query timeouts)

        Returns:
            List of result dictionaries
        """
        import time
        
        # Extract run_id from params if available for tracing
        run_id = run_id or (params.get("run_id") if params else None)
        if params and "run_id" in params:
            params = dict(params)
            params.pop("run_id", None)
        
        # Create query preview (first 120 chars)
        query_preview = cypher[:120] if cypher else ""
        
        # Log query start
        start_time = time.time()
        logger.info(
            "tool.memgraph.query_start",
            query_preview=query_preview,
            has_params=bool(params),
            run_id=run_id,
        )
        
        # Note: timeout_ms parameter is accepted for API compatibility but not currently used
        # gqlalchemy's Memgraph client doesn't support per-query timeouts
        try:
            if params:
                results = list(self._client.execute_and_fetch(cypher, params))
            else:
                results = list(self._client.execute_and_fetch(cypher))
            
            # Log success
            elapsed_ms = int((time.time() - start_time) * 1000)
            row_count = len(results)
            logger.info(
                "tool.memgraph.query_success",
                elapsed_ms=elapsed_ms,
                row_count=row_count,
                run_id=run_id,
            )
            
            return results
        except Exception as e:
            # Log error
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "tool.memgraph.query_error",
                elapsed_ms=elapsed_ms,
                error_class=type(e).__name__,
                error_message=str(e)[:500],
                query_preview=query_preview,
                run_id=run_id,
            )
            raise RuntimeError(f"Memgraph query failed: {e}") from e

    def info(self) -> dict[str, Any]:
        """Return a small info dict; falls back to mg_health() structure."""
        try:
            # Attempt a lightweight call; fallback to mg_health on error
            rows = list(self._client.execute_and_fetch("RETURN 1 AS ok LIMIT 1"))
            return {
                "host": self._host,
                "port": self._port,
                "ok": bool(rows),
            }
        except Exception:
            return mg_health()
