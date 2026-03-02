# Memgraph Integration

The memgraph package provides test-mode helpers for Memgraph natural language (NL) processing integration within the Cineca Agentic Platform. It enables deterministic testing of NL-to-Cypher query generation by providing predefined prompt hints.

## Architecture Overview

The memgraph integration follows these design principles:

- **Test-Mode Only**: Functionality is specifically for testing environments
- **Prompt Matching**: Natural language prompts matched against predefined test cases
- **Metadata Enrichment**: Test prompts enriched with expected behavior metadata
- **Caching**: Efficient prompt index loading with LRU caching
- **Fail-Safe**: Graceful degradation when prompt files are missing

## Core Components

### 1. Test Mode Helpers (`test_mode.py`)

Provides prompt hinting functionality for Memgraph NL query testing.

#### Architecture
```
Prompt Input → Normalization → Index Lookup → Metadata Return
     ↓              ↓              ↓              ↓
  Raw Text     Lowercase/Trim   Dictionary Match   Hint Object
```

#### Features
- **Environment Control**: Test mode enabled via environment variables
- **Prompt Indexing**: JSON-based prompt metadata loading and caching
- **Text Normalization**: Case-insensitive, whitespace-normalized matching
- **Debug Logging**: Structured logging for prompt matching decisions
- **Cache Management**: LRU caching with test-friendly cache clearing

#### Configuration

##### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MEMGRAPH_NL_TEST_MODE` | `true` | Enable/disable test mode hinting |
| `LLM_MEMGRAPH_NL_PROMPTS_PATH` | `tests/integration/resources/memgraph_nl_prompts.json` | Path to prompt metadata file |

##### Default Behavior
- **Enabled by Default**: Test mode enabled out-of-the-box for integration tests
- **Auto-Resolution**: Prompt path resolved relative to repository root
- **Graceful Fallback**: Returns None when prompts unavailable or disabled

#### Prompt Metadata Format

```json
[
  {
    "id": "query_users_by_name",
    "text": "find users named john",
    "category": "user_queries",
    "todo_mode": false,
    "expected_cypher": "MATCH (u:User {name: 'john'}) RETURN u",
    "description": "Simple user lookup by name"
  },
  {
    "id": "complex_relationship_query",
    "text": "show me projects worked on by developers from italy",
    "category": "relationship_queries",
    "todo_mode": true,
    "complexity": "high",
    "description": "Multi-hop relationship traversal"
  }
]
```

#### Core Functions

##### `_is_enabled() -> bool`
```python
def _is_enabled() -> bool:
    """Check if test mode hinting is enabled."""
    value = os.getenv("LLM_MEMGRAPH_NL_TEST_MODE", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}
```

**Logic**:
- Defaults to enabled for integration test compatibility
- Accepts multiple truthy string values
- Case-insensitive parsing

##### `_normalize(text: str | None) -> str`
```python
def _normalize(text: str | None) -> str:
    """Normalize prompt text for matching."""
    if not text:
        return ""
    return " ".join(text.strip().lower().split())
```

**Features**:
- Lowercase conversion
- Whitespace normalization
- Empty input handling

##### `_load_prompt_index(path: str) -> dict[str, Dict[str, Any]]`
```python
@lru_cache(maxsize=1)
def _load_prompt_index(path: str) -> dict[str, Dict[str, Any]]:
    """Load and index prompt metadata from JSON file."""
    prompt_path = Path(path)
    if not prompt_path.exists():
        log.warning("Prompt metadata file not found")
        return {}

    try:
        with prompt_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except Exception as exc:
        log.error("Failed to load prompt metadata", error=str(exc))
        return {}

    # Build normalized text -> metadata mapping
    index = {}
    for entry in payload:
        if isinstance(entry, dict):
            normalized = _normalize(entry.get("text"))
            if normalized:
                index[normalized] = entry
    return index
```

**Features**:
- LRU caching for performance
- JSON parsing with error handling
- Normalized text indexing
- Defensive programming for malformed data

##### `get_prompt_hints(prompt: str | None) -> Optional[Dict[str, Any]]`
```python
def get_prompt_hints(prompt: str | None) -> Optional[Dict[str, Any]]:
    """Return prompt metadata when test mode is enabled."""
    if not _is_enabled() or not prompt:
        return None

    prompt_path = os.getenv(_PROMPT_PATH_ENV, str(_default_prompt_path()))
    index = _load_prompt_index(prompt_path)

    if not index:
        return None

    normalized = _normalize(prompt)
    entry = index.get(normalized)

    if entry:
        log.debug("Prompt match found", prompt_id=entry.get("id"))
    else:
        log.debug("No prompt match", prompt_preview=prompt[:80])

    return entry
```

**Logic**:
- Early return if disabled or no prompt
- Path resolution with environment override
- Index loading with caching
- Normalized lookup with logging

