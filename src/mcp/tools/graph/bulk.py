"""
MCP Tool: graph.bulk

Batch operations for Memgraph with idempotency and dry-run support.

Supported actions
-----------------
- ingest_nodes: Bulk create/update nodes with MERGE semantics
- ingest_edges: Bulk create/update relationships with MERGE semantics
- upsert_nodes: Batch upsert with idempotency keys
- upsert_edges: Batch relationship upsert with idempotency keys

Features
--------
- Batch processing with configurable batch_size (1-1000)
- Idempotency via optional idempotency_key
- Dry-run mode for validation without writes
- Fail-fast or continue-on-error modes
- Progress tracking (processed, succeeded, failed)
- Tenant isolation and audit logging
- Metadata injection (created_by, created_at, tenant)

Security
--------
- Requires tools:write scope for all operations
- Principal and tenant enforcement
- All writes logged for audit

Notes
-----
- Uses MERGE semantics with orig_id as merge key
- Batch size defaults to 100 (max 1000)
- Dry-run validates payloads without executing writes
- Idempotency keys prevent duplicate processing
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP Framework ─────────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphBulkAction, GraphBulkPayload

# ── Memgraph adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for graph.bulk tool")

# ── Audit (best-effort) ───────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _chunked(seq: list[Any], size: int) -> Iterable[list[Any]]:
    """Split sequence into chunks of given size."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _safe_labels(labels: list[str]) -> str:
    """Convert label list to safe Cypher label expression."""
    if not labels or not isinstance(labels, list):
        raise ValueError("labels must be a non-empty list")
    return ":".join(f"`{l!s}`" for l in labels if str(l).strip())


def _validate_node(node: dict[str, Any]) -> None:
    """Validate node structure."""
    if "labels" not in node or not node["labels"]:
        raise ValueError("Node requires non-empty 'labels' field")
    if "orig_id" not in node or not str(node.get("orig_id", "")).strip():
        raise ValueError("Node requires non-empty 'orig_id' field")


def _validate_edge(edge: dict[str, Any]) -> None:
    """Validate edge structure."""
    if "start_orig_id" not in edge or not str(edge.get("start_orig_id", "")).strip():
        raise ValueError("Edge requires non-empty 'start_orig_id' field")
    if "end_orig_id" not in edge or not str(edge.get("end_orig_id", "")).strip():
        raise ValueError("Edge requires non-empty 'end_orig_id' field")
    if "type" not in edge or not str(edge.get("type", "")).strip():
        raise ValueError("Edge requires non-empty 'type' field")


