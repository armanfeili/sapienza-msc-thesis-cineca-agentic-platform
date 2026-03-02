# Scripts Framework

The scripts package provides operational utilities for the Cineca Agentic Platform, including ETL data loading, OpenAPI schema export, database backup/restore, and health monitoring. These scripts support both development and production operations.

## Architecture Overview

The scripts framework follows these design principles:

- **Modular Design**: Each script focuses on a specific operational concern
- **Environment Agnostic**: Scripts work with Docker containers or local installations
- **Error Handling**: Comprehensive error checking with informative messages
- **Configuration**: Environment variable and command-line configuration
- **Idempotent Operations**: Safe to run multiple times where appropriate
- **Logging**: Structured logging with consistent formatting

## Core Components

### 1. ETL Loader (`etl_load.py`)

Python-based ETL loader for Memgraph-compatible databases with synthetic data generation and file-based loading.

#### Architecture
```
Data Source → Schema Mapping → Batch Processing → Database Load
     ↓              ↓              ↓              ↓
  Synthetic     Cypher Templates   MERGE Operations   Bolt Protocol
  JSON/JSONL    Type Labels        Error Handling     Transaction Mgmt
```

#### Features
- **Dual Loading Modes**: Synthetic data generation or JSON/JSONL file loading
- **Schema-Aware Generation**: Realistic data following platform schema
- **Batch Processing**: Configurable batch sizes for performance
- **Type-Safe Labels**: Dynamic label assignment with APOC fallback
- **Progress Tracking**: Structured JSON output with timing metrics
- **Index Creation**: Automatic database index setup

#### Data Schema

The synthetic mode generates data following this graph schema:

```cypher
(User)-[:WORKS_AT]->(Institution)
(User)-[:RUNS]->(Task)
(Task)<-[:INPUT]-(File)
(Task)-[:OUTPUT]->(File)
```

##### Entity Types
- **Institution**: Research institutions with random properties
- **User**: Platform users with realistic names and affiliations
- **Task**: Computational tasks (Blast, SearchbyTaxon, CreateDb, etc.)
- **File**: Data files with metadata (Fasta, BlastDb, Xml, etc.)

#### Synthetic Data Generation

```python
# Generate realistic test data
institutions, users, tasks, files, links = generate_synthetic(
    institutions_count=50,
    users_count=200,
    tasks_per_user_range=(0, 10),  # 0-10 tasks per user
    rng=random.Random(42)          # Reproducible generation
)
```

**Features**:
- **Configurable Counts**: Adjustable entity counts for different scales
- **Realistic Properties**: Faker-generated names, emails, and metadata
- **Relationship Generation**: Proper graph relationships with constraints
- **Type-Specific Logic**: Task and file type handling with appropriate properties
- **Reproducible Seeds**: Deterministic generation for testing

#### File-Based Loading

```json
// nodes.jsonl - One JSON object per line
{"labels": ["User"], "key": {"user_id": "uuid"}, "props": {"name": "John Doe"}}
{"labels": ["Task"], "key": {"task_id": "uuid"}, "props": {"status": "running"}}

// relationships.jsonl - One JSON object per line
{"type": "RUNS", "from": {"label": "User", "key": {"user_id": "uuid"}}, "to": {"label": "Task", "key": {"task_id": "uuid"}}, "props": {}}
```

**Features**:
- **JSONL Format**: Line-delimited JSON for streaming processing
- **Flexible Schema**: Support for arbitrary node/relationship types
- **Key-Based Merging**: MERGE operations using specified keys
- **Batch Loading**: Efficient bulk operations with error handling

#### Cypher Loading Operations

```python
# Batch loading with MERGE operations
cypher = """
UNWIND $rows AS row
MERGE (u:User {user_id: row.user_id})
SET u.user_name = row.user_name,
    u.firstName = row.firstName,
    u.lastName = row.lastName
SET u += row.props
"""

for batch in batch(rows, batch_size):
    db.run(cypher, {"rows": batch})
```

**Features**:
- **MERGE Semantics**: Idempotent upserts preventing duplicates
- **Dynamic Labels**: APOC-assisted label assignment with fallbacks
- **Relationship Loading**: Bidirectional relationship creation
- **Error Recovery**: Graceful handling of missing APOC procedures

