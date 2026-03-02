# Security Guidelines

This document outlines the **security principles**, **controls**, and **operational practices** required to protect the **Agentic Platform** and its data.

---

## 1. Security Principles

1. **Least Privilege**  
   Every user, service, and process should operate with the minimal permissions necessary.

2. **Defense in Depth**  
   Multiple security layers protect against single points of failure.

3. **Secure by Default**  
   Services start with secure configurations, requiring explicit opt-in for risky features.

4. **Fail Securely**  
   When errors occur, systems must default to a safe state.

---

## 2. Sensitive Data Handling

### 2.1 Secrets Management
- Store secrets in `.env` files, vaults, or secure secret managers.
- Never commit secrets to version control.
- Rotate keys periodically (see `docs/runbooks/rotate-secrets.md`).

### 2.2 Data in Transit
- Use **TLS 1.2+** for all HTTP and database connections in production.
- For local dev, HTTP may be unencrypted but avoid exposing ports publicly.

### 2.3 Data at Rest
- Encrypt database volumes (Memgraph, Redis, logs) if persistent storage is used.
- Encrypt backups (see `docs/runbooks/backup-restore.md`).

---

## 3. Authentication & Authorization

### 3.1 API Authentication

- Use API keys, OAuth2 tokens, or JWTs.
- Keys must be rotated regularly and scoped to necessary actions.

### 3.2 Role-Based Access Control (RBAC)

- Define roles in `src/agent/roles.yaml`.
- Map API endpoints and MCP tools to roles.
- Use `SECURITY_ROLE_CONFIG` to point to the configuration.

### 3.3 Admin Surface Hardening

- **JWT Bearer required:** Every `/v1/admin/*` endpoint enforces the FastAPI `HTTPBearer` scheme. Requests without an `Authorization: Bearer <token>` header receive `401 Unauthorized`.
- **Scope enforcement:** Admin routes additionally demand the `admin:all` scope (derived automatically from the `roles` claim when it contains `admin`). Tokens lacking the scope receive `403 Forbidden`.
- **OpenAPI contract:** The aggregated OpenAPI document only exposes a single `HTTPBearer` scheme and annotates admin routes as secured, making it obvious to integrators which credentials are required.
- **Regression tests:** `pytest -q tests/security/test_admin_security.py` validates the 401/403 flow and ensures the bearer scheme stays correctly wired into the docs.

---

## 4. Input Validation & Output Sanitization

### 4.1 Validation

- All inputs (API, CLI, file uploads) must be validated against schemas.
- Reject or sanitize unknown fields.

### 4.2 Output Sanitization

- Prevent injection attacks by sanitizing outputs (e.g., escaping Cypher, SQL, HTML).

---

## 5. Logging & Audit

- All security events (logins, key usage, failed attempts) are logged.
- Logs must be immutable and time-synced.
- Use `src/security/audit.py` to send audit events to a central store.
- Redact sensitive fields in logs (`src/security/pii_scrubber.py`).

---

## 6. Network Security

### 6.1 Container Networking

- Use Docker networks to isolate services.
- Restrict inbound ports; only expose API and UI externally.

### 6.2 Firewall Rules

- Only allow necessary ports (e.g., 8000 API, 7687 Memgraph Bolt).
- Block admin interfaces (e.g., Prometheus, Grafana) from public access.

---

## 7. Rate Limiting & Abuse Prevention

- Enable Redis-backed rate limiting to protect APIs.
- Configure limits in `src/agent/retry.yaml` or `src/services/rate_limit.py`.
- Include IP-based throttling for public endpoints.

---

## 8. Supply Chain Security

- Pin dependencies in `requirements.txt`.
- Run vulnerability scans (`pip-audit`, `safety`) in CI.
- Use pre-commit hooks to block commits with security violations.

---

## 9. Secure Deployment

### 9.1 Containers

- Use minimal base images (e.g., `python:3.11-slim`).
- Run as non-root user.
- Enable `no-new-privileges` in Docker/K8s security contexts.

### 9.2 Production Environment

- Store `.env` in a secret manager or Kubernetes Secret.
- Isolate staging and production environments.
- Apply Infrastructure-as-Code (IaC) security scanning (e.g., `tfsec`, `kubesec`).

---

## 10. Incident Response

- Follow the playbook in `docs/runbooks/incident-response.md`.
- Maintain a 24/7 security contact channel.
- Classify incidents into severity levels and respond accordingly.

---

## 11. Compliance

- GDPR compliance is documented in `docs/compliance/gdpr.md`.
- Data retention policies are in `docs/compliance/data-retention.md`.
- Privacy-by-design principles in `docs/compliance/privacy-by-design.md`.

---

## 12. Security Testing

- Run **static analysis** (Bandit, mypy) on all commits.
- Run **dynamic analysis** (OWASP ZAP) on staging.
- Perform **penetration testing** before major releases.

---

## 13. Checklist for Production Readiness

- [ ] Secrets stored securely, not in repo
- [ ] TLS enabled for all external traffic
- [ ] Rate limiting enabled
- [ ] Logs redacted for PII
- [ ] Role-based access control configured
- [ ] Vulnerability scan passes in CI
- [ ] Backup & restore tested
- [ ] Incident response plan rehearsed

---

**Next Steps:**  
Refer to [docs/configuration.md](configuration.md) for configuring security-related environment variables and files.