def _inject_metadata(props: dict[str, Any], principal: str, tenant: str, is_update: bool = False) -> dict[str, Any]:
    """Inject metadata into properties."""
    result = {**props}
    result["tenant"] = tenant

    if is_update:
        result["updated_by"] = principal
        result["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    else:
        result["created_by"] = principal
        result["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Idempotency Cache (in-memory, per-invocation)
# ──────────────────────────────────────────────────────────────────────────────
class IdempotencyCache:
    """Simple in-memory cache to track processed items by key."""

    def __init__(self):
        self._processed: set[str] = set()

    def is_processed(self, key: str) -> bool:
        """Check if key was already processed."""
        return key in self._processed

    def mark_processed(self, key: str) -> None:
        """Mark key as processed."""
        self._processed.add(key)


# ──────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ──────────────────────────────────────────────────────────────────────────────
def _act_ingest_nodes(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str, dry_run: bool = False
) -> dict[str, Any]:
    """
    Bulk ingest nodes with MERGE semantics.

    Creates or updates nodes using orig_id as merge key.
    Supports dry-run mode for validation.
    """
    start_time = time.time()
    nodes = payload.get("nodes", [])
    batch_size = payload.get("batch_size", 100)
    fail_fast = payload.get("fail_fast", True)

    processed = 0
    succeeded = 0
    failed = 0
    errors: list[str] = []

    # Dry-run: validate all nodes
    if dry_run:
        for node in nodes:
            processed += 1
            try:
                _validate_node(node)
                succeeded += 1
            except Exception as e:
                failed += 1
                errors.append(f"Node {processed}: {e!s}")
                if fail_fast:
                    break

        return {
            "ok": True,
            "action": "ingest_nodes",
            "dry_run": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors[:10],  # Limit error list
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    # Actual processing
    for batch in _chunked(nodes, batch_size):
        for node in batch:
            processed += 1
            try:
                # Validate
                _validate_node(node)

                # Extract fields
                labels = _safe_labels(node["labels"])
                orig_id = str(node["orig_id"]).strip()
                props = node.get("props", {})

                # Inject metadata
                props = _inject_metadata(props, principal, tenant, is_update=False)
                props["orig_id"] = orig_id  # Ensure orig_id in props

                # Execute MERGE
                cypher = f"MERGE (n:{labels} {{orig_id: $orig_id}}) SET n += $props"
                db.query(cypher, {"orig_id": orig_id, "props": props})

                succeeded += 1

            except Exception as e:
                failed += 1
                error_msg = f"Node {processed} (orig_id={node.get('orig_id', 'unknown')}): {e!s}"
                errors.append(error_msg)
                logger.warning("bulk_ingest_nodes_failed", error=str(e), node_index=processed)

                if fail_fast:
                    break

        if fail_fast and failed > 0:
            break

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "ok": True,
        "action": "ingest_nodes",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors[:10],  # Limit to first 10 errors
        "elapsed_ms": elapsed_ms,
    }


def _act_ingest_edges(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str, dry_run: bool = False
) -> dict[str, Any]:
    """
    Bulk ingest edges/relationships with MERGE semantics.

    Creates or updates relationships using endpoints as merge key.
    Supports dry-run mode for validation.
    """
    start_time = time.time()
    edges = payload.get("edges", [])
    batch_size = payload.get("batch_size", 100)
    fail_fast = payload.get("fail_fast", True)

    processed = 0
    succeeded = 0
    failed = 0
    errors: list[str] = []

    # Dry-run: validate all edges
    if dry_run:
        for edge in edges:
            processed += 1
            try:
                _validate_edge(edge)
                succeeded += 1
            except Exception as e:
                failed += 1
                errors.append(f"Edge {processed}: {e!s}")
                if fail_fast:
                    break

        return {
            "ok": True,
            "action": "ingest_edges",
            "dry_run": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors[:10],
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    # Actual processing
    for batch in _chunked(edges, batch_size):
        for edge in batch:
            processed += 1
            try:
                # Validate
                _validate_edge(edge)

                # Extract fields
                start_id = str(edge["start_orig_id"]).strip()
                end_id = str(edge["end_orig_id"]).strip()
                rel_type = str(edge["type"]).strip()
                props = edge.get("props", {})

                # Inject metadata
                props = _inject_metadata(props, principal, tenant, is_update=False)

                # Execute MERGE
                cypher = (
                    f"MATCH (a {{orig_id: $start_id, tenant: $tenant}}), "
                    f"(b {{orig_id: $end_id, tenant: $tenant}}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) "
                    f"SET r += $props"
                )
                db.query(cypher, {"start_id": start_id, "end_id": end_id, "tenant": tenant, "props": props})

                succeeded += 1

            except Exception as e:
                failed += 1
                error_msg = (
                    f"Edge {processed} ({edge.get('start_orig_id', '?')}->{edge.get('end_orig_id', '?')}): {e!s}"
                )
                errors.append(error_msg)
                logger.warning("bulk_ingest_edges_failed", error=str(e), edge_index=processed)

                if fail_fast:
                    break

        if fail_fast and failed > 0:
            break

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "ok": True,
        "action": "ingest_edges",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors[:10],
        "elapsed_ms": elapsed_ms,
    }


def _act_upsert_nodes(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str, dry_run: bool = False
) -> dict[str, Any]:
    """
    Bulk upsert nodes with idempotency support.

    Uses idempotency_key to prevent duplicate processing.
    If idempotency_key is provided, tracks processed items and skips duplicates.
    """
    start_time = time.time()
    nodes = payload.get("nodes", [])
    batch_size = payload.get("batch_size", 100)
    fail_fast = payload.get("fail_fast", True)
    idempotency_key = payload.get("idempotency_key")

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

    # Initialize idempotency cache if key provided
    cache = IdempotencyCache() if idempotency_key else None

    # Dry-run: validate all nodes
    if dry_run:
        for node in nodes:
            processed += 1
            try:
                _validate_node(node)

                # Check idempotency
                if cache:
                    item_key = f"{idempotency_key}:{node.get('orig_id', '')}"
                    if cache.is_processed(item_key):
                        skipped += 1
                        continue
                    cache.mark_processed(item_key)

                succeeded += 1
            except Exception as e:
                failed += 1
                errors.append(f"Node {processed}: {e!s}")
                if fail_fast:
                    break

        return {
            "ok": True,
            "action": "upsert_nodes",
            "dry_run": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "idempotency_key": idempotency_key,
            "errors": errors[:10],
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    # Actual processing
    for batch in _chunked(nodes, batch_size):
        for node in batch:
            processed += 1
            try:
                # Validate
                _validate_node(node)

                # Check idempotency
                if cache:
                    item_key = f"{idempotency_key}:{node.get('orig_id', '')}"
                    if cache.is_processed(item_key):
                        skipped += 1
                        continue
                    cache.mark_processed(item_key)

                # Extract fields
                labels = _safe_labels(node["labels"])
                orig_id = str(node["orig_id"]).strip()
                props = node.get("props", {})

                # Check if node exists (for created_by vs updated_by)
                existed_rows = db.query(
                    "MATCH (n {orig_id: $orig_id, tenant: $tenant}) RETURN count(n) AS c",
                    {"orig_id": orig_id, "tenant": tenant},
                )
                is_update = bool(existed_rows and int(existed_rows[0].get("c", 0)) > 0)

                # Inject metadata
                props = _inject_metadata(props, principal, tenant, is_update=is_update)
                props["orig_id"] = orig_id

                # Execute MERGE
                cypher = f"MERGE (n:{labels} {{orig_id: $orig_id}}) SET n += $props"
                db.query(cypher, {"orig_id": orig_id, "props": props})

                succeeded += 1

            except Exception as e:
                failed += 1
                error_msg = f"Node {processed} (orig_id={node.get('orig_id', 'unknown')}): {e!s}"
                errors.append(error_msg)
                logger.warning("bulk_upsert_nodes_failed", error=str(e), node_index=processed)

                if fail_fast:
                    break

        if fail_fast and failed > 0:
            break

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "ok": True,
        "action": "upsert_nodes",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "errors": errors[:10],
        "elapsed_ms": elapsed_ms,
    }


def _act_upsert_edges(
    db: MemgraphAdapter, payload: dict[str, Any], principal: str, tenant: str, dry_run: bool = False
) -> dict[str, Any]:
    """
    Bulk upsert edges with idempotency support.

    Uses idempotency_key to prevent duplicate processing.
    """
    start_time = time.time()
    edges = payload.get("edges", [])
    batch_size = payload.get("batch_size", 100)
    fail_fast = payload.get("fail_fast", True)
    idempotency_key = payload.get("idempotency_key")

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

    # Initialize idempotency cache if key provided
    cache = IdempotencyCache() if idempotency_key else None

    # Dry-run: validate all edges
    if dry_run:
        for edge in edges:
            processed += 1
            try:
                _validate_edge(edge)

                # Check idempotency
                if cache:
                    item_key = f"{idempotency_key}:{edge.get('start_orig_id', '')}:{edge.get('end_orig_id', '')}:{edge.get('type', '')}"
                    if cache.is_processed(item_key):
                        skipped += 1
                        continue
                    cache.mark_processed(item_key)

                succeeded += 1
            except Exception as e:
                failed += 1
                errors.append(f"Edge {processed}: {e!s}")
                if fail_fast:
                    break

        return {
            "ok": True,
            "action": "upsert_edges",
            "dry_run": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "idempotency_key": idempotency_key,
            "errors": errors[:10],
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    # Actual processing
    for batch in _chunked(edges, batch_size):
        for edge in batch:
            processed += 1
            try:
                # Validate
                _validate_edge(edge)

                # Check idempotency
                if cache:
                    item_key = f"{idempotency_key}:{edge.get('start_orig_id', '')}:{edge.get('end_orig_id', '')}:{edge.get('type', '')}"
                    if cache.is_processed(item_key):
                        skipped += 1
                        continue
                    cache.mark_processed(item_key)

                # Extract fields
                start_id = str(edge["start_orig_id"]).strip()
                end_id = str(edge["end_orig_id"]).strip()
                rel_type = str(edge["type"]).strip()
                props = edge.get("props", {})

                # Check if relationship exists
                existed_rows = db.query(
                    f"MATCH (a {{orig_id: $start_id, tenant: $tenant}})-[r:`{rel_type}`]->(b {{orig_id: $end_id, tenant: $tenant}}) RETURN count(r) AS c",
                    {"start_id": start_id, "end_id": end_id, "tenant": tenant},
                )
                is_update = bool(existed_rows and int(existed_rows[0].get("c", 0)) > 0)

                # Inject metadata
                props = _inject_metadata(props, principal, tenant, is_update=is_update)

                # Execute MERGE
                cypher = (
                    f"MATCH (a {{orig_id: $start_id, tenant: $tenant}}), "
                    f"(b {{orig_id: $end_id, tenant: $tenant}}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) "
                    f"SET r += $props"
                )
                db.query(cypher, {"start_id": start_id, "end_id": end_id, "tenant": tenant, "props": props})

                succeeded += 1

            except Exception as e:
                failed += 1
                error_msg = (
                    f"Edge {processed} ({edge.get('start_orig_id', '?')}->{edge.get('end_orig_id', '?')}): {e!s}"
                )
                errors.append(error_msg)
                logger.warning("bulk_upsert_edges_failed", error=str(e), edge_index=processed)

                if fail_fast:
                    break

        if fail_fast and failed > 0:
            break

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "ok": True,
        "action": "upsert_edges",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "errors": errors[:10],
        "elapsed_ms": elapsed_ms,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ──────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="graph.bulk", required_scope="tools:write")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry point for graph.bulk tool.

    Enforces:
    - tools:write scope requirement
    - Principal and tenant validation
    - Audit logging for all operations

    See module docstring for supported actions and payload formats.
    """
    # Validate payload
    payload = payload or {}
    validated = GraphBulkPayload(**payload)

    # Merge validated defaults with user payload
    validated_dict = {**payload}
    for field_name, field_info in GraphBulkPayload.model_fields.items():
        if field_info.default is not None and field_name not in payload:
            validated_dict[field_name] = getattr(validated, field_name)

    # Extract context
    action = validated_dict["action"]
    principal = validated_dict["principal"]
    tenant = validated_dict["tenant"]
    dry_run = validated_dict.get("dry_run", False)

    # Initialize database adapter
    db = MemgraphAdapter()

    # Dispatch to action handler
    if action == GraphBulkAction.ingest_nodes:
        result = _act_ingest_nodes(db, validated_dict, principal, tenant, dry_run)
    elif action == GraphBulkAction.ingest_edges:
        result = _act_ingest_edges(db, validated_dict, principal, tenant, dry_run)
    elif action == GraphBulkAction.upsert_nodes:
        result = _act_upsert_nodes(db, validated_dict, principal, tenant, dry_run)
    elif action == GraphBulkAction.upsert_edges:
        result = _act_upsert_edges(db, validated_dict, principal, tenant, dry_run)
    else:
        raise ValueError(f"Unsupported action: {action}")

    # Audit (best-effort)
    with suppress(Exception):
        audit_access(
            principal=principal,
            resource="mcp.tools.graph.bulk",
            action=str(action),
            allowed=True,
            attributes={
                "tenant": tenant,
                "processed": result.get("processed", 0),
                "succeeded": result.get("succeeded", 0),
                "failed": result.get("failed", 0),
                "dry_run": dry_run,
                "idempotency_key": validated_dict.get("idempotency_key"),
            },
        )

    return result


# Back-compat aliases
run = invoke
handle = invoke
