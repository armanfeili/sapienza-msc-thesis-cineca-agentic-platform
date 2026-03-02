"""
Intent Classifier: Lightweight classification of user prompts into operational modes.

This module provides heuristic-based classification to determine how the orchestrator
should route and process incoming requests. It uses fast regex/keyword matching first,
with optional LLM-based fallback for ambiguous cases.

Supported Intent Modes
----------------------
- CHAT: General conversation, greetings, meta-questions about the system
- GRAPH: Memgraph/graph database queries and graph operations
- SECURITY: Permission, access control, and RBAC questions
- ADMIN: Administrative operations (write, schema changes, index creation)
- DANGEROUS: Heavy, destructive, or unbounded operations

Classification Priority (highest to lowest)
-------------------------------------------
1. Catalog match (pre-matched prompt with known category)
2. DANGEROUS patterns (always checked first for safety)
3. ADMIN patterns (write operations, schema changes)
4. SECURITY patterns (permission queries)
5. GRAPH patterns (database/Cypher indicators)
6. CHAT patterns (greetings, conversational)
7. Conversational signals (fallback detection)
8. LLM-based classification (if enabled, for ambiguous cases)
9. Default to CHAT with low confidence

Integration Points
------------------
- Orchestrator: `src/services/orchestrator.py` uses `classify_intent()` for routing
- Prompt Catalog: `src/services/prompt_catalog.py` provides pre-classified prompts
- RBAC: `src/security/perm.py` provides permission checking for admin/dangerous
- Metrics: `src/observability/` for classification telemetry

Configuration
-------------
- `INTENT_LLM_FALLBACK_ENABLED`: Enable LLM-based fallback (default: False)
- `INTENT_CONFIDENCE_*` thresholds in `src/config.py`
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

import structlog

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Intent Mode Enum
# ─────────────────────────────────────────────────────────────────────────────

class IntentMode(str, Enum):
    """
    Enumeration of supported intent classification modes.
    
    Used throughout the orchestrator and routing logic for type-safe mode handling.
    """
    CHAT = "chat"
    GRAPH = "graph"
    SECURITY = "security"
    ADMIN = "admin"
    DANGEROUS = "dangerous"
    
    def __str__(self) -> str:
        return self.value


# Type alias for string literals (backwards compatibility)
IntentModeType = Literal["chat", "graph", "security", "admin", "dangerous"]


# ─────────────────────────────────────────────────────────────────────────────
# Classification Source Enum
# ─────────────────────────────────────────────────────────────────────────────

class ClassificationSource(str, Enum):
    """Source of the intent classification decision."""
    PATTERNS = "patterns"
    CATALOG = "catalog"
    LLM = "llm"
    CONVERSATIONAL = "conversational"
    DEFAULT = "default"


# ─────────────────────────────────────────────────────────────────────────────
# Confidence Thresholds (centralized configuration)
# ─────────────────────────────────────────────────────────────────────────────

class IntentConfidenceThresholds:
    """
    Centralized confidence thresholds for intent classification.
    
    These values determine when a classification is considered confident enough
    to route to a specific handler without further checks.
    """
    # Pattern-based matches
    CATALOG_MATCH = 0.95  # Highest confidence for catalog matches
    PATTERN_EXACT = 0.95  # Exact pattern match (e.g., "hello")
    PATTERN_STRONG = 0.90  # Strong pattern match (dangerous operations)
    PATTERN_GOOD = 0.85   # Good pattern match (admin, security, graph)
    CONVERSATIONAL = 0.85  # Conversational signal detection
    
    # LLM-based classification
    LLM_HIGH = 0.90
    LLM_MEDIUM = 0.75
    LLM_LOW = 0.60
    
    # Routing thresholds (used by orchestrator)
    CHAT_ROUTING = 0.60   # Minimum confidence to route to chat mode
    SECURITY_ROUTING = 0.75
    ADMIN_ROUTING = 0.70
    DANGEROUS_ROUTING = 0.70
    GRAPH_ROUTING = 0.80
    
    # Default fallback
    DEFAULT_FALLBACK = 0.50


# ─────────────────────────────────────────────────────────────────────────────
# Classification Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IntentClassification:
    """
    Result of intent classification.
    
    Attributes:
        mode: The classified intent mode (chat, graph, security, admin, dangerous)
        confidence: Confidence score from 0.0 to 1.0
        reasoning: Machine-readable explanation of the classification
        source: How the classification was determined (patterns, catalog, llm, default)
        matched_catalog_id: If matched a prompt in catalog
        matched_patterns: Which patterns triggered the classification
        pattern_categories: Categories of matched patterns for debugging
        principal_blocked: True if principal lacks permissions for this mode
        requires_admin: True if this intent requires admin privileges
    """
    mode: IntentModeType
    confidence: float
    reasoning: str
    source: str = ClassificationSource.PATTERNS.value
    matched_catalog_id: str | None = None
    matched_patterns: list[str] | None = None
    pattern_categories: list[str] | None = None
    principal_blocked: bool = False
    requires_admin: bool = False
    used_llm: bool = False
    
    def to_log_dict(self) -> dict[str, Any]:
        """Return a dict suitable for structured logging (no sensitive data)."""
        return {
            "mode": self.mode,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "matched_catalog_id": self.matched_catalog_id,
            "principal_blocked": self.principal_blocked,
            "requires_admin": self.requires_admin,
            "pattern_count": len(self.matched_patterns) if self.matched_patterns else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Definitions (organized by category)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatternCategory:
    """A category of patterns for classification."""
    name: str
    patterns: list[re.Pattern]
    description: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# CHAT PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

CHAT_GREETINGS = PatternCategory(
    name="greetings",
    description="Simple greetings and salutations",
    patterns=[
        re.compile(r"^(hi|hello|hey|greetings|howdy|hola|ciao)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(hi|hello|hey)\s+(there|everyone|all)[\s!?.,]*$", re.IGNORECASE),
        re.compile(r"^(good\s+)?(morning|afternoon|evening|night)[\s!.,]*$", re.IGNORECASE),
    ]
)

CHAT_COMPOUND_GREETINGS = PatternCategory(
    name="compound_greetings",
    description="Greetings followed by questions",
    patterns=[
        re.compile(r"^(hi|hello|hey)[,!]?\s+how\s+are\s+you", re.IGNORECASE),
        re.compile(r"^(hi|hello|hey)[,!]?\s+what'?s\s+(up|your\s+name)", re.IGNORECASE),
        re.compile(r"^(hi|hello|hey)[,!]?\s+.*\?$", re.IGNORECASE),
    ]
)

CHAT_IDENTITY = PatternCategory(
    name="identity_questions",
    description="Questions about the system/assistant identity",
    patterns=[
        re.compile(r"^who\s+(are|r)\s+(you|u)\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^what\s+(are|r)\s+(you|u)\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^what'?s\s+your\s+name\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^what\s+is\s+your\s+name\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^tell\s+me\s+about\s+(yourself|you)\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^what\s+can\s+you\s+do\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"^(can\s+you\s+)?introduce\s+yourself", re.IGNORECASE),
        re.compile(r"^who\s+made\s+you", re.IGNORECASE),
        re.compile(r"^who\s+created\s+you", re.IGNORECASE),
        re.compile(r"^are\s+you\s+(a\s+)?(bot|ai|assistant|human|robot)", re.IGNORECASE),
    ]
)

CHAT_PLEASANTRIES = PatternCategory(
    name="pleasantries",
    description="Thank you, goodbye, and other social phrases",
    patterns=[
        re.compile(r"^(thanks?|thank\s+you|thx|ty)[\s!.,]*$", re.IGNORECASE),
        re.compile(r"^(bye|goodbye|see\s+you|later|farewell)[\s!.,]*$", re.IGNORECASE),
        re.compile(r"^(you'?re\s+welcome|no\s+problem|np)[\s!.,]*$", re.IGNORECASE),
    ]
)

CHAT_SIMPLE_QUESTIONS = PatternCategory(
    name="simple_questions",
    description="Simple questions that don't need tools",
    patterns=[
        re.compile(r"^how\s+are\s+you\s*[?!.,]*$", re.IGNORECASE),
        re.compile(r"how\s+are\s+you.*what'?s\s+your\s+name", re.IGNORECASE),
        re.compile(r"^(help|help\s+me)[\s!?.,]*$", re.IGNORECASE),
    ]
)

CHAT_META_SYSTEM = PatternCategory(
    name="meta_system",
    description="Questions about the platform/system capabilities",
    patterns=[
        re.compile(r"^what\s+is\s+this\s+(platform|system|tool)", re.IGNORECASE),
        re.compile(r"^what\s+can\s+this\s+(platform|system)\s+do", re.IGNORECASE),
        re.compile(r"^describe\s+your\s+capabilities", re.IGNORECASE),
        re.compile(r"^what\s+endpoints\s+exist", re.IGNORECASE),
        re.compile(r"^how\s+does\s+this\s+(work|system\s+work)", re.IGNORECASE),
        re.compile(r"^explain\s+(this|the)\s+(platform|system)", re.IGNORECASE),
    ]
)

CHAT_PATTERNS_ALL = [
    CHAT_GREETINGS,
    CHAT_COMPOUND_GREETINGS,
    CHAT_IDENTITY,
    CHAT_PLEASANTRIES,
    CHAT_SIMPLE_QUESTIONS,
    CHAT_META_SYSTEM,
]

# ══════════════════════════════════════════════════════════════════════════════
# GRAPH PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

GRAPH_LABELS = PatternCategory(
    name="node_labels",
    description="Node label syntax (e.g., :Blast, :File)",
    patterns=[
        re.compile(r":([A-Z][a-zA-Z0-9_]+)"),
    ]
)

GRAPH_CYPHER_KEYWORDS = PatternCategory(
    name="cypher_keywords",
    description="Cypher query language keywords",
    patterns=[
        re.compile(r"\bMATCH\b", re.IGNORECASE),
        re.compile(r"\bRETURN\b", re.IGNORECASE),
        re.compile(r"\bWHERE\b", re.IGNORECASE),
        re.compile(r"\bLIMIT\b", re.IGNORECASE),
        re.compile(r"\bCypher\b", re.IGNORECASE),
        re.compile(r"\bOPTIONAL\s+MATCH\b", re.IGNORECASE),
        re.compile(r"\bWITH\b", re.IGNORECASE),
        re.compile(r"\bUNWIND\b", re.IGNORECASE),
        re.compile(r"\bORDER\s+BY\b", re.IGNORECASE),
    ]
)

GRAPH_TERMINOLOGY = PatternCategory(
    name="graph_terminology",
    description="Graph database terminology",
    patterns=[
        re.compile(r"\bnode[s]?\b", re.IGNORECASE),
        re.compile(r"\bedge[s]?\b", re.IGNORECASE),
        re.compile(r"\bgraph\b", re.IGNORECASE),
        re.compile(r"\bMemgraph\b", re.IGNORECASE),
        re.compile(r"\brelationship[s]?\b", re.IGNORECASE),
        re.compile(r"\boutdegree\b", re.IGNORECASE),
        re.compile(r"\bindegree\b", re.IGNORECASE),
        re.compile(r"\bvertex\b", re.IGNORECASE),
        re.compile(r"\bvertices\b", re.IGNORECASE),
    ]
)

GRAPH_DOMAIN_LABELS = PatternCategory(
    name="domain_labels",
    description="Domain-specific labels (bioinformatics)",
    patterns=[
        re.compile(r"\bBlast\b"),
        re.compile(r"\bBlastedSeq\b"),
        re.compile(r"\bBlastDb\b"),
        re.compile(r"\bFile\b"),
        re.compile(r"\b:OUTPUT\b", re.IGNORECASE),
        re.compile(r"\bsequence[s]?\b", re.IGNORECASE),
    ]
)

GRAPH_QUERY_OPERATIONS = PatternCategory(
    name="query_operations",
    description="Natural language graph query patterns",
    patterns=[
        re.compile(r"\bcount\b.*\b(node|:)", re.IGNORECASE),
        re.compile(r"how\s+many\s+.*\b(node|:)", re.IGNORECASE),
        re.compile(r"\bshow\s+\d+\b", re.IGNORECASE),
        re.compile(r"\bsample\s+\d+\b", re.IGNORECASE),
        re.compile(r"\brandom\b.*\b(node|:)", re.IGNORECASE),
    ]
)

GRAPH_NL_QUERIES = PatternCategory(
    name="natural_language_queries",
    description="Natural language graph queries without Cypher keywords",
    patterns=[
        re.compile(r"\bshow\s+neighbors\s+of\b", re.IGNORECASE),
        re.compile(r"\bfind\s+(all\s+)?connections?\s+between\b", re.IGNORECASE),
        re.compile(r"\bshortest\s+path\s+from\b", re.IGNORECASE),
        re.compile(r"\bcentral\s+nodes?\b", re.IGNORECASE),
        re.compile(r"\bconnected\s+to\b", re.IGNORECASE),
        re.compile(r"\bpaths?\s+between\b", re.IGNORECASE),
        re.compile(r"\btraverse\b", re.IGNORECASE),
        re.compile(r"\bneighbor(s|hood)?\b", re.IGNORECASE),
        re.compile(r"\badjacen(t|cy)\b", re.IGNORECASE),
    ]
)

GRAPH_PATTERNS_ALL = [
    GRAPH_LABELS,
    GRAPH_CYPHER_KEYWORDS,
    GRAPH_TERMINOLOGY,
    GRAPH_DOMAIN_LABELS,
    GRAPH_QUERY_OPERATIONS,
    GRAPH_NL_QUERIES,
]

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_SCHEMA = PatternCategory(
    name="schema_operations",
    description="Schema modification operations",
    patterns=[
        re.compile(r"\bCREATE\s+INDEX\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+INDEX\b", re.IGNORECASE),
        re.compile(r"\bCREATE\s+CONSTRAINT\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+CONSTRAINT\b", re.IGNORECASE),
        re.compile(r"\bindex\b.*\bcreate\b", re.IGNORECASE),
        re.compile(r"\bcreate\b.*\bindex\b", re.IGNORECASE),
    ]
)

ADMIN_PROPERTIES = PatternCategory(
    name="property_operations",
    description="Property modification operations",
    patterns=[
        re.compile(r"\brename\b.*\bproperty\b", re.IGNORECASE),
        re.compile(r"\bproperty\b.*\brename\b", re.IGNORECASE),
        re.compile(r"\bset\s+default\s+value\b", re.IGNORECASE),
    ]
)

ADMIN_WRITE = PatternCategory(
    name="write_operations",
    description="Write/modify operations",
    patterns=[
        re.compile(r"\bMERGE\b", re.IGNORECASE),
        re.compile(r"\bSET\b.*=", re.IGNORECASE),
        re.compile(r"\bCREATE\s*\(", re.IGNORECASE),
    ]
)

ADMIN_PATTERNS_ALL = [
    ADMIN_SCHEMA,
    ADMIN_PROPERTIES,
    ADMIN_WRITE,
]

# ══════════════════════════════════════════════════════════════════════════════
# DANGEROUS PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

DANGEROUS_DELETE = PatternCategory(
    name="delete_operations",
    description="Delete and removal operations",
    patterns=[
        re.compile(r"\bDELETE\b", re.IGNORECASE),
        re.compile(r"\bDETACH\s+DELETE\b", re.IGNORECASE),
        re.compile(r"\bdelete\b.*\b(all|everything)\b", re.IGNORECASE),
        re.compile(r"\bremove\b.*\b(all|everything)\b", re.IGNORECASE),
        re.compile(r"\bwipe\b", re.IGNORECASE),
        re.compile(r"\bwipe\s+(the\s+)?database\b", re.IGNORECASE),
        re.compile(r"\breset\s+everything\b", re.IGNORECASE),
        re.compile(r"\bpurge\b.*\b(graph|database|entire|all)\b", re.IGNORECASE),
        re.compile(r"\b(graph|database)\b.*\bpurge\b", re.IGNORECASE),
    ]
)

DANGEROUS_DROP = PatternCategory(
    name="drop_operations",
    description="Drop database/graph operations",
    patterns=[
        re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+GRAPH\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+ALL\b", re.IGNORECASE),
    ]
)

DANGEROUS_BULK = PatternCategory(
    name="bulk_operations",
    description="Unbounded or bulk operations with destructive context",
    patterns=[
        # Require destructive verbs before "all nodes"
        re.compile(r"\b(delete|remove|wipe|clear)\b.*\ball\b.*\bnode[s]?\b", re.IGNORECASE),
        re.compile(r"\ball\b.*\bnode[s]?\b.*\b(delete|remove|wipe|clear)\b", re.IGNORECASE),
        re.compile(r"\bentire\b.*\b(graph|database)\b.*\b(delete|remove|wipe)\b", re.IGNORECASE),
        re.compile(r"\b(delete|remove|wipe)\b.*\bentire\b.*\b(graph|database)\b", re.IGNORECASE),
        re.compile(r"\bevery\s+pair\b", re.IGNORECASE),
        re.compile(r"\bno\s+LIMIT\b", re.IGNORECASE),
        re.compile(r"\bwithout\s+LIMIT\b", re.IGNORECASE),
        re.compile(r"\bcartesian\b", re.IGNORECASE),
        re.compile(r"\btriangle\s+count\b", re.IGNORECASE),
    ]
)

DANGEROUS_EXPORT = PatternCategory(
    name="export_operations",
    description="Bulk export operations",
    patterns=[
        re.compile(r"\bexport\b.*\b(entire|all|full)\b", re.IGNORECASE),
        re.compile(r"\b(entire|full|all)\b.*\bexport\b", re.IGNORECASE),
        re.compile(r"\bdownload\s+every\s+user\b", re.IGNORECASE),
        re.compile(r"\bdump\s+all\s+data\b", re.IGNORECASE),
        re.compile(r"\bexport\s+all\s+records\b", re.IGNORECASE),
    ]
)

DANGEROUS_CONTINUOUS = PatternCategory(
    name="continuous_operations",
    description="Continuous or long-running operations",
    patterns=[
        re.compile(r"\bforever\b", re.IGNORECASE),
        re.compile(r"\bevery\s+second\b", re.IGNORECASE),
        re.compile(r"\binfinite\s+loop\b", re.IGNORECASE),
    ]
)

DANGEROUS_PATTERNS_ALL = [
    DANGEROUS_DELETE,
    DANGEROUS_DROP,
    DANGEROUS_BULK,
    DANGEROUS_EXPORT,
    DANGEROUS_CONTINUOUS,
]

# ══════════════════════════════════════════════════════════════════════════════
# SECURITY PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

SECURITY_PERMISSIONS = PatternCategory(
    name="permission_queries",
    description="Questions about permissions and access",
    patterns=[
        re.compile(r"\bpermission[s]?\b", re.IGNORECASE),
        re.compile(r"\bscope[s]?\b", re.IGNORECASE),
        re.compile(r"\ballowed\s+to\b", re.IGNORECASE),
        re.compile(r"\bcan\s+I\s+run\b", re.IGNORECASE),
        re.compile(r"\bdo\s+I\s+have\s+(permission|access)\b", re.IGNORECASE),
        re.compile(r"\bwhat\s+am\s+I\s+allowed\b", re.IGNORECASE),
        re.compile(r"\bmy\s+(effective\s+)?scopes?\b", re.IGNORECASE),
        re.compile(r"\bmy\s+role[s]?\b", re.IGNORECASE),
        re.compile(r"\bmy\s+permissions?\b", re.IGNORECASE),
    ]
)

SECURITY_TENANT = PatternCategory(
    name="tenant_queries",
    description="Questions about tenancy and organization",
    patterns=[
        re.compile(r"\btenant\b", re.IGNORECASE),
        re.compile(r"\bmy\s+organization\b", re.IGNORECASE),
    ]
)

SECURITY_DANGER_QUERIES = PatternCategory(
    name="danger_queries",
    description="Questions about dangerous operations",
    patterns=[
        re.compile(r"\bdangerous\b.*\bquer(y|ies)\b", re.IGNORECASE),
        re.compile(r"\bwhat\s+(is|are)\s+dangerous\b", re.IGNORECASE),
        re.compile(r"\bunsafe\s+operations?\b", re.IGNORECASE),
    ]
)

SECURITY_PATTERNS_ALL = [
    SECURITY_PERMISSIONS,
    SECURITY_TENANT,
    SECURITY_DANGER_QUERIES,
]

# ══════════════════════════════════════════════════════════════════════════════
# EXPLAIN-ONLY PATTERNS (modifies dangerous/admin to safe)
# ══════════════════════════════════════════════════════════════════════════════

EXPLAIN_ONLY_PATTERNS = PatternCategory(
    name="explain_only",
    description="Patterns indicating query plan analysis (safe)",
    patterns=[
        re.compile(r"\bEXPLAIN\b", re.IGNORECASE),
        re.compile(r"\bprofile\b", re.IGNORECASE),
        re.compile(r"\bdo\s+not\s+execute\b", re.IGNORECASE),
        re.compile(r"\bdon'?t\s+execute\b", re.IGNORECASE),
        re.compile(r"\bplan\s+only\b", re.IGNORECASE),
        re.compile(r"\bexecution\s+plan\b", re.IGNORECASE),
        re.compile(r"\bjust\s+show\s+(the\s+)?plan\b", re.IGNORECASE),
    ]
)


# ─────────────────────────────────────────────────────────────────────────────
# Category to Mode Mapping (from catalog)
# ─────────────────────────────────────────────────────────────────────────────

CATALOG_CATEGORY_TO_MODE: dict[str, IntentModeType] = {
    "read_only": IntentMode.GRAPH.value,
    "admin_write": IntentMode.ADMIN.value,
    "dangerous": IntentMode.DANGEROUS.value,
    "security": IntentMode.SECURITY.value,
    "data_quality": IntentMode.GRAPH.value,
    "chat": IntentMode.CHAT.value,
    "meta": IntentMode.CHAT.value,
}


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Matching Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize text for matching: strip, lowercase, collapse whitespace."""
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _match_pattern_category(text: str, category: PatternCategory) -> list[str]:
    """Match text against a pattern category, return matched strings."""
    matched = []
    for pattern in category.patterns:
        match = pattern.search(text)
        if match:
            matched.append(match.group(0))
    return matched


