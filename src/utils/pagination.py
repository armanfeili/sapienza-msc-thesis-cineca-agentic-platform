from __future__ import annotations

import hashlib
import json
from typing import Any


def make_page(
    items: list[Any], page_size: int = 50, page_token: str | None = None
) -> tuple[list[Any], str | None]:
    """Simple stateless pagination over a list.

    - page_token is a base10 offset string (e.g., '0', '50').
    - returns (page_items, next_page_token)
    """
    try:
        offset = int(page_token) if page_token is not None else 0
    except Exception:
        offset = 0
    if page_size <= 0:
        page_size = 50
    end = offset + page_size
    page_items = items[offset:end]
    next_token = str(end) if end < len(items) else None
    return page_items, next_token


def compute_etag(obj: Any, context: dict[str, Any] | None = None) -> str:
    """Compute a weak ETag for a JSON-serializable object.

    Args:
        obj: The primary object to hash (e.g., response body)
        context: Optional dict with route/filter context (e.g., {'route': 'user_jobs', 'status': 'running'})
                 This ensures ETags vary per route and filtered results.
    """
    try:
        # Include context in hash to ensure ETags differ per route and filters
        hash_input = {"data": obj}
        if context:
            hash_input["context"] = context
        raw = json.dumps(hash_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except Exception:
        raw = str(obj).encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    return f'W/"{h}"'
