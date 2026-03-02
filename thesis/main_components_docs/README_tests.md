# README_Cineca-Agentic-Platform_tests.md

## Cineca Agentic Platform Test Suite

### Overview

The Cineca Agentic Platform maintains a comprehensive, multi-layered test suite designed to ensure reliability, security, and performance across all system components. The test suite balances unit correctness, integration fidelity, end-to-end behavior validation, and security posture assessment.

### Test Philosophy

The test suite follows these core principles:

- **Fast and Isolated**: Tests run quickly and independently
- **Behavior-Focused**: Assert on observable behavior, not implementation details
- **Safety-First**: Security and dangerous operation detection prioritized
- **Realistic**: Use fakes for speed, real services for integration confidence
- **Comprehensive**: Cover happy paths, error cases, and edge conditions

### Test Categories

#### Unit Tests (`tests/unit/`)
**Purpose**: Validate individual components in isolation
**Scope**: Pure Python logic, no external dependencies
**Requirements**: Must complete in <1 second each
**Markers**: `@pytest.mark.unit`
**Count**: 60+ test files

Key unit test areas:
- Intent classification and routing logic
- PII scrubbing and data sanitization
- Archive service operations
- Authentication and authorization helpers
- Model validation and normalization
- Tool discovery and invocation
- Health check components
- Session management
- Rate limiting logic
- ETL transformations

#### Integration Tests (`tests/integration/`)
**Purpose**: Validate component interactions with realistic dependencies
**Scope**: Touch adapters/services with fakes or ephemeral resources
**Markers**: `@pytest.mark.integration`
**Count**: 70+ test files

Key integration areas:
- Database operations (PostgreSQL, Redis, Memgraph)
- API contract validation
- Authentication flows
- Batch operations and bulk processing
- Export/import functionality
- Job lifecycle management
- Tool execution pipelines
- Session state persistence
- Tenant isolation
- Model instance management

#### End-to-End Tests (`tests/e2e/`)
**Purpose**: Validate complete user journeys through HTTP interfaces
**Scope**: Hit actual HTTP API endpoints
**Markers**: `@pytest.mark.e2e`
**Count**: 5+ test files

Key e2e validations:
- Health check endpoints (`/health/live`, `/health/ready`, `/health/startup`)
- Authentication flows
- Basic tool invocations
- MCP protocol compliance
- API response consistency

#### Security Tests (`tests/security/`)
**Purpose**: Validate security controls and threat mitigation
**Scope**: Authentication, authorization, input validation, output guards
**Markers**: `@pytest.mark.security`
**Count**: 15+ test files

Key security validations:
- Authentication requirements (401 responses)
- Authorization enforcement (403 responses)
- Intent filtering for dangerous operations
- PII detection and redaction
- Rate limiting effectiveness
- Input sanitization
- Token validation
- RBAC policy enforcement

#### Performance Tests (`tests/performance/`)
**Purpose**: Ensure system meets latency and throughput requirements
**Scope**: Light latency budgets and performance regressions
**Markers**: `@pytest.mark.performance`
**Requirements**: Skipped by default, enabled with `--runslow`
**Count**: 5+ test files

Key performance validations:
- Health probe response times (<50ms P99)
- API endpoint latency budgets
- Memory usage patterns
- Concurrent request handling

### Test Infrastructure

#### Configuration (`tests/conftest.py`)

The global test configuration provides:

**Event Loop Management**
- Session-scoped asyncio event loop for async tests
- Automatic cleanup and isolation

**HTTP Clients**
- `app_client`: Synchronous FastAPI TestClient (no network)
- `async_client`: Async HTTPX client with ASGI transport and lifespan
- `client`: Synchronous TestClient wrapper
- `client_admin`, `client_user`, `client_m2m`: Pre-authenticated clients

**Authentication Fixtures**
- `mint_token`: JWT token generation for testing
- `bearer_headers`: Admin authentication headers
- `configure_oidc`: OIDC/JWKS setup for auth tests

**Database Fixtures**
- `db_engine`: SQLAlchemy engine for PostgreSQL tests
- `db_session`: Database session with transaction management
- `fake_redis`: In-memory Redis stub
- `use_fake_memgraph`: Lightweight Memgraph adapter replacement

