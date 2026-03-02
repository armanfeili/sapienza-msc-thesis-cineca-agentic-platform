# Background Framework Reference

This document provides comprehensive reference documentation for the Background framework implemented in the Cineca Agentic Platform. The Background framework provides scheduled background tasks for health monitoring, backups, cleanup, and provider health checks using APScheduler.

## Overview

The Background framework manages periodic background tasks essential for platform operations:

- **Health Monitoring**: Periodic connectivity checks for core dependencies
- **Provider Health**: Background monitoring of LLM provider availability
- **Backups**: Automated creation of compressed archives with retention
- **Cleanup**: Age-based pruning of temporary files and cache data
- **Metrics Collection**: Prometheus metrics for all background operations

## Architecture

### BackgroundManager

The central coordinator that manages all background tasks using APScheduler.

#### Configuration

```python
from src.background import BackgroundConfig, BackgroundManager

config = BackgroundConfig(
    enabled=True,
    health_enabled=True,
    health_interval_seconds=30,
    backup_enabled=False,
    backup_cron="30 2 * * *",  # Daily at 02:30 UTC
    cleanup_enabled=False,
    cleanup_cron="15 3 * * 0"  # Weekly on Sunday at 03:15 UTC
)

manager = BackgroundManager(config=config)
```

#### Lifecycle Management

```python
# Start background tasks
await manager.start()

# Application runs...

# Stop background tasks
await manager.stop()
```

#### FastAPI Integration

```python
from fastapi import FastAPI
from src.background import lifespan

app = FastAPI(lifespan=lifespan)

# BackgroundManager is attached to app.state.bg
# and automatically started/stopped with the app
```

### APScheduler Integration

The framework uses APScheduler for reliable job scheduling with features like:

- **Job Coalescing**: Prevents overlapping job executions
- **Misfire Handling**: Configurable grace periods for missed executions
- **Error Recovery**: Automatic retry and error logging
- **Metrics Integration**: Performance monitoring for all jobs

## Health Monitoring

### Overview

Periodic health checks verify connectivity to core platform dependencies.

### Supported Checks

#### HTTP Health Checks
Probes API endpoints for availability:

```python
# Default: http://127.0.0.1:8000/health
# Configurable via HEALTHCHECK_HTTP_URLS
result = await probe_http("http://api.example.com/health")
# Returns: {"target": "url", "up": bool, "latency": float, "status": int}
```

#### Memgraph Health Checks
Tests graph database connectivity:

```python
result = await probe_memgraph()
# Returns: {"target": "memgraph", "up": bool, "latency": float}
```

#### Redis Health Checks
Verifies cache connectivity:

```python
result = await probe_redis()
# Returns: {"target": "redis", "up": bool, "latency": float}
```

### Health Check Execution

#### Single Run
Execute all health checks once:

```python
from src.background.health_checks import run_all_health_checks

summary = await run_all_health_checks()
# Returns: HealthSummary with results and up_ratio
```

#### Continuous Monitoring
Run health checks in a loop:

```python
from src.background.health_checks import health_checks_loop

stop_event = asyncio.Event()
await health_checks_loop(stop_event)
```

### Configuration

```bash
# Health check settings
HEALTHCHECK_INTERVAL_SECONDS=30
HEALTHCHECK_TIMEOUT_SECONDS=2.5
HEALTHCHECK_HTTP_URLS=http://api1/health,http://api2/health
HEALTHCHECK_ENABLE_MEMGRAPH=true
HEALTHCHECK_ENABLE_REDIS=true
```

### Metrics

Health checks emit Prometheus metrics:

```python
# Gauge: healthcheck_up{target}
# Histogram: healthcheck_latency_seconds{target}
```

## Provider Health Monitoring

### Overview

Background monitoring of LLM provider availability to ensure fresh health data for the health endpoint.

### Provider Health Checks

#### Single Provider Check
Test individual provider connectivity:

```python
from src.background.provider_health import check_provider_health

provider = {"base_url": "https://api.openai.com/v1", "id": "openai"}
result = await check_provider_health(provider, timeout=2.0)
# Returns: {"ok": bool, "status_code": int, "checked_at": timestamp}
```

#### Bulk Provider Updates
Update health for all providers:

```python
from src.background.provider_health import update_all_provider_health

await update_all_provider_health()
```

### Provider Health Scheduler

Long-running scheduler for periodic health refreshes:

```python
from src.background.provider_health_scheduler import get_scheduler

scheduler = get_scheduler()
await scheduler.start()

# Runs every PROVIDER_HEALTH_REFRESH_INTERVAL (default: 1 hour)
# Updates Redis cache with TTL (default: 2 hours)

await scheduler.stop()
```

### Configuration

