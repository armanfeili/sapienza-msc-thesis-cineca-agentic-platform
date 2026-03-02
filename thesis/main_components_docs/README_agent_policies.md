# Agent Policies Framework

The agent_policies package provides centralized configuration for retry policies and role-based access control in the Cineca Agentic Platform. It implements declarative policies that govern agent behavior, security boundaries, and resilience patterns.

## Architecture Overview

The policies framework follows these design principles:

- **Declarative Configuration**: YAML-based policies for easy versioning and auditing
- **Hierarchical Inheritance**: Base policies with role-specific overrides
- **Runtime Interpretation**: Policies loaded at startup and interpreted by services/adapters
- **Versioned Schema**: Structured metadata with version tracking and documentation
- **Fail-Safe Defaults**: Conservative defaults with explicit opt-in for advanced features

## Core Components

### 1. Retry Policies (`retry.yaml`)

Centralized retry configuration for all outbound calls and internal operations.

#### Architecture
```
Policy Engine → Strategy Selection → Runtime Execution
     ↓              ↓              ↓
  YAML Config   Context Mapping   Backoff/Retry Logic
```

#### Policy Schema

```yaml
_meta:
  version: "1.0.0"
  updated: "2025-08-09"
  description: "Retry policies for platform operations"

defaults:           # Base retry configuration
  attempts: 5       # Maximum retry attempts
  timeout: 30.0     # Per-attempt timeout (seconds)
  max_elapsed: 120.0 # Overall deadline
  backoff:          # Exponential backoff configuration
    type: exponential
    base: 0.5       # Initial delay
    factor: 2.0     # Backoff multiplier
    max: 20.0       # Maximum delay cap
    jitter: full    # Randomization strategy
  retry_on:         # Conditions that trigger retry
    http_status: [429, "500-599"]
    exceptions: ["TimeoutError", "ConnectionError"]
    error_contains: ["timeout", "rate limit"]
  give_up_on:       # Hard failures, never retry
    http_status: [400, 401, 403]
    exceptions: ["ValueError", "AuthenticationError"]
  hedging:          # Parallel retry attempts
    enabled: false
    delay: 0.2      # Delay before starting second attempt
    max_parallel: 2 # Maximum parallel attempts
  circuit_breaker:  # Failure threshold protection
    window: 30.0    # Evaluation window (seconds)
    min_samples: 20 # Minimum calls before evaluation
    error_rate_threshold: 0.5  # Error rate that opens breaker
    cool_down: 15.0 # Recovery time (seconds)

strategies:         # Named retry strategies
  llm_standard:     # Inherits from defaults with overrides
    inherits: defaults
    overrides: {attempts: 6, timeout: 45.0}
    notes: "LLM inference with hedging"

mappings:           # Logical operation → strategy mapping
  llm: llm_standard
  tool_invoke: tool_invoke_default
  db_cypher: db_cypher_safe
```

#### Retry Strategies

##### LLM Standard Strategy
```yaml
llm_standard:
  attempts: 6
  timeout: 45.0
  max_elapsed: 150.0
  backoff:
    type: exponential
    base: 0.4
    factor: 2.0
    max: 25.0
    jitter: full
  hedging:
    enabled: true    # Request hedging for tail latency
    delay: 0.35
    max_parallel: 2
  circuit_breaker:
    window: 60.0
    min_samples: 30
    error_rate_threshold: 0.4
    cool_down: 20.0
```

**Features**:
- Higher attempt count for LLM reliability
- Request hedging to mitigate tail latency
- Conservative circuit breaker thresholds
- Final attempt may lower generation parameters

##### Tool Invoke Strategy
```yaml
tool_invoke_default:
  attempts: 4
  timeout: 20.0
  max_elapsed: 60.0
  give_up_on:
    exceptions: ["PolicyViolation", "ValidationError"]
```

**Features**:
- Strict failure handling for policy/validation errors
- Conservative retry for side-effect-free operations
- Callers must mark non-idempotent operations

