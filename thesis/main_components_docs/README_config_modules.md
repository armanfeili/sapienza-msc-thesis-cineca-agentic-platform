# Config Modules Framework Reference

This document provides comprehensive reference documentation for the Config Modules framework implemented in the Cineca Agentic Platform. The Config Modules framework provides specialized configuration classes that extend the base settings with domain-specific defaults and environment-aware tuning.

## Overview

The Config Modules framework extends the base configuration system (`src.config.settings`) with specialized configuration classes that provide:

- **Device-aware defaults** for compute resources
- **Environment-specific tuning** for different deployment scenarios
- **Domain-specific configuration** for complex subsystems
- **Singleton pattern** for consistent configuration access
- **Pydantic integration** with environment variable overrides

## Architecture

### Base Configuration Integration

Config modules extend the base settings system:

```python
from src.config import settings  # Base configuration
from src.config_modules import compute_config  # Specialized config

# Base settings provide core application config
db_host = settings.MG_HOST

# Config modules provide domain-specific tuning
step_timeout = compute_config.step_timeout_seconds
```

### Singleton Pattern

Configuration modules use singleton instances for consistency:

```python
from src.config_modules.compute import get_compute_config

# Always returns the same instance
config1 = get_compute_config()
config2 = get_compute_config()
assert config1 is config2
```

## Compute Configuration

### Overview

The ComputeConfig module provides device-aware configuration for LLM execution, automatically tuning timeouts, concurrency limits, and model selection based on the available compute resources.

### Core Configuration

#### Device Types

```python
from typing import Literal

DeviceType = Literal["cpu", "cuda", "mps", "auto"]
```

**Supported Devices**:
- `cpu`: CPU-only execution (default)
- `cuda`: NVIDIA GPU execution
- `mps`: Apple Silicon GPU execution
- `auto`: Automatic device detection

#### Basic Properties

```python
class ComputeConfig(BaseSettings):
    # Device configuration
    device: DeviceType = "cpu"
    
    # Concurrency limits
    max_concurrent_llm_calls: int = 1
    
    # Timeout configuration
    step_timeout_seconds: int = 1200  # Individual step timeout
    run_timeout_seconds: int = 1800   # Total run timeout
    
    # Model selection
    plan_model_name: str | None = None
    execute_model_name: str | None = None
    
    # Warmup configuration
    warmup_models: list[str] = []
    
    # Test modes
    test_mode: bool = False
    memgraph_nl_test_mode: bool = False
```

### Device-Aware Defaults

#### Recommended Timeouts

The configuration automatically provides device-appropriate timeouts:

```python
config = get_compute_config()

# CPU execution (default)
print(config.recommended_step_timeout)  # 1200 seconds (20 minutes)
print(config.recommended_run_timeout)   # 1800 seconds (30 minutes)

# GPU execution
config.device = "cuda"
print(config.recommended_step_timeout)  # 30 seconds
print(config.recommended_run_timeout)   # 120 seconds
```

**Device-Specific Timeouts**:

| Device | Step Timeout | Run Timeout | Use Case |
|--------|-------------|-------------|----------|
| `cpu` | 1200s (20m) | 1800s (30m) | CPU inference (phi3:mini) |
| `cuda` | 30s | 120s | GPU-accelerated inference |
| `mps` | 60s | 180s | Apple Silicon GPU |
| `auto` | 60s | 180s | Automatic detection |

#### Concurrency Limits

Device-appropriate concurrency settings:

```python
# CPU: Sequential execution
config.device = "cpu"
print(config.recommended_concurrency)  # 1

# GPU: Parallel execution
config.device = "cuda"
print(config.recommended_concurrency)  # 4

# Apple Silicon: Moderate parallelism
config.device = "mps"
print(config.recommended_concurrency)  # 2
```

### Test Mode Configuration

#### General Test Mode

Reduced timeouts for testing:

```python
config.test_mode = True
print(config.recommended_step_timeout)  # 60 seconds
print(config.recommended_run_timeout)   # 120 seconds
print(config.recommended_concurrency)   # 1
```

#### Memgraph NL Test Mode

Specialized mode for Memgraph natural language integration tests:

```python
config.memgraph_nl_test_mode = True
print(config.recommended_step_timeout)  # 90 seconds
print(config.recommended_run_timeout)   # 180 seconds
```

### Environment Variable Overrides

#### Device Configuration

```bash
# Set compute device
LLM_DEVICE=cuda

# Override timeouts explicitly
LLM_STEP_TIMEOUT_SECONDS=45
LLM_RUN_TIMEOUT_SECONDS=300

# Set concurrency limit
LLM_MAX_CONCURRENT_CALLS=2

# Enable test modes
LLM_TEST_MODE=true
LLM_MEMGRAPH_NL_TEST_MODE=true
```

#### Model Selection

```bash
# Specify models for different phases
LLM_PLAN_MODEL_NAME=gpt-4o-mini
LLM_EXECUTE_MODEL_NAME=gpt-4o
```

### Configuration Application

#### Automatic Defaults

The `apply_recommended_defaults()` method applies device-appropriate settings:

```python
from src.config_modules.compute import ComputeConfig

config = ComputeConfig(device="cuda")
config.apply_recommended_defaults()

print(config.step_timeout_seconds)  # 30 (from recommended_step_timeout)
print(config.run_timeout_seconds)   # 120 (from recommended_run_timeout)
print(config.max_concurrent_llm_calls)  # 4 (from recommended_concurrency)
```

#### Timeout Clamping

Step timeouts are automatically clamped to run timeouts:

```python
config.run_timeout_seconds = 60
config.step_timeout_seconds = 120

config.apply_recommended_defaults()
print(config.step_timeout_seconds)  # 60 (clamped to run_timeout)
```

### Usage in Orchestrator

The compute configuration is consumed by the orchestrator service:

```python
from src.config_modules import compute_config

class Orchestrator:
    def __init__(self):
        self.step_timeout = compute_config.step_timeout_seconds
        self.run_timeout = compute_config.run_timeout_seconds
        self.max_concurrent = compute_config.max_concurrent_llm_calls
    
    async def execute_step(self, step):
        # Use configured timeouts
        async with asyncio.timeout(self.step_timeout):
            return await self._execute_llm_call(step)
```

### Global Instance Management

#### Singleton Access

```python
from src.config_modules.compute import get_compute_config, compute_config

# Function-based access
config = get_compute_config()

# Convenience export (same instance)
assert compute_config is get_compute_config()
```

#### Reset for Testing

```python
from src.config_modules.compute import reset_compute_config

# Reset singleton for test isolation
reset_compute_config()
```

### Configuration Export

#### Dictionary Export

```python
config = get_compute_config()
config_dict = config.to_dict()

print(config_dict)
# {
#     "device": "cpu",
#     "max_concurrent_llm_calls": 1,
#     "step_timeout_seconds": 1200,
#     "run_timeout_seconds": 1800,
#     "plan_model_name": None,
#     "execute_model_name": None,
#     "warmup_models": [],
#     "test_mode": False,
#     "memgraph_nl_test_mode": False,
#     "recommended": {
#         "step_timeout": 1200,
#         "run_timeout": 1800,
#         "concurrency": 1
#     }
# }
```

## Configuration Module Pattern

### Creating New Config Modules

To add a new configuration module:

1. **Create the module file** in `src/config_modules/`:

```python
# src/config_modules/database.py
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    connection_pool_size: int = 10
    query_timeout_seconds: int = 30
    
    model_config = {
        "env_prefix": "DB_",
        "env_file": ".env",
        "extra": "ignore"
    }

# Global singleton
_db_config: DatabaseConfig | None = None

def get_database_config() -> DatabaseConfig:
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config

database_config = get_database_config()
```

2. **Export from `__init__.py`**:

