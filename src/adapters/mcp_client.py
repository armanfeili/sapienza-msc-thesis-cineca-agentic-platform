"""
MCP client adapter (in-process tool bus)

This adapter provides a thin, dependency-free interface to discover and invoke
MCP-style tools implemented as Python modules under `src.mcp.tools`.

Conventions:
- Each tool lives at:  src/mcp/tools/<namespace>/<name>.py
- A tool exposes one callable entrypoint among:
    - `invoke(payload: dict, **kwargs)`
    - `run(**kwargs)`
    - `handle(**kwargs)`
    - `main(**kwargs)`

Discovery:
- `discover()` walks `src.mcp.tools` and returns ToolInfo entries with the
  best-effort detected entrypoint and the first line of the module docstring.

Invocation:
- `invoke(name="graph.query", args={...}, timeout=30)` resolves the module
  `src.mcp.tools.graph.query`, picks the first supported entrypoint, and calls it.
- Both sync and async tool functions are supported. Invocation itself is `async`.

Provenance:
- Optionally records provenance via `src.provenance` on success/failure.

This client is intended for use by orchestrators or routers; the /tools router has
a similar inline logic to avoid a hard dependency on this adapter.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Logging (structlog if available; stdlib otherwise)
try:
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Best-effort provenance
try:  # pragma: no cover
    from src.provenance import record_provenance
except Exception:  # pragma: no cover
    record_provenance = None  # type: ignore


TOOLS_PACKAGE = "src.mcp.tools"
ENTRYPOINT_CANDIDATES: tuple[str, ...] = ("invoke", "run", "handle", "main")


# ---------------- Exceptions ----------------
class MCPError(RuntimeError):
    """Generic MCP client error."""


class ToolNotFound(MCPError):
    """Raised when a tool module cannot be resolved or imported."""


class ToolInvocationError(MCPError):
    """Raised when a tool raises or times out."""


# ---------------- Data models ----------------
@dataclass(frozen=True)
class ToolInfo:
    name: str  # dotted short name (e.g., "graph.query")
    module: str  # import path (e.g., "src.mcp.tools.graph.query")
    entrypoint: str | None  # detected callable name
    description: str | None  # first line of module docstring


@dataclass
class _ResolvedTool:
    name: str
    module: str
    entrypoint_name: str | None
    func: Callable[..., Any] | None


# ---------------- Client ----------------
class MCPClient:
    def __init__(self, base_package: str = TOOLS_PACKAGE) -> None:
        self.base_package = base_package

    # ---- Discovery ----
    def discover(self) -> list[ToolInfo]:
        """Walk the tools package and return best-effort descriptors."""
        out: list[ToolInfo] = []
        try:
            pkg = importlib.import_module(self.base_package)
            if not hasattr(pkg, "__path__"):
                return out
        except Exception as e:  # pragma: no cover
            logger.debug("tools base package not importable: %s", e)
            return out

        for m in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
            mod_path = m.name
            short = self._short_name(mod_path)
            if not short:
                continue
            entry: str | None = None
            desc: str | None = None
            try:
                mod = importlib.import_module(mod_path)
                entry, _ = self._detect_entrypoint(mod)
                doc = getattr(mod, "__doc__", None)
                if isinstance(doc, str):
                    first = doc.strip().splitlines()
                    if first:
                        desc = first[0].strip()
            except Exception:
                # keep listing the module, even if import fails now
                pass
            out.append(ToolInfo(name=short, module=mod_path, entrypoint=entry, description=desc))
        return out

    # ---- Invocation ----
    async def invoke(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        timeout: float | None = 30.0,
        provenance_meta: dict[str, Any] | None = None,
    ) -> Any:
        """
        Invoke a tool by dotted name. Returns the tool's result.

        Args:
            name: dotted tool name (e.g., "graph.query")
            args: payload passed to the tool. If the entrypoint signature is (payload),
                  we pass the dict positionally; otherwise we expand as **kwargs.
            timeout: optional seconds to wait before raising ToolInvocationError.
            provenance_meta: optional dict added to provenance record.

        Raises:
            ToolNotFound, ToolInvocationError
        """
        resolved = self._resolve_tool(name)
        if resolved.func is None:
            # Try a real import to enrich error message
            try:
                mod = importlib.import_module(resolved.module)
                ep, fn = self._detect_entrypoint(mod)
                resolved.entrypoint_name, resolved.func = ep, fn
            except Exception as e:
                self._record_provenance(name, args or {}, {"error": str(e)}, False, provenance_meta)
                raise ToolNotFound(f"Tool '{name}' not found or not importable: {e}") from e

        if resolved.func is None:
            self._record_provenance(name, args or {}, {"error": "entrypoint not found"}, False, provenance_meta)
            raise ToolInvocationError(f"Tool '{name}' has no supported entrypoint {ENTRYPOINT_CANDIDATES}")

        start_ns = time.monotonic_ns()

        async def _call() -> Any:
            try:
                # Prefer kwargs invocation; fall back to positional (payload) for legacy tools
                if args is None:
                    result = resolved.func()  # type: ignore[misc]
                else:
                    try:
                        sig = inspect.signature(resolved.func)  # type: ignore[arg-type]
                        if len(sig.parameters) == 1 and next(iter(sig.parameters.values())).kind in (
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            inspect.Parameter.POSITIONAL_ONLY,
                        ):
                            # Likely a single 'payload' arg
                            result = resolved.func(args)  # type: ignore[misc]
                        else:
                            result = resolved.func(**args)  # type: ignore[misc]
                    except Exception:
                        # If signature inspection failed, try kwargs then payload
                        try:
                            result = resolved.func(**args)  # type: ignore[misc]
                        except Exception:
                            result = resolved.func(args)  # type: ignore[misc]
                if inspect.isawaitable(result):
                    return await result  # type: ignore[misc]
                return result
            except Exception as e:
                raise ToolInvocationError(f"{type(e).__name__}: {e}") from e

        try:
            if timeout and timeout > 0:
                result = await asyncio.wait_for(_call(), timeout=timeout)
            else:
                result = await _call()
            self._record_provenance(name, args or {}, {"result": result}, True, provenance_meta, start_ns)
            return result
        except Exception as e:
            self._record_provenance(
                name, args or {}, {"error": str(e)}, False, provenance_meta, start_ns  # type: ignore[arg-type]
            )
            raise

    # ---- Internals ----
    def _resolve_tool(self, name: str) -> _ResolvedTool:
        module_path = f"{self.base_package}.{name}"
        try:
            mod = importlib.import_module(module_path)
            ep_name, fn = self._detect_entrypoint(mod)
            return _ResolvedTool(name=name, module=module_path, entrypoint_name=ep_name, func=fn)
        except Exception:
            return _ResolvedTool(name=name, module=module_path, entrypoint_name=None, func=None)

    @staticmethod
    def _detect_entrypoint(mod) -> tuple[str | None, Callable[..., Any] | None]:
        for candidate in ENTRYPOINT_CANDIDATES:
            fn = getattr(mod, candidate, None)
            if callable(fn):
                return candidate, fn
        return None, None

    @staticmethod
    def _short_name(module_path: str) -> str | None:
        prefix = TOOLS_PACKAGE + "."
        if module_path.startswith(prefix):
            return module_path[len(prefix) :]
        return None

    @staticmethod
    def _duration_ms(start_ns: int | None) -> int | None:
        if start_ns is None:
            return None
        return int((time.monotonic_ns() - start_ns) / 1_000_000)

    def _record_provenance(
        self,
        name: str,
        args: dict[str, Any],
        out: dict[str, Any],
        success: bool,
        meta: dict[str, Any] | None = None,
        start_ns: int | None = None,
    ) -> None:
        if record_provenance is None:  # provenance not available
            return
        try:
            record_provenance(
                actor="mcp",
                action=f"tool.{name}",
                resource="mcp_client.invoke",
                input={"args": args},
                output=out,
                meta=meta or {},
                success=success,
                duration_ms=self._duration_ms(start_ns),
            )
        except Exception:  # pragma: no cover
            # Do not fail call due to provenance issues
            pass


# ---------------- Singleton factory ----------------
_CLIENT: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = MCPClient()
    return _CLIENT


__all__ = [
    "MCPClient",
    "MCPError",
    "ToolInfo",
    "ToolInvocationError",
    "ToolNotFound",
    "get_mcp_client",
]