```bash
# Provider health settings
PROVIDER_HEALTH_CHECK_INTERVAL=60
PROVIDER_HEALTH_CHECK_TIMEOUT=2.0
PROVIDER_HEALTH_REFRESH_INTERVAL=3600  # 1 hour
PROVIDER_HEALTH_TTL=7200               # 2 hours
```

## Backup System

### Overview

Automated creation of compressed archives with configurable retention policies.

### Backup Configuration

```python
from src.background.backups import BackupConfig

config = BackupConfig(
    dest_dir=Path("./var/backups"),
    sources=[Path("db"), Path("config")],
    retention_days=14,
    label="cineca"
)
```

### Backup Operations

#### Create Backup
Generate a timestamped archive:

```python
from src.background.backups import create_backup

archive_path = create_backup(config)
# Creates: ./var/backups/cineca-backup-20240101-143022.tar.gz
```

#### List Backups
Get available backup files:

```python
from src.background.backups import list_backups

backups = list_backups()  # Sorted newest-first
latest = latest_backup_path()
```

#### Prune Old Backups
Remove backups older than retention period:

```python
from src.background.backups import prune_old_backups

removed_count = prune_old_backups(Path("./var/backups"), 14)
```

### Configuration

```bash
# Backup settings
BACKUP_DIR=./var/backups
BACKUP_SOURCES=db,config
BACKUP_RETENTION_DAYS=14
BACKUP_ENABLED=false
BACKUP_CRON="30 2 * * *"  # Daily at 02:30 UTC
```

### Archive Contents

Backups include configured sources while excluding:

- `__pycache__` directories
- `.git` directories
- `node_modules`
- Virtual environments
- Temporary files (`*.pyc`, `*.swp`, etc.)

## Cleanup System

### Overview

Age-based pruning of temporary files, cache data, and Redis keys.

### Cleanup Configuration

```python
from src.background.cleanup import CleanupConfig

config = CleanupConfig(
    roots=[Path("./var/tmp"), Path("./var/cache")],
    patterns=["*.tmp", "*.log.*", "*.pyc"],
    older_than_days=7,
    remove_empty_dirs=True,
    purge_folders=("__pycache__",),
    redis_patterns=["temp:*", "cache:*"]
)
```

### Cleanup Operations

#### Filesystem Cleanup
Remove old files and directories:

```python
from src.background.cleanup import cleanup_filesystem

stats = cleanup_filesystem(config)
# Returns: {"files_deleted": int, "dirs_deleted": int, "empty_dirs_pruned": int}
```

#### Redis Cleanup
Delete keys matching patterns:

```python
from src.background.cleanup import cleanup_redis

stats = cleanup_redis(["temp:*", "session:expired:*"])
# Returns: {"deleted": int, "scanned": int}
```

#### Unified Cleanup
Run all cleanup operations:

```python
from src.background.cleanup import cleanup_all

summary = cleanup_all(config)
# Returns: {"filesystem": {...}, "redis": {...}, "roots": [...], "patterns": [...]}
```

### Safety Features

- **Path Safeguards**: Prevents deletion outside configured roots
- **Depth Protection**: Avoids deleting shallow system directories
- **Dry Run Mode**: Preview changes without executing deletions
- **Error Resilience**: Continues operation despite individual failures

### Configuration

```bash
# Cleanup settings
CLEANUP_ROOTS=./var/tmp,./var/cache
CLEANUP_PATTERNS=*.tmp,*.temp,*.bak,*.old,*.log.*,*.pyc
CLEANUP_OLDER_THAN_DAYS=7
CLEANUP_REMOVE_EMPTY_DIRS=true
CLEANUP_REDIS_PATTERNS=temp:*,cache:expired:*
CLEANUP_ENABLED=true
CLEANUP_CRON="0 3 * * *"  # Daily at 03:00 UTC
```

## Scheduler Integration

### Job Registration

The scheduler automatically registers jobs based on configuration:

```python
from src.background.scheduler import start_scheduler

# Registers enabled jobs and starts scheduler
scheduler = start_scheduler()
```

### Available Jobs

| Job | Purpose | Default Schedule | Config Flag |
|-----|---------|------------------|-------------|
| `health-checks` | Dependency health monitoring | Every 30s | `HEALTHCHECK_*` |
| `provider-health-checks` | Provider availability | Every 60s | `PROVIDER_HEALTH_*` |
| `backup-run` | Create backup archives | Daily 02:30 UTC | `BACKUP_ENABLED` |
| `backup-prune` | Remove old backups | After backup | `BACKUP_PRUNE_ENABLED` |
| `cleanup-run` | Prune temp files | Every 6h | `CLEANUP_ENABLED` |

