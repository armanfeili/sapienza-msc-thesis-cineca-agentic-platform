# UI Test Suite

Comprehensive test suite for the Streamlit UI application.

## Overview

This test suite provides complete coverage of the UI components, state management, API client, views, and integration workflows.

## Test Structure

```
tests/ui/
├── __init__.py                 # Package initialization
├── conftest.py                 # Pytest fixtures and test configuration
├── test_api.py                 # API client tests
├── test_state.py               # State management tests
├── test_components.py          # UI component tests
├── test_views.py               # View/tab tests
├── test_integration.py         # Integration and workflow tests
├── test_app.py                 # Main app and utility tests
└── README.md                   # This file
```

## Test Files

### `conftest.py`
**Pytest fixtures and test configuration**
- `mock_streamlit`: Mock Streamlit components
- `mock_requests`: Mock HTTP requests library
- `sample_token`: Sample Auth0 JWT token
- `sample_health_response`: Sample health check response
- `sample_tools`: Sample tools list
- `sample_agent_session`: Sample agent session
- `sample_job`: Sample job data
- `sample_tenants`: Sample tenants list
- `mock_env_vars`: Mock environment variables

### `test_api.py`
**API client tests (420+ lines, 7 test classes)**
- `TestAPIClient`: Core API client functionality
  - Environment variable loading
  - Request header construction
  - Token retrieval from state
  
- `TestAuth0Integration`: Auth0 authentication
  - Password grant flow (user/admin)
  - Client credentials grant (machine)
  - Token parsing and validation
  - Error handling
  
- `TestHealthEndpoints`: Health check endpoints
  - `/v1/health/live` (text response)
  - `/v1/health/ready` (JSON response)
  - `/v1/health/components` (detailed checks)
  
- `TestToolsEndpoints`: Tools API
  - List tools
  - Get tool details
  - Invoke tools
  
- `TestAgentEndpoints`: Agents API
  - List agent sessions
  - Create sessions
  - Send messages
  - Get run status
  
- `TestJobsEndpoints`: Jobs API
  - List jobs
  - Create jobs
  - Get job details
  - Cancel jobs
  
- `TestTenantsEndpoints`: Multi-tenancy API
  - List tenants
  - Create tenants
  - Get tenant details
  - Update tenants
  - Delete tenants

### `test_state.py`
**State management tests (240+ lines, 5 test classes)**
- `TestToken`: Token dataclass
  - Initialization
  - Field validation
  - Expiry tracking
  
- `TestTokenSet`: Token collection
  - Admin, user, machine tokens
  - Token lifecycle management
  
- `TestUIState`: Main state container
  - Initialization
  - Active identity switching
  - Tenant selection
  - Error tracking
  
- `TestStateFunctions`: State helper functions
  - `get_state()`
  - `set_token()`
  - `get_active_token()`
  - `add_error()`
  - `clear_errors()`
  
- `TestTenantInfo`: Tenant metadata
  - Tenant information storage
  - Tenant selection

### `test_components.py`
**UI component tests (290+ lines, 8 test classes)**
- `TestTokenBadges`: Token status badges
  - Display format
  - Color coding
  - Expiry warnings
  
- `TestHealthCards`: Health check cards
  - Component status display
  - Metric formatting
  
- `TestDataTable`: Data table component
  - Column rendering
  - Data formatting
  - Empty state
  
- `TestJSONDrawer`: JSON viewer
  - Syntax highlighting
  - Expandable sections
  
- `TestConfirmModal`: Confirmation dialogs
  - Modal display
  - Action confirmation
  
- `TestTimeline`: Timeline component
  - Event ordering
  - Timestamp display
  
- `TestToolCard`: Tool display cards
  - Tool metadata
  - Safety indicators
  
- `TestLogPane`: Log viewer
  - Log file reading
  - Line filtering
  - Tail mode

### `test_views.py`
**View/tab tests (350+ lines, 9 test classes)**
- `TestAuthView`: Authentication tab
  - Admin login flow
  - User login flow
  - Machine authentication
  - Logout functionality
  
- `TestDashboardView`: Dashboard tab
  - Health metrics display
  - Component status cards
  - Refresh functionality
  
- `TestExploreView`: NL→Cypher tab
  - Natural language query input
  - Cypher generation
  - Query execution
  
- `TestAgentsView`: Agents tab
  - Session listing
  - Session creation
  - Message sending
  - Copilot-style display
  
- `TestJobsView`: Jobs tab
  - Job listing
  - Job creation
  - Status monitoring
  - Job cancellation
  
- `TestToolsView`: Tools tab
  - Tool registry
  - Tool invocation
  - Parameter input
  
- `TestModelsView`: Models tab
  - LLM model listing
  - Model configuration
  
- `TestTenantsView`: Tenants tab
  - Tenant listing
  - Tenant creation
  - Tenant selection
  
- `TestAdminView`: Admin tab
  - System statistics
  - Admin-only features
  - Access control

### `test_integration.py`
**Integration tests (380+ lines, 3 test classes)**
- `TestUIIntegration`: End-to-end workflows
  - Full authentication flow
  - Dashboard health check flow
  - Tool invocation flow
  - Agent session flow
  - Job lifecycle flow
  
- `TestErrorHandling`: Error scenarios
  - Error tracking
  - API error handling
  - Graceful degradation
  
- `TestMultiTenancy`: Multi-tenant features
  - Tenant selection
  - Tenant switching
  - Isolated operations

