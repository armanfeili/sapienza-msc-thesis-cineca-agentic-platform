# README_Cineca-Agentic-Platform_docker

## Overview

The Docker configuration for the Cineca Agentic Platform provides a complete containerized deployment environment supporting development, testing, and production scenarios. The setup includes multi-stage builds, service orchestration, GPU support, reverse proxy configuration, and comprehensive monitoring infrastructure.

## Architecture

### Core Services

#### Application Service (`app`)
- **Base Image**: Python 3.11 slim
- **Framework**: FastAPI with uvicorn
- **Port**: 8000
- **Health Checks**: Comprehensive health endpoints with database connectivity
- **Dependencies**: PostgreSQL, Memgraph, Redis, Ollama
- **Features**:
  - OIDC authentication with Auth0
  - Rate limiting with Redis backend
  - LLM provider integration (Ollama, local models)
  - Job processing and background workers
  - OpenTelemetry observability
  - Admin routes and internal utilities

#### Database Services

##### PostgreSQL (`postgres`)
- **Image**: postgres:16-alpine
- **Port**: 5432 (configurable)
- **Features**:
  - UTF-8 encoding with proper collation
  - Persistent data volumes
  - Health checks with pg_isready
  - Initialization scripts
  - Connection pooling configuration

##### Memgraph (`memgraph`)
- **Image**: memgraph/memgraph-platform:latest
- **Ports**: 7687 (Bolt), 3000 (Web UI)
- **Features**:
  - Graph database for agent and session data
  - Cypher query support
  - Web-based management interface
  - Persistent storage
  - Health monitoring

##### Redis (`redis`)
- **Image**: redis:7-alpine
- **Port**: 6379
- **Features**:
  - In-memory data store
  - Append-only file persistence
  - Rate limiting backend
  - Session storage
  - Job queue management

#### AI/ML Services

##### Ollama (`ollama`)
- **Image**: ollama/ollama:latest
- **Port**: 11434
- **Features**:
  - Local LLM serving
  - Model management and caching
  - GPU acceleration support
  - Memory optimization (reduced context window)
  - Parallel processing limits

#### Background Processing

##### Worker (`worker`)
- **Base**: Same as app service
- **Command**: Python jobs worker
- **Features**:
  - Asynchronous job processing
  - Heartbeat monitoring
  - PostgreSQL job storage
  - Configurable polling intervals

##### Database Population (`db-populate`)
- **Purpose**: Initial data seeding
- **Trigger**: One-time execution
- **Dependencies**: Memgraph healthy
- **Features**: Graph database schema and sample data

#### Monitoring & Observability

##### Prometheus (`prometheus`)
- **Image**: prom/prometheus:latest
- **Port**: 9090
- **Features**:
  - Metrics collection
  - Alerting rules
  - Recording rules
  - Web interface
  - Lifecycle management

##### Grafana (`grafana`)
- **Image**: grafana/grafana:11.0.0
- **Port**: 3001 (maps to 3000 internal)
- **Features**:
  - Dashboard visualization
  - Data source provisioning
  - Admin authentication
  - Custom dashboards
  - Observability integration

#### User Interface

##### UI Control Panel (`ui_control_panel`)
- **Build Context**: ui_control_panel/
- **Framework**: Streamlit
- **Port**: 8501
- **Features**:
  - Administrative web interface
  - Auth0 authentication integration
  - Real-time monitoring
  - API exploration tools
  - Multi-tenant management

## Configuration Files

### Main Compose File (`docker-compose.yml`)

#### Environment Variables
```bash
# Database Configuration
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_PASSWORD=change_me_now
DB_SSLMODE=disable
DB_POOL_SIZE=10
DB_POOL_TIMEOUT=30

# Memgraph Configuration
MG_HOST=memgraph
MG_PORT=7687
MG_USER=
MG_PASSWORD=

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# LLM Configuration
LLM_PROVIDER=local-llamacpp
OLLAMA_BASE_URL=http://ollama:11434/v1
OLLAMA_TIMEOUT_SECS=180
DEFAULT_MODEL_NAME=phi3:mini

# Health Check Configuration
HEALTH_TIMEOUT_MS=3000
HEALTH_DB_TIMEOUT_MS=3000
HEALTH_CACHE_TIMEOUT_MS=1000
HEALTH_ALLOW_MG_HEALTH_FALLBACK=true

# Job Configuration
ALLOWED_JOB_TYPES=demo,test,long-running
JOB_STORE_BACKEND=memory
USE_POSTGRES_JOBS=false

# Security Configuration
RATE_LIMIT_MODE=prod
SAFE_TOOLS=system.health,system.status,system.metrics,graph.schema,graph.search

# OIDC Configuration
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
```

#### Volumes
- `postgres_data`: PostgreSQL persistent storage
- `memgraph_data`: Memgraph graph data
- `redis_data`: Redis persistence
- `prometheus_data`: Metrics data
- `grafana_data`: Dashboard data
- `ollama_data`: Model storage

#### Networks
- `app-net`: Bridge network for service communication

