"""
Prompt Catalog: Load and index the Memgraph NL prompt catalog for quick lookup.

This module provides fast access to the test prompt catalog which includes:
- Prompt text and IDs
- Categories (read_only, admin_write, dangerous, security, data_quality)
- Expected Cypher patterns and constraints
- RBAC expectations (allowed_for_user, allowed_for_admin)
- Execution hints (limit_hint, random, todo_mode)

The catalog is loaded once at module import time and cached for the duration.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Catalog Location
# ─────────────────────────────────────────────────────────────────────────────

# Path relative to this file's location
_CATALOG_PATHS = [
    # Primary location
    Path(__file__).parent.parent.parent / "tests/integration/resources/memgraph_nl_prompts.json",
    # Alternative locations
    Path(__file__).parent.parent.parent / "db/memgraph_domain/memgraph_nl_prompts.json",
    Path(__file__).parent.parent.parent / "resources/memgraph_nl_prompts.json",
]


# ─────────────────────────────────────────────────────────────────────────────
# Catalog Structure
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_prompt_catalog() -> dict[str, Any]:
    """
    Load and index the prompt catalog.
    
    Returns a dict with:
    - "by_id": dict mapping prompt ID to full prompt entry
    - "by_text_normalized": dict mapping normalized text to prompt entry
    - "by_category": dict mapping category to list of prompts
    - "all": list of all prompt entries
    - "loaded": bool indicating if catalog was found
    - "path": path to the loaded catalog (if any)
    """
    catalog = {
        "by_id": {},
        "by_text_normalized": {},
        "by_category": {},
        "all": [],
        "loaded": False,
        "path": None,
    }
    
    # Try each possible path
    catalog_path = None
    for path in _CATALOG_PATHS:
        if path.exists():
            catalog_path = path
            break
    
    if not catalog_path:
        log.warning(
            "prompt_catalog.not_found",
            searched_paths=[str(p) for p in _CATALOG_PATHS],
        )
        return catalog
    
    try:
        with open(catalog_path, encoding="utf-8") as f:
            prompts = json.load(f)
        
        catalog["all"] = prompts
        catalog["loaded"] = True
        catalog["path"] = str(catalog_path)
        
        for prompt in prompts:
            # Index by ID
            prompt_id = prompt.get("id")
            if prompt_id:
                catalog["by_id"][prompt_id] = prompt
            
            # Index by normalized text (lowercase, stripped)
            text = prompt.get("text", "")
            normalized = _normalize_text(text)
            if normalized:
                catalog["by_text_normalized"][normalized] = prompt
            
            # Index by category
            category = prompt.get("category", "unknown")
            if category not in catalog["by_category"]:
                catalog["by_category"][category] = []
            catalog["by_category"][category].append(prompt)
        
        log.info(
            "prompt_catalog.loaded",
            path=str(catalog_path),
            total_prompts=len(prompts),
            categories=list(catalog["by_category"].keys()),
        )
        
    except Exception as e:
        log.error(
            "prompt_catalog.load_error",
            path=str(catalog_path),
            error=str(e),
        )
    
    return catalog


def _normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip, collapse whitespace)."""
    import re
    t = (text or "").lower().strip()
    # Collapse multiple whitespace
    t = re.sub(r"\s+", " ", t)
    # Remove trailing punctuation for matching
    t = t.rstrip("?.!,")
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Lookup Functions
# ─────────────────────────────────────────────────────────────────────────────

def get_prompt_by_id(prompt_id: str) -> dict[str, Any] | None:
    """Get a prompt entry by its ID (e.g., 'p01', 'p03')."""
    catalog = load_prompt_catalog()
    return catalog["by_id"].get(prompt_id)


def match_prompt_by_text(text: str, threshold: float = 0.85) -> dict[str, Any] | None:
    """
    Find a matching prompt entry by text.
    
    First tries exact match (after normalization), then fuzzy match if threshold < 1.0.
    
    Args:
        text: The user's prompt text
        threshold: Similarity threshold for fuzzy matching (0.0-1.0)
    
    Returns:
        Matched prompt entry or None
    """
    catalog = load_prompt_catalog()
    
    if not catalog["loaded"]:
        return None
    
    normalized = _normalize_text(text)
    
    # Try exact match first
    exact_match = catalog["by_text_normalized"].get(normalized)
    if exact_match:
        return exact_match
    
    # If threshold < 1.0, try fuzzy matching
    if threshold < 1.0:
        return _fuzzy_match(normalized, catalog["all"], threshold)
    
    return None