### `test_app.py`
**Main app tests (360+ lines, 8 test classes)**
- `TestAppEntry`: App initialization
  - Page configuration
  - Tab structure
  - State initialization
  
- `TestHelpers`: Utility functions
  - Timestamp formatting
  - Duration formatting
  - JSON parsing
  - String truncation
  
- `TestTokenHandling`: Token utilities
  - Expiry checking
  - Scope validation
  
- `TestAPIHelpers`: API utilities
  - Response handling (JSON/text)
  - Error handling
  
- `TestEnvironmentVariables`: Environment setup
  - Required variables
  - Missing variable handling
  
- `TestLogging`: Logging configuration
  - Log file creation
  - Log rotation
  
- `TestErrorRecovery`: Error recovery
  - Graceful degradation
  - API failure handling
  
- `TestDataValidation`: Data validation
  - Job parameters
  - Tool input
  - Tenant data

## Running Tests

### Run all UI tests
```bash
pytest tests/ui/ -v
```

### Run specific test file
```bash
pytest tests/ui/test_api.py -v
```

### Run specific test class
```bash
pytest tests/ui/test_api.py::TestAPIClient -v
```

### Run specific test method
```bash
pytest tests/ui/test_api.py::TestAPIClient::test_get_headers -v
```

### Run with coverage
```bash
pytest tests/ui/ --cov=ui --cov-report=html
```

### Run tests matching pattern
```bash
pytest tests/ui/ -k "test_auth" -v
```

## Test Coverage

The test suite covers:

- ✅ **API Client** (60+ endpoints wrapped)
  - All HTTP methods (GET, POST, PUT, DELETE)
  - Auth0 integration (3 grant types)
  - Response handling (JSON/text)
  - Error handling

- ✅ **State Management**
  - Token storage and retrieval
  - Active identity switching
  - Tenant selection
  - Error tracking

- ✅ **UI Components** (8 components)
  - Token badges
  - Health cards
  - Data tables
  - JSON viewer
  - Confirmation modals
  - Timeline
  - Tool cards
  - Log pane

- ✅ **Views** (9 tabs)
  - Authentication
  - Dashboard
  - Explore (NL→Cypher)
  - Agents (Copilot-style)
  - Jobs
  - Tools
  - Models
  - Tenants
  - Admin

- ✅ **Integration Workflows**
  - End-to-end authentication
  - Multi-step operations
  - Error scenarios
  - Multi-tenancy

- ✅ **Utilities**
  - Environment variables
  - Logging
  - Data validation
  - Error recovery

## Mocking Strategy

### Streamlit Components
All Streamlit components are mocked to avoid GUI dependencies:
```python
@patch("streamlit.button")
@patch("streamlit.text_input")
def test_example(mock_text_input, mock_button):
    mock_text_input.return_value = "test input"
    mock_button.return_value = True
    # Test logic
```

### HTTP Requests
All HTTP requests are mocked to avoid network dependencies:
```python
@patch("requests.get")
def test_example(mock_get):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}
    mock_get.return_value = mock_response
    # Test logic
```

### Session State
Session state is mocked using a dictionary:
```python
@patch("streamlit.session_state", new_callable=dict)
def test_example(mock_session_state):
    state = UIState()
    mock_session_state["ui_state"] = state
    # Test logic
```

## Test Data

### Sample Token (JWT)
```python
{
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 3600
}
```

### Sample Health Response
```python
{
    "status": "healthy",
    "checks": {
        "app": {"ok": True, "status": "ok"},
        "postgres": {"ok": True, "status": "ok"},
        "redis": {"ok": True, "status": "ok"}
    }
}
```

### Sample Tool
```python
{
    "id": "system.health",
    "name": "System Health",
    "description": "Check system health",
    "safe": True,
    "schema": {...}
}
```

### Sample Agent Session
```python
{
    "session_id": "sess-123",
    "agent_type": "researcher",
    "status": "active",
    "created_at": "2024-01-15T10:00:00Z"
}
```

### Sample Job
```python
{
    "id": "job-123",
    "type": "demo",
    "status": "running",
    "progress": 0.5,
    "created_at": "2024-01-15T10:00:00Z"
}
```

## CI/CD Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# .github/workflows/ui-tests.yml
name: UI Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ui/ -v --cov=ui
```

## Debugging Tests

### Run with verbose output
```bash
pytest tests/ui/ -vv
```

### Show print statements
```bash
pytest tests/ui/ -s
```

### Drop into debugger on failure
```bash
pytest tests/ui/ --pdb
```

### Run last failed tests
```bash
pytest tests/ui/ --lf
```

## Best Practices

1. **Isolation**: Each test is independent and can run in any order
2. **Mocking**: All external dependencies (Streamlit, HTTP, filesystem) are mocked
3. **Fixtures**: Reusable test data and setup via pytest fixtures
4. **Assertions**: Clear, specific assertions with helpful failure messages
5. **Coverage**: Aim for >80% code coverage
6. **Speed**: Tests run quickly (<5 seconds total) due to mocking
7. **Documentation**: Each test class and method has a docstring

## Future Enhancements

- [ ] Add performance benchmarks
- [ ] Add visual regression tests (screenshot comparison)
- [ ] Add accessibility tests
- [ ] Add load tests
- [ ] Add security tests
- [ ] Increase coverage to 95%+

## Contributing

When adding new UI features, please:
1. Add corresponding tests to the appropriate test file
2. Update fixtures in `conftest.py` if needed
3. Ensure all tests pass: `pytest tests/ui/ -v`
4. Maintain test coverage above 80%

## License

Same as main project.