### Development Overrides (`docker-compose.override.dev.yml`)

#### Development Features
- **Hot Reload**: Volume mounting for live code changes
- **Debug Mode**: Enhanced logging and development settings
- **Demo Mode**: Enabled for testing scenarios
- **Relaxed Security**: Extended token TTL for development
- **Auto-start**: Optional background process management

#### Key Differences
```yaml
app:
  volumes:
    - ./:/app:delegated
  command: uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
  environment:
    PYTHONUNBUFFERED: '1'
    ENABLE_DOCS: '1'
    APP_ENV: 'dev'
    DEMO_MODE: 'true'
    RATE_LIMIT_MODE: 'test'
    INTERNAL_TOKEN_MAX_TTL_SECONDS: '86400'
```

### Production Nginx Setup (`docker-compose.nginx.yml`)

#### Reverse Proxy Configuration
- **Nginx Image**: Custom build from `./ops/nginx`
- **Ports**: 80, 443
- **SSL Support**: Certificate mounting
- **Load Balancing**: Service routing

#### Security Enhancements
```yaml
app:
  ports: []  # Remove direct exposure
  environment:
    ENABLE_CORS: 'false'
    TRUST_PROXY: 'true'
    SECURE_COOKIES: 'true'

ui_control_panel:
  ports: []  # Remove direct exposure
  environment:
    STREAMLIT_SERVER_ENABLE_CORS: 'false'
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION: 'true'
```

#### Network Configuration
- **External Network**: `platform-network`
- **SSL Volumes**: Certificate management
- **Log Volumes**: Nginx access/error logs

### GPU Support (`docker-compose.gpu.yml`)

#### GPU Configuration
```yaml
app:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  environment:
    NVIDIA_VISIBLE_DEVICES: all
    NVIDIA_DRIVER_CAPABILITIES: compute,utility
```

#### Requirements
- NVIDIA Docker runtime
- CUDA-compatible hardware
- GPU-enabled base images

## Dockerfile Architecture

### Multi-Stage Build

#### App Stage
```dockerfile
FROM python:3.11-slim AS app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tini \
    curl \
    ca-certificates \
    build-essential \
    pkg-config \
    libssl-dev \
    python3-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY src/ ./src/
COPY db/ ./db/
COPY docker-entrypoint.sh ./

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:8000/health" || exit 1

# Entrypoint
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Test Runner Stage
```dockerfile
FROM python:3.11-slim as test-runner

# Test dependencies
RUN apt-get install -y redis-server
RUN pip install pytest pytest-asyncio fakeredis

# Test execution
CMD ["sh", "-c", "redis-server --daemonize yes && pytest -q"]
```

### Build Optimization
- **Layer Caching**: Dependencies installed before code
- **BuildKit**: Modern Docker build features
- **Multi-stage**: Separate app and test images
- **Security**: Non-root user execution

## Entry Point Script (`docker-entrypoint.sh`)

### Database Initialization
```bash
#!/usr/bin/env bash

echo "🚀 Starting Cineca Agentic Platform..."

# Database migrations
if [ -n "$DB_HOST" ]; then
    echo "📦 Running database migrations..."
    cd /app/db/postgres_control && alembic upgrade head
    
    # Default model initialization
    echo "🤖 Initializing default model..."
    python scripts/ollama/init_default_model.py
fi

# Execute main command
exec "$@"
```

### Features
- **Migration Execution**: Alembic database upgrades
- **Model Setup**: Ollama default model initialization
- **Error Handling**: Continues on non-critical failures
- **Signal Handling**: Proper process management with tini

## Deployment Scenarios

### Development Environment
```bash
# Start development stack
docker compose -f docker-compose.yml -f docker-compose.override.dev.yml up -d

# View logs
docker compose logs -f app

# Run tests
docker compose run --rm test-runner
```

### Production Environment
```bash
# Start production stack with nginx
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d

# Scale services
docker compose up -d --scale worker=3
```

### GPU-Enabled Deployment
```bash
# Start with GPU support
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Service Dependencies

### Startup Order
1. **Infrastructure**: PostgreSQL, Redis, Memgraph
2. **AI Services**: Ollama
3. **Application**: Main app service
4. **Workers**: Background job processing
5. **UI**: Control panel interface
6. **Monitoring**: Prometheus, Grafana

### Health Checks
- **PostgreSQL**: `pg_isready` connectivity check
- **Memgraph**: Cypher query execution test
- **Redis**: PING command response
- **Ollama**: Model listing capability
- **App**: HTTP health endpoint
- **UI**: Streamlit health check

## Networking

### Internal Communication
- **Bridge Network**: `app-net` for service-to-service communication
- **Service Discovery**: Docker DNS resolution
- **Port Mapping**: External access configuration

### External Access
- **Development**: Direct port exposure (8000, 8501, etc.)
- **Production**: Nginx reverse proxy with SSL termination
- **Load Balancing**: Service scaling support

## Volumes and Persistence

