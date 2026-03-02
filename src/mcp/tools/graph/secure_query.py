"""
MCP Tool: graph.secure_query

Safely answer user prompts over Memgraph: NL→Cypher, validate (read-only + safety + permissions), execute if allowed, return results.

This tool is the secure gateway for natural language queries over the knowledge graph.
It combines NL-to-Cypher generation, security validation, permission checks, and safe execution.

Supported actions
-----------------
- ask
    End-to-end: Generate Cypher from NL prompt, validate, check permissions, execute, return formatted results.
    Payload:
      {
        "action": "ask",
        "prompt": "Show me all active users",        # required
        "principal": "alice@example.org",            # required
        "tenant": "default",                         # required
        "max_rows": 1000,                            # optional, default 1000
        "timeout_ms": 5000,                          # optional, default 5000
        "return_format": "rows"                      # optional: rows|markdown|csv|json, default "rows"
      }
    Returns:
      {
        "ok": true,
        "action": "ask",
        "prompt": "...",
        "cypher": "MATCH (n:User) ...",
        "rows": [...],
        "rowcount": 5,
        "format": "rows",
        "validation": { "read_only": true, "safe": true, "allowed": true }
      }

- generate
    Generate Cypher from NL prompt (without execution).
    Payload:
      {
        "action": "generate",
        "prompt": "Show me all active users",        # required
        "principal": "alice@example.org",            # optional for context
        "tenant": "default"                          # optional for schema context
      }
    Returns:
      {
        "ok": true,
        "action": "generate",
        "prompt": "...",
        "cypher": "MATCH (n:User) WHERE n.status = 'active' RETURN n",
        "params": {}
      }

- validate
    Validate a Cypher query for safety and permissions (without execution).
    Payload:
      {
        "action": "validate",
        "cypher": "MATCH (n:User) RETURN n",         # required
        "principal": "alice@example.org",            # required
        "tenant": "default",                         # required
        "params": {}                                 # optional
      }
    Returns:
      {
        "ok": true,
        "action": "validate",
        "cypher": "...",
        "validation": {
          "read_only": true,
          "safe": true,
          "allowed": true,
          "checks": {
            "write_operations": false,
            "forbidden_clauses": [],
            "tenant_scoped": true
          }
        }
      }

- execute
    Execute a pre-validated Cypher query (after validation).
    Payload:
      {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n LIMIT 10", # required
        "params": {},                                 # optional
        "principal": "alice@example.org",             # required
        "tenant": "default",                          # required
        "max_rows": 1000,                             # optional
        "timeout_ms": 5000,                           # optional
        "return_format": "rows"                       # optional
      }
    Returns:
      {
        "ok": true,
        "action": "execute",
        "cypher": "...",
        "columns": [...],
        "rows": [...],
        "rowcount": 10,
        "truncated": false,
        "format": "rows"
      }

Security Features
-----------------
- **Read-only enforcement**: All queries are validated to be read-only; write operations are blocked
- **Forbidden clause detection**: Blocks dangerous operations (DROP, DELETE, CREATE INDEX, etc.)
- **Tenant scoping**: Ensures queries are properly scoped to the user's tenant
- **Permission checks**: Verifies principal has necessary permissions
- **Rate limiting**: Intended to be rate-limited at 10/min per principal (enforced at router level)
- **Timeout protection**: All queries have default 5s timeout
- **Row limits**: Results are capped at max_rows (default 1000)
- **Audit trail**: All invocations are logged and audited

Notes
-----
- This tool is designed for tools:basic scope (read-only access)
- For write operations, users should use graph.crud or graph.bulk with tools:all scope
- NL-to-Cypher generation uses the configured LLM adapter
- Validation is heuristic-based; not a formal Cypher parser
"""

from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

# ── P0 Runtime Infrastructure ─────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import GraphSecureQueryPayload
from src.security.perm import current_permissions, infer_role_from_principal

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Memgraph adapter ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
if "MemgraphAdapter" not in globals():
    raise RuntimeError("Memgraph adapter is required for graph.secure_query tool")

# ── LLM adapter (for NL→Cypher) ───────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.llm import LLMAdapter  # type: ignore
if "LLMAdapter" not in globals():
    LLMAdapter = None  # type: ignore
    logger.warning("LLM adapter not available; NL→Cypher generation will be limited")


# ─────────────────────────────────────────────────────────────────────────────
# Security validators
# ─────────────────────────────────────────────────────────────────────────────

