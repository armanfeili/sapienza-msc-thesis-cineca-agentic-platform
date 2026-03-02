# Background Subsystem (`src/background/`)

The background subsystem provides comprehensive background task management for the Cineca Agentic Platform, handling periodic health checks, backups, cleanup operations, and provider health monitoring. Built on APScheduler with async support, it ensures reliable maintenance operations without blocking the main application.

## Architecture Overview

The background subsystem consists of several key components:

- **BackgroundManager**: Central coordinator for background jobs with metrics and logging
- **Scheduler**: APScheduler-based job registration and lifecycle management
- **Health Checks**: Periodic liveness probes against core dependencies
- **Backups**: Automated snapshot creation and retention management
- **Cleanup**: Age-based pruning of temporary files and Redis keys
- **Provider Health**: Continuous monitoring of external LLM provider availability

## Core Components

### BackgroundManager (`__init__.py`)

The `BackgroundManager` class coordinates all background operations with comprehensive error handling and metrics collection.

```python
@dataclass
class BackgroundConfig:
    enabled: bool = True
    health_enabled: bool = True
    backup_enabled: bool = False
    cleanup_enabled: bool = True
    health_interval_seconds: int = 30
    health_cron: str = ""
    backup_cron: str = "0 2 * * *"  # Daily at 02:00 UTC
    cleanup_cron: str = "15 3 * * 0"  # Sundays at 03:15 UTC
```

**Key Features:**
- Async job execution with timeout handling
- Comprehensive metrics collection (Prometheus integration)
- Graceful error handling and logging
- Configurable job scheduling (cron or interval-based)
- FastAPI lifespan integration

**Usage:**
```python
manager = BackgroundManager()
await manager.start()
# Jobs run automatically based on configuration
await manager.stop()
```

### Scheduler (`scheduler.py`)

The scheduler module provides APScheduler integration with conditional job registration based on configuration flags.

**Supported Jobs:**
- Health checks (configurable interval/cron)
- Provider health monitoring
- Database backups with optional pruning
- Cleanup operations

**Configuration:**
```python
# Environment variables
HEALTHCHECK_INTERVAL_SECONDS=30
BACKUP_CRON="0 2 * * *"
CLEANUP_CRON="0 3 * * *"
SCHEDULER_MISFIRE_GRACE_SECONDS=60
```

### Health Checks (`health_checks.py`)

Comprehensive health monitoring system that probes core dependencies and external services.

**Probes Implemented:**
- **HTTP**: Configurable URL endpoints (default: `/health`)
- **Memgraph**: Graph database connectivity and query execution
- **Redis**: Cache and queue connectivity via PING

**Metrics:**
```python
# Prometheus metrics
healthcheck_up{target} → 1|0
healthcheck_latency_seconds{target} (histogram)
```

**Configuration:**
```python
HEALTHCHECK_INTERVAL_SECONDS=30
HEALTHCHECK_TIMEOUT_SECONDS=2.5
HEALTHCHECK_HTTP_URLS="http://localhost:8000/health"
HEALTHCHECK_ENABLE_MEMGRAPH=true
HEALTHCHECK_ENABLE_REDIS=true
```

### Backups (`backups.py`)

Automated backup system for critical data with compression and retention management.

**Features:**
- Timestamped `.tar.gz` archives
- Configurable source directories
- Automatic retention pruning
- Async execution support
- CLI interface for manual backups

**Configuration:**
```python
BACKUP_DIR="./var/backups"
BACKUP_SOURCES="db,config"
BACKUP_RETENTION_DAYS=14
BACKUP_CRON="0 2 * * *"
```

**Usage:**
```python
# Programmatic
cfg = BackupConfig(sources=[Path("db"), Path("config")])
archive_path = create_backup(cfg)

# CLI
python -m src.background.backups --sources db,config --retention-days 14
```

### Cleanup (`cleanup.py`)

Comprehensive cleanup system for temporary files and cache management.

**Features:**
- Age-based file pruning with glob patterns
- Recursive `__pycache__` removal
- Empty directory cleanup
- Redis key deletion by pattern
- Dry-run support for testing

**Configuration:**
```python
CLEANUP_ROOTS="./var/tmp,./var/cache"
CLEANUP_PATTERNS="*.tmp,*.log.*,*.pyc,__pycache__"
CLEANUP_OLDER_THAN_DAYS=7
CLEANUP_REDIS_PATTERNS="temp:*,cache:*"
```