### Cron Expressions

Jobs support flexible scheduling:

```bash
# Examples
HEALTHCHECK_CRON="*/30 * * * *"        # Every 30 seconds
BACKUP_CRON="30 2 * * *"              # Daily at 02:30 UTC
CLEANUP_CRON="0 */6 * * *"            # Every 6 hours
PROVIDER_HEALTH_CHECK_CRON="0 * * * *" # Every hour
```

### Job Execution

Jobs run with automatic error handling and metrics:

```python
# Automatic wrapping provides:
# - Error logging
# - Duration tracking
# - Metrics emission
# - Coalesce prevention
```

## Metrics and Monitoring

### Prometheus Metrics

All background operations emit metrics:

```python
# Job execution metrics
bg_job_duration_seconds{job_name}
bg_job_total{job_name, status}

# Health check metrics
healthcheck_up{target}
healthcheck_latency_seconds{target}

# Provider health metrics
provider_health_status{provider, model}

# Backup metrics
backup_bytes_total
backup_files_total
backup_duration_seconds
```

### Structured Logging

All operations include comprehensive logging:

```json
{
  "event": "background.job.done",
  "job": "health-checks",
  "status": "ok",
  "duration": "0.123s"
}
```

## Configuration Reference

### Environment Variables

#### Background Manager
```bash
BACKGROUND_ENABLED=true
BACKGROUND_HEALTH_ENABLED=true
BACKGROUND_HEALTH_INTERVAL_SECONDS=30
BACKGROUND_BACKUPS_ENABLED=false
BACKGROUND_BACKUPS_CRON="30 2 * * *"
BACKGROUND_CLEANUP_ENABLED=false
BACKGROUND_CLEANUP_CRON="15 3 * * 0"
```

#### Health Checks
```bash
HEALTHCHECK_INTERVAL_SECONDS=30
HEALTHCHECK_TIMEOUT_SECONDS=2.5
HEALTHCHECK_HTTP_URLS=http://127.0.0.1:8000/health
HEALTHCHECK_ENABLE_MEMGRAPH=true
HEALTHCHECK_ENABLE_REDIS=true
```

#### Provider Health
```bash
PROVIDER_HEALTH_CHECK_INTERVAL=60
PROVIDER_HEALTH_CHECK_TIMEOUT=2.0
PROVIDER_HEALTH_REFRESH_INTERVAL=3600
PROVIDER_HEALTH_TTL=7200
```

#### Backups
```bash
BACKUP_DIR=./var/backups
BACKUP_SOURCES=db
BACKUP_RETENTION_DAYS=14
BACKUP_ENABLED=false
BACKUP_CRON="30 2 * * *"
BACKUP_PRUNE_ENABLED=true
```

#### Cleanup
```bash
CLEANUP_ROOTS=./var/tmp,./var/cache
CLEANUP_PATTERNS=*.tmp,*.temp,*.bak,*.old,*.log.*,*.pyc
CLEANUP_OLDER_THAN_DAYS=7
CLEANUP_REMOVE_EMPTY_DIRS=true
CLEANUP_REDIS_PATTERNS=
CLEANUP_ENABLED=true
CLEANUP_CRON="0 */6 * * *"
```

#### Scheduler
```bash
SCHEDULER_ENABLED=true
SCHEDULER_MISFIRE_GRACE_SECONDS=60
```

## Best Practices

### Configuration
1. **Test Schedules**: Use dry-run modes for backup and cleanup testing
2. **Monitor Resources**: Ensure background tasks don't overwhelm system resources
3. **Set Appropriate Timeouts**: Balance thoroughness with execution time limits
4. **Configure Retention**: Set retention periods based on storage capacity and compliance needs

### Error Handling
1. **Graceful Degradation**: Background failures shouldn't affect main application
2. **Comprehensive Logging**: Include context in all log messages for debugging
3. **Metrics Monitoring**: Set up alerts for background job failures
4. **Retry Logic**: Implement appropriate retry strategies for transient failures

### Security
1. **Path Restrictions**: Use safe root directories to prevent accidental deletions
2. **Redis Key Patterns**: Be specific with Redis cleanup patterns to avoid data loss
3. **Backup Encryption**: Consider encrypting sensitive backup data
4. **Access Controls**: Limit access to backup and cleanup operations

### Performance
1. **Schedule Optimization**: Distribute jobs to avoid resource contention
2. **Resource Limits**: Configure appropriate concurrency limits for health checks
3. **Monitoring Overhead**: Balance monitoring frequency with system impact
4. **Cleanup Efficiency**: Use appropriate file patterns to minimize scan time

This Background framework provides robust, configurable background task management essential for maintaining platform health, data integrity, and operational efficiency.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_background.md