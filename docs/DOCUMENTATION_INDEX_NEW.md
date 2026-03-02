# 📚 Cineca Agentic Platform - Documentation Index

> **New Reorganized Structure** - Last Updated: November 1, 2025

Welcome to the reorganized documentation for the Cineca Agentic Platform! This index provides quick access to all documentation organized by purpose and audience.

---

## 🚀 Quick Start

### New to the Platform?
1. 📖 [Getting Started Guide](./guides/getting-started.md)
2. ⚡ [Quickstart](./guides/QUICKSTART.md)
3. 🔧 [Configuration Guide](./guides/configuration.md)

### Want to Use the API?
1. 📋 [API Quick Reference](./api/ENDPOINT_QUICK_REFERENCE.md)
2. 📚 [API Best Practices](./api/API_BEST_PRACTICES.md)
3. 🔍 [Endpoint Descriptions](./api/ENDPOINT_DESCRIPTIONS.md)

### Need to Deploy?
1. 🚀 [Deployment Guide](./operations/deployment/deployment.md)
2. ✅ [Production Readiness](./operations/deployment/PROD_READINESS.md)
3. 📊 [Monitoring Setup](./operations/monitoring/MONITORING_SETUP.md)

---

## 📂 Documentation Structure

### 📖 [User Guides](./guides/)
Essential guides for getting started and using the platform.
- Getting started and quickstart guides
- Configuration and environment setup
- Integration guides (Ollama, etc.)

**Start here if you're new to the platform.**

---

### 🔌 [API Documentation](./api/)
Complete REST API documentation and standards.
- API best practices and standards
- Endpoint descriptions and references
- Error handling, pagination, rate limiting
- OpenAPI specifications and RFC compliance

**Start here for API integration.**

---

### ⚙️ [Features](./features/)
Feature-specific documentation organized by capability.

| Feature | Description |
|---------|-------------|
| [Agents](./features/agents/) | Agent system and API |
| [Jobs](./features/jobs/) | Job management |
| [Models](./features/models/) | Model instances |
| [Providers](./features/providers/) | Provider management |
| [Tenants](./features/tenants/) | Multi-tenancy |
| [Admin](./features/admin/) | Admin functionality |
| [Internal Endpoints](./features/internal-endpoints/) | Internal APIs |
| [Health](./features/health/) | Health checks |
| [User Access](./features/user-access/) | User permissions |
| [Graph Tools](./features/graph-tools/) | Graph database tools |

**Start here for feature-specific documentation.**

---

### 🏗️ [Architecture](./architecture/)
System architecture and design documentation.
- Overall system architecture
- Tools architecture
- Design decisions (see also [ADR](./adr/))

**Start here to understand system design.**

---

### 🗄️ [Database](./database/)
Database systems documentation (PostgreSQL, Redis, Memgraph).
- Database references and schemas
- Migration guides
- Job store documentation
- Key patterns and structures

**Start here for database information.**

---

### 🔒 [Security](./security/)
Security, authentication, and access control.
- Authentication guides (Auth0)
- RBAC matrix and permissions
- Security audits and incident reports
- Token management

**Start here for security implementation.**

---

### 🔧 [MCP Tools](./mcp/)
Model Context Protocol tools documentation.
- MCP tools reference
- Registry documentation
- Built-in manifests

**Start here for MCP tools.**

---

### 🚀 [Operations](./operations/)
Deployment, monitoring, and operational procedures.

#### [Deployment](./operations/deployment/)
- Deployment guides
- Production readiness
- CI/CD setup
- Migration procedures

#### [Monitoring](./operations/monitoring/)
- Monitoring setup
- Observability guides
- SLOs and performance testing
- Incident response and disaster recovery

#### [Runbooks](./operations/runbooks/)
- Operator procedures
- Worker management
- Troubleshooting guides
- Alert handling

**Start here for operational needs.**

---

### 🧪 [Testing](./testing/)
Testing guides and procedures.
- Testing guide and manual testing
- Acceptance and integration testing
- Test execution and validation
- Feature-specific testing

**Start here for testing information.**

---

### 🎨 [UI](./ui/)
User interface documentation.
- UI deployment guides
- UI implementation details
- UI testing and fixes
- Happy path implementation

**Start here for UI development.**

---

### 🛠️ [Implementation](./implementation/)
Implementation and migration guides.
- Tools migration guide
- Implementation patterns

**Start here for implementation guidance.**

---

### 📋 [Reference](./reference/)
Quick references and indices.
- Documentation indices
- Quick reference guides
- Routers and utilities reference
- Services reference

**Start here for quick lookups.**

---

### 📊 [Status Reports](./status-reports/)
Historical status and progress reports.
- Phase completion reports (P1-P7)
- Implementation progress
- Testing completion
- Finalization reports

