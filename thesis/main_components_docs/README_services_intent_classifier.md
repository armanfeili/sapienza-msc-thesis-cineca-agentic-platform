# README_services_intent_classifier.md

## Intent Classifier Service

### Overview

The `intent_classifier.py` module is a core component of the Cineca Agentic Platform, providing lightweight, heuristic-based classification of user prompts into operational modes. This service enables the orchestrator to route incoming requests to appropriate handlers based on the inferred intent, ensuring safe and efficient processing of user interactions.

### Purpose and Scope

The Intent Classifier serves as the first line of defense and routing logic in the platform's request processing pipeline. Its primary responsibilities include:

- **Intent Detection**: Analyzing user prompts to determine operational intent
- **Safety Classification**: Identifying potentially dangerous or destructive operations
- **Permission Checking**: Integrating with RBAC to validate user privileges
- **Routing Guidance**: Providing confidence scores for orchestrator decision-making
- **Fallback Handling**: Graceful degradation when classification is uncertain

The classifier operates on a priority-based system, checking patterns from most critical (dangerous operations) to least critical (general chat), ensuring safety-first processing.

### Architecture

#### Core Design Principles

1. **Lightweight and Fast**: Uses regex-based pattern matching for O(1) performance
2. **Safety-First**: Dangerous patterns checked before all others
3. **Configurable**: Thresholds and patterns easily adjustable
4. **Observable**: Comprehensive logging and metrics integration
5. **Extensible**: Pattern categories can be added without code changes

#### Key Components

- **IntentMode Enum**: Defines supported operational modes
- **PatternCategory Classes**: Organized regex patterns for each intent type
- **IntentClassification Dataclass**: Structured result with metadata
- **Classification Engine**: Priority-based matching algorithm
- **Helper Functions**: Quick-check utilities for common scenarios

#### Data Flow

```
User Prompt → Normalization → Catalog Check → Pattern Matching → Conversational Fallback → Default Classification → Result
```

### Intent Modes

The classifier supports five distinct operational modes:

#### 1. CHAT Mode
**Purpose**: Handle general conversation, greetings, and meta-questions
**Confidence Threshold**: 0.60 for routing
**Examples**:
- "Hello, how are you?"
- "What is your name?"
- "Can you introduce yourself?"

#### 2. GRAPH Mode
**Purpose**: Process Memgraph/Cypher database queries and graph operations
**Confidence Threshold**: 0.80 for routing
**Examples**:
- "MATCH (n:Blast) RETURN n LIMIT 10"
- "Show neighbors of node X"
- "Find shortest path between A and B"

#### 3. SECURITY Mode
**Purpose**: Handle permission, access control, and RBAC questions
**Confidence Threshold**: 0.75 for routing
**Examples**:
- "What permissions do I have?"
- "Can I run admin operations?"
- "What is my role?"

#### 4. ADMIN Mode
**Purpose**: Administrative operations requiring elevated privileges
**Confidence Threshold**: 0.70 for routing
**Requires Admin**: Yes
**Examples**:
- "CREATE INDEX ON :Blast(name)"
- "MERGE (n:File {name: 'test'})"
- "DROP CONSTRAINT ON (n:Blast)"

#### 5. DANGEROUS Mode
**Purpose**: Heavy, destructive, or unbounded operations
**Confidence Threshold**: 0.70 for routing
**Requires Admin**: Yes
**Examples**:
- "DELETE DETACH (n) WHERE true"
- "DROP DATABASE"
- "Export all user data"

### Classification Process

#### Priority Order

The classification follows a strict priority hierarchy:

1. **Catalog Match** (0.95 confidence): Pre-classified prompts from catalog
2. **Dangerous Patterns** (0.90 confidence): Safety-critical destructive operations
3. **Admin Patterns** (0.85 confidence): Schema modifications and writes
4. **Security Patterns** (0.85 confidence): Permission and access queries
5. **Graph Patterns** (0.85 confidence): Database and graph operations
6. **Chat Patterns** (0.95 confidence): Exact conversational matches
7. **Conversational Signals** (0.85 confidence): Fallback detection
8. **Default Fallback** (0.60 confidence): Chat mode with low confidence

#### Pattern Matching Algorithm