##### Database Strategies
```yaml
db_cypher_safe:     # Read/idempotent operations
  attempts: 5
  timeout: 15.0
  backoff:
    type: decorrelated_jitter
    base: 0.3
    max: 6.0
  retry_on:
    exceptions: ["TransientDatabaseError", "ConnectionError"]
  give_up_on:
    exceptions: ["SyntaxError", "ConstraintViolation"]

db_cypher_bulk:     # Bulk write operations
  inherits: db_cypher_safe
  attempts: 3
  timeout: 30.0
  max_elapsed: 45.0
```

**Features**:
- Decorrelated jitter for database load distribution
- Syntax/constraint errors never retried
- Conservative bulk operation retry

##### Network I/O Strategy
```yaml
network_io:
  attempts: 4
  timeout: 20.0
  max_elapsed: 90.0
  retry_on:
    http_status: [408, 425, 429, "500-599"]
  give_up_on:
    http_status: [400, 401, 403, 404]
```

**Features**:
- Generic HTTP error handling
- Timeout and connection error recovery
- Authentication errors never retried

##### MCP Transport Strategy
```yaml
mcp_transport:
  attempts: 6
  timeout: 10.0
  max_elapsed: 80.0
  retry_on:
    error_contains: ["session closed", "transport error"]
```

**Features**:
- Higher attempts for session recovery
- Transport-specific error patterns
- Shorter timeouts for interactive sessions

##### Cache Strategy
```yaml
cache_quick:
  attempts: 5
  timeout: 2.0
  max_elapsed: 6.0
  backoff:
    base: 0.05
    max: 0.5
```

**Features**:
- Very fast timeouts for cache operations
- Tiny backoff delays for quick recovery
- Minimal elapsed time constraints

### 2. Role-Based Access Control (`roles.yaml`)

Role definitions controlling agent capabilities, tool access, and resource limits.

#### Architecture
```
Role Engine → Capability Check → Permission Enforcement
     ↓              ↓              ↓
  YAML Config   Pattern Matching   Access Control
```

#### Role Schema

```yaml
_meta:
  version: "1.0.0"
  updated: "2025-08-09"
  description: "Role-based access control policies"

defaults:           # Base role configuration
  model:            # Default model parameters
    id: "gpt-4o-mini"
    temperature: 0.2
    max_output_tokens: 2048
  tools:            # Tool access patterns
    allow: ["catalog.*", "output.*"]
    deny: []
  scopes:           # API permission scopes
    - "models:list"
    - "models:infer"
  safety:           # Content safety settings
    output_guard: "standard"
    intent_filter: "standard"
    pii_scrubber: "redact"
  provenance:       # Audit logging settings
    enabled: true
    hash_only: true
  limits:           # Rate limiting
    rpm: 60         # Requests per minute
    tpm: 40000      # Tokens per minute
    burst: 20       # Burst capacity
    concurrent_jobs: 3

roles:              # Named role definitions
  admin:            # Inherits defaults with overrides
    description: "Full administrative access"
    tools:
      allow: ["*"]
      deny: []
    scopes: ["admin:*", "models:*", "tools:*"]
    limits:
      rpm: 240
      tpm: 160000
```

#### Role Definitions

##### Admin Role
```yaml
admin:
  description: "Full administrative access, cross-tenant operations, and system controls"
  model:
    id: "gpt-4o"
    max_output_tokens: 4096
  tools:
    allow: ["*"]        # All tools permitted
    deny: []
  scopes:
    - "admin:*"         # Full admin access
    - "models:*"        # All model operations
    - "tools:*"         # All tool operations
    - "db:*"           # Database access
    - "graph:*"        # Graph operations
    - "tenants:*"      # Multi-tenant management
  limits:
    rpm: 240
    tpm: 160000
    concurrent_jobs: 20
```

**Capabilities**:
- Cross-tenant operations
- System administration
- Full tool and API access
- Highest rate limits

##### Researcher Role
```yaml
researcher:
  description: "Scientists exploring the graph, running models, producing summaries"
  tools:
    allow:
      - "graph.query"
      - "graph.search"
      - "catalog.discover"
      - "output.summarize"
      - "viz.render"
    deny:
      - "graph.crud"     # No data modification
      - "system.*"       # No system access
  scopes:
    - "models:infer"    # Model inference only
    - "db:query:read"   # Read-only database
  safety:
    intent_filter: "strict"  # Strict intent filtering
  limits:
    rpm: 60
    tool_rpm_overrides:
      graph.query: 30   # Higher limit for queries
```