#### Usage Examples

##### Synthetic Data Loading
```bash
# Generate test data with defaults
python -m src.scripts.etl_load \
  --mode synthetic \
  --bolt "bolt://localhost:7687"

# Custom scale with reproducibility
python -m src.scripts.etl_load \
  --mode synthetic \
  --institutions 100 \
  --users 500 \
  --tasks-per-user 1:5 \
  --seed 12345 \
  --drop \
  --create-indexes
```

##### File-Based Loading
```bash
# Load from JSONL files
python -m src.scripts.etl_load \
  --mode files \
  --nodes data/export/nodes.jsonl \
  --rels data/export/relationships.jsonl \
  --batch-size 1000
```

##### Docker Integration
```bash
# Connect to Memgraph in Docker
export MEMGRAPH_BOLT_URL="bolt://localhost:7687"
export MEMGRAPH_USER=""
export MEMGRAPH_PASSWORD=""

python -m src.scripts.etl_load \
  --mode synthetic \
  --users 1000 \
  --batch-size 200
```

### 2. OpenAPI Export (`export_openapi.py`)

Exports OpenAPI schema from the FastAPI application in JSON and YAML formats.

#### Architecture
```
FastAPI App → Schema Generation → Format Export → File Output
     ↓              ↓              ↓              ↓
  create_app()    app.openapi()    JSON/YAML       Pretty Print
  Module Import   Cached Schema    PyYAML Lib      Indentation
```

#### Features
- **Factory Support**: Works with both app factories and module-level instances
- **Dual Format Export**: JSON and YAML output options
- **Schema Customization**: Version override and server removal
- **Pretty Printing**: Formatted output for human readability
- **Directory Creation**: Automatic parent directory creation

#### Usage Examples

##### Basic Export
```bash
# Export JSON schema
python -m src.scripts.export_openapi \
  --out api/openapi.json \
  --pretty

# Export both formats
python -m src.scripts.export_openapi \
  --out api/openapi.json \
  --yaml api/openapi.yaml \
  --pretty
```

##### CI/CD Integration
```bash
# Environment-agnostic schema for artifacts
python -m src.scripts.export_openapi \
  --out build/openapi.json \
  --strip-servers \
  --version "1.2.3" \
  --yaml build/openapi.yaml
```

### 3. Database Backup (`backup_db.sh`)

Comprehensive backup script for Memgraph and Redis databases with tamper-evident bundling.

#### Architecture
```
Data Sources → Artifact Collection → Manifest Generation → Bundle Creation
     ↓              ↓              ↓              ↓
  Memgraph        Checksums        Metadata JSON      Tar+Gzip
  Redis RDB       SHA-256          Environment Info   Timestamped
```

#### Features
- **Multi-Source Backup**: Memgraph filesystem and Redis RDB dumps
- **Container Support**: Docker exec for containerized databases
- **Tamper Detection**: SHA-256 checksums for integrity verification
- **Metadata Manifest**: Environment and configuration information
- **Timestamped Archives**: UTC-timestamped backup bundles
- **Cross-Platform**: Works on Linux and macOS

#### Backup Contents

```
backup-bundle.tgz/
├── memgraph.tar.gz      # Memgraph data and config
├── redis_dump.rdb       # Redis database dump (optional)
├── manifest.json        # Backup metadata
└── checksums.sha256     # Integrity checksums
```

#### Usage Examples

##### Basic Backup
```bash
# Backup to default directory
./src/scripts/backup_db.sh

# Custom output directory
./src/scripts/backup_db.sh --output /backups

# With descriptive label
./src/scripts/backup_db.sh --label "pre-deployment"
```

##### Docker Integration
```bash
# Backup from Docker containers
./src/scripts/backup_db.sh \
  --container memgraph \
  --label "docker-backup"

# Skip Redis backup
./src/scripts/backup_db.sh \
  --container memgraph \
  --no-redis
```

##### Environment Configuration
```bash
# Configure via environment
export MEMGRAPH_CONTAINER="cineca-memgraph"
export REDIS_URL="redis://localhost:6379"
export BACKUP_OUTPUT_DIR="/data/backups"

./src/scripts/backup_db.sh
```