```python
def classify_intent(goal, catalog_match=None, principal=None):
    # Normalize input text
    text = _normalize_text(goal)
    
    # Check catalog first (highest priority)
    if catalog_match:
        return _classify_from_catalog(catalog_match, principal)
    
    # Check EXPLAIN modifier
    is_explain = _is_explain_only(text)
    
    # Priority-based pattern checks
    for mode, patterns in PRIORITY_ORDER:
        matches = _match_patterns(text, patterns)
        if matches and not (is_explain and mode in SAFE_MODES):
            return _create_classification(mode, matches, principal)
    
    # Conversational fallback
    if _detect_conversational_signals(text):
        return _create_chat_classification()
    
    # Default to chat
    return _create_default_classification()
```

#### Confidence Scoring

Confidence scores range from 0.0 to 1.0 and determine routing decisions:

- **0.95**: Exact pattern matches, catalog entries
- **0.90**: Strong dangerous/admin indicators
- **0.85**: Good pattern matches for most modes
- **0.75**: LLM-based classifications (when enabled)
- **0.60**: Conversational signals, routing minimums
- **0.50**: Default fallback

### Pattern Categories

#### Chat Patterns

**Greetings**:
- Simple salutations: "hi", "hello", "hey"
- Time-based: "good morning", "good afternoon"
- Group greetings: "hi everyone"

**Identity Questions**:
- Self-referential: "who are you?", "what are you?"
- Capability queries: "what can you do?"
- Origin questions: "who created you?"

**Pleasantries**:
- Social responses: "thanks", "thank you"
- Closings: "bye", "goodbye"
- Acknowledgments: "you're welcome"

**Meta System**:
- Platform questions: "what is this platform?"
- Capability descriptions: "describe your capabilities"
- Endpoint queries: "what endpoints exist?"

#### Graph Patterns

**Cypher Keywords**:
- Query operations: MATCH, RETURN, WHERE
- Control flow: WITH, UNWIND, ORDER BY
- Language references: "Cypher"

**Graph Terminology**:
- Structural: node, edge, relationship
- Database: Memgraph, graph
- Properties: outdegree, indegree

**Domain Labels**:
- Bioinformatics: Blast, BlastedSeq, BlastDb
- File system: File, :OUTPUT
- Sequences: sequence, sequences

**Natural Language Queries**:
- Navigation: "show neighbors of", "find connections between"
- Paths: "shortest path from", "paths between"
- Analysis: "central nodes", "connected to"

#### Admin Patterns

**Schema Operations**:
- Index management: CREATE INDEX, DROP INDEX
- Constraints: CREATE CONSTRAINT, DROP CONSTRAINT
- Property operations: rename property, set default value

**Write Operations**:
- Data modification: MERGE, SET, CREATE

#### Dangerous Patterns

**Delete Operations**:
- Node removal: DELETE, DETACH DELETE
- Bulk removal: "delete all", "remove everything"
- Database purge: "wipe database", "reset everything"

**Drop Operations**:
- Database destruction: DROP DATABASE, DROP GRAPH
- Complete removal: DROP ALL

**Bulk Operations**:
- Unbounded queries: "every pair", "no LIMIT"
- Cartesian products: "cartesian"
- Resource intensive: "triangle count"

**Export Operations**:
- Data extraction: "export entire", "download every user"
- Bulk dumps: "dump all data"

**Continuous Operations**:
- Infinite loops: "forever", "infinite loop"
- Continuous execution: "every second"

#### Security Patterns

**Permission Queries**:
- Access questions: "permissions", "scopes"
- Capability checks: "allowed to", "can I run"
- Role queries: "my roles", "my permissions"

**Tenant Queries**:
- Organization context: "tenant", "my organization"

**Danger Queries**:
- Safety questions: "dangerous queries", "unsafe operations"

#### Explain-Only Patterns

**Safe Modifiers**:
- Plan analysis: EXPLAIN, PROFILE
- Non-execution: "do not execute", "plan only"
- Preview: "just show the plan"

### API Reference

#### Main Function

```python
def classify_intent(
    goal: str,
    *,
    catalog_match: dict[str, Any] | None = None,
    principal: dict[str, Any] | None = None,
) -> IntentClassification
```

**Parameters**:
- `goal`: The user's prompt text to classify
- `catalog_match`: Optional pre-matched catalog entry with metadata
- `principal`: Optional user principal for RBAC checking

**Returns**: `IntentClassification` object with mode, confidence, and metadata

#### IntentClassification Dataclass

```python
@dataclass
class IntentClassification:
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
```

**Attributes**:
- `mode`: Classified intent mode ("chat", "graph", "security", "admin", "dangerous")
- `confidence`: Confidence score (0.0-1.0)
- `reasoning`: Machine-readable explanation
- `source`: Classification source ("patterns", "catalog", "llm", "conversational", "default")
- `matched_catalog_id`: Catalog prompt ID if matched
- `matched_patterns`: List of matched pattern strings
- `pattern_categories`: List of matched category names
- `principal_blocked`: True if user lacks permissions
- `requires_admin`: True if operation requires admin privileges
- `used_llm`: True if LLM fallback was used

