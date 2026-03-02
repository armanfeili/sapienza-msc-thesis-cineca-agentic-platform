# Project Documentation

Welcome to the **Agentic Platform** documentation.  
This directory contains all the guides, references, architecture decisions, and operational runbooks needed to understand, configure, deploy, and maintain the system.

---

## 📚 Documentation Structure

### 1. **Getting Started**
- [`getting-started.md`](getting-started.md) — Quick start guide for developers and operators to get the platform running locally or in a staging environment.

### 2. **Architecture**
- [`architecture.md`](architecture.md) — High-level overview of system components, their interactions, and deployment topology.
- [`diagrams/`](diagrams) — Visual diagrams for architecture, data flow, and component relationships.

### 3. **Configuration & Deployment**
- [`configuration.md`](configuration.md) — Detailed explanation of configuration options, environment variables, and YAML/JSON files.
- [`deployment.md`](deployment.md) — Guides for deploying to various environments (Docker Compose, Kubernetes, cloud services).

### 4. **Security & Compliance**
- [`security.md`](security.md) — Security considerations, authentication, authorization, and encryption.
- [`compliance/gdpr.md`](compliance/gdpr.md) — GDPR compliance guidelines.
- [`compliance/data-retention.md`](compliance/data-retention.md) — Data retention policies.
- [`compliance/privacy-by-design.md`](compliance/privacy-by-design.md) — Privacy by design principles.

### 5. **API Reference**
- [`api/README.md`](api/README.md) — Overview of the MCP API and tool surface.
- [`api/mcp-tools.md`](api/mcp-tools.md) — Tool-specific documentation and usage examples.
- [`api/openapi.json`](api/openapi.json) — Auto-generated OpenAPI spec for client integration.

### 6. **Observability**
- [`observability/observability.md`](observability/observability.md) — Introduction to system observability.
- [`observability/metrics.md`](observability/metrics.md) — Metrics exposed by the system.
- [`observability/tracing.md`](observability/tracing.md) — Distributed tracing setup.
- [`observability/alerting.md`](observability/alerting.md) — Alert configuration and playbooks.
- [`observability/dashboards.md`](observability/dashboards.md) — Dashboard references and usage.
- [`observability/promql-examples.md`](observability/promql-examples.md) — Common PromQL queries.
- Grafana dashboards:
  - [`observability/mcp-tools-dashboard.json`](observability/mcp-tools-dashboard.json)
  - [`observability/grafana-dashboard.json`](observability/grafana-dashboard.json)
  - [`observability/db-memgraph-dashboard.json`](observability/db-memgraph-dashboard.json)

### 7. **Operational Runbooks**
- [`runbooks/backup-restore.md`](runbooks/backup-restore.md) — Procedures for database and configuration backup & restore.
- [`runbooks/incident-response.md`](runbooks/incident-response.md) — Steps to follow during incidents or outages.
- [`runbooks/rotate-secrets.md`](runbooks/rotate-secrets.md) — Rotating and revoking credentials securely.

### 8. **Architecture Decision Records (ADRs)**
- [`adr/_template.md`](adr/_template.md) — Template for creating new ADRs.
- [`adr/0001-record-architecture-decisions.md`](adr/0001-record-architecture-decisions.md) — First ADR documenting the decision-making process.

---

## 📖 How to Use This Documentation

1. **New Developers** — Start with [Getting Started](getting-started.md) to set up your environment.
2. **Operators** — Focus on [Configuration](configuration.md), [Deployment](deployment.md), and [Runbooks](runbooks/).
3. **Security Officers** — Review [Security](security.md) and [Compliance](compliance/).
4. **Integrators** — Check [API Reference](api/) and `openapi.json` for client integration.

---

## 🛠 Contributing to Docs

If you make changes to the codebase that affect configuration, APIs, or operational processes:
1. Update the relevant markdown files.
2. If diagrams change, update `.drawio` sources and export them as `.png` for easy viewing.
3. Submit your changes in the same PR as the code updates when possible.

---

_Last updated: {{DATE}}_