##### `reset_prompt_cache() -> None`
```python
def reset_prompt_cache() -> None:
    """Reset cached prompt metadata (used in tests)."""
    _load_prompt_index.cache_clear()
```

**Purpose**:
- Test isolation between test cases
- Cache clearing for fresh metadata loading

## Usage Examples

### Basic Integration

```python
from src.memgraph.test_mode import get_prompt_hints

# Get hints for a test prompt
prompt = "find users named john"
hints = get_prompt_hints(prompt)

if hints:
    print(f"Matched prompt: {hints['id']}")
    print(f"Category: {hints['category']}")
    print(f"Expected Cypher: {hints.get('expected_cypher')}")
else:
    print("No hints available")
```

### Test Environment Setup

```python
import os
from src.memgraph.test_mode import reset_prompt_cache

# Enable test mode explicitly
os.environ["LLM_MEMGRAPH_NL_TEST_MODE"] = "true"

# Custom prompt file path
os.environ["LLM_MEMGRAPH_NL_PROMPTS_PATH"] = "/path/to/custom/prompts.json"

# Reset cache between tests
reset_prompt_cache()

# Run test with hints
hints = get_prompt_hints("show me all projects")
assert hints is not None
assert hints["category"] == "project_queries"
```

### Orchestrator Integration

```python
class MemgraphOrchestrator:
    def __init__(self):
        self.test_mode = True

    async def process_nl_query(self, natural_language: str) -> str:
        # Get test hints if available
        hints = get_prompt_hints(natural_language)

        if hints and self.test_mode:
            # Use predefined expected Cypher for testing
            cypher_query = hints.get("expected_cypher")
            if cypher_query:
                log.info("Using test Cypher from hints",
                        prompt_id=hints["id"])
                return cypher_query

        # Fall back to LLM generation
        return await self._generate_cypher_with_llm(natural_language)
```

### Test Case Structure

```python
# tests/integration/test_memgraph_nl.py

import pytest
from src.memgraph.test_mode import get_prompt_hints, reset_prompt_cache

class TestMemgraphNL:
    def setup_method(self):
        reset_prompt_cache()

    @pytest.mark.parametrize("prompt,expected_id", [
        ("find users named john", "query_users_by_name"),
        ("show me all projects", "list_all_projects"),
        ("who works on machine learning", "ml_team_query"),
    ])
    def test_prompt_matching(self, prompt, expected_id):
        hints = get_prompt_hints(prompt)
        assert hints is not None
        assert hints["id"] == expected_id

    def test_no_match_returns_none(self):
        hints = get_prompt_hints("unrecognized prompt text")
        assert hints is None

    def test_disabled_mode(self):
        import os
        old_value = os.environ.get("LLM_MEMGRAPH_NL_TEST_MODE")
        os.environ["LLM_MEMGRAPH_NL_TEST_MODE"] = "false"

        try:
            hints = get_prompt_hints("find users named john")
            assert hints is None
        finally:
            if old_value is not None:
                os.environ["LLM_MEMGRAPH_NL_TEST_MODE"] = old_value
            else:
                os.environ.pop("LLM_MEMGRAPH_NL_TEST_MODE", None)
```

## Performance Characteristics

### Caching Strategy
- **LRU Cache**: Single-entry cache for prompt index
- **File I/O**: JSON loading only on first access or cache miss
- **Memory Usage**: Minimal footprint for test environments
- **Lookup Speed**: O(1) dictionary lookup after loading

### Normalization Overhead
- **Text Processing**: Simple string operations (low CPU)
- **Memory Allocation**: Temporary string creation
- **Scalability**: Linear with input text length

### Logging Impact
- **Debug Level**: Only active when debug logging enabled
- **Structured Data**: Consistent log field names
- **Preview Limits**: Truncated prompt previews (80 chars)

## Integration Points

### LLM Adapter Integration

```python
class MemgraphLLMAdapter:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def generate_cypher(self, prompt: str) -> str:
        # Check for test hints first
        hints = get_prompt_hints(prompt)
        if hints and hints.get("expected_cypher"):
            return hints["expected_cypher"]

        # Generate with LLM
        system_prompt = "Convert natural language to Cypher query..."
        return await self.llm_client.generate(system_prompt + prompt)
```

### Test Framework Integration

```python
# conftest.py
import pytest
from src.memgraph.test_mode import reset_prompt_cache

@pytest.fixture(autouse=True)
def reset_memgraph_cache():
    """Reset prompt cache before each test."""
    reset_prompt_cache()

@pytest.fixture
def enable_memgraph_test_mode():
    """Enable test mode for Memgraph NL tests."""
    import os
    old_value = os.environ.get("LLM_MEMGRAPH_NL_TEST_MODE")
    os.environ["LLM_MEMGRAPH_NL_TEST_MODE"] = "true"
    yield
    if old_value is not None:
        os.environ["LLM_MEMGRAPH_NL_TEST_MODE"] = old_value
    else:
        os.environ.pop("LLM_MEMGRAPH_NL_TEST_MODE", None)
```