```python
# src/config_modules/__init__.py
from src.config_modules.database import DatabaseConfig, get_database_config, database_config

__all__ = [
    # Existing exports...
    "DatabaseConfig", "get_database_config", "database_config"
]
```

3. **Use in application code**:

```python
from src.config_modules import database_config

pool_size = database_config.connection_pool_size
```

### Best Practices

#### Environment Variables

- Use descriptive prefixes: `LLM_`, `DB_`, `API_`
- Document all available overrides
- Provide sensible defaults

#### Singleton Management

- Use global singleton for consistency
- Provide reset functions for testing
- Initialize lazily to avoid import-time side effects

#### Device Awareness

- Detect capabilities automatically when possible
- Provide conservative defaults for unknown hardware
- Allow explicit overrides for fine-tuning

#### Validation

- Use Pydantic for type safety and validation
- Validate configuration at startup
- Provide clear error messages for invalid settings

## Integration with Base Settings

### Configuration Hierarchy

1. **Base Settings** (`src.config.settings`): Core application configuration
2. **Config Modules**: Domain-specific tuning and device awareness
3. **Environment Variables**: Runtime overrides
4. **Command Line Args**: Instance-specific overrides

### Example Integration

```python
from src.config import settings
from src.config_modules import compute_config

# Base settings for core config
database_url = settings.MG_HOST

# Config modules for domain-specific tuning
llm_timeout = compute_config.step_timeout_seconds
concurrency = compute_config.max_concurrent_llm_calls

# Environment variables override both
# LLM_STEP_TIMEOUT_SECONDS=60
# MG_HOST=production-db
```

## Testing Configuration

### Test Isolation

```python
import pytest
from src.config_modules.compute import reset_compute_config, get_compute_config

@pytest.fixture(autouse=True)
def reset_config():
    """Reset config before each test."""
    reset_compute_config()
    yield

def test_cpu_defaults():
    config = get_compute_config()
    assert config.device == "cpu"
    assert config.step_timeout_seconds == 1200
```

### Environment Mocking

```python
import os
from unittest.mock import patch

def test_cuda_configuration():
    with patch.dict(os.environ, {"LLM_DEVICE": "cuda"}):
        from src.config_modules.compute import reset_compute_config
        reset_compute_config()
        
        config = get_compute_config()
        assert config.device == "cuda"
        assert config.recommended_step_timeout == 30
```

### Configuration Validation

```python
def test_timeout_clamping():
    config = ComputeConfig(
        run_timeout_seconds=60,
        step_timeout_seconds=120
    )
    config.apply_recommended_defaults()
    
    # Step timeout clamped to run timeout
    assert config.step_timeout_seconds == 60
```

## Performance Tuning Guidelines

### CPU Environments

```python
# Conservative settings for CPU inference
config = ComputeConfig(device="cpu")
# - step_timeout: 1200s (20 minutes for phi3:mini)
# - run_timeout: 1800s (30 minutes for multi-step)
# - concurrency: 1 (sequential execution)
```

### GPU Environments

```python
# Aggressive settings for GPU acceleration
config = ComputeConfig(device="cuda")
# - step_timeout: 30s (fast GPU inference)
# - run_timeout: 120s (quick multi-step runs)
# - concurrency: 4 (parallel execution)
```

### Apple Silicon

```python
# Balanced settings for MPS
config = ComputeConfig(device="mps")
# - step_timeout: 60s (moderate MPS performance)
# - run_timeout: 180s (balanced multi-step)
# - concurrency: 2 (limited parallelism)
```

### Testing Environments

```python
# Reduced timeouts for fast test cycles
config = ComputeConfig(test_mode=True)
# - step_timeout: 60s (fast test execution)
# - run_timeout: 120s (quick test runs)
# - concurrency: 1 (simplified testing)
```

This Config Modules framework provides flexible, device-aware configuration management that automatically adapts to different deployment environments while maintaining consistent application behavior.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_config_modules.md