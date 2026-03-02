# Security Policy

We take security seriously and appreciate responsible disclosure. This document explains **how to report vulnerabilities**, **what’s in scope**, and **what we do to fix issues**.

---

## Supported Versions

| Version/Branch | Supported |
|:--|:--|
| `main` | ✅ |
| Release tags (if any) | case-by-case |

If you are using a fork or an older snapshot, please reproduce the issue on `main` where possible.

---

## Reporting a Vulnerability

Please use **one** of the following private channels:

1. **GitHub Security Advisory (preferred)**  
   Open a private advisory for the repository (Security → Advisories → “Report a vulnerability”).

2. **Email (fallback)**  
   Send details to: **security@yourdomain.example**  
   If you require encryption, use our PGP key (replace placeholder):
   - PGP: `pgp-public-key-here`
   - Fingerprint: `0000 0000 0000 0000 0000  0000 0000 0000 0000 0000`

### What to include
- A clear description of the issue and **impact** (data exfiltration, RCE, auth bypass, etc.).
- **Steps to reproduce** or a proof-of-concept (PoC).
- Affected **endpoints/tools** and configuration (env vars, feature flags).
- Any logs, stack traces, or error messages.
- Suggested **CVSS v3.1** vector/score if you can.

Please **do not** open public issues for vulnerabilities.

---

## Coordinated Disclosure

We aim to:
- **Acknowledge** your report within **48 hours**.
- **Triage** within **5 business days**.
- Provide a **remediation plan/ETA** within **10 business days**.
- Release a **fix and advisory** as soon as reasonably possible (target **< 90 days** for complex issues).

We will credit researchers upon request (unless you prefer anonymity).

---

## Scope

In scope (representative, not exhaustive):
- **FastAPI app** (everything under `src/`), especially:
  - `src/routers/*` (REST endpoints)
  - `src/services/*` (orchestration, session)
  - `src/security/*` (authN/Z, validation, rate limiting, output guard)
  - `src/adapters/*` (LLM, Memgraph)
  - `src/mcp/*` (manifest/policies/tools)
  - `src/observability/*` (metrics/middleware)
- **Database modules**:
  - `db/redis_cache/*` (Redis client, job storage, caching)
  - `db/postgres_control/*` (PostgreSQL client, repositories, migrations)
  - `db/memgraph_domain/*` (Memgraph client, graph operations)
- **Container & runtime configs**:
  - `Dockerfile`, `docker-compose.yml`, `ops/*`, `.env` handling

Out of scope:
- Social engineering, physical attacks, third-party infrastructure not controlled by this project.
- Denial of Service purely through volumetric traffic (but **algorithmic DoS** is in scope).
- Findings without a demonstrable security impact (e.g., missing security headers on non-sensitive routes in dev mode).

---

## Common Vulnerability Classes We Care About

- **Authentication**: weak tokens, predictable sessions, missing expiry/rotation.
- **Authorization**: horizontal/vertical privilege escalation, multi-tenant breaks.
- **Injection**: prompt/LLM, Cypher, SQL (if added), command injection.
- **Deserialization & RCE**.
- **Path traversal & file disclosure**.
- **SSRF** via outbound adapters (LLM, webhooks).
- **XSS/CSRF** (if browser clients are introduced).
- **Insecure defaults** in `docker-compose.yml` or `.env`.
- **Sensitive data exposure**: logs without scrubbing, mis-scoped PII.
- **Bypass of rate limit / abuse protections**.
- **Cryptographic misuse**.

---

## How We Handle Vulnerabilities

1. **Confirm & Triage**  
   Reproduce in a clean environment; assess severity with CVSS v3.1.

2. **Patch**  
   - Add test coverage to prevent regressions.
   - Integrate with the **security pipeline**:
     - Input checks: `src/security/validators.py`
     - Intent filter: `src/security/intent_filter.py`
     - Output/Cypher guard: `src/security/output_guard.py`
     - AuthN/Z: `src/security/{auth.py,authorization.py}`
     - PII scrubber: `src/security/pii_scrubber.py`
     - Rate limiting: `src/security/rate_limit.py` (memory/Redis via `db/redis_cache/client.py`)
     - Audit trail: `src/security/audit.py`

3. **Advisory & Release**  
   Publish a security advisory with remediation details and affected versions.

---

## Operational Guidance (Deployers)

- **Secrets**: never commit; use env vars or a secret manager. Rotate per `docs/runbooks/rotate-secrets.md`.
- **Logging**: keep `LOG_LEVEL` appropriate (avoid DEBUG in prod). PII scrubbing is built-in but not foolproof.
- **CORS/CSRF**: restrict origins; disable interactive docs in prod if not needed.
- **Network**: isolate Memgraph/Redis from public ingress; prefer private networking.
- **TLS**: terminate at a trusted proxy or use app-level TLS.
- **Backups**: encrypt and protect access; see `docs/runbooks/backup-restore.md`.
- **Rate Limits**: enable Redis backend (`RATE_LIMIT_BACKEND=redis`) in production.

---

## Dependency Security

- We recommend continuous scanning (e.g., **pip-audit**, GitHub Dependabot/CodeQL).
- Pin dependencies in `requirements.txt`.  
- Apply updates promptly for critical CVEs and document exceptions.

---

## Testing Guidance for Researchers

- Only test on **your own deployments** or with explicit permission.
- Avoid sending real PII; use test data from `examples/data/*`.
- Respect rate limits and avoid disrupting shared environments.

---

## Contact & Attribution

- Private reports: **security@yourdomain.example**
- Alternative: GitHub Security Advisory

Thank you for helping keep this project and its users safe.