def _match_all_categories(
    text: str,
    categories: list[PatternCategory],
) -> tuple[list[str], list[str]]:
    """
    Match text against all pattern categories.
    
    Returns:
        Tuple of (matched_strings, matched_category_names)
    """
    all_matches: list[str] = []
    matched_categories: list[str] = []
    
    for category in categories:
        matches = _match_pattern_category(text, category)
        if matches:
            all_matches.extend(matches)
            matched_categories.append(category.name)
    
    return all_matches, matched_categories


def _is_explain_only(text: str) -> bool:
    """Check if this is an EXPLAIN-only request (safe for any query)."""
    matches = _match_pattern_category(text, EXPLAIN_ONLY_PATTERNS)
    return len(matches) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Principal Context Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _extract_principal_permissions(principal: dict[str, Any] | None) -> set[str]:
    """Extract permissions set from principal."""
    if not principal:
        return set()
    
    perms: set[str] = set()
    
    # Direct permissions
    if isinstance(principal.get("permissions"), (list, tuple)):
        perms.update(str(p) for p in principal["permissions"])
    
    # Scopes
    if isinstance(principal.get("scopes"), (list, tuple)):
        perms.update(str(s) for s in principal["scopes"])
    elif isinstance(principal.get("scopes"), str):
        perms.update(principal["scopes"].split())
    
    # Roles -> implicit permissions
    roles = principal.get("roles") or []
    if isinstance(roles, (list, tuple)):
        if any(str(r).lower() == "admin" for r in roles):
            perms.add("admin:all")
    
    return perms