**Capabilities**:
- Graph exploration and analysis
- Model inference for research
- Visualization and summarization
- Strict safety controls

##### Curator Role
```yaml
curator:
  description: "Data stewards who can edit graph content, run quality checks"
  tools:
    allow:
      - "graph.crud"     # Create/read/update/delete
      - "graph.bulk"     # Bulk operations
      - "data.quality"   # Quality checks
      - "data.archive"   # Archival operations
    deny:
      - "system.*"       # No system administration
  scopes:
    - "db:write"        # Database write access
    - "graph:crud"      # Graph modification
    - "archive:write"   # Archive management
  limits:
    rpm: 90
    tool_rpm_overrides:
      graph.bulk: 10    # Controlled bulk operations
```

**Capabilities**:
- Graph content curation
- Data quality management
- Bulk data operations
- Archive management

##### Data Engineer Role
```yaml
data_engineer:
  description: "ETL and infrastructure-focused users with bulk operations"
  model:
    temperature: 0.1   # Low creativity for ETL
  tools:
    allow:
      - "graph.bulk"
      - "system.backup"
      - "system.metrics"
      - "db.switch"     # Database switching
    deny:
      - "security.*"    # No security operations
  scopes:
    - "etl:*"          # ETL operations
    - "system:backup"  # Backup permissions
  limits:
    rpm: 120
    tool_rpm_overrides:
      graph.bulk: 20   # High bulk operation limits
      system.backup: 2 # Limited backup frequency
```

**Capabilities**:
- ETL pipeline management
- Bulk data operations
- System backup and monitoring
- Database administration

##### Operator Role
```yaml
operator:
  description: "SRE / operations role for monitoring and runtime controls"
  tools:
    allow:
      - "system.health"
      - "system.metrics"
      - "ratelimit.manage"
      - "security.check"
    deny:
      - "graph.crud"    # No data modification
  scopes:
    - "system:health"
    - "ratelimit:manage"
    - "security:check"
  limits:
    rpm: 180
    concurrent_jobs: 10
```

**Capabilities**:
- System monitoring and health checks
- Rate limit management
- Security monitoring
- No data modification permissions

##### Auditor Role
```yaml
auditor:
  description: "Read-only oversight for security and compliance"
  model:
    temperature: 0.0   # Deterministic responses
    max_output_tokens: 512
  tools:
    allow:
      - "security.audit"
      - "system.metrics"
      - "catalog.discover"
    deny:
      - "graph.query"   # Avoid direct data access
      - "models.*"      # No model generation
  scopes:
    - "security:audit:read"
    - "system:metrics"
  safety:
    output_guard: "strict"
    intent_filter: "strict"
  limits:
    rpm: 30
    concurrent_jobs: 2
```

**Capabilities**:
- Security and compliance monitoring
- System metrics access
- Strict safety controls
- Read-only operations

##### Guest Role
```yaml
guest:
  description: "Trial or external users with minimal capabilities"
  tools:
    allow:
      - "catalog.discover"
      - "graph.schema"
      - "output.summarize"
    deny:
      - "graph.query"   # No data access
      - "system.*"      # No system access
  safety:
    output_guard: "strict"
    intent_filter: "strict"
  limits:
    rpm: 20
    concurrent_jobs: 1
```

**Capabilities**:
- Limited tool access
- Schema discovery only
- Strict safety controls
- Minimal rate limits

## Configuration

### Loading Policies

```python
from src.agent_policies.retry import load_retry_policies
from src.agent_policies.roles import load_role_policies

# Load at application startup
retry_policies = load_retry_policies()
role_policies = load_role_policies()

# Access specific policies
llm_strategy = retry_policies.get_strategy('llm')
admin_role = role_policies.get_role('admin')
```

### Runtime Policy Resolution