### 4. Health Check (`check_health.sh`)

Comprehensive health monitoring for API endpoints and infrastructure components.

#### Architecture
```
Health Checks → Parallel Execution → Result Aggregation → Exit Code Logic
     ↓              ↓              ↓              ↓
  HTTP Endpoints   Container State   TCP Probes        0=OK, 1=Fail, 2=Degraded
  Docker Status    Port Connectivity JSON Output       Structured Logging
```

#### Features
- **Multi-Layer Checks**: API endpoints, containers, and network ports
- **Parallel Execution**: Concurrent health checks for performance
- **Structured Output**: JSON format for monitoring integration
- **Configurable Timeouts**: Adjustable request timeouts and retries
- **Exit Code Semantics**: Different codes for failure types

#### Health Check Types

##### API Endpoints
- **`/livez`**: Liveness probe (basic service availability)
- **`/readyz`**: Readiness probe (service can accept traffic)
- **`/healthz`**: Comprehensive health check

##### Container Status
- **Running State**: Container is actively running
- **Health Status**: Docker health check results (if configured)

##### Network Probes
- **TCP Connectivity**: Port-level connectivity checks
- **Service Discovery**: Memgraph Bolt (7687) and Redis (6379) ports

#### Usage Examples

##### Basic Health Check
```bash
# Check local deployment
./src/scripts/check_health.sh

# Custom API endpoint
./src/scripts/check_health.sh \
  --url http://api.example.com \
  --timeout 10
```

##### Container Monitoring
```bash
# Monitor Docker containers
./src/scripts/check_health.sh \
  --app-container cineca-api \
  --memgraph-container cineca-memgraph \
  --redis-container cineca-redis
```

##### Network Probing
```bash
# Include port connectivity checks
./src/scripts/check_health.sh \
  --probe-memgraph-port localhost:7687 \
  --probe-redis-port localhost:6379 \
  --json
```

##### CI/CD Integration
```bash
# JSON output for automated processing
./src/scripts/check_health.sh \
  --url $API_URL \
  --json \
  --verbose
```

### 5. Database Restore (`restore_db.sh`)

Restores database backups created by the backup script with integrity verification.

#### Architecture
```
Backup Bundle → Integrity Check → Data Extraction → Target Restore
     ↓              ↓              ↓              ↓
  Tar Archive     SHA-256 Verify   File Untar       Docker/Local
  Checksums       Manifest Validate Permission Check Container Copy
```

#### Features
- **Integrity Verification**: SHA-256 checksum validation
- **Flexible Targets**: Docker containers or local filesystem
- **Safety Checks**: Permission validation and running container warnings
- **Selective Restore**: Memgraph-only or full restore options
- **Redis Support**: RDB file placement with restart handling

#### Restore Modes

##### Docker Restore
```bash
# Restore to running container (with warning)
./src/scripts/restore_db.sh backup.tgz \
  --container memgraph \
  --force-hot

# Restore to stopped container (recommended)
docker stop memgraph
./src/scripts/restore_db.sh backup.tgz \
  --container memgraph
docker start memgraph
```

##### Local Restore
```bash
# Restore to local filesystem (requires root)
sudo ./src/scripts/restore_db.sh backup.tgz \
  --local
```

##### Redis Restore
```bash
# Restore Redis RDB to container
./src/scripts/restore_db.sh backup.tgz \
  --restore-redis \
  --redis-container redis \
  --redis-dir /data \
  --restart-redis
```

## Configuration

### Environment Variables

| Variable | Scripts | Default | Description |
|----------|---------|---------|-------------|
| `MEMGRAPH_BOLT_URL` | etl_load.py | bolt://localhost:7687 | Memgraph connection URL |
| `MEMGRAPH_USER` | etl_load.py | "" | Memgraph username |
| `MEMGRAPH_PASSWORD` | etl_load.py | "" | Memgraph password |
| `MEMGRAPH_CONTAINER` | backup_db.sh, restore_db.sh | "" | Docker container name |
| `MEMGRAPH_DATA_DIR` | backup_db.sh, restore_db.sh | /var/lib/memgraph | Data directory |
| `MEMGRAPH_CONF_DIR` | backup_db.sh, restore_db.sh | /etc/memgraph | Config directory |
| `REDIS_URL` | backup_db.sh | "" | Redis connection URL |
| `BACKUP_OUTPUT_DIR` | backup_db.sh | ./backups | Backup output directory |
| `API_BASE_URL` | check_health.sh | http://localhost:8000 | API base URL |