def _fuzzy_match(
    normalized: str,
    prompts: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any] | None:
    """
    Find best fuzzy match using Levenshtein distance.
    
    Uses a simple ratio calculation: 1 - (distance / max_len)
    """
    best_match = None
    best_score = 0.0
    
    for prompt in prompts:
        prompt_text = _normalize_text(prompt.get("text", ""))
        if not prompt_text:
            continue
        
        # Calculate similarity score
        score = _similarity_score(normalized, prompt_text)
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = prompt
    
    return best_match


def _similarity_score(s1: str, s2: str) -> float:
    """
    Calculate similarity score between two strings.
    
    Uses simple substring and word overlap metrics for speed.
    For better accuracy, consider using difflib.SequenceMatcher or fuzzywuzzy.
    """
    if not s1 or not s2:
        return 0.0
    
    # Exact match
    if s1 == s2:
        return 1.0
    
    # Substring match (one contains the other)
    if s1 in s2:
        return len(s1) / len(s2)
    if s2 in s1:
        return len(s2) / len(s1)
    
    # Word overlap score
    words1 = set(s1.split())
    words2 = set(s2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union)  # Jaccard similarity


def get_prompts_by_category(category: str) -> list[dict[str, Any]]:
    """Get all prompts in a category."""
    catalog = load_prompt_catalog()
    return catalog["by_category"].get(category, [])


def get_all_categories() -> list[str]:
    """Get list of all categories in the catalog."""
    catalog = load_prompt_catalog()
    return list(catalog["by_category"].keys())


def get_catalog_stats() -> dict[str, Any]:
    """Get statistics about the catalog."""
    catalog = load_prompt_catalog()
    
    return {
        "loaded": catalog["loaded"],
        "path": catalog["path"],
        "total_prompts": len(catalog["all"]),
        "categories": {
            cat: len(prompts)
            for cat, prompts in catalog["by_category"].items()
        },
        "smoke_tests": sum(
            1 for p in catalog["all"] if p.get("smoke", False)
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Catalog Policy Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_execution_hints(prompt: dict[str, Any]) -> dict[str, Any]:
    """
    Extract execution hints from a catalog prompt entry.
    
    Returns:
        {
            "limit_hint": int | None,
            "random": bool,
            "todo_mode": str | None,
            "expected_pattern": str | None,
            "expected_cypher_contains": list[str],
        }
    """
    return {
        "limit_hint": prompt.get("limit_hint"),
        "random": prompt.get("random", False),
        "todo_mode": prompt.get("todo_mode"),
        "expected_pattern": prompt.get("expected_pattern"),
        "expected_cypher_contains": prompt.get("expected_cypher_contains", []),
    }


def is_allowed_for_role(prompt: dict[str, Any], is_admin: bool = False) -> bool:
    """Check if a prompt is allowed for a given role."""
    if is_admin:
        return prompt.get("allowed_for_admin", True)
    return prompt.get("allowed_for_user", True)


def get_category_policy(category: str) -> dict[str, Any]:
    """
    Get default policies for a category.
    
    Returns:
        {
            "requires_admin": bool,
            "allow_execution": bool,
            "needs_limit": bool,
            "suggest_explain": bool,
        }
    """
    policies = {
        "read_only": {
            "requires_admin": False,
            "allow_execution": True,
            "needs_limit": False,
            "suggest_explain": False,
        },
        "admin_write": {
            "requires_admin": True,
            "allow_execution": True,
            "needs_limit": False,
            "suggest_explain": False,
        },
        "dangerous": {
            "requires_admin": True,
            "allow_execution": False,
            "needs_limit": True,
            "suggest_explain": True,
        },
        "security": {
            "requires_admin": False,
            "allow_execution": True,  # Metadata only, no graph queries
            "needs_limit": False,
            "suggest_explain": False,
        },
        "data_quality": {
            "requires_admin": False,
            "allow_execution": True,
            "needs_limit": True,  # Data quality can be heavy
            "suggest_explain": False,
        },
    }
    
    return policies.get(category, {
        "requires_admin": False,
        "allow_execution": True,
        "needs_limit": False,
        "suggest_explain": False,
    })


__all__ = [
    "load_prompt_catalog",
    "get_prompt_by_id",
    "match_prompt_by_text",
    "get_prompts_by_category",
    "get_all_categories",
    "get_catalog_stats",
    "get_execution_hints",
    "is_allowed_for_role",
    "get_category_policy",
]