```python
# Retry policy selection
operation_type = "llm"  # Maps to strategy via mappings
strategy = retry_policies.get_strategy_for_operation(operation_type)

# Role capability checking
user_role = "researcher"
role_config = role_policies.get_role(user_role)

# Check tool permission
if role_config.can_use_tool("graph.query"):
    # Execute tool
    pass
```

## Usage Examples

### Implementing Retry Logic

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMAdapter:
    def __init__(self, retry_policies):
        self.retry_config = retry_policies.get_strategy('llm')

    @retry(
        stop=stop_after_attempt(self.retry_config.attempts),
        wait=wait_exponential(
            multiplier=self.retry_config.backoff.base,
            max=self.retry_config.backoff.max
        ),
        retry=retry_if_exception_type(TimeoutError)
    )
    async def generate(self, prompt: str) -> str:
        return await self._call_llm_api(prompt)
```

### Role-Based Tool Filtering

```python
class ToolRegistry:
    def __init__(self, role_policies):
        self.role_policies = role_policies

    def get_allowed_tools(self, user_role: str) -> List[str]:
        role_config = self.role_policies.get_role(user_role)
        return role_config.get_allowed_tools()

    def can_execute_tool(self, user_role: str, tool_name: str) -> bool:
        role_config = self.role_policies.get_role(user_role)
        return role_config.can_use_tool(tool_name)
```

### Rate Limit Enforcement

```python
from src.agent_policies.roles import RoleConfig

class RateLimiter:
    def __init__(self, role_config: RoleConfig):
        self.limits = role_config.limits

    async def check_limits(self, user_id: str) -> bool:
        # Check RPM limit
        requests_this_minute = await self.get_requests_last_minute(user_id)
        if requests_this_minute >= self.limits.rpm:
            return False

        # Check TPM limit
        tokens_this_minute = await self.get_tokens_last_minute(user_id)
        if tokens_this_minute >= self.limits.tpm:
            return False

        return True
```

## Security Considerations

### Policy Validation
- **Schema Validation**: YAML structure validated at load time
- **Version Checking**: Policy versions tracked for compatibility
- **Audit Logging**: Policy changes logged for compliance
- **Fail-Safe Defaults**: Conservative defaults prevent accidental privilege escalation

### Access Control
- **Pattern Matching**: Tool permissions use glob patterns for flexibility
- **Deny Overrides**: Explicit deny rules take precedence over allow rules
- **Scope Hierarchies**: API scopes support wildcards for hierarchical permissions
- **Context Awareness**: Policies can be parameterized by tenant/context

### Safety Controls
- **Content Filtering**: Multiple levels of output and intent filtering
- **PII Protection**: Configurable PII scrubbing (off/mask/redact)
- **Provenance Tracking**: Input/output hashing for audit trails
- **Rate Limiting**: Multi-dimensional limits prevent abuse

## Performance Characteristics

### Policy Loading
- **Startup Time**: Policies loaded once at application startup
- **Memory Usage**: Minimal memory footprint for cached policies
- **Lookup Speed**: O(1) policy resolution with dictionary caching
- **Hot Reloading**: Optional runtime policy updates for development

### Retry Impact
- **Backoff Efficiency**: Exponential backoff prevents thundering herd
- **Circuit Breaker**: Fast-fail protection during outages
- **Hedging Benefits**: Parallel attempts reduce tail latency
- **Resource Usage**: Controlled retry attempts prevent resource exhaustion

### Rate Limiting
- **Memory Efficient**: Token bucket algorithms with fixed memory usage
- **Distributed Ready**: Redis-backed limits for multi-instance deployments
- **Configurable Burst**: Burst capacity allows for legitimate traffic spikes
- **Per-User Tracking**: Individual limits prevent single-user monopolization

## Monitoring and Observability

### Policy Metrics
- **Retry Attempts**: Success/failure rates by strategy
- **Circuit Breaker State**: Open/closed status and transitions
- **Role Usage**: Active users per role over time
- **Rate Limit Hits**: Throttled requests by limit type

### Audit Logging
```python
# Policy decision logging
logger.info("Policy decision", extra={
    "user_id": user_id,
    "role": user_role,
    "operation": operation,
    "decision": "allowed|denied",
    "reason": "tool_not_permitted|rate_limit_exceeded"
})