#### Helper Functions

```python
def is_simple_chat(goal: str) -> bool
```
Returns True if prompt is definitely simple chat (fast path for orchestrator).

```python
def is_graph_query(goal: str) -> bool
```
Quick check for graph database queries.

```python
def requires_admin(goal: str) -> bool
```
Returns True if operation requires admin privileges.

```python
def is_security_question(goal: str) -> bool
```
Quick check for security/permission questions.

```python
def is_dangerous_operation(goal: str) -> bool
```
Quick check for dangerous/destructive operations.

#### Enums and Types

```python
class IntentMode(str, Enum):
    CHAT = "chat"
    GRAPH = "graph"
    SECURITY = "security"
    ADMIN = "admin"
    DANGEROUS = "dangerous"

class ClassificationSource(str, Enum):
    PATTERNS = "patterns"
    CATALOG = "catalog"
    LLM = "llm"
    CONVERSATIONAL = "conversational"
    DEFAULT = "default"

IntentModeType = Literal["chat", "graph", "security", "admin", "dangerous"]
```

### Usage Examples

#### Basic Classification

```python
from src.services.intent_classifier import classify_intent

# Simple chat
result = classify_intent("Hello, how are you?")
print(result.mode)  # "chat"
print(result.confidence)  # 0.95

# Graph query
result = classify_intent("MATCH (n:Blast) RETURN n LIMIT 5")
print(result.mode)  # "graph"
print(result.confidence)  # 0.85

# Dangerous operation
result = classify_intent("DELETE DETACH (n) WHERE true")
print(result.mode)  # "dangerous"
print(result.confidence)  # 0.90
print(result.requires_admin)  # True
```

#### With Principal Context

```python
principal = {
    "permissions": ["read:graph"],
    "roles": ["user"],
    "scopes": ["tenant:123"]
}

result = classify_intent("DROP DATABASE", principal=principal)
print(result.principal_blocked)  # True
print(result.reasoning)  # Contains permission check info
```

#### Catalog Integration

```python
catalog_match = {
    "id": "blast_query_001",
    "category": "read_only",
    "severity": "normal",
    "requires_admin": False
}

result = classify_intent("Custom blast query", catalog_match=catalog_match)
print(result.source)  # "catalog"
print(result.confidence)  # 0.95
```

#### Quick Checks

```python
from src.services.intent_classifier import (
    is_simple_chat, is_graph_query, requires_admin,
    is_security_question, is_dangerous_operation
)

assert is_simple_chat("Hi there!") == True
assert is_graph_query("MATCH (n) RETURN n") == True
assert requires_admin("CREATE INDEX") == True
assert is_security_question("What permissions do I have?") == True
assert is_dangerous_operation("DELETE everything") == True
```

### Configuration

#### Confidence Thresholds

The `IntentConfidenceThresholds` class provides centralized configuration:

```python
class IntentConfidenceThresholds:
    # Pattern-based matches
    CATALOG_MATCH = 0.95
    PATTERN_EXACT = 0.95
    PATTERN_STRONG = 0.90
    PATTERN_GOOD = 0.85
    CONVERSATIONAL = 0.85
    
    # LLM-based classification
    LLM_HIGH = 0.90
    LLM_MEDIUM = 0.75
    LLM_LOW = 0.60
    
    # Routing thresholds
    CHAT_ROUTING = 0.60
    SECURITY_ROUTING = 0.75
    ADMIN_ROUTING = 0.70
    DANGEROUS_ROUTING = 0.70
    GRAPH_ROUTING = 0.80
    
    # Default fallback
    DEFAULT_FALLBACK = 0.50
```

#### Environment Variables

- `INTENT_LLM_FALLBACK_ENABLED`: Enable LLM-based fallback (default: False)
- `INTENT_CONFIDENCE_*`: Override specific thresholds

#### Pattern Customization

Patterns are organized in `PatternCategory` objects for easy extension:

```python
@dataclass
class PatternCategory:
    name: str
    patterns: list[re.Pattern]
    description: str = ""
```

To add new patterns:

```python
NEW_PATTERNS = PatternCategory(
    name="new_category",
    description="New pattern category",
    patterns=[
        re.compile(r"new\s+pattern", re.IGNORECASE),
        re.compile(r"another\s+pattern", re.IGNORECASE),
    ]
)

# Add to appropriate pattern list
PATTERN_LIST.append(NEW_PATTERNS)
```

