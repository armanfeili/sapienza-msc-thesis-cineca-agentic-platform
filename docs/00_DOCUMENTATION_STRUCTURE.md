# Documentation Structure Guide

This document describes the organization of the Cineca Agentic Platform documentation.

## 📁 Directory Structure

### Root Level Documents
- **README.md** - Main documentation entry point
- **PROJECT_DOCUMENTATION.md** - Comprehensive project documentation
- **EXECUTIVE_SUMMARY.md** - High-level project overview

---

## 📂 Main Documentation Categories

### `/guides/` - User Guides and Getting Started
Essential guides for getting started and using the platform:
- `getting-started.md` - Quick start guide for new users
- `QUICKSTART.md` - Fast-track setup instructions
- `configuration.md` - System configuration guide
- `environment-variables.md` - Environment variables reference
- `ollama.md` - Ollama integration guide
- `BEHAVIORAL_FEATURES_SUMMARY.md` - Platform behavior documentation

**Use this when:** You need to set up or understand how to use the platform.

---

### `/api/` - API Documentation
Complete API documentation and standards:
- `API_BEST_PRACTICES.md` - API design best practices
- `ENDPOINT_DESCRIPTIONS.md` - Detailed endpoint descriptions
- `ENDPOINT_QUICK_REFERENCE.md` - Quick API reference
- `ERROR_HANDLING_STANDARDIZATION.md` - Error handling patterns
- `IDEMPOTENCY_GUIDE.md` - Idempotency implementation
- `PAGINATION_GUIDE.md` - Pagination patterns
- `RATE_LIMITING_IMPLEMENTATION.md` - Rate limiting details
- `REST_API_POLISH_README.md` - REST API documentation index
- `RFC_COMPLIANCE_FINAL_REPORT.md` - RFC compliance report
- OpenAPI documentation files
- Swagger UI improvements

**Use this when:** You need to understand or use the platform's REST APIs.

---

### `/features/` - Feature-Specific Documentation
Documentation organized by platform features:

#### `/features/agents/`
Agent system documentation:
- `AGENTS_API_GUIDE.md` - Agents API reference
- `AGENTS_README.md` - Agent system overview
- `AGENTS_QUICKSTART.md` - Quick start for agents

#### `/features/jobs/`
Job management documentation:
- Job API guides
- Job implementation details

#### `/features/models/`
Model instance management:
- `MODEL_INSTANCES_API_GUIDE.md` - Model instances API
- Model configuration guides

#### `/features/providers/`
Provider management:
- Provider API documentation
- Provider implementation guides

#### `/features/tenants/`
Multi-tenancy documentation:
- `tenants-guide.md` - Tenant management guide

#### `/features/admin/`
Admin functionality:
- Admin endpoint documentation
- Admin processes guides

#### `/features/internal-endpoints/`
Internal API documentation:
- Internal endpoint implementation guides
- RBAC testing documentation

#### `/features/health/`
Health check APIs:
- Health API reference
- Health endpoint documentation

#### `/features/user-access/`
User access and permissions:
- User access implementation guides
- Token scope documentation

#### `/features/graph-tools/`
Graph database tools:
- Graph tools implementation
- Cypher query guides

**Use this when:** You need feature-specific documentation.

---

### `/architecture/` - Architecture Documentation
System architecture and design:
- `architecture.md` - Overall system architecture
- `tools-architecture.md` - Tools architecture design

**Use this when:** You need to understand the system design.

---

### `/database/` - Database Documentation
Database systems and migrations:
- `DATABASE_POSTGRESQL_REFERENCE.md` - PostgreSQL reference
- `DATABASE_REDIS_REFERENCE.md` - Redis reference
- `DATABASE_MEMGRAPH_REFERENCE.md` - Memgraph reference
- `redis-job-store-production.md` - Redis job store guide
- `POSTGRES_FILES_REORGANIZATION.md` - PostgreSQL migration guides
- `TOOLS_POSTGRES_REDIS_IMPLEMENTATION.md` - Database implementations

**Use this when:** You need database-specific information.

---

### `/security/` - Security Documentation
Security policies and implementations:
- `AUTH_GUIDE.md` - Authentication guide
- `AUTH0_INTEGRATION.md` - Auth0 integration
- `security.md` - Security overview
- `SECURITY_AUDIT_REPORT.md` - Security audit findings
- `SECURITY_INCIDENT_2025-10-22.md` - Security incident reports
- `SECURITY_REFERENCE.md` - Security reference
- `RBAC_MATRIX.md` - Role-based access control matrix
- `REAL_TOKENS_INTEGRATION.md` - Token integration guide

**Use this when:** You need security or authentication information.

---

### `/mcp/` - MCP Tools Documentation
Model Context Protocol tools:
- `MCP_TOOLS_REFERENCE.md` - Complete MCP tools reference
- `MCP_TOOLS_INDEX.md` - MCP tools index
- `MCP_REGISTRY_INDEX.md` - MCP registry documentation
- `BUILTINS_MANIFESTS_IMPLEMENTATION.md` - Built-in manifests

**Use this when:** You need MCP tools documentation.

---

### `/operations/` - Operations Documentation