# Retry attempt logging
logger.warning("Retry attempt", extra={
    "strategy": strategy_name,
    "attempt": attempt_number,
    "error": str(exception),
    "backoff_delay": delay_seconds
})
```

## Integration Points

### FastAPI Integration
```python
from fastapi import Depends, HTTPException
from src.agent_policies.roles import get_current_user_role

@app.post("/api/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str,
    payload: dict,
    user_role: str = Depends(get_current_user_role)
):
    # Check tool permission
    role_config = role_policies.get_role(user_role)
    if not role_config.can_use_tool(tool_name):
        raise HTTPException(403, f"Tool '{tool_name}' not permitted for role '{user_role}'")

    # Check rate limits
    if not await rate_limiter.check_limits(get_current_user_id()):
        raise HTTPException(429, "Rate limit exceeded")

    # Execute with retry policy
    strategy = retry_policies.get_strategy_for_operation("tool_invoke")
    result = await execute_with_retry(tool_func, strategy, payload)

    return result
```

### Adapter Integration
```python
class LLMAdapter:
    def __init__(self, retry_policies, role_policies):
        self.retry_policies = retry_policies
        self.role_policies = role_policies

    async def generate_with_policies(
        self,
        prompt: str,
        user_role: str,
        options: dict = None
    ) -> str:
        # Get role-specific model config
        role_config = self.role_policies.get_role(user_role)
        model_config = role_config.model

        # Merge with request options
        final_config = {**model_config.dict(), **(options or {})}

        # Get retry strategy
        strategy = self.retry_policies.get_strategy('llm')

        # Execute with retry
        return await self._generate_with_retry(prompt, final_config, strategy)
```

## Testing

### Policy Testing
```python
import pytest
from src.agent_policies.roles import RolePolicies

def test_admin_role_permissions():
    policies = RolePolicies.load_from_file("roles.yaml")

    admin_role = policies.get_role("admin")

    # Test tool permissions
    assert admin_role.can_use_tool("graph.crud")
    assert admin_role.can_use_tool("system.*")
    assert admin_role.can_use_tool("any.tool.name")

    # Test scope permissions
    assert admin_role.has_scope("admin:*")
    assert admin_role.has_scope("models:list")
    assert admin_role.has_scope("tools:invoke")

def test_guest_role_restrictions():
    policies = RolePolicies.load_from_file("roles.yaml")

    guest_role = policies.get_role("guest")

    # Test denied tools
    assert not guest_role.can_use_tool("graph.query")
    assert not guest_role.can_use_tool("system.health")

    # Test allowed tools
    assert guest_role.can_use_tool("catalog.discover")
    assert guest_role.can_use_tool("output.summarize")
```

### Retry Testing
```python
import pytest
from unittest.mock import Mock, patch
from src.agent_policies.retry import RetryPolicies

@pytest.mark.asyncio
async def test_llm_retry_on_timeout():
    policies = RetryPolicies.load_from_file("retry.yaml")
    strategy = policies.get_strategy("llm_standard")

    mock_adapter = Mock()
    mock_adapter.generate.side_effect = [
        TimeoutError("Connection timeout"),
        TimeoutError("Connection timeout"),
        "Success response"
    ]

    with patch('asyncio.sleep'):  # Speed up test
        result = await execute_with_retry(
            mock_adapter.generate,
            strategy,
            "test prompt"
        )

    assert result == "Success response"
    assert mock_adapter.generate.call_count == 3
```

## Future Enhancements

- **Dynamic Policies**: Runtime policy updates via API
- **Context-Aware Rules**: Policies based on request context/attributes
- **Policy Inheritance**: Complex role hierarchies with multiple inheritance
- **Audit Integration**: Detailed policy decision logging and reporting
- **A/B Testing**: Policy experimentation and gradual rollouts
- **Metrics Export**: Prometheus metrics for policy effectiveness
- **Policy Simulation**: Test policy changes before deployment</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_agent_policies.md