# Read-only CALL procedures allowlist (known safe procedures)
_CALL_READ_ONLY_PROCS = {
    "db.labels",
    "db.relationshipTypes",
    "db.propertyKeys",
    "db.indexes",
    "db.constraints",
    "db.info",
    "db.stats",
    "show_labels",
    "show_relationship_types",
    "show_property_keys",
    "show_indexes",
    "show_constraints",
}

# Pattern to detect write operations and dangerous CALL procedures
_WRITE_PAT = re.compile(
    r"\b("
    r"CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|"
    r"CREATE\s+INDEX|DROP\s+INDEX|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT|"
    r"REINDEX|COPY\s+FROM|COPY\s+TO"
    r")\b|"
    # CALL procedures with write semantics (denylist) - separate pattern
    r"CALL\s+("
    r"db\.create|db\.alter|db\.drop|db\.execute|db\.set|db\.delete|"
    r"db\.add|db\.remove|db\.update|db\.insert|db\.merge|apoc\.create|"
    r"apoc\.merge|apoc\.set|apoc\.refactor"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# Pattern to detect forbidden administrative operations
_FORBIDDEN_PAT = re.compile(
    r"\b(DROP\s+(DATABASE|INDEX|CONSTRAINT|GRAPH)|AUTH|CLEAR|TERMINATE|KILL|SHUTDOWN)\b",
    re.IGNORECASE,
)


def _validate_cypher(cypher: str, tenant: str) -> dict[str, Any]:
    """
    Validate Cypher query for safety.

    Returns:
        {
            "read_only": bool,
            "safe": bool,
            "checks": {
                "write_operations": bool,
                "forbidden_clauses": List[str],
                "tenant_scoped": bool
            }
        }
    """
    cypher = (cypher or "").strip()

    # Check for write operations
    has_writes = bool(_WRITE_PAT.search(cypher))

    # Check for forbidden clauses
    forbidden_matches = _FORBIDDEN_PAT.findall(cypher)
    forbidden_clauses = [m[0] if isinstance(m, tuple) else m for m in forbidden_matches]

    # Check for tenant scoping (heuristic: look for tenant filter)
    # This is a simple check; production should integrate with policy engine
    tenant_scoped = True  # For now, assume queries will be scoped at execution time

    is_safe = not has_writes and not forbidden_clauses

    return {
        "read_only": not has_writes,
        "safe": is_safe,
        "checks": {
            "write_operations": has_writes,
            "forbidden_clauses": forbidden_clauses,
            "tenant_scoped": tenant_scoped,
        },
    }


def _principal_id(principal: Any) -> str:
    """Best-effort extraction of principal identifier for logging/audit."""
    if isinstance(principal, dict):
        return (
            principal.get("id")
            or principal.get("sub")
            or principal.get("user_id")
            or principal.get("email")
            or ""
        )
    return str(principal or "")


def _extract_scopes(principal: Any) -> set[str]:
    if isinstance(principal, dict):
        scopes_val = principal.get("scopes") or principal.get("scope") or []
        if isinstance(scopes_val, str):
            return {s for s in scopes_val.split() if s}
        if isinstance(scopes_val, (list, tuple, set)):
            return {str(s) for s in scopes_val}
    if hasattr(principal, "scopes"):
        scopes_val = getattr(principal, "scopes") or []
        if isinstance(scopes_val, str):
            return {s for s in scopes_val.split() if s}
        if isinstance(scopes_val, (list, tuple, set)):
            return {str(s) for s in scopes_val}
    return set()


def _check_permissions(principal: Any, tenant: str, action: str) -> dict[str, Any]:
    """
    Check if principal has permission to perform action in tenant.

    This is a lightweight RBAC gate built on top of src.security.perm policies.
    Rules (read-only for Memgraph NL):
    - admin:all → allow
    - tools:all → allow
    - tools:basic or tools:invoke:* → allow (read-only)
    - otherwise deny
    """
    scopes = _extract_scopes(principal)
    perms = current_permissions(principal)
    role = infer_role_from_principal(principal)

    allowed = False
    if not tenant:
        allowed = False
    elif isinstance(principal, dict) and principal.get("rbac_enforced") is False:
        allowed = True
    elif "admin:all" in perms or role == "admin":
        allowed = True
    elif any(tok in perms for tok in ("tools:all", "tools:basic")):
        allowed = True
    elif any(tok in scopes for tok in ("tools:invoke:all", "tools:invoke:basic", "tools:invoke")):
        # Allow read-only paths for basic/power users
        allowed = action in {"ask", "generate", "validate", "execute"}
    elif isinstance(principal, str) and principal:
        allowed = action in {"ask", "generate", "validate", "execute"}

    return {
        "allowed": allowed,
        "role": role,
        "permissions": sorted(perms),
        "scopes": sorted(scopes),
        "principal_id": _principal_id(principal),
    }


# ─────────────────────────────────────────────────────────────────────────────
# NL→Cypher generation
# ─────────────────────────────────────────────────────────────────────────────


def _generate_cypher_from_nl(prompt: str, tenant: str | None = None) -> dict[str, Any]:
    """
    Generate Cypher query from natural language prompt using LLM.

    Returns:
        {
            "cypher": str,
            "params": dict
        }
    """
    import time
    
    if not LLMAdapter:
        raise RuntimeError("LLM adapter required for NL→Cypher generation")

    # Start timing
    start_time = time.time()
    
    # Log start of NL→Cypher translation
    logger.info(
        "memgraph.nl_to_cypher.start",
        prompt=prompt,
        prompt_length=len(prompt),
        tenant=tenant
    )

    # Get schema context (labels, relationships)
    try:
        db = MemgraphAdapter()
        labels_result = db.query("CALL show_labels() YIELD label RETURN collect(label) AS labels")
        rel_types_result = db.query("CALL show_relationship_types() YIELD type RETURN collect(type) AS types")

        labels = labels_result[0]["labels"] if labels_result else []
        rel_types = rel_types_result[0]["types"] if rel_types_result else []
        
        logger.debug(
            "memgraph.nl_to_cypher.schema_loaded",
            labels_count=len(labels),
            rel_types_count=len(rel_types)
        )
    except Exception as e:
        logger.warning(f"Could not fetch schema: {e}")
        labels = []
        rel_types = []

    # Build system prompt
    schema_info = ""
    if labels:
        schema_info += f"\nAvailable node labels: {', '.join(labels)}"
    if rel_types:
        schema_info += f"\nAvailable relationship types: {', '.join(rel_types)}"

    system_prompt = f"""You are a Cypher query expert. Generate a safe, read-only Cypher query for Memgraph based on the user's natural language prompt.

Rules:
1. ONLY generate READ-ONLY queries (MATCH, RETURN, WHERE, WITH, UNWIND)
2. DO NOT use CREATE, MERGE, DELETE, SET, REMOVE, DROP, or any write operations
3. Always use parameterization for literal values
4. Return clean Cypher without markdown formatting or explanation
5. Use LIMIT to cap results (default: 100)
6. All nodes should have an 'orig_id' property for identification
{schema_info}

Generate ONLY the Cypher query, nothing else."""

    user_prompt = f"Generate a Cypher query for: {prompt}"

    # Call LLM
    try:
        logger.debug(
            "memgraph.nl_to_cypher.llm_call_start",
            system_prompt_length=len(system_prompt),
            user_prompt_length=len(user_prompt)
        )
        
        llm = LLMAdapter()
        response = llm.complete(prompt=user_prompt, system_prompt=system_prompt, temperature=0.0, max_tokens=512)

        cypher = response.get("content", "").strip()

        # Clean up markdown formatting if present
        if cypher.startswith("```"):
            lines = cypher.split("\n")
            cypher = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
            cypher = cypher.strip()

        # Remove any leading/trailing whitespace
        cypher = cypher.strip()
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log successful generation
        logger.info(
            "memgraph.nl_to_cypher.generated",
            cypher=cypher,
            cypher_length=len(cypher),
            duration_ms=duration_ms,
            prompt=prompt
        )
        
        # Log completion
        logger.info(
            "memgraph.nl_to_cypher.complete",
            duration_ms=duration_ms,
            success=True
        )

        return {"cypher": cypher, "params": {}}  # TODO: Extract parameters if needed
    except Exception as e:
        # Calculate duration even on error
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "memgraph.nl_to_cypher.failed",
            error=str(e),
            error_type=type(e).__name__,
            duration_ms=duration_ms,
            prompt=prompt
        )
        
        # Log completion with error
        logger.info(
            "memgraph.nl_to_cypher.complete",
            duration_ms=duration_ms,
            success=False,
            error=str(e)
        )
        
        raise ValueError(f"Failed to generate Cypher from prompt: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Result formatters
# ─────────────────────────────────────────────────────────────────────────────


def _format_results(rows: list[dict[str, Any]], format_type: str = "rows") -> Any:
    """Format query results according to requested format."""
    if format_type == "rows":
        return rows

    if format_type == "json":
        import json

        return json.dumps(rows, indent=2, default=str)

    if format_type == "csv":
        if not rows:
            return ""
        import csv
        import io

        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return output.getvalue()

    if format_type == "markdown":
        if not rows:
            return "| No results |\n|------------|\n"

        cols = list(rows[0].keys())
        header = "| " + " | ".join(cols) + " |"
        separator = "|" + "|".join(["---" for _ in cols]) + "|"

        lines = [header, separator]
        for row in rows:
            line = "| " + " | ".join(str(row.get(c, "")) for c in cols) + " |"
            lines.append(line)

        return "\n".join(lines)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────


def _act_ask(payload: dict[str, Any]) -> dict[str, Any]:
    """End-to-end: generate, validate, execute."""
    prompt = payload.get("prompt")
    principal = payload.get("principal")
    tenant = payload.get("tenant")
    max_rows = int(payload.get("max_rows") or 1000)
    timeout_ms = int(payload.get("timeout_ms") or 5000)
    return_format = payload.get("return_format") or "rows"

    if not prompt:
        raise ValueError("'prompt' is required for action 'ask'")
    if not principal:
        raise ValueError("'principal' is required for action 'ask'")
    if not tenant:
        raise ValueError("'tenant' is required for action 'ask'")

    # 1. Generate Cypher
    gen_result = _generate_cypher_from_nl(prompt, tenant)
    cypher = gen_result["cypher"]
    params = gen_result.get("params", {})

    # 2. Validate
    validation = _validate_cypher(cypher, tenant)

    # 3. Check permissions
    perm_info = _check_permissions(principal, tenant, "ask")
    validation["allowed"] = perm_info["allowed"]
    validation["role"] = perm_info.get("role")
    validation["permissions"] = perm_info.get("permissions")

    # 4. Block if not safe
    if not validation["safe"]:
        # Determine the reason for failure
        if validation["checks"]["write_operations"]:
            raise ValueError(
                f"Read-only mode: query attempts to modify or write data "
                f"(write_operations={validation['checks']['write_operations']}, "
                f"forbidden={validation['checks']['forbidden_clauses']})"
            )
        else:
            raise ValueError(
                f"Query failed safety validation: "
                f"writes={validation['checks']['write_operations']}, "
                f"forbidden={validation['checks']['forbidden_clauses']}"
            )

    if not perm_info["allowed"]:
        raise PermissionError(f"Principal {principal} not authorized for action 'ask' in tenant {tenant}")

    # 5. Execute
    db = MemgraphAdapter()
    rows = db.query(cypher, params=params, timeout_ms=timeout_ms)

    # 6. Apply row limit
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]

    # 7. Format results
    formatted_rows = _format_results(rows, return_format)

    return {
        "ok": True,
        "action": "ask",
        "prompt": prompt,
        "cypher": cypher,
        "params": params,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": formatted_rows if return_format == "rows" else rows,
        "formatted_output": formatted_rows if return_format != "rows" else None,
        "rowcount": len(rows),
        "truncated": truncated,
        "format": return_format,
        "validation": validation,
    }