### Integration Points

#### Orchestrator Integration

The classifier integrates with the main orchestrator (`src/services/orchestrator.py`):

```python
from src.services.intent_classifier import classify_intent

class Orchestrator:
    def route_request(self, goal: str, principal: dict) -> str:
        classification = classify_intent(goal, principal=principal)
        
        # Check permissions
        if classification.principal_blocked:
            raise PermissionError("Insufficient privileges")
        
        # Route based on mode and confidence
        if classification.confidence >= self.get_routing_threshold(classification.mode):
            return self.get_handler(classification.mode)
        
        # Fallback routing
        return self.fallback_handler
```

#### Prompt Catalog Integration

Works with `src/services/prompt_catalog.py` for pre-classified prompts:

```python
from src.services.prompt_catalog import get_catalog_match

# Get catalog match first
catalog_match = get_catalog_match(goal)

# Pass to classifier
classification = classify_intent(goal, catalog_match=catalog_match)
```

#### RBAC Integration

Integrates with `src/security/perm.py` for permission checking:

```python
from src.security.perm import check_permission

def enhanced_permission_check(classification: IntentClassification, principal: dict):
    # Basic mode-based check
    if classification.requires_admin and not _principal_has_admin(principal):
        return False
    
    # Fine-grained permission check
    return check_permission(principal, f"{classification.mode}:execute")
```

#### Metrics Integration

Records classification metrics to `src/observability/metrics.py`:

```python
def _record_classification_metrics(result: IntentClassification, duration: float):
    try:
        from src.observability.metrics import record_intent_classification
        record_intent_classification(
            mode=result.mode,
            source=result.source,
            confidence=result.confidence,
            duration_seconds=duration,
            adjusted=result.principal_blocked,
        )
    except ImportError:
        pass  # Metrics not available
```

### Security Considerations

#### Permission Validation

- **Principal Blocking**: Non-admin users blocked from admin/dangerous operations
- **RBAC Integration**: Fine-grained permission checking
- **Audit Logging**: All classifications logged for security review

#### Safe Pattern Handling

- **EXPLAIN Modifier**: Makes dangerous queries safe for analysis
- **Pattern Priority**: Dangerous patterns checked first
- **Confidence Thresholds**: Minimum confidence required for routing

#### Input Validation

- **Text Normalization**: Strips and collapses whitespace
- **Empty Input Handling**: Defaults to safe chat mode
- **Regex Safety**: All patterns use safe regex operations

### Performance Characteristics

#### Time Complexity

- **Pattern Matching**: O(n) where n is number of patterns (currently ~100)
- **Text Processing**: O(m) where m is input text length
- **Overall**: Sub-millisecond for typical inputs

#### Memory Usage

- **Pattern Objects**: Pre-compiled regex objects (~10KB)
- **Classification Results**: Small dataclass objects
- **No External Dependencies**: Pure Python implementation

#### Scalability

- **Concurrent Safe**: Stateless design, thread-safe
- **Caching Potential**: Results could be cached for repeated queries
- **Batch Processing**: Could be extended for bulk classification

### Testing Strategy

#### Unit Tests

Pattern matching tests:
```python
def test_dangerous_patterns():
    assert classify_intent("DELETE DETACH (n)").mode == "dangerous"
    assert classify_intent("DROP DATABASE").mode == "dangerous"
    assert classify_intent("EXPLAIN DELETE (n)").mode == "graph"  # Safe
```

#### Integration Tests

End-to-end classification:
```python
def test_orchestrator_integration():
    goal = "MATCH (n:Blast) RETURN n"
    result = classify_intent(goal)
    assert result.mode == "graph"
    assert result.confidence >= 0.80
```

#### Performance Tests

Benchmarking:
```python
def test_classification_performance():
    goals = ["hello", "MATCH query", "DELETE all", ...]
    start = time.time()
    for goal in goals:
        classify_intent(goal)
    duration = time.time() - start
    assert duration < 0.1  # 100ms for 100 queries
```

#### Edge Cases

Boundary testing:
```python
def test_edge_cases():
    # Empty input
    assert classify_intent("").mode == "chat"
    
    # Very long input
    long_text = "hello " * 1000
    result = classify_intent(long_text)
    assert result.mode == "chat"
    
    # Special characters
    assert classify_intent("MATCH (n:Node) WHERE n.prop =~ '.*'").mode == "graph"
```

### Observability and Monitoring

#### Logging

