# README_Cineca-Agentic-Platform_scripts

## Overview

The scripts and configuration files for the Cineca Agentic Platform provide a comprehensive development toolkit supporting authentication management, build automation, testing infrastructure, dependency management, and project configuration. These tools enable efficient development workflows, automated testing, security validation, and deployment processes.

## Authentication Management

### Auth0 Token Fetcher (`fetch_auth0_tokens.sh`)

#### Overview
A comprehensive Bash script for fetching and managing Auth0 authentication tokens for testing and development purposes.

#### Features
- **Multi-token Support**: Fetches Admin, User, and Machine tokens with different scopes
- **Token Validation**: Decodes JWT tokens to display permissions and expiry information
- **Environment Integration**: Loads configuration from `.env` file with validation
- **Flexible Output**: Display tokens in console, save to `.env`, or export to shell
- **Error Handling**: Comprehensive error checking and user-friendly messages
- **Backup Management**: Automatic backup of `.env` file before modifications

#### Token Types
```bash
# Admin Token (Full Access)
# Scopes: user:me, tools:invoke:all, admin:all
# Use: Administrative operations, full platform access

# User Token (Basic Access)  
# Scopes: user:me, tools:invoke:basic
# Use: Standard user operations, limited tool access

# Machine Token (Service-to-Service)
# Scopes: Configurable via client credentials
# Use: Automated processes, API integrations
```

#### Configuration Requirements
```bash
# Auth0 Domain and Audience
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_AUDIENCE=https://api.your-platform.com

# User Client Credentials (for password grants)
AUTH0_USER_CLIENT_ID=your-user-client-id
AUTH0_USER_CLIENT_SECRET=your-user-client-secret

# Machine Client Credentials (for client credentials)
AUTH0_MACHINE_CLIENT_ID=your-machine-client-id
AUTH0_MACHINE_CLIENT_SECRET=your-machine-client-secret

# Test User Credentials
AUTH0_ADMIN_USERNAME=admin@example.com
AUTH0_ADMIN_PASSWORD=admin-password
AUTH0_USER_USERNAME=user@example.com
AUTH0_USER_PASSWORD=user-password
```

#### Usage Examples
```bash
# Display tokens in console
./fetch_auth0_tokens.sh

# Save tokens to .env file
./fetch_auth0_tokens.sh --save-to-env

# Export to current shell session
./fetch_auth0_tokens.sh --export

# Use tokens in API calls
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/user/me
```

#### Security Features
- **Token Masking**: Sensitive data redaction in logs
- **Environment Validation**: Required variables checking
- **Backup Creation**: Automatic `.env` file backups
- **Error Sanitization**: Safe error message display
- **Shell Injection Prevention**: Proper variable quoting

## Build Automation (`Makefile`)

### Overview
Comprehensive Makefile providing development workflow automation, testing, deployment, and maintenance tasks for the Cineca Agentic Platform.

### Core Targets

#### Environment Setup
```makefile
env              # Create .env from example if missing
install          # Install Python dependencies
pre-commit-install  # Install and enable pre-commit hooks
```

#### Development Server
```makefile
dev              # Run FastAPI with auto-reload
ready            # Probe health endpoints locally
```

#### Docker Compose Management
```makefile
up               # Start all services
up-cpu           # CPU-optimized deployment
up-gpu           # GPU-enabled deployment
up-observability # Monitoring stack only
up-redis         # Redis service only
down             # Stop services
clean            # Stop and remove volumes/orphans
restart          # Restart app service
logs             # Tail service logs
ps               # Show process status
```

#### Code Quality
```makefile
fmt              # Auto-format with black + ruff
lint             # Lint with ruff (with fixes)
typecheck        # Static type checking with mypy
check            # Run all quality checks
```

#### Testing
```makefile
test             # Quick test run
test-all         # Full test suite
test-ollama      # Ollama-specific tests
test-memgraph-nl # NL→Cypher integration tests
test-memgraph-nl-smoke # Smoke test subset
security         # Security linting and auditing
```

