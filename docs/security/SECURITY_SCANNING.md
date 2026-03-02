# Security Scanning Guide

This document describes the automated security scanning tools and processes for the Cineca Agentic Platform.

## Overview

Security scanning is automated via GitHub Actions and runs on:
- Every push to `main` and `develop` branches
- Every pull request
- Daily at 2 AM UTC (scheduled scan)
- Manual workflow dispatch

## Scanning Tools

### 1. SAST (Static Application Security Testing)

#### Bandit - Python Security Linter
- **Purpose**: Identifies common security issues in Python code
- **Configuration**: `pyproject.toml` → `[tool.bandit]`
- **Checks for**:
  - SQL injection vulnerabilities
  - Shell injection risks
  - Insecure random number generation
  - Hardcoded passwords/secrets
  - Weak cryptographic algorithms
  - Use of dangerous functions (eval, exec, pickle)

**Example issues detected**:
```python
# BAD - Bandit will flag this
password = "hardcoded_secret_123"  # B105: Hardcoded password

# GOOD
password = os.environ.get("PASSWORD")
```

### 2. Dependency Scanning

#### Python Dependencies
- **pip-audit**: Scans for known vulnerabilities in Python packages
- **Safety**: Checks against Safety DB for vulnerable dependencies

**Reports**:
- JSON format for automation
- Human-readable console output

#### Node.js Dependencies
- **npm audit**: Scans Node.js dependencies (Playwright, dev tools)

**Actions on findings**:
1. Review vulnerability details
2. Check if upgrade is available
3. If no fix: Document risk acceptance or apply workaround

### 3. Container Scanning

#### Trivy - Container Vulnerability Scanner
- **Scans**: Docker images for both `app` and `ui` services
- **Severity levels**: CRITICAL, HIGH, MEDIUM
- **Reports**: 
  - SARIF format (uploaded to GitHub Security tab)
  - Table format (console output)

**Images scanned**:
- `cineca-app:latest` (main backend)
- `cineca-ui:latest` (Streamlit UI)

### 4. Secret Scanning

#### Gitleaks
- Scans commit history for leaked secrets
- Checks for API keys, tokens, passwords, private keys

#### Custom Secret Patterns
Additional regex-based checks for:
- `api_key=`, `secret=`, `password=`, `token=`
- Hardcoded credentials in source files

**Excluded from scanning**:
- `/tests/` - Test fixtures may contain mock secrets
- `/examples/` - Example code with dummy values
- `/docs/` - Documentation with sample values

### 5. DAST (Dynamic Application Security Testing)

#### OWASP ZAP Baseline Scan
- **Type**: Passive scanner (non-intrusive)
- **Target**: Running API at `http://localhost:8000`
- **Configuration**: `.zap/rules.tsv`

**Checks for**:
- Missing security headers
- Cross-Site Scripting (XSS)
- SQL Injection
- Command Injection
- Insecure HTTP methods
- Information disclosure

**ZAP Rules Thresholds**:
- `FAIL`: Critical security issues (XSS, injection attacks)
- `WARN`: Important but not critical (missing headers)
- `IGNORE`: Development-only issues or false positives

### 6. License Compliance

#### pip-licenses
- **Purpose**: Ensure dependency licenses are compatible
- **Checks for**: GPL, AGPL, SSPL (copyleft licenses)
- **Output**: JSON and Markdown reports

**Policy**:
- Copyleft licenses trigger warning (manual review required)
- Permissive licenses (MIT, Apache 2.0, BSD) are approved

## Workflow Integration

### security.yml Workflow

```yaml
Jobs:
  1. sast-bandit          → Static analysis (Python)
  2. dependency-scan-python → pip-audit, Safety
  3. dependency-scan-nodejs → npm audit
  4. container-scan       → Trivy (app + ui images)
  5. secret-scan          → Gitleaks + custom patterns
  6. zap-baseline         → OWASP ZAP passive scan
  7. license-compliance   → License check
  8. security-summary     → Aggregate results
```

### Failure Handling

**Critical failures (block merge)**:
- Secret scan detects exposed credentials
- OWASP ZAP finds FAIL-level vulnerabilities

**Warnings (don't block merge, require review)**:
- Dependency vulnerabilities (no fix available)
- Container vulnerabilities (MEDIUM severity)
- Missing security headers
- Copyleft licenses

## Artifacts

All scan reports are uploaded as GitHub Actions artifacts:
- `bandit-report.json`
- `pip-audit-report.json`, `safety-report.json`
- `npm-audit-report.json`
- `trivy-app-sarif`, `trivy-ui-sarif`
- `zap-scan-report`
- `license-report` (JSON + Markdown)

**Retention**: 30 days

## Viewing Results

### GitHub Security Tab
1. Navigate to repository
2. Click **Security** tab
3. Click **Code scanning alerts**
4. View Trivy and other SARIF uploads

### Workflow Artifacts
1. Go to Actions → security.yml workflow
2. Click on a run
3. Scroll to **Artifacts** section
4. Download reports

### Local Scanning

#### Run Bandit locally
```bash
bandit -c pyproject.toml -r src -f screen
```

#### Run Trivy locally
```bash
# Scan Docker image
docker build -t cineca-app:latest .
trivy image cineca-app:latest
```

#### Run OWASP ZAP locally
```bash
docker compose up -d
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://host.docker.internal:8000 \
  -r zap-report.html
```

#### Run dependency scans locally
```bash
# Python
pip install pip-audit safety
pip-audit
safety check

# Node.js
npm audit
```

## Remediation Process

### High/Critical Vulnerabilities

1. **Assess severity and exploitability**
   - Is the vulnerable code path reachable?
   - Are there mitigating controls?

2. **Check for updates**
   ```bash
   pip list --outdated
   npm outdated
   ```

3. **Apply fixes**
   - Update to patched version
   - Apply workaround if no patch available
   - Document risk acceptance if cannot fix

4. **Verify fix**
   ```bash
   # Re-run scans
   pip-audit
   trivy image cineca-app:latest
   ```

5. **Update CHANGELOG.md**
   ```markdown
   ### Security
   - Fixed [CVE-2024-XXXX] by upgrading package X to version Y
   ```

### False Positives

If a finding is a false positive:

1. **Document justification** in `docs/security/FALSE_POSITIVES.md`
2. **Update scan configuration** to suppress
3. **Add comment in code** explaining why it's safe

Example:
```python
# nosec B602 - subprocess call is safe here because input is validated
subprocess.run([cmd], check=True)
```

## Security Best Practices

### Dependency Management
- Pin dependency versions in `requirements.txt`
- Review changelogs before upgrading
- Run tests after dependency updates

### Secrets Management
- **Never** commit secrets to git
- Use environment variables
- Rotate secrets regularly
- Use secrets management service (e.g., AWS Secrets Manager, HashiCorp Vault)

### Container Security
- Use minimal base images
- Run containers as non-root user
- Scan images before deployment
- Update base images regularly

### Code Security
- Validate all user inputs
- Use parameterized queries (no string concatenation in SQL)
- Sanitize outputs to prevent XSS
- Use secure random for tokens/IDs
- Enable security headers (HSTS, CSP, X-Frame-Options)

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [OWASP ZAP Documentation](https://www.zaproxy.org/docs/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

## Contact

For security concerns or to report vulnerabilities:
- See `SECURITY.md` in project root
- Email: security@cineca.it (if available)
- Open a **private** security advisory on GitHub

