# Agent Run Workflow A - Synchronous Execution via BackgroundTasks

> **Status**: ✅ Production Ready  
> **Last Updated**: January 2026  
> **Authors**: Cineca Agentic Platform Team

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation Details](#implementation-details)
4. [Orchestrator Internals](#orchestrator-internals)
5. [Intent Classification System](#intent-classification-system)
6. [Mode Handlers](#mode-handlers)
7. [TODO Planning and Execution](#todo-planning-and-execution)
8. [LLM Client Management](#llm-client-management)
9. [MCP Tools Integration](#mcp-tools-integration)
10. [Files Involved](#files-involved)
11. [Complete Workflow A Step-by-Step](#complete-workflow-a-step-by-step)
12. [API Usage](#api-usage)
13. [Configuration](#configuration)
14. [Schemas and Data Models](#schemas-and-data-models)
15. [Error Handling](#error-handling)
16. [Metrics and Observability](#metrics-and-observability)
17. [Comparison: Workflow A vs Workflow B](#comparison-workflow-a-vs-workflow-b)

---

## Overview

Workflow A provides **synchronous-style agent execution** using FastAPI's `BackgroundTasks` mechanism. The endpoint returns immediately with `status=queued`, while the orchestration runs in the same process context.

### Key Characteristics

| Feature | Workflow A |
|---------|------------|
| **Endpoint** | `POST /v1/agent-runs` |
| **Execution** | FastAPI BackgroundTasks (same process) |
| **Response** | HTTP 201 with `status=queued` + `Location` header |
| **Progress** | Poll `GET /v1/agent-runs/{run_id}` |
| **Persistence** | AgentRun in PostgreSQL |
| **Timeout** | `RUN_TIMEOUT_SECONDS` (configurable) |
| **Best For** | Quick responses, simple workflows |

### Use Cases

| Scenario | Recommendation |
|----------|----------------|
| Quick chat responses (< 30s) | ✅ Use Workflow A |
| Simple Q&A interactions | ✅ Use Workflow A |
| Single-step orchestration | ✅ Use Workflow A |
| Low-latency requirements | ✅ Use Workflow A |
| Complex multi-step orchestration | ❌ Use Workflow B |
| Long-running NL→Cypher queries | ❌ Use Workflow B |
| Fault-tolerant execution | ❌ Use Workflow B |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW A ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐     ┌─────────────────────┐     ┌─────────────┐               │
│  │  Client  │────▶│  POST /v1/agent-runs│────▶│  PostgreSQL │               │
│  │   (UI)   │     │     (API Layer)     │     │ (AgentRun)  │               │
│  └──────────┘     └─────────────────────┘     └─────────────┘               │
│       │                    │                                                 │
│       │                    │ HTTP 201 (status=queued)                        │
│       │◀───────────────────┘                                                 │
│       │                                                                      │
│       │           ┌──────────────────────────────────────────────────┐      │
│       │           │         FASTAPI BACKGROUNDTASKS (same process)    │      │
│       │           │  ┌────────────────────────────────────────────┐  │      │
│       │           │  │  execute_agent_run_background()            │  │      │
│       │           │  │                                            │  │      │
│       │           │  │  1. Update status: queued → running        │  │      │
│       │           │  │  2. Initialize Orchestrator.from_env()     │  │      │
│       │           │  │  3. Call orchestrator.run() with timeout   │  │      │
│       │           │  │     ├─ Intent Classification               │  │      │
│       │           │  │     │   ├─ chat → _handle_chat_mode()      │  │      │
│       │           │  │     │   ├─ graph → _handle_graph_mode()    │  │      │
│       │           │  │     │   ├─ security → _handle_security_mode│  │      │
│       │           │  │     │   ├─ admin → _handle_admin_mode()    │  │      │
│       │           │  │     │   ├─ dangerous → refuse + EXPLAIN    │  │      │
│       │           │  │     │   └─ explain → _handle_explain_only()│  │      │
│       │           │  │     ├─ TODO List Creation (LLM-based)      │  │      │
│       │           │  │     ├─ Step Execution (tools, MCP, graph)  │  │      │
│       │           │  │     └─ Response Generation                 │  │      │
│       │           │  │  4. Extract results (output, todos, steps) │  │      │
│       │           │  │  5. Update status: running → succeeded/failed│ │      │
│       │           │  │  6. Record provenance event                │  │      │
│       │           │  │  7. Emit Prometheus metrics                │  │      │
│       │           │  └────────────────────────────────────────────┘  │      │
│       │           └──────────────────────────────────────────────────┘      │
│       │                                      │                              │
│       │                                      ▼                              │
│       │           ┌──────────────────────────────────────────────────┐      │
│       │           │               POLLING ENDPOINT                    │      │
│       └──────────▶│  GET /v1/agent-runs/{run_id}                     │      │
│                   │  - Returns current status                         │      │
│                   │  - ETag support for caching                       │      │
│                   │  - Full result when complete                      │      │
│                   └──────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### State Machine

```
     ┌─────────┐
     │ queued  │ ◀─── POST /v1/agent-runs creates run
     └────┬────┘
          │ BackgroundTask starts
          ▼
     ┌─────────┐
     │ running │ ◀─── Orchestrator executing
     └────┬────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌──────────┐ ┌────────┐
│ succeeded│ │ failed │
└──────────┘ └────────┘
    │           │
    └─────┬─────┘
          │
    Terminal States
```

---

## Implementation Details

### Entry Point: `POST /v1/agent-runs`

The endpoint is defined in [src/routers/agent_runs.py](src/routers/agent_runs.py) and performs:

1. **Rate Limiting**: Per-user rate limit check via `RateLimitHandler`
2. **Readiness Gate**: Rejects requests if orchestrator not ready (503)
3. **Idempotency**: Optional `Idempotency-Key` header for safe retries
4. **Session Management**: Creates or validates existing session
5. **Model Configuration**: Loads default model from database
6. **Run Creation**: Creates `AgentRun` record with `status=queued`
7. **Background Scheduling**: Adds `execute_agent_run_background()` to BackgroundTasks
8. **Response**: Returns HTTP 201 with run details and `Location` header

### Background Execution: `execute_agent_run_background()`

The background task handles the actual orchestration:

```python
async def execute_agent_run_background(
    run_id: uuid.UUID,
    prompt: str,
    user_id: str,
    session_id: str,
    tenant_id: str,
    params: dict[str, Any],
    request_id: str | None = None,
):
    """Execute orchestrator in background and update run status."""
```

**Steps**:
1. Get new database session for background context
2. Update status: `queued` → `running`
3. Initialize orchestrator via `Orchestrator.from_env()`
4. Execute `orchestrator.run()` with `asyncio.wait_for()` timeout
5. Extract results: output, todos, steps, metrics
6. Handle errors/timeouts gracefully
7. Update status: `running` → `succeeded`/`failed`
8. Record provenance event
9. Emit Prometheus metrics

### Orchestrator Integration

The `Orchestrator` class coordinates:

- **LLM Calls**: Planning and reflection via configured LLM providers
- **Tool Invocations**: MCP-style tools or Python callables
- **Graph Access**: Memgraph for NL→Cypher queries
- **Cache Lookups**: Redis for session state
- **Audit Logging**: Security hooks and provenance

```python
from src.services.orchestrator import Orchestrator

orch = Orchestrator.from_env()
result = await orch.run(
    goal=prompt,
    user_id=user_id,
    session_id=session_id,
    tenant_id=tenant_id,
    run_id=str(run_id),
    params=params,
)
```

---

## Orchestrator Internals

The `Orchestrator` class (8,000+ lines in `src/services/orchestrator.py`) is the core of Workflow A. It coordinates all aspects of agent execution.

### Key Data Structures

#### Step Dataclass

```python
@dataclass
class Step:
    """Single orchestration step."""
    id: str
    action: str                           # e.g., "graph.query", "llm:planner"
    input: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None
```

#### OrchestrationContext Dataclass

```python
@dataclass
class OrchestrationContext:
    """Mutable blackboard for orchestration state."""
    goal: str
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    run_id: str | None = None
    principal: dict[str, Any] | None = None
    vars: dict[str, Any] = field(default_factory=dict)  # Shared state
```

#### OrchestrationResult Dataclass

```python
@dataclass
class OrchestrationResult:
    """Complete result with metrics tracking."""
    goal: str
    started_at: str
    finished_at: str | None = None
    current_stage: str = "initializing"
    
    # Core results
    steps: list[Step] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)
    
    # Metrics
    overall_ms: int | None = None
    llm_call_count: int = 0
    total_llm_calls: int = 0
    llm_attempted_calls: int = 0
    llm_successful_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    llm_metrics: list[dict[str, Any]] = field(default_factory=list)
    tool_metrics: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    
    # Status
    error: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    used_fallback: bool = False
    timeout_stage: str | None = None
```

#### GraphResultEnvelope (for Graph Queries)

```python
@dataclass
class GraphResultItem:
    type: str                # "count", "types", "rows", "schema", "plan", "properties"
    data: Any
    label: str | None = None
    query: str | None = None

@dataclass
class GraphResultEnvelope:
    """Structured result envelope for graph queries."""
    primary: GraphResultItem
    aux: list[GraphResultItem] = field(default_factory=list)
    goal: str | None = None
    cypher: str | None = None
    
    @classmethod
    def from_count_query(cls, count: int, goal: str, cypher: str) -> "GraphResultEnvelope":
        """Create envelope for count queries."""
        ...
    
    @classmethod
    def from_rows_query(cls, rows: list, goal: str, cypher: str) -> "GraphResultEnvelope":
        """Create envelope for row-returning queries."""
        ...
```

### Orchestrator Factory: `from_env()`

The `Orchestrator.from_env()` factory method initializes the orchestrator with:

1. **LLM Clients** - Loaded from `model_defaults` database table (NOT env vars)
2. **MCP Tools** - Loaded and validated (minimum 32 tools required)
3. **Graph Database** - Memgraph connection for NL→Cypher
4. **Redis Cache** - Session state and tool caching
5. **Model Warmup** - RAM-aware fallback to lighter models if needed

```python
@classmethod
def from_env(cls) -> "Orchestrator":
    """Factory method for environment-based initialization."""
    # Load LLM clients from model_defaults table
    llm_clients = _load_llm_clients_from_db()
    
    # Load MCP tools (validates minimum 32 tools)
    tools = load_mcp_tools()
    if len(tools) < 32:
        raise ServiceError("Insufficient MCP tools loaded")
    
    # Warmup model with RAM-aware fallback
    warmup_models = ["phi3-mini", "llama-3.2-3b", "qwen-2.5-3b"]
    ...
```

---

## Intent Classification System

The orchestrator uses a sophisticated intent classification system to route requests to specialized handlers. This is one of the most important architectural components.

### Intent Modes

| Mode | Description | Handler |
|------|-------------|---------|
| `chat` | General conversational responses | `_handle_chat_mode()` |
| `graph` | Graph database queries (NL→Cypher) | `_handle_graph_mode()` |
| `security` | Security/permissions questions | `_handle_security_mode()` |
| `admin` | Administrative write operations | `_handle_admin_mode()` |
| `dangerous` | Potentially dangerous queries | `_handle_dangerous_mode()` |
| `explain` | EXPLAIN-only query analysis | `_handle_explain_only()` |

### Classification Flow

```
User Goal
    │
    ▼
┌─────────────────────────────────┐
│    _classify_user_intent()      │
│                                 │
│  1. Check params.category       │
│  2. Match prompt catalog        │
│  3. Apply classify_intent()     │
│  4. Return mode + confidence    │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│        Intent Result            │
│  - mode: IntentMode             │
│  - confidence: 0.0-1.0          │
│  - reasoning: str               │
│  - matched_catalog_id: str|None │
│  - matched_patterns: list       │
└─────────────────────────────────┘
    │
    ▼
Route to appropriate handler
```

### Intent Classification Method

```python
def _classify_user_intent(
    self,
    goal: str,
    ctx: OrchestrationContext,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify the user's intent to determine routing.
    
    Returns:
        - mode: "chat" | "graph" | "security" | "admin" | "dangerous"
        - confidence: float 0.0-1.0
        - reasoning: str explanation
        - matched_catalog_id: str | None
    """
```

### Catalog Matching

The system can match prompts against a pre-defined catalog:

```python
# From src/services/prompt_catalog.py
def match_prompt_by_text(goal: str) -> dict | None:
    """Match goal text against the prompt catalog."""
    ...

def get_execution_hints(catalog_entry: dict) -> dict:
    """Get execution hints from catalog entry."""
    return {
        "limit_hint": catalog_entry.get("limit"),
        "random": catalog_entry.get("random", False),
        "todo_mode": catalog_entry.get("todo_mode"),
    }
```

---

## Mode Handlers

Each intent mode has a dedicated handler that provides specialized processing.

### Chat Mode (`_handle_chat_mode`)

Handles general conversational queries without graph operations.

```python
async def _handle_chat_mode(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """Handle general chat/conversational responses."""
```

### Security Mode (`_handle_security_mode`)

Handles questions about user permissions, identity, and security context.

```python
async def _handle_security_mode(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """
    Handle security-related queries:
    - Permission questions ("Can I write?")
    - Identity questions ("What are my scopes?")
    - Safety questions ("What queries are dangerous?")
    """
```

**Security Mode Features:**
- Uses `security.describe_principal` tool
- Uses `security.allowed_operations` tool
- Provides RBAC-aware responses

### Admin Mode (`_handle_admin_mode`)

Handles administrative write operations with strict RBAC validation.

```python
async def _handle_admin_mode(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """
    Handle admin write operations:
    - CREATE INDEX / DROP INDEX
    - CREATE CONSTRAINT / DROP CONSTRAINT
    - MERGE, SET (write operations)
    - DELETE operations
    - Property renames
    
    Returns denial for non-admin users.
    """
```

**Admin Mode Features:**
- Validates admin privileges before execution
- Generates denial response with LLM explanation
- Uses `graph_access_policy.validate_for_principal()`
- Full audit logging of admin operations

### Dangerous Mode (`_handle_dangerous_mode`)

Refuses execution of dangerous queries and offers EXPLAIN alternatives.

```python
async def _handle_dangerous_mode(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """
    Handle dangerous queries - refuse execution and offer EXPLAIN.
    
    Dangerous operations include:
    - Unbounded queries (no LIMIT)
    - Full graph scans
    - Cartesian products
    - DELETE all / DROP operations
    - Heavy export operations
    """
```

**Danger Analysis:**
- Identifies specific danger reasons
- Suggests safer alternatives
- Provides EXPLAIN query for plan analysis

### Graph Mode (`_handle_graph_mode`)

Handles graph queries with a streamlined 4-step pipeline.

```python
async def _handle_graph_mode(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """
    Handle graph queries with 4-step pipeline:
    1. Generate Cypher from natural language
    2. Validate query against security policy
    3. Execute the validated query
    4. Build natural language response
    """
```

**Graph Mode Pipeline:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    GRAPH MODE PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: Generate Cypher                                        │
│  ├─ Detect relationship type queries                            │
│  ├─ Use graph.generate_cypher tool                              │
│  └─ Or use raw Cypher from goal                                 │
│                                                                 │
│  Step 2: Security Validation                                    │
│  ├─ validate_for_principal(cypher, principal)                   │
│  └─ Block if not safe                                           │
│                                                                 │
│  Step 3: Execute Query                                          │
│  ├─ Use graph.secure_query or graph.query                       │
│  └─ Capture rows and metrics                                    │
│                                                                 │
│  Step 4: Build Response                                         │
│  ├─ Create GraphResultEnvelope                                  │
│  └─ Build NL response from envelope                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Explain Mode (`_handle_explain_only`)

Safe execution of query plan analysis without running the actual query.

```python
async def _handle_explain_only(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
    intent: dict[str, Any],
) -> ServiceResult[dict[str, Any]]:
    """Handle EXPLAIN-only queries for safe plan analysis."""
```

---

## TODO Planning and Execution

The orchestrator uses a TODO-based execution model for complex goals.

### TODO List Creation

```python
async def _create_agent_todo_list(
    self,
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
) -> list[dict[str, Any]]:
    """
    Create TODO list via LLM.
    
    Returns list of TODOs:
    - task: str description
    - status: "pending" | "in_progress" | "completed" | "failed"
    - meta: execution hints
    - requires_llm_planning: bool
    """
```

**TODO Planning Modes:**

| Mode | Description | LLM Calls |
|------|-------------|-----------|
| `full` | Full LLM planning for each TODO | Multiple |
| `optional` | Try graph tools, fallback to LLM | 1-2 |
| `none` | Deterministic execution only | 0-1 |

### TODO Execution

```python
async def _execute_todo_with_steps(
    self,
    todos: list[dict[str, Any]],
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
) -> None:
    """Execute each TODO with step tracking."""
```

**Execution Flow:**
```
For each TODO:
    │
    ├─ is_tool_discovery_task → Execute catalog.discover
    │
    ├─ is_storage_task → Handle storage operations
    │
    ├─ is_format_task → Format discovered tools
    │
    ├─ requires_llm_planning=False → Direct execution
    │   └─ _execute_direct_todo() or _handle_simple_memgraph_todo()
    │
    └─ requires_llm_planning=True → LLM-based execution
        ├─ Generate plan via plan()
        └─ Execute each step with timeout
```

### Direct TODO Execution (No LLM)

For simple Memgraph queries, the system can bypass LLM planning:

```python
async def _execute_memgraph_direct_todo(
    self,
    *,
    todo_idx: int,
    todo: dict[str, Any],
    goal: str,
    ctx: OrchestrationContext,
    result: OrchestrationResult,
) -> bool:
    """
    Deterministic Memgraph execution path (no per-TODO LLM).
    
    - Runs graph.generate_cypher (if available)
    - Then graph.secure_query/graph.query
    - Summarizes count directly from tool outputs
    """
```

---

## LLM Client Management

The orchestrator manages multiple LLM clients with fallback support.

### Client Configuration

```python
class Orchestrator:
    llm_clients: dict[str, Any]        # Named LLM clients
    main_llm_name: str | None          # Primary client name
    default_model: str | None          # Default model identifier
    llm: Any                           # Primary LLM adapter
```

### Model Warmup

On startup, the orchestrator warms up LLM models with RAM-aware fallback:

```python
# Warmup with fallback to lighter models
fallback_models = ["phi3-mini", "llama-3.2-3b", "qwen-2.5-3b"]

for model in [primary_model] + fallback_models:
    if try_warmup(model):
        break
```

### LLM Call with Metrics

```python
async def call_model_with_metrics(
    self,
    prompt: str,
    result: OrchestrationResult,
    *,
    client_name: str | None = None,
    purpose: str = "general",
    budget_ms: int | None = None,
    **kwargs,
) -> str:
    """
    Call LLM and track metrics.
    
    Args:
        prompt: The prompt to send
        result: OrchestrationResult to record metrics
        client_name: Named client to use
        purpose: Purpose label for metrics
        budget_ms: Soft timeout budget
    """
```

### Runtime LLM Management

```python
# Register new LLM at runtime
orchestrator.register_llm(
    name="workerA",
    base_url="http://localhost:8001",
    model="llama-3.2-3b",
    tenant_id="tenant-1",
)

# Set tenant's main LLM
orchestrator.set_main_llm("workerA", tenant_id="tenant-1")

# Unregister LLM
orchestrator.unregister_llm("workerA")

# List available LLMs
llms = orchestrator.list_llms()
```

---

## MCP Tools Integration

The orchestrator loads and validates MCP (Model Context Protocol) tools.

### Tool Loading

```python
# Minimum 32 tools required for startup
MIN_MCP_TOOLS = 32

tools = load_mcp_tools()
if len(tools) < MIN_MCP_TOOLS:
    raise ServiceError(f"Insufficient MCP tools: {len(tools)} < {MIN_MCP_TOOLS}")
```

### Core MCP Tools

| Tool | Description |
|------|-------------|
| `graph.query` | Execute Cypher queries |
| `graph.secure_query` | Execute with RBAC validation |
| `graph.generate_cypher` | NL→Cypher generation |
| `graph.schema` | Get graph schema info |
| `catalog.discover` | Discover available tools |
| `security.describe_principal` | Get principal info |
| `security.allowed_operations` | Get allowed operations |
| `agent.context` | Get/set agent context |
| `system.metrics` | Get system metrics |
| `system.health` | Health check |
| `model.manage` | Model management |
| `cache.manage` | Cache operations |

### Tool Execution

```python
async def execute_tool(
    self,
    name: str,
    payload: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    Execute a tool by name.
    
    MCP tools expect payload dict with:
    - principal: User principal for RBAC
    - tenant: Tenant ID for isolation
    - Other tool-specific parameters
    """
```

### Tool ACL (Access Control)

```python
# Set per-client tool permissions
orchestrator.set_tool_acl({
    "workerA": ["graph.query", "cache.manage"],
    "workerB": ["graph.query", "graph.generate_cypher"],
})
```

---

## Memgraph Response Builder

The orchestrator includes a sophisticated NL response builder for Memgraph query results.

### Builder Modes

| Mode | Description | LLM Usage |
|------|-------------|-----------|
| `fallback-only` | Deterministic summarizer only | None |
| `llm-best-effort` | Try LLM, fall back on error | Optional |
| `llm-required` | LLM required, fail on error | Required |

Configure via:
```python
MEMGRAPH_RESPONSE_MODE = "llm-best-effort"  # Default
MEMGRAPH_BUILDER_LLM_TIMEOUT_MS = 300000    # 5 min default
```

### Response Building Pipeline

```python
async def build_memgraph_nl_response(
    self,
    *,
    goal: str,
    cypher: str | None,
    rows: list[Any] | None,
    rowcount: int | None,
    steps: list[Step],
    role: str | None,
    todos: list[dict[str, Any]],
    prompt_id: str | None,
    verbose: bool,
    result: OrchestrationResult | None,
) -> str:
    """
    Build natural language response from graph query results.
    
    Steps:
    1. Summarize rows into examples
    2. Build deterministic template
    3. (If verbose) Enhance with LLM
    4. Clean up and return
    """
```

### Query Type Detection

The builder detects query types for appropriate formatting:

| Query Type | Detection | Format |
|------------|-----------|--------|
| Count | "how many", "count" | "There are N :Label nodes" |
| Relationship Types | "relationship type" | Bullet list of types |
| Grouped Count | "grouped by" | Groups with counts |
| Example Values | "example values" | List of distinct values |
| Sample | "random", "sample" | Node properties |

### Row Summarization

```python
def _summarize_memgraph_rows(
    self,
    rows: list[Any] | None,
    *,
    max_nodes: int = 10,
    max_props: int = 5,
    max_val_len: int = 80,
    goal: str | None = None,
) -> list[str]:
    """
    Return compact bullet-friendly node/property samples.
    
    Priority properties: dbname, blasttype, status, blast_version, output_result
    """
```

---

## Files Involved

### Core Files

| File | Purpose |
|------|---------|
| [src/routers/agent_runs.py](src/routers/agent_runs.py) | API endpoints, background task |
| [src/services/orchestrator.py](src/services/orchestrator.py) | Orchestration logic |
| [src/schemas/agents.py](src/schemas/agents.py) | Pydantic schemas |
| [db/postgres_control/repositories/agents.py](db/postgres_control/repositories/agents.py) | AgentRun repository |

### Supporting Files

| File | Purpose |
|------|---------|
| [src/config.py](src/config.py) | Timeout configuration |
| [src/config_modules/compute.py](src/config_modules/compute.py) | Device-aware timeouts |
| [src/metrics/agent_metrics.py](src/metrics/agent_metrics.py) | Prometheus metrics |
| [src/provenance.py](src/provenance.py) | Audit trail recording |
| [src/middleware/idempotency.py](src/middleware/idempotency.py) | Idempotency handling |
| [src/middleware/rate_limit.py](src/middleware/rate_limit.py) | Rate limiting |

---

## Complete Workflow A Step-by-Step

### Phase 1: Request Reception (API Layer)

| Step | Component | Description |
|------|-----------|-------------|
| 1 | Client | User sends `POST /v1/agent-runs` with prompt |
| 2 | OIDC | JWT token validation via `require_perms()` |
| 3 | Rate Limiter | Check per-user rate limit (`runs:create`) |
| 4 | Readiness | Verify `Orchestrator.is_ready()` returns True |
| 5 | Idempotency | Check `Idempotency-Key` header for cached response |
| 6 | Validation | Validate request body via `CreateRunRequest` schema |

### Phase 2: Run Initialization

| Step | Component | Description |
|------|-----------|-------------|
| 7 | Session | Get existing session or create new one |
| 8 | Model Config | Load default model from `model_defaults` table |
| 9 | AgentRun | Create database record with `status=queued` |
| 10 | Trace ID | Generate stable `trace_id` for this run |
| 11 | Params | Build orchestration params (temperature, max_steps, etc.) |
| 12 | Principal | Serialize user principal for RBAC |
| 13 | Commit | Persist run record to PostgreSQL |
| 14 | Metrics | Increment `agent_run_queued_total` counter |

### Phase 3: Response (Immediate)

| Step | Component | Description |
|------|-----------|-------------|
| 15 | Background | Schedule `execute_agent_run_background()` |
| 16 | Headers | Set `Location`, `Idempotency-Key`, `X-Request-Id` |
| 17 | Cache | Cache idempotent response (if key provided) |
| 18 | Response | Return HTTP 201 with `status=queued` |

### Phase 4: Background Execution

| Step | Component | Description |
|------|-----------|-------------|
| 19 | DB Session | Create new database session for background task |
| 20 | Status | Update: `queued` → `running` |
| 21 | Metrics | Decrement queued, increment running counters |
| 22 | Orchestrator | Initialize via `Orchestrator.from_env()` |
| 23 | Intent | Classify intent via `_classify_user_intent()` |
| 24 | Routing | Route to mode handler based on intent |
| 25 | Planning | Generate TODO list via LLM (if not simple mode) |
| 26 | Execution | Execute steps with timeout protection |
| 27 | LLM Calls | Make LLM provider calls (with fallback) |
| 28 | MCP Tools | Invoke MCP tools (with RBAC checks) |
| 29 | Graph | Execute NL→Cypher pipeline (if GRAPH mode) |
| 30 | Response | Generate final response text |

### Phase 4a: Intent-Based Routing (Detail)

| Mode | Handler | Description |
|------|---------|-------------|
| `chat` | `_handle_chat_mode()` | Conversational response |
| `graph` | `_handle_graph_mode()` | 4-step graph pipeline |
| `security` | `_handle_security_mode()` | Security/permissions info |
| `admin` | `_handle_admin_mode()` | Admin writes with RBAC |
| `dangerous` | `_handle_dangerous_mode()` | Refuse + EXPLAIN offer |
| `explain` | `_handle_explain_only()` | Query plan analysis |

### Phase 5: Result Processing

| Step | Component | Description |
|------|-----------|-------------|
| 31 | Extraction | Extract output, todos, steps from result |
| 32 | Metrics | Extract LLM and tool metrics |
| 33 | Errors | Collect and classify errors |
| 34 | Warnings | Collect non-fatal warnings |
| 35 | Latency | Calculate total execution time |

### Phase 6: Finalization

| Step | Component | Description |
|------|-----------|-------------|
| 36 | Status | Update: `running` → `succeeded`/`failed` |
| 37 | Persist | Save output, todos, steps, metrics to DB |
| 38 | Provenance | Record provenance event with `trace_id` |
| 39 | Metrics | Emit completion metrics (duration, success/fail) |
| 40 | Cleanup | Close database session |

### Phase 7: Client Polling

| Step | Component | Description |
|------|-----------|-------------|
| 41 | Client | `GET /v1/agent-runs/{run_id}` |
| 42 | Auth | Validate ownership (user owns run or is admin) |
| 43 | ETag | Check `If-None-Match` header |
| 44 | Response | Return full run details when complete |

---

## API Usage

### Create Agent Run

```bash
# Create an agent run (returns immediately)
curl -X POST https://api.example.com/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-request-id-123" \
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.2,
    "max_steps": 8
  }'

# Response (HTTP 201)
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "user@example.com",
  "tenant_id": "default",
  "status": "queued",
  "started_at": "2026-01-23T10:30:00Z",
  "trace_id": "abcd1234-5678-90ab-cdef-123456789012"
}

# Headers:
# Location: /v1/agent-runs/550e8400-e29b-41d4-a716-446655440000
# Idempotency-Key: unique-request-id-123
# X-Request-Id: req-abc123
```

### Poll for Status

```bash
# Check run status
curl https://api.example.com/v1/agent-runs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: \"etag-from-previous-request\""

# Response when still running (HTTP 200)
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "started_at": "2026-01-23T10:30:00Z"
}

# Response when complete (HTTP 200)
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "output": {
    "text": "The capital of France is Paris."
  },
  "todos": [
    {
      "task": "Answer the question about France's capital",
      "status": "completed"
    }
  ],
  "steps": [...],
  "metrics": {
    "overall_ms": 1234,
    "llm_call_count": 2,
    "tool_calls": 0
  },
  "finished_at": "2026-01-23T10:30:01.234Z",
  "latency_ms": 1234
}
```

### Get Execution Steps

```bash
# Get detailed execution steps
curl https://api.example.com/v1/agent-runs/550e8400-e29b-41d4-a716-446655440000/steps \
  -H "Authorization: Bearer $TOKEN"

# Response
[
  {
    "step_id": "1",
    "action": "llm:planner",
    "input": {"prompt": "What is the capital of France?"},
    "output": {"text": "Paris"},
    "latency_ms": 800
  }
]
```

### Get Outputs

```bash
# Get execution outputs
curl https://api.example.com/v1/agent-runs/550e8400-e29b-41d4-a716-446655440000/outputs \
  -H "Authorization: Bearer $TOKEN"

# Response
[
  {
    "step_id": "final-output",
    "action": "finalize",
    "output": {"text": "The capital of France is Paris."}
  }
]
```

### With Existing Session

```bash
# Create run with existing session
curl -X POST https://api.example.com/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "prompt": "Tell me more about Paris"
  }'
```

### Force Full Agentic Mode

```bash
# Disable trivial fast paths (force full orchestration)
curl -X POST https://api.example.com/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello",
    "force_full_agentic": true
  }'
```

---

## Configuration

### Timeout Configuration

Timeouts are device-aware (CPU vs GPU):

| Variable | CPU Default | GPU Default | Description |
|----------|-------------|-------------|-------------|
| `RUN_TIMEOUT_SECONDS` | 1200 (20 min) | 60 (1 min) | Total run timeout |
| `STEP_TIMEOUT_SECONDS` | 300 (5 min) | 30 (30 sec) | Per-step timeout |

Configuration via [src/config_modules/compute.py](src/config_modules/compute.py):

```python
# Device detection
device = "cuda" if torch.cuda.is_available() else "cpu"

# Timeouts scale with device capability
if device == "cpu":
    run_timeout = 1200   # 20 minutes
    step_timeout = 300   # 5 minutes
else:
    run_timeout = 60     # 1 minute
    step_timeout = 30    # 30 seconds
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_MODEL` | - | Default LLM model name |
| `LLM_CLIENTS` | - | Comma-separated LLM client configs |
| `OPENAI_API_KEY` | - | OpenAI API key (if using OpenAI) |
| `MEMGRAPH_FORCE_LLM` | `false` | Force LLM for Memgraph queries |
| `APP_ENV` | `production` | Environment (test, development, production) |

### Database Configuration

Model configuration is loaded from the `model_defaults` table:

```sql
-- Example: Set default model
INSERT INTO model_defaults (scope, tenant_id, instance_id, priority)
VALUES ('global', NULL, 'phi3-mini', 10);
```

---

## Schemas and Data Models

### CreateRunRequest

```python
class CreateRunRequest(BaseModel):
    session_id: UUID | None = None      # Optional existing session
    prompt: str                          # Required: user's prompt
    manager: str | None = None           # Manager/planner LLM name
    preferred_workers: list[str] | None  # Preferred worker LLMs
    llm_preferences: dict[str, str] | None  # Tool→LLM mapping
    agent_role: str | None = None        # Agent role (researcher, coder)
    tools: list[str] | None = None       # Allowed tools
    temperature: float = 0.2             # Sampling temperature (0-2)
    max_steps: int = 8                   # Max orchestration steps (1-64)
    metadata: dict[str, Any] = {}        # Custom metadata
    force_full_agentic: bool = False     # Disable fast paths
```

### RunResponse

```python
class RunResponse(BaseModel):
    run_id: UUID                         # Run identifier
    session_id: UUID | None              # Associated session
    user_id: str                         # Owner user ID
    tenant_id: str                       # Tenant ID
    model: str | None                    # Model used
    manager: str | None                  # Manager used
    latency_ms: int | None               # Execution time
    trace_id: str | None                 # Stable trace ID
    request_id: str | None               # HTTP request ID
    event_id: str | None                 # Provenance event ID
    status: str                          # queued, running, succeeded, failed
    started_at: datetime                 # Start timestamp
    finished_at: datetime | None         # Finish timestamp
    output: dict | list | None           # Run output
    steps: list[Step] | None             # Execution steps
    todos: list[TodoItem] | None         # Generated TODOs
    metrics: ExecutionMetrics | None     # Performance metrics
    metadata: dict[str, Any] | None      # Request metadata
    errors: list[str] | None             # Errors encountered
    warnings: list[str] | None           # Non-fatal warnings
    degraded: bool | None                # Quality degraded flag
    used_fallback: bool | None           # Fallback used flag
```

### ExecutionMetrics

```python
class ExecutionMetrics(BaseModel):
    overall_ms: int                      # Total execution time
    llm: list[LLMCallMetrics]            # Per-LLM call metrics
    tools: list[ToolCallMetrics]         # Per-tool call metrics
    total_llm_calls: int | None          # Total LLM API calls
    llm_call_count: int | None           # LLM calls in this run
    llm_attempted_calls: int | None      # Attempted calls
    llm_successful_calls: int | None     # Successful calls
    tool_calls: int | None               # Tool invocations
    tool_errors: int | None              # Tool errors
    timeout_stage: str | None            # Where timeout occurred
    first_llm_call_ms: int | None        # First LLM call latency
```

### TodoItem

```python
class TodoItem(BaseModel):
    task: str                            # Task description
    status: str | None                   # pending, in_progress, completed, failed
    expect_evidence: bool = True         # Expect external evidence
    evidence: list[str] = []             # Supporting evidence
    meta: dict[str, Any] = {}            # Execution hints
    requires_llm_planning: bool = True   # Needs LLM planning
    nested_steps: list[str] = []         # Nested step descriptions
    fallback_mode: bool = False          # Fallback/LLM-only mode
```

---

## Error Handling

### Error Classification

The system classifies LLM errors for observability:

```python
def classify_llm_error(error_message: str) -> str:
    """Classify LLM error type from error message."""
    msg_lower = error_message.lower()
    
    if "timeout" in msg_lower:
        return "timeout"
    elif "context length" in msg_lower:
        return "context_length"
    elif "rate limit" in msg_lower:
        return "rate_limit"
    elif "connection" in msg_lower:
        return "connection"
    elif "validation" in msg_lower:
        return "validation"
    else:
        return "unknown"
```

### Failure Types

| Type | Description | Recovery |
|------|-------------|----------|
| `timeout` | Run exceeded `RUN_TIMEOUT_SECONDS` | Increase timeout or simplify prompt |
| `context_length` | LLM context window exceeded | Reduce prompt/history length |
| `rate_limit` | LLM provider rate limit hit | Wait and retry |
| `connection` | Network/provider unavailable | Check connectivity |
| `orchestrator_error` | Internal orchestration failure | Check logs |

### Error Response Format

Failed runs include structured error information:

```json
{
  "run_id": "550e8400-...",
  "status": "failed",
  "output": {
    "error": "Orchestrator timed out after 1200 seconds",
    "failure_type": "run_timeout",
    "todos_completed": 2,
    "todos_failed": 1,
    "partial_results": true,
    "timeout_reason": "Timeout occurred during executing_step after 3/5 successful LLM call(s)"
  },
  "errors": ["Orchestrator timed out after 1200 seconds"],
  "warnings": ["Timeout occurred during executing_step..."],
  "metrics": {
    "overall_ms": 1200000,
    "timeout_stage": "executing_step",
    "llm_attempted_calls": 5,
    "llm_successful_calls": 3
  }
}
```

---

## Metrics and Observability

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_run_queued_total` | Counter | `tenant_id` | Runs created (queued) |
| `agent_run_running_total` | Gauge | `tenant_id` | Currently running |
| `agent_run_duration_seconds` | Histogram | `status`, `tenant_id` | Execution duration |
| `agent_run_success_total` | Counter | `tenant_id` | Successful runs |
| `agent_run_failures_total` | Counter | `failure_type`, `tenant_id` | Failed runs |
| `agent_todos_count` | Histogram | `tenant_id` | TODOs per run |

### Structured Logging

All operations emit structured logs:

```json
{
  "event": "agent_run.background.completed",
  "run_id": "550e8400-...",
  "user_id": "user@example.com",
  "tenant_id": "default",
  "status": "succeeded",
  "latency_ms": 1234,
  "request_id": "req-abc123",
  "trace_id": "abcd1234-..."
}
```

### Log Events

| Event | Description |
|-------|-------------|
| `agent_run.created` | Run record created |
| `agent_run.scheduled` | Background task scheduled |
| `agent_run.background.started` | Background execution started |
| `agent_run.background.running` | Status changed to running |
| `agent_run.background.completed` | Execution completed |
| `agent_run.background.timeout` | Run timed out |
| `agent_run.background.fatal_error` | Unhandled exception |

---

## Comparison: Workflow A vs Workflow B

| Aspect | Workflow A (BackgroundTasks) | Workflow B (Jobs Worker) |
|--------|------------------------------|--------------------------|
| **Endpoint** | `POST /v1/agent-runs` | `POST /v1/jobs` |
| **Execution** | Same process as API | Separate worker process |
| **HTTP Response** | 201 with `status=queued` | 202 with `Location` header |
| **Progress** | Poll `GET /agent-runs/{id}` | SSE `GET /jobs/{id}/events` |
| **Real-time Updates** | No (polling only) | Yes (SSE streaming) |
| **Cancellation** | Limited | Full support |
| **Fault Tolerance** | Lost on API restart | Survives restarts |
| **Scalability** | Limited to API instances | Horizontal worker scaling |
| **Persistence** | AgentRun only | Job + AgentRun (linked) |
| **Best For** | Quick, simple tasks | Long-running, complex tasks |

### When to Use Each

**Use Workflow A when:**
- Response expected in < 30 seconds
- Simple chat interactions
- Low latency is critical
- Single-step orchestration
- Don't need real-time progress

**Use Workflow B when:**
- Complex multi-step orchestration
- Long-running NL→Cypher queries
- Need real-time progress updates
- Require job cancellation
- Processing batch requests
- High availability required
- Need horizontal scaling

### Switching Between Workflows

You can use Workflow B from the agent-runs endpoint with the `use_jobs` parameter:

```bash
# Use jobs worker via agent-runs endpoint
POST /v1/agent-runs?use_jobs=true
```

This creates a job internally and returns the job_id in the response.

---

## Troubleshooting

### Common Issues

**1. Run stuck in `queued` status**
- Check API server logs for background task errors
- Verify orchestrator is ready: `Orchestrator.is_ready()`
- Check database connectivity

**2. Run times out**
- Check `RUN_TIMEOUT_SECONDS` configuration
- Review `timeout_stage` in metrics for where timeout occurred
- Consider using Workflow B for long-running tasks

**3. Run fails immediately**
- Check for model configuration in `model_defaults` table
- Verify LLM provider connectivity
- Review request validation errors

**4. Idempotency not working**
- Ensure `Idempotency-Key` header is provided
- Check Redis connectivity for idempotency cache
- Verify key format is consistent

**5. 503 "Agent service warming up"**
- Orchestrator is initializing
- Wait and retry after a few seconds
- Check startup logs for initialization errors

---

## References

- [Agent Runs API Documentation](../api/AGENT_RUNS_API.md)
- [Orchestrator Documentation](../orchestrator/README.md)
- [Workflow B Documentation](WORKFLOW_B.md)
- [LLM Model Configuration](../LLM_MODEL_CONFIGURATION.md)
- [Metrics Guide](../observability/METRICS.md)


---

# Workflow A Quick Reference

> Quick reference for the Agent Run Workflow (sync via BackgroundTasks)

## TL;DR

```bash
# 1. Create run
POST /v1/agent-runs
{
  "prompt": "Your question here"
}

# 2. Poll for result
GET /v1/agent-runs/{run_id}

# 3. Get steps (optional)
GET /v1/agent-runs/{run_id}/steps
```

## State Machine

```
queued → running → succeeded | failed
```

## Request Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | ✅ | - | User's question/goal |
| `session_id` | uuid | ❌ | auto | Existing session ID |
| `temperature` | float | ❌ | 0.2 | Sampling temperature |
| `max_steps` | int | ❌ | 8 | Max orchestration steps |
| `manager` | string | ❌ | null | Manager LLM name |
| `tools` | array | ❌ | null | Allowed tools |
| `metadata` | object | ❌ | {} | Custom metadata |
| `force_full_agentic` | bool | ❌ | false | Disable fast paths |

## Response Fields

| Field | Description |
|-------|-------------|
| `run_id` | Unique identifier |
| `status` | queued → running → succeeded/failed |
| `output` | Final output (when complete) |
| `todos` | Generated TODO list |
| `steps` | Execution steps |
| `metrics` | Performance metrics |
| `errors` | Error messages (if failed) |

## Recommended Polling Interval

- **Initial**: 1-2 seconds
- **After 10s**: 2-5 seconds
- **After 60s**: 5-10 seconds

## Timeout Configuration

| Device | RUN_TIMEOUT | STEP_TIMEOUT |
|--------|-------------|--------------|
| CPU | 1200s (20 min) | 300s (5 min) |
| GPU | 60s (1 min) | 30s (30 sec) |

## Key Files

| File | Purpose |
|------|---------|
| `src/routers/agent_runs.py` | API endpoints |
| `src/services/orchestrator.py` | Orchestration logic |
| `src/schemas/agents.py` | Pydantic schemas |