#### Database Operations
```makefile
# Memgraph
seed             # Seed original database
populate         # Populate demo data
backup           # Create database backup
restore          # Restore from backup

# PostgreSQL
db-migrate       # Run Alembic migrations
db-migrate-down  # Rollback migration
db-reset         # Reset database (DESTRUCTIVE)
db-seed          # Seed demo tenants
db-revision      # Create new migration
db-shell         # Open PostgreSQL shell
db-logs          # Show database logs
```

#### Model Management
```makefile
bootstrap-models # Download model artifacts
ollama-models    # Create Ollama models
llm-smoke-test   # Verify LLM configuration
runtime-smoke    # End-to-end model testing
```

#### Documentation
```makefile
openapi          # Export OpenAPI specification
openapi-docker   # Export via Docker container
```

### Advanced Features

#### Integration Testing
```makefile
test-memgraph-nl:
    # Automated pipeline:
    # 1. Fetch fresh Auth0 tokens
    # 2. Restart application
    # 3. Run NL→Cypher tests
    # 4. Display results and logs
```

#### CI/CD Support
```makefile
ci:              # Aggregate CI target
test-ci:         # Docker-based integration tests
```

#### Environment Profiles
```makefile
up-cpu:          # CPU-optimized configuration
up-gpu:          # GPU-enabled configuration
```

### Configuration Variables
```makefile
PROJECT_NAME     ?= cineca-agentic-platform
APP_HOST         ?= 0.0.0.0
APP_PORT         ?= 8000
BACKUP_DIR       ?= backups
```

## Testing Infrastructure

### End-to-End Testing (`package.json`)

#### Overview
Node.js package configuration for Playwright-based end-to-end testing of the Cineca Agentic Platform UI.

#### Dependencies
```json
{
  "@playwright/test": "^1.48.0",
  "@types/node": "^22.0.0"
}
```

#### Scripts
```json
{
  "test:e2e": "playwright test",
  "test:e2e:ui": "playwright test --ui",
  "test:e2e:headed": "playwright test --headed",
  "test:e2e:debug": "playwright test --debug",
  "playwright:install": "playwright install --with-deps"
}
```

#### Features
- **Cross-browser Testing**: Chromium, Firefox, Safari support
- **CI Integration**: Conditional test execution
- **Debugging Tools**: UI mode, headed execution, debug mode
- **Automatic Setup**: Web server startup for local testing

### Playwright Configuration (`playwright.config.ts`)

#### Test Configuration
```typescript
export default defineConfig({
  testDir: './tests/e2e/playwright',
  timeout: 120 * 1000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  
  reporter: [
    ['html', { outputFolder: 'test-results/playwright-report' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['list']
  ],
  
  use: {
    baseURL: process.env.UI_BASE_URL || 'http://localhost:8501',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15 * 1000,
    navigationTimeout: 30 * 1000,
  },
  
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // Firefox and Safari conditionally enabled
  ],
  
  webServer: process.env.CI ? undefined : {
    command: 'docker compose up -d',
    url: 'http://localhost:8501',
    timeout: 120 * 1000,
  },
});
```

#### Browser Support Matrix
- **Primary**: Chromium (Desktop Chrome)
- **Extended**: Firefox, Safari (via `FULL_E2E=true`)
- **CI Optimization**: Single worker, retry logic

#### Test Execution Modes
- **Local Development**: Auto-start web server, UI debugging
- **CI Pipeline**: Headless execution, JUnit reporting
- **Debug Mode**: Interactive debugging with browser dev tools

## Python Project Configuration

### Dependencies (`requirements.txt`)

#### Core Application
```txt
fastapi>=0.111.0                    # Web framework
uvicorn[standard]>=0.30.0           # ASGI server
pydantic-settings>=2.2.1            # Configuration management
python-dotenv>=1.0.1                # Environment variables
```