**⚠️ Historical only - see feature docs for current information.**

---

### 🎯 [Quickstarts](./quickstarts/)
Feature-specific quickstart guides.
- Archive and restore
- Bulk import
- Secure NL to Cypher

**Start here for quick feature demos.**

---

### 📐 [ADR](./adr/)
Architecture Decision Records.
- Architectural decisions and rationale

**Start here to understand past decisions.**

---

### ✅ [Compliance](./compliance/)
Compliance documentation.
- GDPR, data retention
- Privacy by design

**Start here for compliance needs.**

---

### 📊 [Diagrams](./diagrams/)
System diagrams and visual documentation.
- System context and container diagrams
- Sequence diagrams

**Start here for visual documentation.**

---

### 👁️ [Observability](./observability/)
Detailed observability configuration.
- Metrics and alerting
- Dashboards (Grafana)
- Tracing and PromQL examples

**Start here for observability implementation.**

---

## 🔍 Finding What You Need

### By Role

#### 👨‍💻 Developers
```
1. API Documentation → /api/
2. Features → /features/{feature}/
3. Database → /database/
4. Architecture → /architecture/
5. Security → /security/
```

#### 👷 Operators
```
1. Deployment → /operations/deployment/
2. Monitoring → /operations/monitoring/
3. Runbooks → /operations/runbooks/
4. Security → /security/
5. Database → /database/
```

#### 🧪 Testers
```
1. Testing Guide → /testing/
2. Feature Tests → /features/{feature}/
3. API Tests → /api/
4. Manual Testing → /testing/MANUAL_TESTING_GUIDE.md
```

#### 📝 Documentation Writers
```
1. Structure Guide → /00_DOCUMENTATION_STRUCTURE.md
2. API Docs → /api/
3. Features → /features/
4. References → /reference/
```

---

## 📌 Key Documents

### Essential Reading
- [00_DOCUMENTATION_STRUCTURE.md](./00_DOCUMENTATION_STRUCTURE.md) - Complete structure guide
- [PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md) - Comprehensive project docs
- [README.md](./README.md) - Main entry point

### For New Users
- [Getting Started](./guides/getting-started.md)
- [Quickstart](./guides/QUICKSTART.md)
- [Configuration](./guides/configuration.md)

### For API Users
- [API Quick Reference](./api/ENDPOINT_QUICK_REFERENCE.md)
- [API Best Practices](./api/API_BEST_PRACTICES.md)

### For Operators
- [Deployment Guide](./operations/deployment/deployment.md)
- [Operator Runbook](./operations/runbooks/OPERATOR_RUNBOOK.md)
- [Monitoring Setup](./operations/monitoring/MONITORING_SETUP.md)

### For Security
- [Auth Guide](./security/AUTH_GUIDE.md)
- [RBAC Matrix](./security/RBAC_MATRIX.md)
- [Security Audit](./security/SECURITY_AUDIT_REPORT.md)

---

## 📈 Documentation Statistics

- **Total Files**: 336+ documentation files
- **Directories**: 32 organized directories
- **Features Documented**: 10 major features
- **README Files**: 8+ navigation guides
- **API Endpoints**: Comprehensive coverage

---

## 🆘 Need Help?

### Can't Find Something?
1. Check this index
2. Look in relevant section README
3. Search by filename or keyword
4. Check [00_DOCUMENTATION_STRUCTURE.md](./00_DOCUMENTATION_STRUCTURE.md)

### Something Missing?
- Historical reports → [/status-reports/](./status-reports/)
- Feature docs → [/features/](./features/)
- API docs → [/api/](./api/)

---

## 🔗 External Resources

- **Source Code**: `../backend/`
- **Configuration**: `../config/`
- **Scripts**: `../scripts/`
- **Tests**: `../tests/`

---

## 📝 Maintenance

When adding new documentation:
- Follow the structure in [00_DOCUMENTATION_STRUCTURE.md](./00_DOCUMENTATION_STRUCTURE.md)
- Update relevant README files
- Keep historical reports in `/status-reports/`
- Add feature docs to `/features/{feature-name}/`

---

## ✨ Recent Reorganization

The documentation was recently reorganized (November 1, 2025) to improve:
- ✅ Discoverability and navigation
- ✅ Logical organization by purpose
- ✅ Separation of current vs. historical docs
- ✅ Clear pathways for different user types

See [REORGANIZATION_SUMMARY.md](./REORGANIZATION_SUMMARY.md) for details.

---

**Welcome to the Cineca Agentic Platform Documentation! 🚀**

*For a complete structure guide, see [00_DOCUMENTATION_STRUCTURE.md](./00_DOCUMENTATION_STRUCTURE.md)*