def _principal_has_admin(principal: dict[str, Any] | None) -> bool:
    """Check if principal has admin privileges."""
    if not principal:
        return False
    
    perms = _extract_principal_permissions(principal)
    if "admin:all" in perms:
        return True
    
    # Check roles directly
    roles = principal.get("roles") or []
    if isinstance(roles, (list, tuple)):
        return any(str(r).lower() in ("admin", "super-admin", "system-operator") for r in roles)
    
    return False


def _check_principal_for_mode(
    mode: IntentModeType,
    principal: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Check if principal has permission for the classified mode.
    
    Returns:
        Tuple of (is_blocked, reason)
    """
    if mode not in (IntentMode.ADMIN.value, IntentMode.DANGEROUS.value):
        return False, ""
    
    if not principal:
        # No principal = unknown, don't block but flag
        return False, ""
    
    if _principal_has_admin(principal):
        return False, ""
    
    # Non-admin trying admin/dangerous operation
    return True, f"Principal lacks admin privileges for {mode} operations"


# ─────────────────────────────────────────────────────────────────────────────
# Conversational Signal Detection
# ─────────────────────────────────────────────────────────────────────────────

def _detect_conversational_signals(text: str) -> bool:
    """
    Detect conversational signals that indicate chat intent.
    
    Used as fallback when pattern matching is inconclusive.
    """
    text_lower = text.lower()
    
    signals = [
        # Question patterns about self/system
        text_lower.startswith("how are"),
        text_lower.startswith("what's your"),
        text_lower.startswith("what is your"),
        text_lower.startswith("who are you"),
        text_lower.startswith("can you tell me about yourself"),
        text_lower.startswith("could you"),
        text_lower.startswith("would you"),
        text_lower.startswith("please"),
        
        # Greetings embedded in longer text
        text_lower.startswith("hi ") or text_lower.startswith("hi,"),
        text_lower.startswith("hello ") or text_lower.startswith("hello,"),
        text_lower.startswith("hey ") or text_lower.startswith("hey,"),
        
        # Personal/meta questions
        "your name" in text_lower,
        "about yourself" in text_lower,
        "introduce yourself" in text_lower,
        
        # Confusion/help patterns
        "i'm confused" in text_lower,
        "i don't understand" in text_lower,
        "what does it mean" in text_lower,
        "can you explain" in text_lower,
        "help me understand" in text_lower,
    ]
    
    return any(signals)


def _detect_task_signals(text: str) -> bool:
    """
    Detect task/command signals that indicate non-chat intent.
    
    Used to override conversational fallback for imperative commands.
    """
    text_lower = text.lower()
    
    # Imperative commands for graph operations
    task_patterns = [
        text_lower.startswith("find "),
        text_lower.startswith("show "),
        text_lower.startswith("get "),
        text_lower.startswith("list "),
        text_lower.startswith("count "),
        text_lower.startswith("query "),
        text_lower.startswith("search "),
        text_lower.startswith("retrieve "),
        "between" in text_lower and "path" in text_lower,
    ]
    
    return any(task_patterns)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Integration
# ─────────────────────────────────────────────────────────────────────────────

def _record_classification_metrics(
    result: IntentClassification,
    duration_seconds: float,
) -> None:
    """Record classification metrics to Prometheus (if available)."""
    try:
        from src.observability.metrics import record_intent_classification
        
        record_intent_classification(
            mode=result.mode,
            source=result.source,
            confidence=result.confidence,
            duration_seconds=duration_seconds,
            adjusted=result.principal_blocked,
        )
    except ImportError:
        pass  # Metrics not available
    except Exception as e:
        log.debug("intent_classifier.metrics_error", error=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Main Classification Function
# ─────────────────────────────────────────────────────────────────────────────

def classify_intent(
    goal: str,
    *,
    catalog_match: dict[str, Any] | None = None,
    principal: dict[str, Any] | None = None,
) -> IntentClassification:
    """
    Classify the intent of a user prompt.
    
    Args:
        goal: The user's prompt/goal text
        catalog_match: Optional pre-matched catalog entry with category metadata
        principal: Optional principal for RBAC context
    
    Returns:
        IntentClassification with mode, confidence, reasoning, and metadata
    
    Priority Order:
        1. Catalog match (if provided and has category)
        2. DANGEROUS patterns (checked first for safety)
        3. ADMIN patterns
        4. SECURITY patterns  
        5. GRAPH patterns
        6. CHAT patterns
        7. Conversational signals (fallback)
        8. Default to CHAT with low confidence
    """
    start_time = time.time()
    text = _normalize_text(goal)
    
    # Empty prompt defaults to chat
    if not text:
        result = IntentClassification(
            mode=IntentMode.CHAT.value,
            confidence=1.0,
            reasoning="source=default; mode=chat; reason=empty_prompt",
            source=ClassificationSource.DEFAULT.value,
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. Check catalog match first (highest confidence)
    # ─────────────────────────────────────────────────────────────────────────
    if catalog_match:
        category = catalog_match.get("category", "")
        prompt_id = catalog_match.get("id", "unknown")
        
        # Use shared mapping
        mode = CATALOG_CATEGORY_TO_MODE.get(category, IntentMode.GRAPH.value)
        
        # Check for additional catalog metadata
        requires_admin = catalog_match.get("requires_admin", mode in (IntentMode.ADMIN.value, IntentMode.DANGEROUS.value))
        severity = catalog_match.get("severity", "normal")
        
        # Adjust confidence based on severity
        confidence = IntentConfidenceThresholds.CATALOG_MATCH
        if severity == "high":
            confidence = 0.98
        
        # Check principal permissions
        is_blocked, block_reason = _check_principal_for_mode(mode, principal)
        
        result = IntentClassification(
            mode=mode,
            confidence=confidence,
            reasoning=f"source=catalog; mode={mode}; id={prompt_id}; category={category}",
            source=ClassificationSource.CATALOG.value,
            matched_catalog_id=prompt_id,
            requires_admin=requires_admin,
            principal_blocked=is_blocked,
        )
        
        if is_blocked:
            log.info(
                "intent_classifier.principal_blocked",
                prompt_id=prompt_id,
                mode=mode,
                reason=block_reason,
            )
        
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. Check EXPLAIN-only modifier (makes dangerous queries safe)
    # ─────────────────────────────────────────────────────────────────────────
    is_explain = _is_explain_only(text)
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. Check DANGEROUS patterns first (safety priority)
    # ─────────────────────────────────────────────────────────────────────────
    dangerous_matches, dangerous_categories = _match_all_categories(text, DANGEROUS_PATTERNS_ALL)
    if dangerous_matches and not is_explain:
        is_blocked, _ = _check_principal_for_mode(IntentMode.DANGEROUS.value, principal)
        
        result = IntentClassification(
            mode=IntentMode.DANGEROUS.value,
            confidence=IntentConfidenceThresholds.PATTERN_STRONG,
            reasoning=f"source=patterns; mode=dangerous; matches={dangerous_matches[:3]}",
            source=ClassificationSource.PATTERNS.value,
            matched_patterns=dangerous_matches,
            pattern_categories=dangerous_categories,
            requires_admin=True,
            principal_blocked=is_blocked,
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. Check ADMIN patterns
    # ─────────────────────────────────────────────────────────────────────────
    admin_matches, admin_categories = _match_all_categories(text, ADMIN_PATTERNS_ALL)
    if admin_matches and not is_explain:
        is_blocked, _ = _check_principal_for_mode(IntentMode.ADMIN.value, principal)
        
        result = IntentClassification(
            mode=IntentMode.ADMIN.value,
            confidence=IntentConfidenceThresholds.PATTERN_GOOD,
            reasoning=f"source=patterns; mode=admin; matches={admin_matches[:3]}",
            source=ClassificationSource.PATTERNS.value,
            matched_patterns=admin_matches,
            pattern_categories=admin_categories,
            requires_admin=True,
            principal_blocked=is_blocked,
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. Check SECURITY patterns
    # ─────────────────────────────────────────────────────────────────────────
    security_matches, security_categories = _match_all_categories(text, SECURITY_PATTERNS_ALL)
    if security_matches:
        result = IntentClassification(
            mode=IntentMode.SECURITY.value,
            confidence=IntentConfidenceThresholds.PATTERN_GOOD,
            reasoning=f"source=patterns; mode=security; matches={security_matches[:3]}",
            source=ClassificationSource.PATTERNS.value,
            matched_patterns=security_matches,
            pattern_categories=security_categories,
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 6. Check CHAT patterns (exact matches)
    # ─────────────────────────────────────────────────────────────────────────
    chat_matches, chat_categories = _match_all_categories(text, CHAT_PATTERNS_ALL)
    if chat_matches:
        result = IntentClassification(
            mode=IntentMode.CHAT.value,
            confidence=IntentConfidenceThresholds.PATTERN_EXACT,
            reasoning=f"source=patterns; mode=chat; matches={chat_matches[:3]}",
            source=ClassificationSource.PATTERNS.value,
            matched_patterns=chat_matches,
            pattern_categories=chat_categories,
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 7. Check GRAPH patterns
    # ─────────────────────────────────────────────────────────────────────────
    graph_matches, graph_categories = _match_all_categories(text, GRAPH_PATTERNS_ALL)
    if graph_matches:
        # If EXPLAIN-only with dangerous patterns, mark as safe graph
        if is_explain and dangerous_matches:
            result = IntentClassification(
                mode=IntentMode.GRAPH.value,
                confidence=IntentConfidenceThresholds.PATTERN_STRONG,
                reasoning=f"source=patterns; mode=graph; reason=explain_only; matches={graph_matches[:3]}",
                source=ClassificationSource.PATTERNS.value,
                matched_patterns=graph_matches,
                pattern_categories=graph_categories,
            )
        else:
            result = IntentClassification(
                mode=IntentMode.GRAPH.value,
                confidence=IntentConfidenceThresholds.PATTERN_GOOD,
                reasoning=f"source=patterns; mode=graph; matches={graph_matches[:3]}",
                source=ClassificationSource.PATTERNS.value,
                matched_patterns=graph_matches,
                pattern_categories=graph_categories,
            )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 8. Conversational signal detection (fallback before default)
    # ─────────────────────────────────────────────────────────────────────────
    
    # Check for task signals first (imperative commands)
    if _detect_task_signals(text):
        # Likely a task, but we don't know which mode - check if graph-like
        result = IntentClassification(
            mode=IntentMode.GRAPH.value,
            confidence=IntentConfidenceThresholds.DEFAULT_FALLBACK + 0.15,
            reasoning="source=conversational; mode=graph; reason=task_signals_detected",
            source=ClassificationSource.CONVERSATIONAL.value,
            matched_patterns=["task_signal"],
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # Check for conversational signals
    if _detect_conversational_signals(text):
        result = IntentClassification(
            mode=IntentMode.CHAT.value,
            confidence=IntentConfidenceThresholds.CONVERSATIONAL,
            reasoning="source=conversational; mode=chat; reason=conversational_signals",
            source=ClassificationSource.CONVERSATIONAL.value,
            matched_patterns=["conversational"],
        )
        _record_classification_metrics(result, time.time() - start_time)
        return result
    
    # ─────────────────────────────────────────────────────────────────────────
    # 9. Default to CHAT with low confidence
    # ─────────────────────────────────────────────────────────────────────────
    result = IntentClassification(
        mode=IntentMode.CHAT.value,
        confidence=IntentConfidenceThresholds.DEFAULT_FALLBACK + 0.1,
        reasoning="source=default; mode=chat; reason=no_patterns_matched",
        source=ClassificationSource.DEFAULT.value,
    )
    
    log.debug(
        "intent_classifier.default_fallback",
        goal_preview=text[:80] if len(text) > 80 else text,
        confidence=result.confidence,
    )
    
    _record_classification_metrics(result, time.time() - start_time)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Quick Check Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def is_simple_chat(goal: str) -> bool:
    """
    Quick check if a goal is definitely a simple chat prompt.
    
    This is a fast path for the orchestrator to skip TODO planning entirely.
    """
    intent = classify_intent(goal)
    return (
        intent.mode == IntentMode.CHAT.value
        and intent.confidence >= IntentConfidenceThresholds.CHAT_ROUTING
    )


def is_graph_query(goal: str) -> bool:
    """Quick check if a goal is a graph database query."""
    intent = classify_intent(goal)
    return intent.mode == IntentMode.GRAPH.value


def requires_admin(goal: str) -> bool:
    """Quick check if a goal requires admin privileges."""
    intent = classify_intent(goal)
    return intent.mode in (IntentMode.ADMIN.value, IntentMode.DANGEROUS.value)


def is_security_question(goal: str) -> bool:
    """Quick check if a goal is a security/permission question."""
    intent = classify_intent(goal)
    return intent.mode == IntentMode.SECURITY.value


def is_dangerous_operation(goal: str) -> bool:
    """Quick check if a goal is a dangerous/destructive operation."""
    intent = classify_intent(goal)
    return intent.mode == IntentMode.DANGEROUS.value


# ─────────────────────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Enums and types
    "IntentMode",
    "IntentModeType",
    "ClassificationSource",
    "IntentConfidenceThresholds",
    # Main result type
    "IntentClassification",
    # Pattern categories (for extension)
    "PatternCategory",
    "CATALOG_CATEGORY_TO_MODE",
    # Main function
    "classify_intent",
    # Quick checks
    "is_simple_chat",
    "is_graph_query",
    "requires_admin",
    "is_security_question",
    "is_dangerous_operation",
]