#### Database & Caching
```txt
gqlalchemy>=1.8.0                   # Memgraph client
SQLAlchemy>=2.0.30                  # ORM
psycopg2-binary>=2.9.9              # PostgreSQL driver
alembic>=1.13.0                     # Database migrations
redis>=5.0.1                        # Redis client
```

#### Authentication & Security
```txt
python-jose[cryptography]>=3.3.0    # JWT handling
passlib[bcrypt]>=1.7.4              # Password hashing
email-validator>=2.1.1              # Email validation
```

#### AI/ML Integration
```txt
httpx>=0.27.0                       # HTTP client for LLM APIs
tenacity>=8.2.3                     # Retry logic
```

#### Observability
```txt
prometheus-client>=0.20.0           # Metrics collection
opentelemetry-api>=1.26.0           # Tracing
opentelemetry-sdk>=1.26.0
opentelemetry-instrumentation-fastapi>=0.47b0
```

#### Development & Testing
```txt
pytest>=8.2.0                       # Testing framework
pytest-asyncio>=0.22.0              # Async testing
streamlit>=1.30.0                   # UI framework
psutil>=5.9.0                       # System monitoring
pandas>=2.2.0                       # Data manipulation
```

#### Code Quality
```txt
ruff>=0.5.0                         # Linting and formatting
black>=24.4.2                       # Code formatting
mypy>=1.10.0                        # Type checking
bandit>=1.7.9                       # Security linting
pip-audit>=2.7.3                    # Dependency auditing
```

### Project Configuration (`pyproject.toml`)

#### Build System
```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"
```

#### Project Metadata
```toml
[project]
name = "cineca-agentic-platform"
version = "0.1.0"
description = "Agentic FastAPI service with Memgraph (Cypher via MCP tools), security guardrails, and observability."
python = ">=3.10"
keywords = ["fastapi", "memgraph", "cypher", "agentic", "llm", "mcp", "observability", "security"]
```

#### Optional Dependencies
```toml
[project.optional-dependencies]
dev = ["ruff>=0.5.0", "black>=24.4.2", "mypy>=1.10.0", "bandit>=1.7.9", "pip-audit>=2.7.3", "psutil>=5.9.0", "pandas>=2.2.0"]
test = ["pytest>=8.2.0", "coverage[toml]>=7.5.0", "psutil>=5.9.0", "pandas>=2.2.0"]
```

#### Code Formatting (Black)
```toml
[tool.black]
line-length = 100
target-version = ["py310", "py311"]
include = "\\.pyi?$"
extend-exclude = """
/(
  docs|
  examples|
  ops|
  db/original-dataset|
  db/populated
)/
"""
```

#### Linting (Ruff)
```toml
[tool.ruff]
target-version = "py311"
line-length = 100
select = [
  "E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM", "PTH", "RUF", "PL"
]
ignore = ["E501"]  # Line length handled by black
```

#### Type Checking (MyPy)
```toml
[tool.mypy]
python_version = "3.11"
plugins = ["pydantic.mypy"]
check_untyped_defs = true
disallow_incomplete_defs = true
disallow_untyped_defs = true
no_implicit_optional = true
warn_unused_ignores = true
```

#### Testing Configuration (Pytest)
```toml
[tool.pytest.ini_options]
addopts = "-p no:pytest_cov"
testpaths = ["tests"]
pythonpath = ["src"]
xfail_strict = true
markers = [
  "e2e: end-to-end tests",
  "integration: integration tests", 
  "performance: performance tests",
  "security: security-related tests",
  "slow: marks tests as slow",
  "memgraph_nl: NL→Memgraph Cypher translation tests"
]
```

#### Coverage Configuration
```toml
[tool.coverage.run]
branch = true
source = ["src"]
omit = ["*/tests/*", "*/test_*.py"]

[tool.coverage.report]
show_missing = true
precision = 2
fail_under = 60
```

#### Security Configuration (Bandit)
```toml
[tool.bandit]
skips = ["B101", "B601"]
targets = ["src"]
exclude_dirs = ["/tests", "/examples", "/docs", "/ops"]
```