Structured logging with context:
```python
log.info(
    "intent_classifier.classification",
    mode=result.mode,
    confidence=result.confidence,
    source=result.source,
    principal_blocked=result.principal_blocked,
    pattern_count=len(result.matched_patterns or []),
)
```

#### Metrics

Prometheus metrics:
- `intent_classification_duration_seconds`
- `intent_classification_confidence`
- `intent_classification_mode_total`
- `intent_classification_source_total`
- `intent_classification_blocked_total`

#### Health Checks

Service health monitoring:
```python
def health_check():
    # Test basic functionality
    result = classify_intent("hello")
    return result.mode == "chat" and result.confidence > 0.5
```

### Error Handling

#### Graceful Degradation

- **Import Failures**: Metrics integration fails silently
- **Pattern Errors**: Invalid regex patterns logged and skipped
- **Principal Errors**: Missing principal treated as anonymous user

#### Exception Safety

- **No Exceptions Raised**: All errors handled internally
- **Default Classification**: Fallback to safe chat mode on errors
- **Error Logging**: All exceptions logged with context

### Future Enhancements

#### LLM Integration

Optional LLM fallback for ambiguous cases:
```python
if INTENT_LLM_FALLBACK_ENABLED and confidence < LLM_THRESHOLD:
    llm_result = await classify_with_llm(text)
    if llm_result.confidence > confidence:
        return llm_result
```

#### Machine Learning Models

Trained classification models:
- **Supervised Learning**: Train on labeled prompt data
- **Feature Engineering**: Extract linguistic features
- **Model Serving**: Deploy as microservice

#### Advanced Pattern Matching

Enhanced pattern capabilities:
- **Semantic Matching**: BERT embeddings for similarity
- **Context Awareness**: Consider conversation history
- **Multi-language Support**: Patterns for different languages

#### Real-time Learning

Dynamic pattern updates:
- **Feedback Loop**: Learn from classification corrections
- **A/B Testing**: Compare pattern effectiveness
- **Automated Tuning**: Adjust thresholds based on accuracy

#### Performance Optimizations

- **Trie-based Matching**: Faster pattern matching
- **GPU Acceleration**: For large-scale classification
- **Caching Layer**: Redis-based result caching

### Troubleshooting

#### Common Issues

**Low Confidence Scores**:
- Check pattern coverage for domain-specific terms
- Consider adding custom patterns
- Review conversational signal detection

**Incorrect Classifications**:
- Verify pattern regex accuracy
- Check priority order conflicts
- Examine catalog category mappings

**Performance Problems**:
- Profile pattern matching time
- Consider pattern optimization
- Implement result caching

#### Debug Information

Enable debug logging:
```python
import logging
logging.getLogger("intent_classifier").setLevel(logging.DEBUG)
```

Check classification details:
```python
result = classify_intent("problematic query")
print(result.to_log_dict())
print(f"Matched patterns: {result.matched_patterns}")
print(f"Categories: {result.pattern_categories}")
```

### Contributing

#### Adding New Patterns

1. Define pattern category:
```python
NEW_CATEGORY = PatternCategory(
    name="new_patterns",
    description="New intent patterns",
    patterns=[
        re.compile(r"new\s+intent", re.IGNORECASE),
    ]
)
```

2. Add to appropriate pattern list:
```python
PATTERN_LIST_ALL.append(NEW_CATEGORY)
```

3. Update tests and documentation

#### Modifying Confidence Thresholds

1. Update `IntentConfidenceThresholds` class
2. Test impact on routing decisions
3. Update integration tests

#### Extending Intent Modes

1. Add new mode to `IntentMode` enum
2. Create pattern categories
3. Update routing logic in orchestrator
4. Add confidence thresholds
5. Update documentation and tests

### License

This module is part of the Cineca Agentic Platform and follows the project's licensing terms.

### Changelog

#### Version 1.0.0
- Initial implementation with basic pattern matching
- Support for 5 intent modes
- Principal-based permission checking
- Metrics integration

#### Version 1.1.0
- Added EXPLAIN modifier for safe query analysis
- Improved conversational signal detection
- Enhanced pattern categories with descriptions

#### Version 1.2.0
- Catalog integration for pre-classified prompts
- Improved confidence scoring
- Better error handling and logging

### Support

For issues or questions regarding the Intent Classifier:

- **Documentation**: This README and inline code documentation
- **Logs**: Check structured logs for classification details
- **Metrics**: Monitor classification performance and accuracy
- **Tests**: Run test suite for validation

---

*This README provides comprehensive documentation for the Intent Classifier service. For the latest updates, refer to the source code and project changelog.*