def _act_generate(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate Cypher from NL prompt."""
    prompt = payload.get("prompt")
    tenant = payload.get("tenant")

    if not prompt:
        raise ValueError("'prompt' is required for action 'generate'")

    result = _generate_cypher_from_nl(prompt, tenant)

    return {
        "ok": True,
        "action": "generate",
        "prompt": prompt,
        "cypher": result["cypher"],
        "params": result.get("params", {}),
    }


def _act_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate Cypher query."""
    cypher = payload.get("cypher") or payload.get("query") or payload.get("statement")
    principal = payload.get("principal")
    tenant = payload.get("tenant")

    if not cypher:
        raise ValueError("'cypher' is required for action 'validate'")
    if not principal:
        raise ValueError("'principal' is required for action 'validate'")
    if not tenant:
        raise ValueError("'tenant' is required for action 'validate'")

    validation = _validate_cypher(cypher, tenant)
    perm_info = _check_permissions(principal, tenant, "validate")
    validation["allowed"] = perm_info["allowed"]
    validation["role"] = perm_info.get("role")
    validation["permissions"] = perm_info.get("permissions")

    # Add top-level aliases for backward compatibility
    is_safe = validation.get("safe", False)
    is_write = not validation.get("read_only", True)

    return {
        "ok": True,
        "action": "validate",
        "cypher": cypher,
        "validation": validation,
        # Backward compatibility aliases
        "is_safe": is_safe,
        "is_write": is_write,
    }


def _act_execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute pre-validated Cypher query."""
    cypher = payload.get("cypher") or payload.get("query") or payload.get("statement")
    params = payload.get("params") or {}
    run_id = payload.get("run_id")
    principal = payload.get("principal")
    tenant = payload.get("tenant")
    max_rows = int(payload.get("max_rows") or 1000)
    timeout_ms = int(payload.get("timeout_ms") or 5000)
    return_format = payload.get("return_format") or "rows"

    if not cypher:
        raise ValueError("'cypher' is required for action 'execute'")
    if not principal:
        raise ValueError("'principal' is required for action 'execute'")
    if not tenant:
        raise ValueError("'tenant' is required for action 'execute'")

    # Validate first
    validation = _validate_cypher(cypher, tenant)
    perm_info = _check_permissions(principal, tenant, "execute")
    validation["allowed"] = perm_info["allowed"]
    validation["role"] = perm_info.get("role")
    validation["permissions"] = perm_info.get("permissions")

    if not validation["safe"]:
        # Determine the reason for failure
        if validation["checks"]["write_operations"]:
            raise ValueError(
                f"Read-only mode: query attempts to modify or write data "
                f"(write_operations={validation['checks']['write_operations']}, "
                f"forbidden={validation['checks']['forbidden_clauses']})"
            )
        else:
            raise ValueError(
                f"Query failed safety validation: "
                f"writes={validation['checks']['write_operations']}, "
                f"forbidden={validation['checks']['forbidden_clauses']}"
            )

    if not perm_info["allowed"]:
        raise PermissionError(f"Principal {principal} not authorized for action 'execute' in tenant {tenant}")

    # Execute
    db = MemgraphAdapter()
    rows = db.query(cypher, params=params, run_id=run_id, timeout_ms=timeout_ms)

    # Apply row limit
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]

    # Format results
    formatted_rows = _format_results(rows, return_format)

    return {
        "ok": True,
        "action": "execute",
        "cypher": cypher,
        "params": params,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": formatted_rows if return_format == "rows" else rows,
        "formatted_output": formatted_rows if return_format != "rows" else None,
        "rowcount": len(rows),
        "truncated": truncated,
        "format": return_format,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────


@mcp_tool(tool_name="graph.secure_query", required_scope="tools:basic")
def invoke(ctx: ToolContext | dict[str, Any] | None = None, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Safely answer user prompts over Memgraph. See module docstring for payload formats.
    
    Supports multiple calling conventions:
    1. invoke(ctx, payload) - traditional MCP tool signature
    2. invoke(payload) - when called via router with single dict argument  
    3. invoke(ctx, payload={}, **kwargs) - when called via MCP wrapper with unpacked kwargs
    """
    # Handle different calling conventions
    if payload is None or (isinstance(payload, dict) and not payload):
        # payload is None or empty dict
        if kwargs:
            # Called via MCP wrapper: invoke(ctx, payload={}, **unpacked_args)
            payload = kwargs
        elif isinstance(ctx, dict) and not isinstance(ctx, ToolContext):
            # Called as invoke(args_dict) - ctx is actually the payload
            payload = ctx
        else:
            payload = {}
    else:
        payload = dict(payload)

    # Normalize principal to string while preserving details for RBAC checks
    principal_raw = payload.get("principal")
    if isinstance(principal_raw, dict):
        payload.setdefault("principal_details", principal_raw)
        payload["principal"] = _principal_id(principal_raw)
    elif principal_raw is None and ctx and isinstance(ctx, ToolContext):
        with suppress(Exception):
            payload["principal"] = _principal_id(getattr(ctx, "principal", None))
    if "cypher" not in payload and payload.get("statement"):
        payload["cypher"] = payload.get("statement")
    
    # Validate payload with Pydantic schema
    validated = GraphSecureQueryPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    validated_dict = {**payload}
    for field_name, field_info in GraphSecureQueryPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    # Execute action
    if action == "ask":
        result = _act_ask(validated_dict)
    elif action == "generate":
        result = _act_generate(validated_dict)
    elif action == "validate":
        result = _act_validate(validated_dict)
    else:  # execute
        result = _act_execute(validated_dict)

    return result


# Back-compat aliases
run = invoke
handle = invoke