**Service Mocks**
- `_DeterministicLLMStub`: Predictable LLM responses for testing
- `llm_stub`: Injects deterministic LLM behavior

**Utility Fixtures**
- `settings_patch`: Dynamic configuration patching
- `tmp_backup_dir`: Isolated temporary directories
- `sample_data`: Synthetic graph data for ETL testing

#### Test Data (`tests/fixtures/`)

**Fake Adapters**
- `fake_memgraph.py`: In-memory Memgraph implementation
- `mock_memgraph.py`: Alternative mocking approach

**Sample Data**
- `sample_data.py`: Synthetic nodes and relationships
- `oidc.py`: OIDC key generation and JWKS management

#### Markers and Selection

```python
# Run specific test categories
pytest -m "unit"           # Fast unit tests only
pytest -m "integration"    # Component integration
pytest -m "e2e"            # End-to-end HTTP tests
pytest -m "security"       # Security validation
pytest -m "performance"    # Performance benchmarks

# Combined selections
pytest -m "unit or integration"
pytest -m "e2e and not performance"
```

### Running Tests

#### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run full suite
pytest -q

# Run with verbose output
pytest -v

# Run specific categories
pytest -m "unit" -q
pytest -m "integration" -q
pytest -m "e2e" -q
```

#### Docker Environment

```bash
# Start full stack
docker compose up -d --build

# Run tests in container
docker compose run --rm app pytest -q

# Run specific test
docker compose run --rm app pytest tests/unit/test_intent_classifier.py -v
```

#### Real Services Testing

```bash
# Start external services
docker compose up -d postgres redis memgraph

# Run integration tests against real databases
export MG_HOST=localhost
export REDIS_URL=redis://localhost:6379/0
pytest -m "integration" --run-real-memgraph
```

#### E2E Testing

```bash
# Test against running server
export BASE_URL=http://localhost:8000
pytest -m "e2e" --live

# Or use in-process testing (default)
pytest -m "e2e"
```

### Test Execution Options

#### Output and Debugging

```bash
# Show durations for slowest tests
pytest --durations=10

# Capture print statements
pytest -s

# Stop on first failure
pytest -x

# Run failed tests first
pytest --lf

# Verbose single test
pytest -vv tests/unit/test_intent_classifier.py::TestIntentModeEnum::test_mode_values_are_strings
```

#### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Parallel by category
pytest -m "unit" -n 4
pytest -m "integration" -n 2
```

#### Coverage Reporting

```bash
# Generate coverage report
pip install coverage
coverage run -m pytest -q
coverage html
open htmlcov/index.html

# CI coverage command
pytest --maxfail=1 --disable-warnings -q \
  --cov=src --cov-report=term-missing:skip-covered
```

### Key Test Components

#### Intent Classifier Tests

**File**: `tests/unit/test_intent_classifier.py`
**Coverage**: Intent classification logic, safety detection, routing decisions

Critical validations:
- Chat mode detection (prevents 309s response times)
- Dangerous operation blocking
- Pattern matching accuracy
- Confidence threshold enforcement
- Principal permission checking

#### Authentication Tests

**File**: `tests/security/test_auth.py`
**Coverage**: Login flows, token validation, protected endpoints

Security validations:
- Public endpoints remain accessible
- Protected endpoints require authentication
- Invalid tokens are rejected
- Token-based access works correctly

#### Health Check Tests

**File**: `tests/e2e/test_end_to_end_health.py`
**Coverage**: Health endpoints, readiness probes, startup checks

Validations:
- Liveness endpoint returns 200
- Readiness includes dependency status
- Detailed checks provide component health
- JSON serialization works correctly

#### Database Integration Tests

**Files**: `tests/integration/test_*.py`
**Coverage**: PostgreSQL, Redis, Memgraph interactions

Integration validations:
- Connection handling
- Transaction management
- Query execution
- Data persistence
- Error recovery

#### Fake Memgraph Implementation

**File**: `tests/fixtures/fake_memgraph.py`
**Purpose**: Fast, deterministic database testing

