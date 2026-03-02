````markdown
# Runbook — Rotate Secrets

## Overview

This runbook describes the **process for rotating secrets** (API keys, database passwords, certificates, tokens, etc.) in the MCP Platform.

**Goals:**
- Replace sensitive credentials before expiry or when compromised.
- Minimize service downtime during rotation.
- Ensure compliance with **security policies** and **regulatory requirements**.

---

## 1. When to Rotate Secrets

Secrets should be rotated:

- **Periodically** (based on the security policy — default: every 90 days).
- **Immediately** if:
  - A security breach is suspected.
  - Credentials are exposed in logs, repositories, or third-party services.
  - Access privileges change (e.g., staff departure).

---

## 2. Types of Secrets Covered

| Secret Type | Examples | Rotation Method |
|-------------|----------|-----------------|
| **Database Credentials** | PostgreSQL, Memgraph usernames/passwords | Update in DB + `.env` |
| **API Keys** | Third-party APIs (OpenAI, Slack, AWS) | Regenerate from provider portal |
| **Certificates** | TLS/SSL certs | Generate new cert + update Nginx/Traefik |
| **OAuth Tokens** | GitHub, Google, etc. | Re-authorize application |
| **Internal Service Keys** | JWT signing keys, encryption keys | Generate new keys securely |

---

## 3. Preparation

**Before starting rotation:**

1. **Identify affected services** — list all systems that use the secret.
2. **Check dependencies** — ensure you know all configs, containers, or scripts that load the secret.
3. **Plan maintenance window** if downtime is expected.
4. **Back up current configuration** (store securely).
5. **Document** in the ticketing system:
   - Secret name
   - Current usage scope
   - Reason for rotation
   - Planned rotation date/time

---

## 4. Rotation Process

### Step 1 — Generate New Secret

- Follow **secure generation methods**:
  - Use a password manager or secret management tool (Vault, AWS Secrets Manager).
  - Minimum length & complexity per security policy.
  - Never generate secrets in plaintext on public machines.

**Example:**
```bash
openssl rand -base64 48
````

---

### Step 2 — Update Secret in Secret Manager / `.env`

* **If using a Secret Manager (recommended):**

  * Create a new version of the secret.
  * Set access policies (IAM roles, ACLs).
* **If using `.env` files:**

  * Edit `.env` or `.env.production`.
  * Ensure permissions are set to `600` (owner read/write only).

---

### Step 3 — Update Dependent Services

* Update configurations referencing the secret:

  * Kubernetes `Secret` objects
  * Docker Compose `env_file`
  * Systemd environment files
* Restart services to apply the new secret.

**Example (Docker Compose):**

```bash
docker compose up -d --force-recreate <service_name>
```

---

### Step 4 — Validation

* Verify new secret is active:

  * Run health checks (`/health` endpoint).
  * Check logs for authentication/connection errors.
* Ensure no service is still using the old secret.

---

### Step 5 — Revoke Old Secret

* Remove or deactivate the old secret to prevent misuse.
* In third-party platforms (AWS, GitHub, etc.), explicitly delete the old key.

---

### Step 6 — Documentation & Closure

* Update internal documentation with:

  * Rotation date
  * New expiry date
  * Responsible person/team
* Close the ticket in the incident/change tracking system.

---

## 5. Special Cases

### 5.1 Zero-Downtime Rotation

* If the system supports multiple active secrets, **enable both old and new** temporarily.
* Switch clients to the new secret.
* Remove the old secret after validation.

### 5.2 Emergency Rotation

* Skip scheduled window — rotate immediately.
* Communicate via **incident response channel**.
* Follow `incident-response.md` in parallel.

---

## 6. Security Notes

* Never store secrets in Git repositories.
* Avoid sending secrets over email or chat without encryption.
* Use short-lived credentials where possible.
* Log **only the rotation events**, never the secret itself.

---

## 7. Rotation Tracking Template

```yaml
secret_id: SECRET-YYYYMMDD-XXX
type: api-key|db-password|cert|token
owner: "Team or person responsible"
rotation_reason: scheduled|compromise|expiry
new_secret_location: vault://path/to/secret
generated_at: YYYY-MM-DD HH:MM:SS UTC
applied_to_services:
  - service-name
validated_at: YYYY-MM-DD HH:MM:SS UTC
old_secret_revoked_at: YYYY-MM-DD HH:MM:SS UTC
next_rotation_due: YYYY-MM-DD
notes: |
  Additional context or issues encountered
```

---

## 8. References

* [HashiCorp Vault Secret Rotation](https://developer.hashicorp.com/vault/docs/secrets/rotation)
* [AWS Secrets Manager Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
* [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_CheatSheet.html)
