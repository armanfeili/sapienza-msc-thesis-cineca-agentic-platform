from __future__ import annotations

import contextlib
import inspect
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

# Simple in-memory fallback store for tests / environments without Redis
_IN_MEMORY_STORE: dict = {}


def _get(key: str) -> dict | None:
    return _IN_MEMORY_STORE.get(key)


def _set(key: str, value: dict, ex: int | None = None) -> None:
    _IN_MEMORY_STORE[key] = value


def idempotent(key_fn: Callable[..., str], ttl: int = 24 * 3600) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator factory that provides idempotency for FastAPI endpoints.

    key_fn will be called as key_fn(idempotency_key, **bound_args) where bound_args are the
    wrapped function's parameters bound by name. This avoids positional mis-binding which
    can confuse FastAPI/Pydantic when generating schemas.

    The decorated function may return a dict or a Response; if it's a dict it will be
    stored and replayed as the same body. For richer responses, key_fn may arrange to
    store headers/status in the returned envelope.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            # Bind args/kwargs to parameter names to call key_fn safely
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except Exception:
                bound = None

            # Extract Idempotency-Key if present (common FastAPI pattern: Request param)
            idem_key = None
            if bound is not None:
                for _name, val in bound.arguments.items():
                    # FastAPI Request is usually from starlette.requests.Request
                    if (hasattr(val, "headers") and isinstance(val.headers, dict)) or hasattr(val, "headers"):
                        # attempt to grab header attr
                        try:
                            idem_key = val.headers.get("Idempotency-Key")
                            if idem_key:
                                break
                        except Exception:
                            pass

            if not idem_key:
                # Fallback to kwargs or args inspection
                idem_key = kwargs.get("idempotency_key") or kwargs.get("Idempotency-Key")

            if not idem_key:
                # No idempotency requested; just call the function
                return await fn(*args, **kwargs)

            cache_key = key_fn(idem_key, **(bound.arguments if bound is not None else {}))
            # Attempt to get cached envelope
            try:
                cached = _get(cache_key)
            except Exception:
                cached = None

            if cached is not None:
                # Replay stored response envelope: we expect {'status':int,'headers':{},'body':...}
                status = cached.get("status", 200)
                headers = cached.get("headers", {})
                body = cached.get("body")
                # Return the body directly (FastAPI will serialize dicts)
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=status, content=body, headers=headers)

            # No cached value: call the handler and store envelope
            result = await fn(*args, **kwargs)

            # Normalize envelope
            envelope = {"status": 200, "headers": {}, "body": None}
            if hasattr(result, "status_code") and hasattr(result, "body"):
                # It's a Response-like object
                try:
                    envelope["status"] = int(result.status_code)
                except Exception:
                    envelope["status"] = 200
                try:
                    # body might be bytes; attempt to decode
                    raw = result.body
                    if isinstance(raw, (bytes, bytearray)):
                        try:
                            body = raw.decode("utf-8")
                            envelope["body"] = json.loads(body)
                        except Exception:
                            envelope["body"] = raw.decode("utf-8", errors="ignore")
                    else:
                        envelope["body"] = raw
                except Exception:
                    envelope["body"] = None
                # Headers
                try:
                    hdrs = dict(result.headers or {})
                    envelope["headers"] = hdrs
                except Exception:
                    envelope["headers"] = {}
            else:
                # Assume it's serializable (dict/Model)
                try:
                    if hasattr(result, "model_dump"):
                        envelope["body"] = result.model_dump()
                    elif isinstance(result, dict):
                        envelope["body"] = result
                    else:
                        envelope["body"] = result
                except Exception:
                    envelope["body"] = None

            # Store envelope
            with contextlib.suppress(Exception):
                _set(cache_key, envelope, ex=ttl)

            return result

        # Ensure FastAPI sees original signature for docs/schema generation
        wrapper.__signature__ = sig
        return wrapper

    return decorator