#### `/operations/deployment/`
Deployment and production readiness:
- `deployment.md` - Deployment guide
- `PROD_READINESS.md` - Production readiness checklist
- `PRODUCTION_READINESS_INDEX.md` - Production index
- `PRODUCTION_VALIDATION_REPORT.md` - Validation reports
- `CI_CD_SETUP_GUIDE.md` - CI/CD setup
- `MIGRATION.md` - Migration guides

#### `/operations/monitoring/`
Monitoring and observability:
- `MONITORING_SETUP.md` - Monitoring setup guide
- `OBSERVABILITY.md` - Observability guide
- `SLO.md` - Service Level Objectives
- `PERFORMANCE_TESTING.md` - Performance testing guide
- `INCIDENT_RESPONSE.md` - Incident response procedures
- `DISASTER_RECOVERY.md` - Disaster recovery plans

#### `/operations/runbooks/`
Operational runbooks:
- `OPERATOR_RUNBOOK.md` - Operator procedures
- `OPERATIONS_RUNBOOK.md` - Operations guide
- `worker-guide.md` - Worker management
- `alerts.md` - Alert handling
- `slos.md` - SLO definitions
- `troubleshooting-tools.md` - Troubleshooting guide

**Use this when:** You need operational or deployment information.

---

### `/testing/` - Testing Documentation
Testing guides and reports:
- `TESTING_GUIDE.md` - Testing guide
- `MANUAL_TESTING_GUIDE.md` - Manual testing procedures
- `ACCEPTANCE_QUICK_REFERENCE.md` - Acceptance testing
- `INTEGRATION_QUICK_REFERENCE.md` - Integration testing
- Test execution reports
- Test verification documentation

**Use this when:** You need to understand testing procedures.

---

### `/ui/` - UI Documentation
User interface documentation:
- `UI_DEPLOYMENT_GUIDE.md` - UI deployment guide
- `UI_DOCUMENTATION_INDEX.md` - UI documentation index
- `UI_QUICK_REFERENCE.md` - UI quick reference
- UI implementation guides
- UI testing documentation

**Use this when:** You need UI-specific information.

---

### `/implementation/` - Implementation Guides
Implementation and migration guides:
- `tools-migration-guide.md` - Tools migration guide
- Feature implementation guides

**Use this when:** You're implementing new features or migrations.

---

### `/reference/` - Quick References
Quick reference guides and indices:
- `INDEX.md` - General documentation index
- `DOCUMENTATION_INDEX.md` - Documentation index
- `QUICK_REFERENCE.txt` - Platform quick reference
- `ROUTERS_UTILITIES_REFERENCE.md` - Routers and utilities
- `SERVICES_REFERENCE.md` - Services reference

**Use this when:** You need a quick lookup.

---

### `/status-reports/` - Status and Progress Reports
Historical status reports and completion summaries:
- P1-P7 phase completion reports
- Implementation progress reports
- Finalization checklists
- Session completion reports
- Platform status reports

**Use this when:** You need historical context or project status.

---

### `/adr/` - Architecture Decision Records
Architectural decisions and rationale.

**Use this when:** You need to understand why architectural decisions were made.

---

### `/compliance/` - Compliance Documentation
Compliance-related documentation and reports.

**Use this when:** You need compliance information.

---

### `/diagrams/` - System Diagrams
Visual representations of system architecture and flows.

**Use this when:** You need visual documentation.

---

### `/observability/` - Observability Details
Detailed observability configuration and metrics.

**Use this when:** You need observability implementation details.

---

### `/quickstarts/` - Feature Quickstarts
Quick start guides for specific features:
- `archive-restore.md` - Archive and restore quickstart
- `bulk-import.md` - Bulk import quickstart
- `secure-nl-to-cypher.md` - Secure NL to Cypher quickstart

**Use this when:** You need to quickly get started with a specific feature.

---

## 🔍 Finding Documentation

### For New Users
1. Start with **README.md** or **EXECUTIVE_SUMMARY.md**
2. Follow **guides/getting-started.md**
3. Review **guides/QUICKSTART.md**

### For Developers
1. Check **api/** for API documentation
2. Review **features/** for feature-specific docs
3. Consult **architecture/** for system design
4. See **database/** for data layer information

### For Operators
1. Start with **operations/deployment/**
2. Review **operations/monitoring/**
3. Keep **operations/runbooks/** handy
4. Check **security/** for security procedures

### For Testers
1. Review **testing/TESTING_GUIDE.md**
2. Check feature-specific testing docs in **features/**
3. Use quick references for test scenarios

---

## 📝 Documentation Maintenance

When adding new documentation:

1. **Guides** → `/guides/` (user-facing how-to docs)
2. **API docs** → `/api/` (endpoint and API specs)
3. **Feature docs** → `/features/{feature-name}/` (feature-specific)
4. **Architecture** → `/architecture/` (design docs)
5. **Operations** → `/operations/{deployment|monitoring|runbooks}/`
6. **Status reports** → `/status-reports/` (historical only)
7. **References** → `/reference/` (quick lookups)

---

## 🔗 Related Resources

- Main codebase: `../backend/`
- Configuration examples: `../config/`
- Scripts: `../scripts/`

---

*Last updated: 2025-11-01*