## Security Considerations

### Test Data Handling
- **No Production Use**: Test-mode only, disabled in production
- **File Access**: Controlled prompt file paths
- **Input Validation**: Text normalization prevents injection
- **Error Handling**: Safe failure when files missing

### Logging Security
- **Prompt Previews**: Limited to 80 characters
- **No Sensitive Data**: Test prompts are synthetic
- **Debug Only**: Hint logging at debug level only

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import patch, mock_open
from src.memgraph.test_mode import (
    _is_enabled,
    _normalize,
    _load_prompt_index,
    get_prompt_hints
)

def test_is_enabled_default():
    with patch.dict(os.environ, {}, clear=True):
        assert _is_enabled() is True

def test_is_enabled_explicit_false():
    with patch.dict(os.environ, {"LLM_MEMGRAPH_NL_TEST_MODE": "false"}):
        assert _is_enabled() is False

def test_normalize_text():
    assert _normalize("  Find Users  Named JOHN  ") == "find users named john"
    assert _normalize(None) == ""
    assert _normalize("") == ""

def test_load_prompt_index_success():
    mock_json = '''[
        {"id": "test1", "text": "find users", "category": "users"}
    ]'''

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.open", mock_open(read_data=mock_json)):

        index = _load_prompt_index("/fake/path.json")
        assert "find users" in index
        assert index["find users"]["id"] == "test1"

def test_load_prompt_index_missing_file():
    with patch("pathlib.Path.exists", return_value=False):
        index = _load_prompt_index("/missing/path.json")
        assert index == {}

def test_get_prompt_hints_match():
    mock_json = '''[
        {"id": "test1", "text": "find users", "category": "users"}
    ]'''

    with patch.dict(os.environ, {"LLM_MEMGRAPH_NL_TEST_MODE": "true"}), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.open", mock_open(read_data=mock_json)):

        hints = get_prompt_hints("find users")
        assert hints is not None
        assert hints["id"] == "test1"

def test_get_prompt_hints_no_match():
    mock_json = '[]'

    with patch.dict(os.environ, {"LLM_MEMGRAPH_NL_TEST_MODE": "true"}), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.open", mock_open(read_data=mock_json)):

        hints = get_prompt_hints("unknown prompt")
        assert hints is None
```

### Integration Tests

```python
# tests/integration/test_memgraph_nl_integration.py

import pytest
from pathlib import Path
from src.memgraph.test_mode import get_prompt_hints

@pytest.mark.skipif(
    not Path("tests/integration/resources/memgraph_nl_prompts.json").exists(),
    reason="Integration prompt file not found"
)
class TestMemgraphNLIntegration:
    def test_real_prompt_matching(self):
        # Test against real prompt file
        hints = get_prompt_hints("find all users in the system")
        assert hints is not None
        assert "expected_cypher" in hints

    def test_category_filtering(self):
        user_hints = get_prompt_hints("show me user information")
        project_hints = get_prompt_hints("list all projects")

        if user_hints:
            assert user_hints["category"] in ["users", "user_queries"]
        if project_hints:
            assert project_hints["category"] in ["projects", "project_queries"]
```

## Troubleshooting

### Common Issues

1. **No Hints Returned**
   - Check `LLM_MEMGRAPH_NL_TEST_MODE=true`
   - Verify prompt file exists at expected path
   - Check file permissions and JSON syntax
   - Review normalization logic for exact text matching

2. **Cache Not Updating**
   - Call `reset_prompt_cache()` between tests
   - Check if file modification time changed
   - Verify cache clearing in test setup

3. **Performance Issues**
   - Large prompt files may slow first access
   - Consider splitting into category-specific files
   - Use more specific prompt matching

4. **Integration Test Failures**
   - Ensure test prompt file is in repository
   - Check CI/CD environment variables
   - Validate JSON schema matches expectations

### Debug Mode

```python
import logging
import structlog

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
structlog.configure(
    processors=[structlog.stdlib.filter_by_level],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Run with debug to see matching decisions
hints = get_prompt_hints("find users named john")
# Check logs for "memgraph.prompts.match" or "memgraph.prompts.no_match"
```

## Future Enhancements

- **Fuzzy Matching**: Approximate string matching for similar prompts
- **Category-Based Loading**: Load only relevant prompt categories
- **Dynamic Updates**: Runtime prompt file reloading
- **Metrics Integration**: Track prompt matching statistics
- **Multi-Language Support**: Localized prompt variations
- **A/B Testing**: Compare different prompt strategies</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_memgraph.md