Capabilities:
- Node and relationship CRUD operations
- Cypher query pattern recognition
- Bulk operations support
- Snapshot import/export
- Health check simulation

### Test Data Management

#### Sample Data Generation

```python
# Synthetic graph data for ETL testing
sample_nodes = [
    {"id": "1", "labels": ["User"], "properties": {"name": "Alice"}},
    {"id": "2", "labels": ["Company"], "properties": {"name": "ACME Corp"}},
]

sample_relationships = [
    {"start": "1", "end": "2", "type": "WORKS_AT", "properties": {"since": 2020}},
]
```

#### OIDC Test Infrastructure

```python
# RSA keypair generation for JWT testing
@pytest.fixture(scope="session")
def oidc_keys(tmp_path_factory):
    pair = generate_rsa_keypair()
    jwks_path = tmp_path_factory.mktemp("jwks") / "jwks.json"
    write_jwks(jwks_path, pair["public_jwk"])
    return {
        "kid": pair["kid"],
        "private_pem": pair["private_pem"],
        "public": pair["public_jwk"],
        "jwks_path": jwks_path,
        "issuer": "https://test-issuer.local/",
        "audience": "cineca-api",
    }
```

### Continuous Integration

#### CI Pipeline Integration

```yaml
# .github/workflows/test.yml
- name: Run Unit Tests
  run: pytest -m "unit" --cov=src --cov-report=xml

- name: Run Integration Tests
  run: |
    docker compose up -d postgres redis
    pytest -m "integration"

- name: Run Security Tests
  run: pytest -m "security"

- name: Run E2E Tests
  run: |
    docker compose up -d
    pytest -m "e2e" --live
```

#### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-unit
        name: Unit Tests
        entry: pytest
        args: [-m, unit, --tb=short]
        language: system
        pass_filenames: false
```

### Test Maintenance

#### Adding New Tests

1. **Choose appropriate category**:
   - Unit: Pure logic, no I/O
   - Integration: Component interaction
   - E2E: HTTP API validation
   - Security: Auth/authz concerns

2. **Use proper markers**:
   ```python
   @pytest.mark.unit
   def test_my_feature():
       pass
   ```

3. **Leverage fixtures**:
   ```python
   def test_with_db(db_session):
       # Database test
       pass

   def test_with_auth(client_admin):
       # Authenticated API test
       pass
   ```

4. **Follow naming conventions**:
   - `test_*` for test functions
   - `Test*` for test classes
   - Descriptive names explaining behavior

#### Test Isolation

- **Database**: Use transactions or unique namespaces
- **Redis**: Ephemeral keys with prefixes
- **Files**: Temporary directories via `tmp_path`
- **State**: Reset global state between tests

#### Flaky Test Prevention

- **Time-dependent**: Use `freezegun` for time mocking
- **Async**: Proper event loop management
- **Network**: Use fakes for external services
- **Race conditions**: Avoid shared state

### Performance Benchmarking

#### Latency Budgets

```python
@pytest.mark.performance
def test_health_probe_latency():
    start = time.time()
    response = client.get("/health/live")
    duration = time.time() - start
    
    assert response.status_code == 200
    assert duration < 0.050  # 50ms P99 budget
```

#### Load Testing

```python
@pytest.mark.performance
def test_concurrent_requests():
    import asyncio
    
    async def make_request():
        async with httpx.AsyncClient() as client:
            return await client.get("http://localhost:8000/health")
    
    # Test 100 concurrent requests
    tasks = [make_request() for _ in range(100)]
    results = asyncio.run(asyncio.gather(*tasks))
    
    assert all(r.status_code == 200 for r in results)
```

### Security Testing Strategy

#### Authentication Testing

- **Token Validation**: Invalid, expired, malformed tokens
- **Grant Types**: Password, client-credentials, refresh flows
- **Scopes**: Insufficient permissions, scope validation
- **Multi-tenancy**: Tenant isolation enforcement

#### Authorization Testing

- **RBAC**: Role-based access control
- **Permissions**: Fine-grained permission checking
- **Principal Context**: User identity propagation
- **Policy Evaluation**: Dynamic policy enforcement

#### Input Validation

- **Intent Filtering**: Dangerous operation detection
- **PII Scrubbing**: Sensitive data removal
- **SQL Injection**: Cypher query sanitization
- **XSS Prevention**: Output encoding validation

#### Output Guards

- **Content Filtering**: Unsafe content detection
- **Data Leakage**: Sensitive information redaction
- **Format Validation**: Response structure compliance
- **Error Handling**: Secure error message exposure

### Troubleshooting Common Issues

#### Database Connection Failures

```bash
# Check Docker services
docker compose ps