### Command-Line Options

#### ETL Loader
```bash
python -m src.scripts.etl_load [options]

Options:
  --mode {synthetic,files}    Load mode (default: synthetic)
  --bolt URL                  Bolt connection URL
  --user USER                 Database username
  --password PASS             Database password
  --drop                      Drop existing data
  --create-indexes            Create database indexes
  --institutions N            Number of institutions (synthetic)
  --users N                   Number of users (synthetic)
  --tasks-per-user MIN:MAX    Tasks per user range (synthetic)
  --seed N                    Random seed for reproducibility
  --nodes FILE                Nodes JSONL file (files mode)
  --rels FILE                 Relationships JSONL file (files mode)
  --batch-size N              Batch size for operations
```

#### OpenAPI Export
```bash
python -m src.scripts.export_openapi [options]

Options:
  --out FILE                  Output JSON file
  --yaml FILE                 Output YAML file
  --pretty                    Pretty-print JSON
  --strip-servers             Remove servers from schema
  --version VER               Override API version
```

#### Database Backup
```bash
./src/scripts/backup_db.sh [options]

Options:
  -o, --output DIR            Output directory
  -c, --container NAME        Memgraph container name
  -l, --label TEXT            Backup label
      --no-redis              Skip Redis backup
  -h, --help                  Show help
```

#### Health Check
```bash
./src/scripts/check_health.sh [options]

Options:
  --url URL                   API base URL
  --timeout SEC               Request timeout
  --retries N                 Retry count
  --app-container NAME        App container name
  --memgraph-container NAME   Memgraph container name
  --redis-container NAME      Redis container name
  --no-docker                 Skip Docker checks
  --probe-memgraph-port HOST:PORT  Memgraph port probe
  --probe-redis-port HOST:PORT    Redis port probe
  --json                      JSON output
  --verbose                   Verbose logging
  -h, --help                  Show help
```

#### Database Restore
```bash
./src/scripts/restore_db.sh <backup.tgz> [options]

Options:
  --container NAME            Memgraph container name
  --local                     Restore to local filesystem
  --force-hot                 Allow restore to running container
  --restore-redis             Restore Redis RDB
  --redis-container NAME      Redis container name
  --redis-dir DIR             Redis data directory
  --restart-redis             Restart Redis after restore
  --no-verify                 Skip integrity verification
  -h, --help                  Show help
```

## Performance Characteristics

### ETL Loader
- **Batch Processing**: Configurable batch sizes (default 500)
- **Memory Usage**: Bounded by batch size and entity counts
- **Network Efficiency**: Single Cypher statements per batch
- **Index Creation**: One-time operation with error tolerance
- **Progress Tracking**: Real-time operation counting

### Backup Script
- **Compression**: Gzip compression for storage efficiency
- **Incremental**: Only processes existing data directories
- **Container Overhead**: Docker exec for containerized databases
- **Checksum Calculation**: SHA-256 for tamper detection
- **Archive Size**: Depends on data volume and compression ratio

### Health Check
- **Parallel Execution**: Concurrent checks for reduced latency
- **Timeout Control**: Configurable timeouts prevent hanging
- **Lightweight Probes**: Minimal resource impact on services
- **Caching**: No caching - real-time health assessment

### Restore Script
- **Integrity First**: Checksum verification before extraction
- **Safe Operations**: Permission checks and container state validation
- **Minimal Downtime**: Supports hot restore with warnings
- **Selective Restore**: Component-level restore options

## Security Considerations

### Authentication
- **Environment Variables**: Sensitive credentials via env vars
- **File Permissions**: Backup archives with restricted permissions (umask 077)
- **Container Access**: Docker exec with appropriate user permissions
- **Network Security**: Bolt/Redis URLs may contain credentials