### Data Volumes
- **PostgreSQL**: `postgres_data` - Database files
- **Memgraph**: `memgraph_data` - Graph data
- **Redis**: `redis_data` - Cache persistence
- **Ollama**: `ollama_data` - Model storage
- **Prometheus**: `prometheus_data` - Metrics data
- **Grafana**: `grafana_data` - Dashboard configuration

### Configuration Volumes
- **Prometheus**: Alerting and recording rules
- **Grafana**: Data source and dashboard provisioning
- **Nginx**: SSL certificates and configuration
- **Ollama**: Model artifacts (read-only)

## Security Considerations

### Container Security
- **Non-root Users**: Application runs as `app` user
- **Minimal Images**: Slim base images with essential packages
- **Read-only Volumes**: Model data mounted read-only
- **Network Isolation**: Bridge network segmentation

### Authentication
- **OIDC Integration**: Auth0 authentication provider
- **Token Management**: Secure token handling
- **Rate Limiting**: Redis-backed request throttling
- **CORS Configuration**: Environment-based CORS settings

### Secrets Management
- **Environment Variables**: Sensitive configuration via env vars
- **Volume Mounting**: SSL certificates for nginx
- **Network Security**: Internal service communication

## Monitoring and Observability

### Health Monitoring
- **Application Health**: Multiple health check endpoints
- **Database Connectivity**: PostgreSQL and Memgraph health
- **Cache Availability**: Redis connectivity checks
- **AI Service Status**: Ollama model availability

### Metrics Collection
- **Prometheus**: Time-series metrics storage
- **Custom Metrics**: Application-specific monitoring
- **Alerting**: Configurable alert rules
- **Recording Rules**: Metric aggregation

### Visualization
- **Grafana Dashboards**: Pre-configured monitoring views
- **Real-time Metrics**: Live system monitoring
- **Historical Data**: Trend analysis and reporting

## Performance Optimization

### Resource Management
- **Memory Limits**: Ollama memory constraints (10G limit, 7G reservation)
- **CPU Limits**: Ollama CPU restrictions (8 cores, 4 reserved)
- **Connection Pooling**: Database connection management
- **Caching**: Redis-based caching strategies

### Scaling Considerations
- **Horizontal Scaling**: Worker service scaling
- **Load Balancing**: Nginx upstream configuration
- **Database Scaling**: Connection pool sizing
- **Cache Distribution**: Redis cluster support

## Troubleshooting

### Common Issues

#### Service Startup Failures
- **Health Check Timeouts**: Increase `start_period` in health checks
- **Dependency Failures**: Check service dependency order
- **Resource Constraints**: Monitor memory and CPU usage

#### Database Connection Issues
- **PostgreSQL**: Verify connection string and credentials
- **Memgraph**: Check Bolt protocol connectivity
- **Redis**: Validate Redis URL configuration

#### AI Service Problems
- **Ollama**: Check model loading and GPU availability
- **Model Loading**: Verify model file paths and permissions
- **Memory Issues**: Monitor Ollama memory usage

### Debugging Commands
```bash
# View service logs
docker compose logs -f [service_name]

# Execute commands in containers
docker compose exec app bash

# Check service health
docker compose ps

# View resource usage
docker stats
```

### Log Analysis
- **Application Logs**: Structured logging with configurable levels
- **Container Logs**: Docker logging drivers
- **Nginx Logs**: Access and error log analysis
- **Database Logs**: Query performance and error tracking

## Development Workflow

### Local Development
1. **Environment Setup**: Copy `.env.example` to `.env`
2. **Service Startup**: Use development compose overrides
3. **Code Changes**: Hot reload with volume mounting
4. **Testing**: Run test suite with test-runner service
5. **Debugging**: Access container shells for debugging

### CI/CD Integration
- **Automated Testing**: Test runner container for CI pipelines
- **Image Building**: Multi-stage Dockerfile for efficient builds
- **Security Scanning**: Container image vulnerability assessment
- **Deployment**: Automated deployment with compose files

## Migration and Updates

### Database Migrations
- **Alembic**: Version-controlled schema changes
- **Migration Scripts**: Automated upgrade process
- **Rollback Support**: Version downgrade capability
- **Data Integrity**: Migration validation and testing

### Service Updates
- **Rolling Updates**: Zero-downtime service updates
- **Health Checks**: Automated health verification
- **Rollback Procedures**: Quick reversion strategies
- **Version Pinning**: Specific image version control

## Backup and Recovery

### Data Backup
- **PostgreSQL**: Database dump and restore procedures
- **Memgraph**: Graph data export/import
- **Redis**: RDB file backup
- **Configuration**: Environment and compose file backups

### Disaster Recovery
- **Volume Snapshots**: Persistent data snapshots
- **Service Recreation**: Automated service recovery
- **Data Validation**: Backup integrity verification
- **Failover**: Multi-region deployment support

This comprehensive Docker configuration provides a production-ready, scalable, and maintainable deployment environment for the Cineca Agentic Platform, supporting everything from local development to enterprise production deployments with monitoring, security, and high availability features.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_Cineca-Agentic-Platform_docker.md