## Development Workflow

### Getting Started
```bash
# Setup environment
make env
make install
make pre-commit-install

# Start development environment
make up

# Run development server
make dev

# Run tests
make test
```

### Code Quality Assurance
```bash
# Format code
make fmt

# Lint and type check
make lint
make typecheck

# Run security checks
make security

# Run all checks
make check
```

### Testing Strategy
```bash
# Unit tests
make test

# Integration tests
make test-all

# E2E tests
cd tests/e2e/playwright
npm run test:e2e

# NL→Cypher integration
make test-memgraph-nl
```

### Database Management
```bash
# PostgreSQL operations
make db-migrate
make db-seed

# Memgraph operations
make populate
make backup
```

## CI/CD Integration

### Automated Pipelines
```yaml
# Example GitHub Actions workflow
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: make install
      - name: Run checks
        run: make check
      - name: Run tests
        run: make test-all
```

### Docker-based Testing
```bash
# Run tests in container
make test-ci

# Export OpenAPI spec
make openapi-docker
```

## Security Validation

### Static Analysis
```bash
# Security linting
bandit -c pyproject.toml -r src

# Dependency auditing
pip-audit --progress-spinner=off

# Combined security checks
make security
```

### Authentication Testing
```bash
# Fetch test tokens
./fetch_auth0_tokens.sh --save-to-env

# Test token validation
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/user/me
```

## Performance Monitoring

### LLM Testing
```bash
# Smoke test LLM configuration
make llm-smoke-test

# End-to-end model testing
make runtime-smoke
```

### Health Checks
```bash
# Check application readiness
make ready

# Monitor service health
make logs S=app
```

## Deployment Automation

### Environment-specific Deployments
```bash
# Development
make up

# GPU-enabled
make up-gpu

# CPU-optimized
make up-cpu

# Monitoring only
make up-observability
```

### Model Management
```bash
# Bootstrap models
make bootstrap-models TARGET_DIR=/opt/models

# Create Ollama models
make ollama-models
```

## Troubleshooting

### Common Issues

#### Authentication Problems
```bash
# Refresh Auth0 tokens
./fetch_auth0_tokens.sh --save-to-env

# Check token validity
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/user/me
```

#### Test Failures
```bash
# Run specific test with debug
pytest tests/path/to/test.py -v -s

# E2E test debugging
npm run test:e2e:debug
```

#### Database Issues
```bash
# Check database status
make db-shell

# Reset database (CAUTION)
make db-reset
```

#### Performance Issues
```bash
# Check service logs
make logs

# Monitor resource usage
docker stats
```

### Debug Commands
```bash
# Environment information
make doctor

# Service status
make ps

# Detailed logs
make logs S=app
```

## Architecture Decisions

### Makefile Design
- **Modular Targets**: Organized by functionality with clear naming
- **Environment Variables**: Configurable parameters with sensible defaults
- **Error Handling**: Proper exit codes and error messages
- **Documentation**: Comprehensive help system with `make help`

### Testing Strategy
- **Multi-layer Testing**: Unit, integration, E2E, and security tests
- **Parallel Execution**: Optimized for CI with configurable workers
- **Comprehensive Reporting**: Multiple output formats (JUnit, HTML, console)
- **Debugging Support**: Interactive debugging tools and verbose output

### Dependency Management
- **Version Pinning**: Specific versions for reproducibility
- **Security Updates**: Regular dependency auditing
- **Development Tools**: Separate dev and test dependency groups
- **Compatibility**: Python 3.10+ support with type hints

### Configuration Management
- **Layered Configuration**: Environment variables, config files, defaults
- **Validation**: Runtime configuration validation
- **Documentation**: Comprehensive configuration documentation
- **Security**: Sensitive data handling and masking

This comprehensive development toolkit provides everything needed for efficient development, testing, deployment, and maintenance of the Cineca Agentic Platform, ensuring code quality, security, and operational reliability.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_Cineca-Agentic-Platform_scripts.md