**Supported Patterns:**
- File extensions: `.tmp`, `.temp`, `.bak`, `.old`, `.pyc`, `.pyo`
- Log rotation: `*.log.*`
- Editor files: `*.swp`, `*.swo`, `*.~*`
- Special folders: `__pycache__`

### Provider Health (`provider_health.py`, `provider_health_scheduler.py`)

Continuous monitoring of external LLM provider availability with Redis caching.

**Features:**
- OpenAI-compatible `/models` endpoint probing
- Redis cache with TTL-based expiration
- Prometheus metrics integration
- Configurable check intervals and timeouts

**Configuration:**
```python
PROVIDER_HEALTH_CHECK_INTERVAL=60
PROVIDER_HEALTH_CHECK_TIMEOUT=2.0
PROVIDER_HEALTH_REFRESH_INTERVAL=3600  # 1 hour
PROVIDER_HEALTH_TTL=7200  # 2 hours
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKGROUND_ENABLED` | `true` | Enable/disable all background tasks |
| `HEALTHCHECK_INTERVAL_SECONDS` | `30` | Health check frequency |
| `BACKUP_ENABLED` | `false` | Enable backup jobs |
| `BACKUP_CRON` | `"0 2 * * *"` | Backup schedule (cron format) |
| `CLEANUP_ENABLED` | `true` | Enable cleanup jobs |
| `CLEANUP_CRON` | `"15 3 * * 0"` | Cleanup schedule |
| `SCHEDULER_MISFIRE_GRACE_SECONDS` | `60` | Job misfire tolerance |

### FastAPI Integration

The background manager integrates seamlessly with FastAPI lifespan events:

```python
from src.background import lifespan

app = FastAPI(lifespan=lifespan)
# Background tasks start/stop automatically with the application
```

## Usage Patterns

### Programmatic Control

```python
from src.background import BackgroundManager, BackgroundConfig

# Custom configuration
config = BackgroundConfig(
    health_interval_seconds=60,
    backup_enabled=True,
    cleanup_enabled=False
)

manager = BackgroundManager(config=config)
await manager.start()

# Manual job execution
await manager._job_health()
await manager._job_backup()
await manager._job_cleanup()
```

### Scheduler Integration

```python
from src.background.scheduler import start_scheduler, shutdown_scheduler

# Start all configured jobs
scheduler = start_scheduler()

# Jobs run automatically based on configuration
# ...

# Cleanup
shutdown_scheduler()
```

### Health Check Integration

```python
from src.background.health_checks import run_all_health_checks

# Manual health check execution
summary = await run_all_health_checks()
print(f"Health ratio: {summary.up_ratio:.2%}")
```

## Performance Characteristics

### Resource Usage
- **Memory**: Minimal footprint (~10-50MB depending on configuration)
- **CPU**: Low overhead, primarily during scheduled job execution
- **Storage**: Backup archives only (configurable retention)
- **Network**: Health check probes (configurable timeouts)

### Scalability
- **Concurrent Jobs**: Limited to 1 instance per job type (prevents resource conflicts)
- **Job Parallelization**: Health checks run in parallel across targets
- **Error Isolation**: Job failures don't affect other scheduled tasks

### Reliability
- **Graceful Degradation**: Missing dependencies don't crash the scheduler
- **Misfire Handling**: Configurable grace periods for delayed job execution
- **Metrics Collection**: Comprehensive monitoring of job execution and failures

## Security Considerations

### File System Access
- **Safe Guards**: Cleanup operations restricted to configured root directories
- **Depth Protection**: Prevents deletion of shallow system directories
- **Pattern Validation**: Conservative glob patterns prevent accidental deletion

### Network Security
- **Timeout Protection**: All HTTP probes have configurable timeouts
- **Error Handling**: Network failures logged but don't expose sensitive information
- **Provider Isolation**: Individual provider failures don't affect others

### Data Protection
- **Backup Encryption**: Consider encrypting backup archives for sensitive data
- **Access Control**: Backup and cleanup operations respect file permissions
- **Audit Logging**: All operations logged with structured data

## Integration Examples

### With Health Service

```python
from src.health.service import HealthService
from src.background import BackgroundManager

health = HealthService()
manager = BackgroundManager(health=health)
await manager.start()
```

### With Archive Service

```python
from src.services.archive import ArchiveService
from src.background import BackgroundManager

archive = ArchiveService()
manager = BackgroundManager(archive=archive)
await manager.start()
```

