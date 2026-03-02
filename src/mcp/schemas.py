"""
Pydantic schemas for MCP tool payloads.

Provides input validation and documentation for all MCP tools.
Each schema defines the payload structure for one or more actions.
"""

from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Graph tools
# ─────────────────────────────────────────────────────────────────────────────


class GraphQueryAction(str, Enum):
    """Supported actions for graph.query"""

    run = "run"
    explain = "explain"
    profile = "profile"


class GraphQueryPayload(BaseModel):
    """Payload for graph.query tool."""

    action: GraphQueryAction = Field(default=GraphQueryAction.run)
    cypher: str = Field(
        ...,
        min_length=1,
        description="Cypher query to execute",
        validation_alias=AliasChoices("cypher", "query"),
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    read_only: bool = Field(default=True, description="Enforce read-only mode")
    timeout_ms: int | None = Field(default=5000, ge=100, description="Query timeout in milliseconds")
    limit: int | None = Field(default=None, ge=1, description="Client-side row limit")
    run_id: str | None = Field(default=None, description="Optional agent run ID for tracing/logging")

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class GraphSecureQueryAction(str, Enum):
    """Supported actions for graph.secure_query"""

    ask = "ask"
    generate = "generate"
    validate = "validate"
    execute = "execute"


class GraphSecureQueryPayload(BaseModel):
    """Payload for graph.secure_query tool."""

    action: GraphSecureQueryAction

    # NL prompt (for ask, generate)
    prompt: str | None = Field(None, min_length=3, description="Natural language prompt")

    # Cypher query (for validate, execute)
    cypher: str | None = Field(
        None,
        description="Cypher query",
        validation_alias=AliasChoices("cypher", "query", "statement"),
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Query parameters")

    # Required context
    principal: str = Field(..., min_length=1, description="Principal ID (required)")
    tenant: str = Field(..., min_length=1, description="Tenant ID (required)")
    run_id: str | None = Field(default=None, description="Optional agent run ID for tracing/logging")

    # Safety limits
    max_rows: int = Field(default=1000, ge=1, le=10000, description="Maximum rows to return")
    timeout_ms: int = Field(default=5000, ge=100, le=30000, description="Query timeout")

    # Output formatting
    return_format: str = Field(default="rows", pattern="^(rows|markdown|csv|json)$")

    # Tracing
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        action = self.action

        # ask and generate require prompt
        if action in {"ask", "generate"} and not self.prompt:
            raise ValueError(f"'prompt' is required for action '{action}'")

        # validate and execute require cypher
        if action in {"validate", "execute"} and not self.cypher:
            raise ValueError(f"'cypher' is required for action '{action}'")

        return self

    model_config = ConfigDict(use_enum_values=True)


class GraphCrudOperation(str, Enum):
    """CRUD operations for graph.crud"""

    create_node = "create_node"
    update_node = "update_node"
    delete_node = "delete_node"
    create_relationship = "create_relationship"
    delete_relationship = "delete_relationship"


class GraphCrudPayload(BaseModel):
    """Payload for graph.crud tool."""

    operation: GraphCrudOperation

    # Node operations
    label: str | None = None
    labels: list[str] | None = None
    match: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None

    # Relationship operations
    from_: dict[str, Any] | None = Field(None, alias="from")
    to: dict[str, Any] | None = None
    rel_type: str | None = None

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


class GraphGenerateCypherAction(str, Enum):
    """Supported actions for graph.generate_cypher"""

    select = "select"
    insert_node = "insert_node"
    update_node = "update_node"
    delete_node = "delete_node"
    upsert_rel = "upsert_rel"
    match_rel = "match_rel"
    count_by_label = "count_by_label"
    schema_inventory = "schema_inventory"


class GraphGenerateCypherPayload(BaseModel):
    """Payload for graph.generate_cypher tool."""

    action: GraphGenerateCypherAction = GraphGenerateCypherAction.select

    # SELECT action fields
    label: str | None = None
    where: dict[str, Any] | None = None
    return_: list[str] | None = Field(None, alias="return")
    limit: int | None = Field(default=25, ge=1, le=10000)

    # INSERT_NODE action fields
    labels: list[str] | None = None
    orig_id: str | None = None
    props: dict[str, Any] | None = None
    mode: str | None = Field(default="merge", pattern="^(merge|create)$")

    # UPDATE_NODE action fields (uses orig_id, props)

    # DELETE_NODE action fields (uses orig_id)
    detach: bool = Field(default=True, description="Use DETACH DELETE")

    # UPSERT_REL action fields
    start_orig_id: str | None = None
    end_orig_id: str | None = None
    type_: str | None = Field(None, alias="type")

    # MATCH_REL action fields (uses limit, type_)
    from_label: str | None = None
    to_label: str | None = None
    from_where: dict[str, Any] | None = None
    to_where: dict[str, Any] | None = None

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    @field_validator("labels", mode="after")
    @classmethod
    def validate_labels_non_empty(cls, v, info):
        """Validate labels is non-empty list for insert_node."""
        if hasattr(info, "data"):
            action = info.data.get("action")
            if action == "insert_node":
                if not v or not isinstance(v, list) or len(v) == 0:
                    raise ValueError("'labels' must be a non-empty list for insert_node")
        return v

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields for each action."""
        # UPDATE_NODE and DELETE_NODE require orig_id
        if self.action in {"update_node", "delete_node"} and not self.orig_id:
            raise ValueError(f"'orig_id' is required for action '{self.action}'")

        # UPSERT_REL requires start_orig_id, end_orig_id, and type
        if self.action == "upsert_rel":
            if not self.start_orig_id or not self.end_orig_id or not self.type_:
                raise ValueError("'start_orig_id', 'end_orig_id', and 'type' are required for upsert_rel")

        return self

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


# ─────────────────────────────────────────────────────────────────────────────
# System tools
# ─────────────────────────────────────────────────────────────────────────────


class SystemHealthAction(str, Enum):
    """Supported actions for system.health"""

    liveness = "liveness"
    readiness = "readiness"
    details = "details"


class SystemHealthPayload(BaseModel):
    """Payload for system.health tool."""

    action: SystemHealthAction = Field(default=SystemHealthAction.liveness)
    verbose: bool = Field(default=False, description="Include detailed component info")

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data tools
# ─────────────────────────────────────────────────────────────────────────────


class DataArchiveAction(str, Enum):
    """Supported actions for data.archive"""

    mark = "mark"
    restore = "restore"
    purge = "purge"
    status = "status"
    list = "list"


class DataArchivePayload(BaseModel):
    """Payload for data.archive tool."""

    action: DataArchiveAction

    # Filters
    node_ids: list[str] | None = None
    label: str | None = None
    timestamp_before: str | None = None  # ISO8601 datetime
    limit: int | None = Field(default=100, ge=1, le=10000)

    # Safety
    only_archived: bool = Field(default=True, description="Only purge archived nodes")
    confirm: bool = Field(default=False, description="Confirm destructive operations")

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_confirm_for_purge(self):
        """Require confirm=true for purge action."""
        if self.action == "purge" and not self.confirm:
            raise ValueError("'confirm' must be true for purge action")
        return self

    model_config = ConfigDict(use_enum_values=True)


class GraphSchemaAction(str, Enum):
    """Supported actions for graph.schema"""

    labels = "labels"
    relationship_types = "relationship_types"
    node_properties = "node_properties"
    relationship_properties = "relationship_properties"
    node_counts = "node_counts"
    relationship_counts = "relationship_counts"
    indexes = "indexes"
    constraints = "constraints"
    inventory = "inventory"


class GraphSchemaPayload(BaseModel):
    """Payload for graph.schema tool."""

    action: GraphSchemaAction

    # Optional filters
    label: str | None = Field(None, min_length=1, description="Node label filter (for node_properties)")
    type_: str | None = Field(
        None, alias="type", min_length=1, description="Relationship type filter (for relationship_properties)"
    )

    # Required context
    principal: str = Field(..., min_length=1, description="Principal ID (required)")
    tenant: str = Field(..., min_length=1, description="Tenant ID (required)")

    # Tracing
    trace_id: str | None = None

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


# ─────────────────────────────────────────────────────────────────────────────
# Security tools
# ─────────────────────────────────────────────────────────────────────────────


class SecurityAuditAction(str, Enum):
    """Supported actions for security.audit"""

    access = "access"
    custom = "custom"
    list = "list"
    stats = "stats"
    clear = "clear"


class SecurityAuditPayload(BaseModel):
    """Payload for security.audit tool."""

    action: SecurityAuditAction

    # Access event fields
    category: str | None = None
    event_action: str | None = None
    outcome: str | None = None
    resource: str | None = None
    meta: dict[str, Any] | None = None

    # List filters
    limit: int = Field(default=100, ge=1, le=10000)

    # Clear confirmation
    confirm: bool = Field(default=False)

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_confirm_for_clear(self):
        """Require confirm=true for clear action."""
        if self.action == "clear" and not self.confirm:
            raise ValueError("'confirm' must be true for clear action")
        return self

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Model tools
# ─────────────────────────────────────────────────────────────────────────────


class ModelManageAction(str, Enum):
    """Supported actions for model.manage"""

    info = "info"
    get_config = "get_config"
    set_config = "set_config"
    reset_config = "reset_config"
    list_models = "list_models"
    capabilities = "capabilities"
    health = "health"


class ModelManagePayload(BaseModel):
    """Payload for model.manage tool."""

    action: ModelManageAction

    # Config updates
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=1, le=128000)

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Security tools
# ─────────────────────────────────────────────────────────────────────────────


class SecurityPermissionsAction(str, Enum):
    """Supported actions for security.permissions"""

    check = "check"
    resolve = "resolve"
    list_roles = "list_roles"
    reload = "reload"


class SecurityPermissionsPayload(BaseModel):
    """Payload for security.permissions tool."""

    action: SecurityPermissionsAction

    # For 'check' action
    principal: str | None = Field(None, description="Principal identifier (user, service)")
    roles: list[str] | None = Field(None, description="Role list (can also be single string)")
    resource: str | None = Field(None, min_length=1, description="Resource to check access for")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context (tenant, etc.)")

    # For 'resolve' action
    resources: list[str] | None = Field(None, description="Resources to preview")
    actions: list[str] | None = Field(None, description="Actions to preview")

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        action = self.action

        # 'check' requires resource
        if action == "check" and not self.resource:
            raise ValueError("'resource' is required for action 'check'")

        return self

    model_config = ConfigDict(use_enum_values=True)


class GraphSearchAction(str, Enum):
    """Supported actions for graph.search"""

    nodes = "nodes"
    edges = "edges"
    count = "count"
    distinct = "distinct"


class GraphSearchPayload(BaseModel):
    """Payload for graph.search tool."""

    action: GraphSearchAction = Field(default=GraphSearchAction.nodes)

    # Filtering
    label: str | None = Field(None, description="Node label to filter by")
    labels: list[str] | None = Field(None, description="Multiple node labels (OR)")
    type: str | None = Field(None, description="Edge type to filter by")
    types: list[str] | None = Field(None, description="Multiple edge types (OR)")
    where: dict[str, Any] = Field(default_factory=dict, description="Property filters")

    # Pagination
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=25, ge=1, le=1000, description="Items per page")

    # Projection
    select: list[str] | None = Field(None, description="Fields to return (default: all)")

    # Ordering
    order_by: str | None = Field(None, description="Field to order by")
    order_desc: bool = Field(default=False, description="Descending order")

    # For 'distinct' action
    property: str | None = Field(None, description="Property for distinct values")
    limit: int | None = Field(default=100, ge=1, le=10000, description="Max distinct values")

    # Safety
    timeout_ms: int = Field(default=5000, ge=100, le=30000, description="Query timeout")

    # Context (required)
    principal: str = Field(..., min_length=1, description="Principal ID")
    tenant: str = Field(..., min_length=1, description="Tenant ID")
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        action = self.action

        if action == "distinct" and not self.property:
            raise ValueError("'property' is required for action 'distinct'")

        return self

    model_config = ConfigDict(use_enum_values=True)


class GraphAnalyticsAction(str, Enum):
    """Supported actions for graph.analytics"""

    degree_distribution = "degree_distribution"
    shortest_path = "shortest_path"
    top_k_degree = "top_k_degree"
    label_counts = "label_counts"
    relationship_counts = "relationship_counts"
    connected_components = "connected_components"


class GraphAnalyticsPayload(BaseModel):
    """Payload for graph.analytics tool."""

    action: GraphAnalyticsAction

    # For shortest_path
    start_id: str | None = Field(None, description="Start node orig_id for shortest path")
    end_id: str | None = Field(None, description="End node orig_id for shortest path")
    max_depth: int | None = Field(default=5, ge=1, le=10, description="Max path depth")

    # For top_k_degree
    k: int | None = Field(default=10, ge=1, le=100, description="Top K nodes")
    direction: str | None = Field(default="both", pattern="^(in|out|both)$", description="Degree direction")

    # For label_counts, relationship_counts
    labels: list[str] | None = Field(None, description="Filter by specific labels")
    types: list[str] | None = Field(None, description="Filter by specific types")

    # Safety (mandatory for analytics)
    timeout_ms: int = Field(default=5000, ge=100, le=60000, description="Query timeout")
    row_limit: int = Field(default=1000, ge=1, le=10000, description="Result row limit")

    # Context (required)
    principal: str = Field(..., min_length=1, description="Principal ID")
    tenant: str = Field(..., min_length=1, description="Tenant ID")
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        action = self.action

        if action == "shortest_path" and (not self.start_id or not self.end_id):
            raise ValueError("'start_id' and 'end_id' are required for action 'shortest_path'")

        return self

    model_config = ConfigDict(use_enum_values=True)


class GraphBulkAction(str, Enum):
    """Supported actions for graph.bulk"""

    ingest_nodes = "ingest_nodes"
    ingest_edges = "ingest_edges"
    upsert_nodes = "upsert_nodes"
    upsert_edges = "upsert_edges"


class GraphBulkPayload(BaseModel):
    """Payload for graph.bulk tool."""

    action: GraphBulkAction

    # Data payload
    nodes: list[dict[str, Any]] | None = Field(None, description="List of nodes to ingest")
    edges: list[dict[str, Any]] | None = Field(None, description="List of edges to ingest")

    # Batch configuration
    batch_size: int = Field(default=100, ge=1, le=1000, description="Batch size for processing")
    allow_mixed_labels: bool = Field(default=False, description="Allow mixed labels in batch")
    allow_create_endpoints: bool = Field(default=False, description="Create missing edge endpoints")

    # Idempotency
    idempotency_key: str | None = Field(None, description="Key for idempotent operations")

    # Error handling
    fail_fast: bool = Field(default=True, description="Stop on first error vs continue")

    # Dry run
    dry_run: bool = Field(default=False, description="Validate only, no writes")

    # Safety
    timeout_ms: int = Field(default=30000, ge=1000, le=300000, description="Operation timeout")

    # Context (required)
    principal: str = Field(..., min_length=1, description="Principal ID")
    tenant: str = Field(..., min_length=1, description="Tenant ID")
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        action = self.action

        # Node actions require nodes
        if action in {"ingest_nodes", "upsert_nodes"}:
            if not self.nodes or len(self.nodes) == 0:
                raise ValueError(f"'nodes' list is required and must be non-empty for action '{action}'")

        # Edge actions require edges
        if action in {"ingest_edges", "upsert_edges"}:
            if not self.edges or len(self.edges) == 0:
                raise ValueError(f"'edges' list is required and must be non-empty for action '{action}'")

        return self

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# DB tools
# ─────────────────────────────────────────────────────────────────────────────


class DbSwitchAction(str, Enum):
    """Supported actions for db.switch"""

    get = "get"
    set = "set"
    switch = "switch"
    test = "test"


class DbSwitchPayload(BaseModel):
    """Payload for db.switch tool."""

    action: DbSwitchAction

    # Connection parameters (for set/test)
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = None
    password: str | None = None

    # Preset target (for switch)
    target: str | None = Field(default=None, pattern="^(local|docker|default)$")

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        if self.action == "switch" and not self.target:
            raise ValueError("'target' is required for action 'switch'")
        return self

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Errors tools
# ─────────────────────────────────────────────────────────────────────────────


class ErrorsReportPayload(BaseModel):
    """Payload for errors.report tool."""

    # Required
    message: str = Field(..., min_length=1, description="Human-readable error message")

    # Optional fields
    code: str | None = Field(default=None, max_length=100, description="Error code (e.g., E_GRAPH_TIMEOUT)")
    severity: str | None = Field(default="error", pattern="^(info|warning|error|critical)$")
    category: str | None = Field(default="application", max_length=100)
    resource: str | None = Field(default=None, max_length=200)
    principal: str | dict[str, Any] | None = None
    trace_id: str | None = None
    context: dict[str, Any] | None = Field(
        default_factory=dict, description="Additional context (will be PII-scrubbed)"
    )
    exception: dict[str, Any] | None = None
    capture_stack: bool = Field(default=False, description="Capture current stack trace")

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit tools
# ─────────────────────────────────────────────────────────────────────────────


class RateLimitManageAction(str, Enum):
    """Supported actions for ratelimit.manage"""

    status = "status"
    enable = "enable"
    disable = "disable"
    set = "set"
    reset = "reset"
    check = "check"


class RateLimitManagePayload(BaseModel):
    """Payload for ratelimit.manage tool."""

    action: RateLimitManageAction

    # For status
    verbose: bool = Field(default=False, description="Include detailed stats")

    # For set
    rate: float | None = Field(default=None, ge=0.0, description="Requests per second")
    burst: int | None = Field(default=None, ge=1, description="Burst capacity")
    window: int | None = Field(default=None, ge=1, description="Time window in seconds")
    dry_run: bool | None = None

    # For check
    key: str | None = Field(default=None, min_length=1, description="Key to check (e.g., user:123)")
    cost: int = Field(default=1, ge=1, description="Cost of operation")

    # Context
    principal: str | dict[str, Any] | None = None
    tenant: str | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def validate_action_requirements(self):
        """Validate required fields based on action."""
        if self.action == "check" and not self.key:
            raise ValueError("'key' is required for action 'check'")
        return self

    model_config = ConfigDict(use_enum_values=True)


# ─────────────────────────────────────────────────────────────────────────────
# Utility: Get schema for tool
# ─────────────────────────────────────────────────────────────────────────────

TOOL_SCHEMAS = {
    "graph.query": GraphQueryPayload,
    "graph.secure_query": GraphSecureQueryPayload,
    "graph.crud": GraphCrudPayload,
    "graph.generate_cypher": GraphGenerateCypherPayload,
    "graph.schema": GraphSchemaPayload,
    "graph.search": GraphSearchPayload,
    "graph.analytics": GraphAnalyticsPayload,
    "graph.bulk": GraphBulkPayload,
    "system.health": SystemHealthPayload,
    "data.archive": DataArchivePayload,
    "security.audit": SecurityAuditPayload,
    "security.permissions": SecurityPermissionsPayload,
    "model.manage": ModelManagePayload,
    "db.switch": DbSwitchPayload,
    "errors.report": ErrorsReportPayload,
    "ratelimit.manage": RateLimitManagePayload,
}


def get_schema(tool_name: str) -> type[BaseModel] | None:
    """Get Pydantic schema for a tool."""
    return TOOL_SCHEMAS.get(tool_name)
