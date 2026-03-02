# Cineca Agentic Platform - Complete Project Documentation

**Version**: 1.0  
**Date**: November 2025  
**Author**: Arman Feili  
**Institution**: Sapienza University of Rome  
**Project Type**: Master's Thesis (ILP Thesis 2025)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Overview](#project-overview)
3. [What Has Been Done](#what-has-been-done)
4. [Current Status](#current-status)
5. [What Needs to Be Done Next](#what-needs-to-be-done-next)
6. [Architecture Overview](#architecture-overview)
7. [Technology Stack](#technology-stack)
8. [Key Features](#key-features)
9. [API Documentation](#api-documentation)
10. [Deployment Guide](#deployment-guide)
11. [Testing Status](#testing-status)
12. [Security & Compliance](#security--compliance)
13. [Known Issues & Limitations](#known-issues--limitations)
14. [Future Roadmap](#future-roadmap)
15. [Contributing](#contributing)

---

## Executive Summary

The **Cineca Agentic Platform** is an advanced, production-ready platform for intelligent agent orchestration with natural language processing capabilities. Built as a thesis project at Sapienza University of Rome, it demonstrates enterprise-grade architecture patterns for building scalable, secure, and observable AI-powered systems.

### Key Highlights

- **Purpose**: Enable natural language queries to graph databases, orchestrate AI agents, and manage multi-tenant LLM-powered applications
- **Status**: Production-ready core features, with high-priority enhancements in progress
- **Technology**: FastAPI, PostgreSQL, Redis, Memgraph, Streamlit, Docker
- **Test Coverage**: 114+ passing unit tests
- **Documentation**: 330+ markdown documents covering all aspects

### Quick Metrics

| Metric | Value |
|--------|-------|
| **Total Test Coverage** | 114+ passing tests |
| **API Endpoints** | 50+ REST endpoints |
| **MCP Tools** | 32 standardized tools |
| **Container Services** | 12 containerized services |
| **Documentation Files** | 330+ markdown documents |
| **Lines of Code** | ~25,000+ Python |

---

## Project Overview

### What Is This Platform?

The Cineca Agentic Platform is a comprehensive system that enables:

1. **Natural Language to Graph Database Queries**
   - Converts natural language requests into Cypher queries for Memgraph
   - Validates queries for security and correctness
   - Executes queries with proper access control

2. **AI Agent Orchestration**
   - Manages multi-turn conversations with context preservation
   - Supports session-based agent workflows
   - Integrates with multiple LLM providers (OpenAI, Ollama, custom)

3. **Multi-Tenant SaaS Platform**
   - Complete tenant isolation
   - Role-based access control (RBAC)
   - Audit logging for compliance

4. **Background Job Processing**
   - Asynchronous task execution
   - Progress tracking via SSE (Server-Sent Events)
   - Job queuing and scheduling

5. **LLM Provider Management**
   - Register and manage multiple LLM providers
   - Model manifest system for built-in models
   - Default model configuration

### Problem Statement

Traditional database interfaces require:
- Technical expertise (SQL, Cypher knowledge)
- Schema understanding
- Security awareness

**This platform solves these problems by:**
- Enabling natural language queries with automatic translation
- Providing intelligent schema exploration
- Enforcing security policies automatically

### Use Cases

1. **Enterprise Knowledge Graphs** - Explore organizational data using conversational interfaces
2. **Research Data Analysis** - Query scientific datasets without learning Cypher
3. **Multi-Tenant SaaS** - Provide secure, isolated environments for multiple organizations
4. **AI Agent Development** - Framework for building context-aware conversational agents

---

## What Has Been Done

### ✅ Completed Core Features (100% Complete)

#### 1. Backend API (FastAPI)
- ✅ **50+ REST API endpoints** across 12 routers
- ✅ **OpenAPI 3.1 specification** with auto-generated docs
- ✅ **Authentication & Authorization** (Auth0 OIDC + JWT)
- ✅ **Rate limiting** middleware (Redis-backed)
- ✅ **Request validation** and error handling
- ✅ **CORS** configuration
- ✅ **Security headers** middleware (HSTS, CSP, etc.)

#### 2. Database Layer
- ✅ **PostgreSQL 16** integration for persistent storage
- ✅ **Redis** for caching and rate limiting
- ✅ **Memgraph** graph database integration
- ✅ **Alembic migrations** for schema management
- ✅ **Connection pooling** and health checks
- ✅ **Backup/restore scripts** (automated daily backups)

#### 3. Agent Orchestration
- ✅ **Session management** (create, read, update, delete)
- ✅ **Step sequencing** for multi-turn conversations
- ✅ **Agent runs** execution
- ✅ **Context preservation** across sessions
- ✅ **Idempotency** support with Idempotency-Key header

#### 4. MCP Tools System
- ✅ **32 standardized tools** covering:
  - Graph operations (CRUD, queries, visualization)
  - System operations (health, metrics, status)
  - Security operations (audit, rate limiting)
  - Data management (ETL, backups)
  - User management (profiles, tenants)
- ✅ **Tool registry** with versioning
- ✅ **Tool invocation** tracking and audit
- ✅ **RBAC** for tool access control

#### 5. LLM Provider Management
- ✅ **Multi-provider support** (OpenAI, Ollama, custom)
- ✅ **Provider registration** API
- ✅ **Model manifest system** (built-in models)
- ✅ **Model instance management** (load/unload models)
- ✅ **Default model** auto-configuration
- ✅ **Provider health checks**

#### 6. Job Processing
- ✅ **PostgreSQL-backed job storage**
- ✅ **Background worker** service
- ✅ **Redis queues** for job distribution
- ✅ **SSE streaming** for job events
- ✅ **Job status tracking** (queued → running → finished/failed)
- ✅ **Heartbeat monitoring**

#### 7. Multi-Tenancy
- ✅ **Tenant CRUD operations**
- ✅ **Tenant isolation** enforcement
- ✅ **Keyset pagination** for tenant lists
- ✅ **ETag-based caching**
- ✅ **JSONB metadata** support

#### 8. UI (Streamlit)
- ✅ **10-tab interface**:
  - Dashboard
  - Agents (sessions, runs)
  - Models (providers, instances, manifests)
  - Tools (registry, invocations)
  - Jobs (creation, monitoring)
  - Tenants (management)
  - Admin (system operations)
  - Explore (graph queries)
  - Cypher (direct queries)
  - Auth (token management)
- ✅ **Token management** (display, refresh, auto-renewal)
- ✅ **Error handling** with retry buttons
- ✅ **Loading states** and skeletons
- ✅ **Success notifications**
- ✅ **Responsive design** (mobile/tablet support)

#### 9. Security Features
- ✅ **Auth0 OIDC integration**
- ✅ **JWT token validation**
- ✅ **RBAC** with scope-based permissions
- ✅ **Intent filtering** (configurable)
- ✅ **PII scrubbing** (configurable)
- ✅ **Output guards** (configurable)
- ✅ **Audit logging** system
- ✅ **Rate limiting** (per-user, per-endpoint)

#### 10. Observability
- ✅ **Prometheus metrics** integration
- ✅ **Grafana dashboards** (3 pre-configured)
- ✅ **Structured logging** (structlog)
- ✅ **Request tracing** (OpenTelemetry support)
- ✅ **Health checks** (liveness, readiness, startup)
- ✅ **Dependency monitoring** (PostgreSQL, Redis, Memgraph)

#### 11. Operations
- ✅ **Docker Compose** setup (12 services)
- ✅ **Nginx reverse proxy** configuration
- ✅ **SSL/TLS** support
- ✅ **Production deployment guide**
- ✅ **Automated backups** (daily with retention)
- ✅ **Health check endpoints**

### ✅ Completed Critical Features (November 2025)

Based on the TODO.md completion status:

#### Critical Items (100% Complete ✅)
- ✅ **Permission error fix** - Aggressive cache clearing mechanism
- ✅ **Token refresh mechanism** - Auto-renewal 5 minutes before expiry
- ✅ **Database backups** - Automated daily backups with retention
- ✅ **Auto-set default model** - First model becomes default automatically
- ✅ **Global error handler** - All tabs have retry buttons and developer mode
- ✅ **Audit logging** - Complete audit trail system

#### High Priority Items (100% Complete ✅)
- ✅ **Token badge display** - Shows all scopes instead of "+1 more"
- ✅ **Loading skeletons** - Implemented in all tabs
- ✅ **Error messages** - User-friendly errors with clear next steps
- ✅ **Success notifications** - All tabs have success messages
- ✅ **Pagination component** - Reusable pagination component created
- ✅ **User guide** - Comprehensive 554-line USER_GUIDE.md
- ✅ **API documentation** - 4 OpenAPI JSON files
- ✅ **Deployment guide** - PRODUCTION_DEPLOYMENT_GUIDE.md
- ✅ **Troubleshooting guide** - Included in user guide

#### Quick Wins (100% Complete ✅)
- ✅ **Default model validator** - Auto-set first model as default
- ✅ **Token expiration warnings** - Show warning in sidebar
- ✅ **Clear Cache button** - Added to sidebar
- ✅ **UI layout fixes** - Responsive CSS for mobile/tablet
- ✅ **Code formatting** - Black formatter applied
- ✅ **Linter fixes** - Whitespace and SQLAlchemy deprecation warnings fixed

---

## Current Status

### Platform Status: **Production-Ready Core ✅**

The platform has achieved **production-ready status** for core functionality:

- ✅ **All critical features** implemented and tested
- ✅ **All high-priority features** completed
- ✅ **Comprehensive documentation** written
- ✅ **114+ unit tests** passing
- ✅ **12 container services** running successfully
- ✅ **Error handling** robust throughout
- ✅ **Security features** implemented
- ✅ **Observability** fully configured

### Deployment Status

```
✅ app (FastAPI backend) - healthy
✅ ui (Streamlit frontend) - healthy  
✅ postgres - healthy
✅ redis - healthy
✅ memgraph - running
✅ ollama - healthy
✅ jobs-worker - running
✅ grafana - running
✅ prometheus - running
✅ nginx (optional) - configured
```

### Code Quality

- ✅ **Black formatting** applied
- ✅ **Linter warnings** fixed
- ✅ **Type hints** (partial - can be improved)
- ✅ **Documentation** comprehensive
- ✅ **Error handling** robust

### Test Coverage

- ✅ **114+ unit tests** passing
- ✅ **Integration tests** available
- ✅ **E2E tests** (Playwright) configured
- ⚠️ **Target**: 70% coverage (currently ~60%)

---

## What Needs to Be Done Next

### 🔴 High Priority - Complete Next (This Month)

#### 1. Increase Test Coverage to 70%

**Status**: ~60% coverage, target 70%

**What's Needed**:
- [ ] Add unit tests for critical paths
  - [ ] Agent orchestration edge cases
  - [ ] Tool invocation error scenarios
  - [ ] Token refresh edge cases
  - [ ] Database connection failures
- [ ] Add integration tests for:
  - [ ] Multi-tenant isolation
  - [ ] Job processing workflows
  - [ ] Model loading/unloading
- [ ] Add E2E tests for:
  - [ ] Complete user workflows
  - [ ] Error recovery flows
  - [ ] Token expiration scenarios

**Files to Create/Modify**:
- `tests/unit/test_agent_edge_cases.py`
- `tests/integration/test_tenant_isolation.py`
- `tests/e2e/test_user_workflows.py`

**Estimated Effort**: 2-3 days

---

#### 2. End-to-End Testing

**Status**: Framework exists, needs expansion

**What's Needed**:
- [ ] Test complete user workflows:
  - [ ] Create tenant → Register provider → Load model → Run agent
  - [ ] Create job → Monitor progress → Retrieve results
  - [ ] Token expiration → Auto-renewal → Continue session
- [ ] Test error scenarios:
  - [ ] Network failures during agent run
  - [ ] Database connection loss
  - [ ] Redis unavailability
- [ ] Test multi-user scenarios:
  - [ ] Concurrent agent runs
  - [ ] Rate limiting enforcement
  - [ ] Tenant isolation

**Files to Create/Modify**:
- `tests/e2e/test_complete_workflows.py`
- `tests/e2e/test_error_scenarios.py`
- `tests/e2e/test_concurrent_users.py`

**Estimated Effort**: 3-4 days

---

#### 3. Load Testing

**Status**: Not implemented

**What's Needed**:
- [ ] Define expected load:
  - [ ] Concurrent users (target: 100+)
  - [ ] Requests per second (target: 1000+)
  - [ ] Agent runs per minute (target: 50+)
- [ ] Set up load testing tool (Locust, k6, or Artillery)
- [ ] Create test scenarios:
  - [ ] Spike tests (sudden traffic increase)
  - [ ] Stress tests (find breaking point)
  - [ ] Soak tests (sustained load)
- [ ] Identify bottlenecks:
  - [ ] Database query performance
  - [ ] Redis cache effectiveness
  - [ ] LLM provider latency
  - [ ] Memory usage

**Files to Create**:
- `tests/load/locustfile.py`
- `tests/load/test_scenarios.py`
- `docs/load-testing-results.md`

**Estimated Effort**: 3-5 days

---

#### 4. Code Review & Refactoring

**Status**: Initial review needed

**What's Needed**:
- [ ] Review complex areas:
  - [ ] Agent orchestration logic
  - [ ] Tool invocation flow
  - [ ] Session state management
  - [ ] Token refresh mechanism
- [ ] Refactor identified issues:
  - [ ] Reduce code duplication
  - [ ] Improve error handling consistency
  - [ ] Optimize database queries
  - [ ] Simplify complex functions
- [ ] Address technical debt:
  - [ ] Session state caching strategy
  - [ ] Token storage (consider HTTP-only cookies)
  - [ ] Error boundary implementation

**Files to Review**:
- `src/services/orchestrator.py`
- `src/routers/agent.py`
- `ui/state.py`
- `ui/components/auto_renew.py`

**Estimated Effort**: 5-7 days

---

### 🟡 Medium Priority - Next Month

#### 5. Webhook Support

**Status**: Not implemented

**What's Needed**:
- [ ] Design webhook system:
  - [ ] Event types (agent.run.completed, job.finished, etc.)
  - [ ] Webhook registration API
  - [ ] Retry mechanism with exponential backoff
  - [ ] Signature verification
- [ ] Implement webhook delivery:
  - [ ] Async delivery queue
  - [ ] HTTP client with retries
  - [ ] Dead letter queue for failures
- [ ] Add webhook management UI:
  - [ ] Register webhooks
  - [ ] View delivery history
  - [ ] Retry failed deliveries

**Estimated Effort**: 5-7 days

---

#### 6. Batch Operations

**Status**: Not implemented

**What's Needed**:
- [ ] Design batch API:
  - [ ] Batch create/update/delete
  - [ ] Batch agent runs
  - [ ] Batch job creation
- [ ] Implement batch processing:
  - [ ] Transaction support
  - [ ] Partial success handling
  - [ ] Progress tracking
- [ ] Add batch UI:
  - [ ] Upload CSV/JSON files
  - [ ] Batch operation forms
  - [ ] Progress display

**Estimated Effort**: 4-5 days

---

#### 7. Export/Import Functionality

**Status**: Not implemented

**What's Needed**:
- [ ] Export capabilities:
  - [ ] Export tenant configurations
  - [ ] Export agent configurations
  - [ ] Export tool registrations
  - [ ] Export job history
- [ ] Import capabilities:
  - [ ] Validate imported data
  - [ ] Idempotent import (skip existing)
  - [ ] Import preview
- [ ] Add UI:
  - [ ] Export buttons
  - [ ] Import forms
  - [ ] Validation errors display

**Estimated Effort**: 3-4 days

---

#### 8. Agent Templates

**Status**: Not implemented

**What's Needed**:
- [ ] Create template system:
  - [ ] Pre-configured agent setups
  - [ ] Template library (customer support, data analysis, etc.)
  - [ ] Custom template creation
- [ ] Implement template API:
  - [ ] List templates
  - [ ] Create agent from template
  - [ ] Save agent as template
- [ ] Add UI:
  - [ ] Template gallery
  - [ ] Template preview
  - [ ] One-click agent creation

**Estimated Effort**: 4-5 days

---

#### 9. Performance Optimization

**Status**: Basic optimization done, needs more

**What's Needed**:
- [ ] Database optimization:
  - [ ] Add indexes for frequently queried columns
  - [ ] Optimize slow queries
  - [ ] Implement query result caching
- [ ] Response caching:
  - [ ] Cache frequently accessed data
  - [ ] Implement cache invalidation strategy
  - [ ] Add cache warming
- [ ] UI optimization:
  - [ ] Lazy load components
  - [ ] Optimize bundle size
  - [ ] Reduce initial load time

**Estimated Effort**: 5-7 days

---

#### 10. Monitoring & Alerting

**Status**: Basic monitoring exists, needs alerts

**What's Needed**:
- [ ] Set up alerting:
  - [ ] Prometheus alert rules
  - [ ] Grafana alert channels (email, Slack, PagerDuty)
  - [ ] Alert thresholds configuration
- [ ] Create alert rules for:
  - [ ] High error rates
  - [ ] Slow response times
  - [ ] Database connection failures
  - [ ] Redis unavailability
  - [ ] High memory usage
- [ ] Set up status page:
  - [ ] Public system status dashboard
  - [ ] Incident history
  - [ ] Scheduled maintenance announcements

**Estimated Effort**: 3-4 days

---

### ⚪ Low Priority - Future Enhancements

#### 11. Mobile Optimization

**Status**: Basic responsive design exists

**What's Needed**:
- [ ] Improve mobile UI:
  - [ ] Touch-friendly buttons
  - [ ] Responsive tables
  - [ ] Mobile navigation menu
- [ ] Mobile-specific features:
  - [ ] Push notifications
  - [ ] Offline support
  - [ ] Mobile-optimized forms

**Estimated Effort**: 5-7 days

---

#### 12. Dark Mode

**Status**: Not implemented

**What's Needed**:
- [ ] Implement theme system:
  - [ ] Dark theme CSS
  - [ ] Theme switcher
  - [ ] Persist theme preference
- [ ] Test all components in dark mode:
  - [ ] Tables
  - [ ] Forms
  - [ ] Charts
  - [ ] Modals

**Estimated Effort**: 2-3 days

---

#### 13. Advanced Analytics

**Status**: Basic metrics exist

**What's Needed**:
- [ ] Usage analytics:
  - [ ] User activity tracking
  - [ ] Feature usage statistics
  - [ ] Cost analysis (LLM API costs)
- [ ] Dashboard:
  - [ ] User activity dashboard
  - [ ] Cost tracking dashboard
  - [ ] Performance metrics dashboard

**Estimated Effort**: 5-7 days

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATIONS                           │
│           (Web UI, CLI, REST Clients, SDKs)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FASTAPI REST API LAYER                        │
│  ┌──────────────┬──────────────┬─────────────────────────────┐ │
│  │  Auth/AuthZ  │  Rate Limit  │  Validation & Logging       │ │
│  │  Middleware  │  Middleware   │  Middleware                  │ │
│  └──────────────┴──────────────┴─────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              ROUTERS (21 modules)                         │  │
│  │  Agents│Health│Tools│Jobs│Models│Tenants│Admin│Internal  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                              │
│  ┌─────────────┬─────────────┬──────────────────────────────┐  │
│  │  Agent      │  Tool       │  Job & Model Management      │  │
│  │  Orchestr.  │  Execution  │  & LLM Adapter              │  │
│  └─────────────┴─────────────┴──────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                MCP TOOLS REGISTRY (32 tools)                     │
│  ┌─────────────┬─────────────┬──────────────────────────────┐  │
│  │  Graph      │  System     │  Security & Data Management   │  │
│  │  Operations │  Health     │  & Analytics                  │  │
│  └─────────────┴─────────────┴──────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────┬──────────────┬──────────────┐
│ PostgreSQL   │    Redis     │  Memgraph    │
│  (ACID DB)   │   (Cache)    │  (Graph DB)  │
└──────────────┴──────────────┴──────────────┘
```

### Component Details

#### 1. API Layer (FastAPI)
- **Routers**: 21 router modules handling different domains
- **Middleware**: Authentication, rate limiting, CORS, security headers
- **Validation**: Pydantic models for request/response validation
- **Documentation**: Auto-generated OpenAPI specs

#### 2. Service Layer
- **Orchestrator**: Coordinates agent execution and tool selection
- **Session Management**: Manages agent conversation state
- **Job Service**: Handles background task processing
- **Model Service**: Manages LLM provider and model instances

#### 3. Data Layer
- **PostgreSQL**: Persistent storage for tenants, jobs, tools, audit logs
- **Redis**: Caching, rate limiting, job queues
- **Memgraph**: Graph database for knowledge graphs

#### 4. UI Layer (Streamlit)
- **Multi-tab Interface**: 10 tabs for different functionalities
- **State Management**: Session state with caching
- **Token Management**: Display, refresh, auto-renewal
- **Error Handling**: Global error handlers with retry

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11+ | Core language |
| **FastAPI** | 0.109+ | REST API framework |
| **Pydantic** | 2.5+ | Data validation |
| **SQLAlchemy** | 2.0+ | ORM for PostgreSQL |
| **Alembic** | 1.13+ | Database migrations |
| **Redis** | 7.0+ | Caching and queues |
| **Memgraph** | 2.13+ | Graph database |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Streamlit** | 1.31+ | UI framework |
| **Python** | 3.11+ | UI logic |

### Infrastructure

| Technology | Version | Purpose |
|------------|---------|---------|
| **Docker** | 24.0+ | Containerization |
| **Docker Compose** | 2.24+ | Orchestration |
| **PostgreSQL** | 16 | Primary database |
| **Redis** | 7.0 | Cache and queues |
| **Memgraph** | 2.13 | Graph database |
| **Ollama** | Latest | Local LLM inference |
| **Nginx** | Latest | Reverse proxy |
| **Prometheus** | Latest | Metrics collection |
| **Grafana** | Latest | Metrics visualization |

### Authentication & Security

| Technology | Purpose |
|------------|---------|
| **Auth0** | OIDC provider |
| **JWT** | Token-based auth |
| **PyJWT** | JWT validation |

### Testing

| Technology | Purpose |
|------------|---------|
| **pytest** | Unit/integration testing |
| **Playwright** | E2E testing |
| **pytest-asyncio** | Async test support |

---

## Key Features

### 1. Natural Language to Cypher Conversion

- Converts natural language queries into Cypher
- Validates queries for security (read-only enforcement)
- Executes queries with proper access control
- Returns structured results

### 2. Agent Orchestration

- **Session Management**: Create, read, update, delete sessions
- **Step Sequencing**: Ordered execution tracking
- **Context Preservation**: Maintains conversation history
- **Multi-turn Conversations**: Supports complex workflows

### 3. Multi-LLM Support

- **Provider Registry**: Register multiple LLM providers
- **Model Manifests**: Built-in model definitions
- **Instance Management**: Load/unload models dynamically
- **Default Configuration**: Auto-set first model as default

### 4. Background Job Processing

- **PostgreSQL Storage**: Persistent job storage
- **Redis Queues**: Fast job distribution
- **SSE Streaming**: Real-time progress updates
- **Status Tracking**: Complete job lifecycle

### 5. Multi-Tenancy

- **Tenant Isolation**: Complete data separation
- **RBAC**: Role-based access control
- **Audit Logging**: Full audit trail
- **Keyset Pagination**: Scalable tenant lists

### 6. Security Features

- **OIDC Authentication**: Auth0 integration
- **JWT Validation**: Token-based auth
- **Rate Limiting**: Per-user, per-endpoint limits
- **Intent Filtering**: Configurable guardrails
- **PII Scrubbing**: Configurable data protection
- **Output Guards**: Configurable output filtering

### 7. Observability

- **Prometheus Metrics**: Comprehensive metrics
- **Grafana Dashboards**: Pre-configured dashboards
- **Structured Logging**: JSON logs with correlation IDs
- **Health Checks**: Liveness, readiness, startup probes
- **Tracing**: OpenTelemetry support

---

## API Documentation

### API Endpoints Overview

The platform exposes **50+ REST API endpoints** organized into the following categories:

#### Meta & Health
- `GET /v1/` - Service info
- `GET /v1/health/live` - Liveness probe
- `GET /v1/health/ready` - Readiness probe
- `GET /v1/health/startup` - Startup checks

#### Authentication
- `POST /v1/auth/token` - Exchange credentials for JWT
- `GET /v1/auth/me` - Get current user info

#### Agents
- `POST /v1/agent-runs` - One-shot agent run
- `POST /v1/agents/sessions` - Create session
- `GET /v1/agents/sessions/{id}` - Get session
- `POST /v1/agents/sessions/{id}/steps` - Add step
- `DELETE /v1/agents/sessions/{id}` - Delete session

#### Tools
- `GET /v1/tools` - List tools
- `GET /v1/tools/{name}` - Get tool details
- `POST /v1/tools/{name}/invocations` - Invoke tool

#### Jobs
- `GET /v1/jobs/{id}` - Get job status
- `POST /v1/jobs` - Create job
- `DELETE /v1/jobs/{id}` - Cancel job
- `GET /v1/jobs/{id}/events` - Stream job events (SSE)

#### Models
- `GET /v1/models` - List models
- `POST /v1/models/completions` - Text completion
- `POST /v1/models/chat/completions` - Chat completion
- `POST /v1/models/embeddings` - Generate embeddings

#### Admin (requires `admin:all` scope)
- `GET /v1/admin/models/instances` - List instances
- `POST /v1/admin/models/instances` - Load model
- `GET /v1/admin/models/providers` - List providers
- `POST /v1/admin/models/providers/register` - Register provider
- `GET /v1/admin/tenants` - List tenants
- `POST /v1/admin/tenants` - Create tenant

**Complete API Documentation**: See `docs/api/` directory and `/v1/openapi.json` endpoint.

---

## Deployment Guide

### Quick Start (5 Minutes)

```bash
# 1. Clone repository
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Start all services
docker compose up -d

# 4. Wait for healthy status (~30s)
docker compose ps

# 5. Verify health
curl http://localhost:8000/v1/health/ready

# 6. Access UI
# http://localhost:8501
```

### Production Deployment

See `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` for complete production deployment instructions including:
- SSL/TLS configuration
- Security hardening
- Monitoring setup
- Backup configuration
- Scaling considerations

---

## Testing Status

### Current Test Coverage

- ✅ **114+ unit tests** passing
- ✅ **Integration tests** available
- ✅ **E2E tests** (Playwright) configured
- ⚠️ **Target**: 70% coverage (currently ~60%)

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run E2E tests
pytest tests/e2e/

# Run with coverage
pytest --cov=src --cov-report=html
```

### Test Structure

```
tests/
├── unit/          # Unit tests (114+ tests)
├── integration/   # Integration tests
├── e2e/           # End-to-end tests (Playwright)
└── load/          # Load tests (to be added)
```

**Complete Testing Guide**: See `docs/TESTING_GUIDE.md`

---

## Security & Compliance

### Security Features

- ✅ **OIDC Authentication** - Auth0 integration
- ✅ **JWT Validation** - Token-based auth
- ✅ **RBAC** - Role-based access control
- ✅ **Rate Limiting** - Per-user, per-endpoint limits
- ✅ **Audit Logging** - Full audit trail
- ✅ **PII Scrubbing** - Configurable data protection
- ✅ **Output Guards** - Configurable output filtering
- ✅ **Security Headers** - HSTS, CSP, etc.
- ✅ **HTTPS Support** - SSL/TLS termination

### Compliance

- ✅ **GDPR Ready** - Data retention policies
- ✅ **Audit Trail** - Complete action logging
- ✅ **Data Isolation** - Multi-tenant separation
- ✅ **Privacy by Design** - Configurable guardrails

**Security Documentation**: See `docs/security/` directory

---

## Known Issues & Limitations

### Current Limitations

1. **Test Coverage**: Currently ~60%, target 70%
   - **Impact**: Some edge cases may not be tested
   - **Mitigation**: Working on increasing coverage

2. **Load Testing**: Not yet performed
   - **Impact**: Unknown performance limits
   - **Mitigation**: Load testing planned for next sprint

3. **Session State Management**: Current approach has caching issues
   - **Impact**: May cause stale state in some scenarios
   - **Mitigation**: Clear Cache button available, refactoring planned

4. **Token Storage**: Uses session state (not HTTP-only cookies)
   - **Impact**: Vulnerable to XSS attacks
   - **Mitigation**: Consider HTTP-only cookies for production

5. **Mobile Optimization**: Basic responsive design only
   - **Impact**: Mobile UX could be improved
   - **Mitigation**: Mobile optimization planned

### Known Issues

1. **Permission Error Caching**: Fixed with aggressive cache clearing
2. **Token Expiration**: Fixed with auto-renewal and warnings
3. **Default Model**: Fixed with auto-configuration
4. **Error Recovery**: Fixed with retry buttons

---

## Future Roadmap

### Short Term (Next Month)

1. **Increase Test Coverage** to 70%
2. **Load Testing** implementation
3. **Code Review** and refactoring
4. **Webhook Support** implementation

### Medium Term (Next 3 Months)

1. **Batch Operations** support
2. **Export/Import** functionality
3. **Agent Templates** system
4. **Performance Optimization**
5. **Monitoring & Alerting** setup

### Long Term (6+ Months)

1. **Mobile Optimization**
2. **Dark Mode** support
3. **Advanced Analytics** dashboard
4. **Multi-language Support** (i18n)
5. **Marketplace** for tools/agents

---

## Contributing

### Getting Started

1. Clone the repository
2. Set up development environment (see `docs/guides/getting-started.md`)
3. Create a feature branch
4. Make changes
5. Run tests: `pytest`
6. Submit a pull request

### Code Style

- **Formatter**: Black
- **Linter**: flake8
- **Type Hints**: Preferred (mypy compatible)
- **Documentation**: Docstrings for all functions

### Testing Requirements

- All new features must include tests
- Maintain or improve test coverage
- All tests must pass before PR

---

## Additional Resources

### Documentation Index

- **User Guide**: `docs/USER_GUIDE.md`
- **API Reference**: `docs/api/`
- **Deployment Guide**: `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`
- **Testing Guide**: `docs/TESTING_GUIDE.md`
- **Architecture**: `docs/architecture/`
- **Security**: `docs/security/`

### Quick Links

- **GitHub Repository**: https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform
- **OpenAPI Spec**: `/v1/openapi.json`
- **Health Check**: `/v1/health/ready`

---

## Conclusion

The **Cineca Agentic Platform** is a **production-ready** platform for intelligent agent orchestration with comprehensive features, robust security, and excellent observability. While core functionality is complete and tested, there are high-priority enhancements planned to improve test coverage, performance, and user experience.

### Key Achievements

- ✅ **Production-ready core** features
- ✅ **Comprehensive documentation** (330+ files)
- ✅ **114+ passing tests**
- ✅ **Security & compliance** features
- ✅ **Full observability** stack

### Next Steps

1. **Increase test coverage** to 70%
2. **Perform load testing**
3. **Code review and refactoring**
4. **Implement webhook support**
5. **Add batch operations**

---

**Last Updated**: November 2025  
**Status**: Production-Ready Core ✅  
**Next Milestone**: Test Coverage & Load Testing