### With Metrics Service

```python
from src.services.service_metrics import ServiceMetrics
from src.background import BackgroundManager

metrics = ServiceMetrics()
manager = BackgroundManager(metrics=metrics)
await manager.start()
```

## Monitoring and Observability

### Prometheus Metrics

```python
# Background job metrics
background_job_duration_seconds{job_name, status}
background_job_total{job_name, status}

# Health check metrics
healthcheck_up{target}
healthcheck_latency_seconds{target}

# Provider health metrics
provider_health_status{provider_id, model_name}
```

### Structured Logging

All background operations emit structured logs with correlation IDs:

```json
{
  "event": "background.job.done",
  "job": "health",
  "status": "ok",
  "duration": "0.123s",
  "correlation_id": "abc-123"
}
```

### Health Endpoints

Background health status is exposed through the main health endpoint:

```json
{
  "status": "healthy",
  "checks": {
    "background_scheduler": {
      "status": "ok",
      "jobs_running": 3,
      "last_health_check": "2024-01-15T10:30:00Z"
    }
  }
}
```

## Troubleshooting

### Common Issues

**Jobs Not Running:**
- Check `BACKGROUND_ENABLED=true`
- Verify cron expressions are valid
- Check scheduler logs for misfire warnings

**Health Checks Failing:**
- Verify service endpoints are accessible
- Check network connectivity and DNS resolution
- Review timeout configurations

**Backup Failures:**
- Ensure backup directory is writable
- Check available disk space
- Verify source paths exist

**Cleanup Issues:**
- Review configured root directories
- Check file permissions
- Use dry-run mode for testing

### Debug Commands

```bash
# Manual health check
python -c "import asyncio; from src.background.health_checks import run_all_health_checks; asyncio.run(run_all_health_checks())"

# Manual backup
python -m src.background.backups --dry-run

# Manual cleanup
python -m src.background.cleanup --dry-run
```

### Log Analysis

```bash
# Check job execution
grep "background.job.done" logs/app.log

# Monitor health checks
grep "health.http\|health.memgraph\|health.redis" logs/app.log

# Backup operations
grep "backup.created\|backup.pruned" logs/app.log
```

## Development and Testing

### Unit Testing

```python
import pytest
from src.background import BackgroundManager

@pytest.mark.asyncio
async def test_background_manager():
    manager = BackgroundManager()
    await manager.start()
    
    # Test job execution
    await manager._job_health()
    
    await manager.stop()
```

### Integration Testing

```python
# Test with real scheduler
from src.background.scheduler import get_scheduler

def test_scheduler_jobs():
    sched = get_scheduler()
    jobs = sched.get_jobs()
    assert len(jobs) >= 3  # health, backup, cleanup
```

### Mock Testing

```python
from unittest.mock import AsyncMock, patch

async def test_health_job():
    manager = BackgroundManager()
    
    with patch.object(manager.health, 'check', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = HealthResult(ok=True)
        await manager._job_health()
        mock_check.assert_called_once()
```

## API Reference

### BackgroundManager

- `start()`: Initialize and start all configured jobs
- `stop()`: Gracefully shutdown scheduler and jobs
- `_job_health()`: Execute health check sweep
- `_job_backup()`: Create system backup
- `_job_cleanup()`: Run cleanup operations

### Scheduler Functions

- `start_scheduler()`: Initialize and start APScheduler with jobs
- `shutdown_scheduler()`: Stop scheduler gracefully
- `add_default_jobs()`: Register all configured jobs

### Health Checks

- `run_all_health_checks()`: Execute all configured probes
- `probe_http(url)`: Test HTTP endpoint availability
- `probe_memgraph()`: Test graph database connectivity
- `probe_redis()`: Test Redis cache connectivity

### Backups

- `create_backup(config)`: Create timestamped archive
- `prune_old_backups(dir, days)`: Remove expired backups
- `list_backups(dir)`: Get backup file listing

### Cleanup

- `cleanup_all(config)`: Run filesystem and Redis cleanup
- `cleanup_filesystem(config)`: Remove old files and directories
- `cleanup_redis(patterns)`: Delete Redis keys by pattern

### Provider Health

- `run_provider_health_check()`: Update all provider health status
- `check_provider_health(provider)`: Test single provider availability
- `update_all_provider_health()`: Refresh health for all providers</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/src/background/README_background.md