### Data Protection
- **Encryption**: Backups should be encrypted for sensitive data
- **Access Control**: Restore operations require appropriate permissions
- **Audit Logging**: Backup/restore operations should be logged
- **Integrity Checks**: SHA-256 verification prevents tampering

### Operational Security
- **Container Isolation**: Scripts respect container boundaries
- **Permission Validation**: Checks for required filesystem permissions
- **Safe Defaults**: Conservative defaults prevent accidental data loss
- **Error Handling**: Safe failure modes prevent partial operations

## Integration Examples

### CI/CD Pipeline
```yaml
# .github/workflows/backup.yml
name: Database Backup
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run backup
        run: ./src/scripts/backup_db.sh --label "daily-${{ github.run_number }}"
      - name: Upload backup
        uses: actions/upload-artifact@v3
        with:
          name: cineca-backup
          path: backups/
```

### Docker Compose Health Checks
```yaml
# docker-compose.yml
services:
  api:
    image: cineca-api
    healthcheck:
      test: ["CMD", "/app/src/scripts/check_health.sh", "--url", "http://localhost:8000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Monitoring Integration
```python
# monitoring/health_check.py
import subprocess
import json

def check_platform_health():
    """Check platform health using the health script."""
    result = subprocess.run(
        ['./src/scripts/check_health.sh', '--json'],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        health_data = json.loads(result.stdout)
        return health_data
    else:
        raise Exception(f"Health check failed: {result.stderr}")
```

## Troubleshooting

### Common Issues

#### ETL Loader
1. **Neo4j Driver Import Error**
   ```bash
   pip install neo4j
   ```

2. **Connection Refused**
   - Check Memgraph is running
   - Verify BOLT URL and credentials
   - Check firewall settings

3. **APOC Unavailable**
   - Script falls back to static labels
   - Some dynamic labeling may not work
   - Consider installing APOC procedures

#### Backup Script
1. **Docker Connection Failed**
   ```bash
   docker ps  # Check container is running
   docker exec -it <container> ls /var/lib/memgraph
   ```

2. **Permission Denied**
   ```bash
   sudo ./src/scripts/backup_db.sh  # May need root for local backup
   ```

3. **Redis Backup Failed**
   - Check redis-cli is installed
   - Verify REDIS_URL format
   - Some Redis versions don't support --rdb

#### Health Check
1. **API Endpoints Failing**
   - Check service is running
   - Verify URL is correct
   - Check application logs

2. **Container Not Found**
   ```bash
   docker ps --filter "name=<container>"
   ```

3. **Port Probes Failing**
   - Check services are bound to correct ports
   - Verify network connectivity
   - Check firewall rules

#### Restore Script
1. **Checksum Verification Failed**
   - Backup may be corrupted
   - Check storage integrity
   - Use --no-verify to skip (not recommended)

2. **Container Restore Issues**
   ```bash
   docker cp backup.tgz <container>:/tmp/
   docker exec <container> tar -tzf /tmp/backup.tgz
   ```

3. **Permission Issues**
   ```bash
   sudo ./src/scripts/restore_db.sh backup.tgz --local
   ```

### Debug Mode

#### Verbose Logging
```bash
# Enable verbose output for health checks
./src/scripts/check_health.sh --verbose --json

# Debug ETL loading
python -m src.scripts.etl_load --mode synthetic --users 10 --seed 42
```

#### Performance Monitoring
```bash
# Time backup operations
time ./src/scripts/backup_db.sh --label "perf-test"

# Monitor ETL progress
python -c "
import time
start = time.time()
# Run ETL command
end = time.time()
print(f'ETL completed in {end - start:.2f} seconds')
"
```

## Future Enhancements

- **Parallel Loading**: Multi-threaded ETL operations
- **Incremental Backups**: Change-based backup strategies
- **Cloud Storage**: Direct backup to cloud storage
- **Automated Testing**: Self-testing backup integrity
- **Metrics Export**: Prometheus metrics for operations
- **Webhook Integration**: Notification system for backup events
- **Encryption**: Built-in encryption for sensitive backups
- **Compression Options**: Configurable compression algorithms</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_scripts.md