"""
ETag generation and validation utilities for HTTP caching.

Features:
- Generate weak ETags from JSON-serialized objects
- Validate ETags against If-None-Match headers
- Support for strong and weak ETags (RFC 7232)
- Content-addressable ETag generation using SHA-256

Model
-----
- Strong ETag: changes when content changes (binary identical)
- Weak ETag: changes when content semantically changes (W/"xxx")
- List/collection ETags: hash of combined items

API
---
- generate_etag(obj: Any, weak=False) -> str
- validate_etag(if_none_match: str, current_etag: str) -> bool
- etag_for_list(items: List[Any]) -> str
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _json_serialize(obj: Any) -> str:
    """
    Serialize object to JSON for content hashing.
    Uses default encoder with sorted keys for deterministic output.
    """
    try:
        return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        # Fallback to str representation for non-JSON-serializable objects
        return str(obj)


def generate_etag(obj: Any, weak: bool = False) -> str:
    """
    Generate an ETag from an object's JSON representation.

    Args:
        obj: Object to generate ETag for (typically a dict or list)
        weak: If True, returns weak ETag (W/"..."), else strong ("...")

    Returns:
        ETag string in format: "abc123" or W/"abc123"

    Example:
        >>> resp = {"id": "123", "name": "test"}
        >>> etag = generate_etag(resp)
        >>> etag
        '"a1b2c3d4..."'
    """
    json_str = _json_serialize(obj)
    hash_digest = hashlib.sha256(json_str.encode("utf-8")).hexdigest()[:16]

    if weak:
        return f'W/"{hash_digest}"'
    return f'"{hash_digest}"'


def etag_for_list(items: list[Any], weak: bool = False) -> str:
    """
    Generate ETag for a list of items.
    Useful for list endpoints where ETag should reflect all items.

    Args:
        items: List of items (typically response items)
        weak: If True, returns weak ETag

    Returns:
        ETag string

    Example:
        >>> items = [{"id": "1"}, {"id": "2"}]
        >>> etag = etag_for_list(items)
    """
    combined = json.dumps(items, sort_keys=True, default=str, separators=(",", ":"))
    hash_digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    if weak:
        return f'W/"{hash_digest}"'
    return f'"{hash_digest}"'


def validate_etag(if_none_match: str | None, current_etag: str) -> bool:
    """
    Check if current ETag matches If-None-Match header.
    If matched, caller should return 304 Not Modified.

    Args:
        if_none_match: Value from If-None-Match header (e.g., '"abc123"' or W/"abc123" or '*')
        current_etag: Current ETag for the resource

    Returns:
        True if ETag matches (should return 304), False otherwise

    Implementation notes:
    - RFC 7232: If-None-Match: "abc" matches "abc" and W/"abc" (weak match)
    - If-None-Match: * matches any representation
    - Multiple ETags separated by comma: "abc", W/"def" (any match = 304)

    Example:
        >>> if_none_match = '"abc123"'
        >>> current_etag = '"abc123"'
        >>> validate_etag(if_none_match, current_etag)
        True
    """
    if not if_none_match:
        return False

    # Trim whitespace
    if_none_match = if_none_match.strip()
    current_etag = current_etag.strip()

    # Handle wildcard
    if if_none_match == "*":
        return True

    # Parse multiple ETags (comma-separated)
    candidates = [tag.strip() for tag in if_none_match.split(",")]

    for candidate in candidates:
        # Strip quotes for comparison (weak match per RFC 7232)
        # Strong ETags: "abc"
        # Weak ETags: W/"abc"
        candidate_val = candidate.lower().replace("w/", "").strip('"')
        current_val = current_etag.lower().replace("w/", "").strip('"')

        if candidate_val == current_val:
            return True

    return False


def extract_etag_value(etag: str) -> str:
    """
    Extract the hash value from an ETag string.
    Removes quotes and W/ prefix.

    Args:
        etag: ETag string (e.g., '"abc123"' or W/"abc123")

    Returns:
        Hash value (e.g., 'abc123')

    Example:
        >>> extract_etag_value('"abc123"')
        'abc123'
        >>> extract_etag_value('W/"abc123"')
        'abc123'
    """
    return etag.lower().replace("w/", "").strip('"')


__all__ = [
    "etag_for_list",
    "extract_etag_value",
    "generate_etag",
    "validate_etag",
]