# Verify connections
docker compose exec postgres pg_isready -U cineca_user -d cineca_platform
docker compose exec redis redis-cli ping

# Reset databases
docker compose down -v
docker compose up -d postgres redis
```

#### Authentication Test Failures

```bash
# Check OIDC configuration
export OIDC_ISSUER=https://test-issuer.local/
export OIDC_AUDIENCE=cineca-api

# Verify token generation
pytest tests/security/test_auth.py::test_login_flow_and_access_me -v -s
```

#### Performance Regressions

```bash
# Profile slow tests
pytest --durations=10

# Enable performance markers
pytest -m "performance" --runslow

# Memory profiling
pip install memory-profiler
mprof run pytest tests/performance/ -m "performance"
```

#### Flaky Test Debugging

```bash
# Run with retries
pip install pytest-rerunfailures
pytest --reruns 3 --reruns-delay 1

# Debug async issues
pytest -s --tb=long tests/integration/test_async_operation.py
```

### Test Coverage Goals

#### Unit Tests: 90%+
- Core business logic
- Utility functions
- Data transformations
- Validation logic

#### Integration Tests: 85%+
- API endpoints
- Database operations
- External service interactions
- Component orchestration

#### Security Tests: 95%+
- Authentication flows
- Authorization checks
- Input validation
- Output sanitization

#### E2E Tests: 80%+
- Critical user journeys
- API contracts
- Error scenarios
- Performance validation

### Future Enhancements

#### Test Automation Improvements

- **Property-Based Testing**: Use Hypothesis for edge case generation
- **Contract Testing**: API contract validation with Pact
- **Visual Regression**: UI component testing
- **Chaos Engineering**: Fault injection testing

#### Performance Testing Expansion

- **Load Testing**: k6 or Locust for high-throughput scenarios
- **Stress Testing**: Resource limit validation
- **Scalability Testing**: Horizontal scaling validation
- **Memory Leak Detection**: Long-running process monitoring

#### Security Testing Enhancements

- **Fuzz Testing**: Input fuzzing for robustness
- **Penetration Testing**: Automated security scanning
- **Compliance Testing**: Regulatory requirement validation
- **Supply Chain Security**: Dependency vulnerability scanning

#### Observability Integration

- **Test Metrics**: Prometheus metrics for test execution
- **Distributed Tracing**: Request tracing through test scenarios
- **Log Aggregation**: Centralized test log collection
- **Dashboard Integration**: Test result visualization

### Contributing to Tests

#### Code Review Checklist

- [ ] Appropriate test category (unit/integration/e2e/security)
- [ ] Proper pytest markers
- [ ] Fixture usage for isolation
- [ ] Descriptive test names
- [ ] Edge case coverage
- [ ] Performance considerations
- [ ] Security implications reviewed

#### Test Documentation

- [ ] Test purpose clearly documented
- [ ] Setup requirements specified
- [ ] Expected behavior described
- [ ] Failure scenarios covered
- [ ] Maintenance notes included

### Support and Resources

#### Getting Help

- **Test Failures**: Check CI logs and error messages
- **Fixture Issues**: Review `conftest.py` configuration
- **Performance Problems**: Use `--durations` to identify slow tests
- **Coverage Gaps**: Run coverage reports to find untested code

#### Key Files Reference

- `tests/README.md`: Main test documentation
- `tests/conftest.py`: Global test configuration
- `tests/fixtures/`: Test data and mocks
- `pytest.ini`: Pytest configuration
- `.pre-commit-config.yaml`: Quality gates

---

*This comprehensive README covers the Cineca Agentic Platform's test suite architecture, execution, maintenance, and best practices. For the latest updates, refer to the test source code and CI pipeline configurations.*