# Secrets Rotation Guide

**Last Updated**: November 2, 2025  
**Security Level**: Critical  
**Frequency**: Quarterly (minimum) or immediately after suspected compromise

---

## 📋 Overview

This guide covers the secure rotation of all secrets and credentials used by the Cineca Agentic Platform. Regular rotation reduces the risk of credential compromise and is a critical security best practice.

## 🔐 Secrets Inventory

### Critical Secrets (Rotate Quarterly)

| Secret | Location | Rotation Impact | Dependencies |
|--------|----------|----------------|--------------|
| **Auth0 Client Secret** | `.env`, Secrets Manager | High - Requires service restart | All API endpoints, UI authentication |
| **PostgreSQL Password** | `.env`, `docker-compose.yml` | High - Database restart needed | All services using PostgreSQL |
| **Redis Password** | `.env`, `docker-compose.yml` | Medium - Cache invalidated | Session storage, rate limiting |
| **JWT Signing Key** | `.env` | Critical - All tokens invalidated | All authenticated requests |
| **Encryption Keys** | `.env`, Secrets Manager | High - Cannot decrypt old data | Encrypted data at rest |

### Important Secrets (Rotate Annually)

| Secret | Location | Rotation Impact | Dependencies |
|--------|----------|----------------|--------------|
| **Memgraph Password** | `.env`, `docker-compose.yml` | Medium - Graph DB restart | Knowledge graph operations |
| **API Keys (External)** | `.env`, Database | Low-Medium | External service integrations |
| **SSH Keys** | Server filesystem | Medium | Deployment, server access |
| **TLS Certificates** | `/etc/ssl/`, Load balancer | High - HTTPS affected | All external connections |

---

## 🔄 Rotation Procedures

### 1. Auth0 Client Secret Rotation

**When**: Quarterly or on suspected compromise  
**Impact**: All users must re-authenticate  
**Downtime**: ~5 minutes

#### Pre-Rotation Checklist
- [ ] Schedule maintenance window (off-peak hours)
- [ ] Notify users 24-48 hours in advance
- [ ] Backup current configuration
- [ ] Test in staging environment first

#### Steps

**1. Create New Client Secret in Auth0**
```bash
# Login to Auth0 Dashboard
# Navigate to: Applications > [Your App] > Settings > Credentials
# Click "Rotate" next to Client Secret
# Copy new secret to secure location
```

**2. Update Environment Variables**
```bash
# Backup current .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Update .env (use secure editor)
vim .env
# Replace AUTH0_CLIENT_SECRET with new value
```

**3. Update Secrets in Production**
```bash
# If using Kubernetes secrets
kubectl create secret generic auth0-secret \
  --from-literal=client-secret='NEW_SECRET' \
  --dry-run=client -o yaml | kubectl apply -f -

# If using Docker secrets
echo 'NEW_SECRET' | docker secret create auth0_client_secret_v2 -

# If using AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id cineca-platform/auth0/client-secret \
  --secret-string 'NEW_SECRET'
```

**4. Rolling Restart**
```bash
# Using deployment script
./scripts/deploy-production.sh production

# Or manual rolling restart
docker compose up -d --no-deps --force-recreate app
docker compose up -d --no-deps --force-recreate ui
```

**5. Verification**
```bash
# Test authentication
curl -X POST https://api.example.com/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "NEW_SECRET"
  }'

# Expected: HTTP 200 with access token
```

**6. Deactivate Old Secret**
```bash
# In Auth0 Dashboard
# Wait 24 hours to ensure all systems updated
# Then remove old client secret
```

#### Rollback Procedure
```bash
# If new secret fails
cp .env.backup.TIMESTAMP .env
docker compose restart app ui
# Update Auth0 to use old secret again
```

---

### 2. Database Password Rotation (PostgreSQL)

**When**: Quarterly  
**Impact**: Brief database reconnection  
**Downtime**: ~2 minutes

#### Steps

**1. Generate New Password**
```bash
# Generate strong password (32 characters)
NEW_PG_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
echo "New password: $NEW_PG_PASSWORD"
# Store securely immediately
```

**2. Create New Database User (Recommended) or Update Existing**

**Option A: Create New User (Zero Downtime)**
```sql
-- Connect to PostgreSQL
psql -U postgres -d cineca_platform

-- Create new user with same privileges
CREATE USER cineca_app_v2 WITH PASSWORD 'NEW_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE cineca_platform TO cineca_app_v2;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cineca_app_v2;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cineca_app_v2;
```

**Option B: Update Existing User Password**
```sql
-- Connect to PostgreSQL
psql -U postgres

-- Change password
ALTER USER cineca_app WITH PASSWORD 'NEW_PASSWORD';
```

**3. Update Application Configuration**
```bash
# Update .env
DATABASE_URL="postgresql://cineca_app_v2:NEW_PASSWORD@postgres:5432/cineca_platform"

# Update docker-compose.yml if using environment variables
vim docker-compose.yml
```

**4. Test Connection**
```bash
# Test new credentials
psql "postgresql://cineca_app_v2:NEW_PASSWORD@localhost:5432/cineca_platform" -c "SELECT version();"
```

**5. Rolling Restart Application**
```bash
# Restart services one by one
docker compose up -d --no-deps --force-recreate app
sleep 10
docker compose logs app | grep -i "database connection"
```

**6. Cleanup Old User (After 48 Hours)**
```sql
-- Verify new user is working
-- Then drop old user
DROP USER cineca_app;
```

---

### 3. Redis Password Rotation

**When**: Quarterly  
**Impact**: Session invalidation (users logged out)  
**Downtime**: ~1 minute

#### Steps

**1. Generate New Password**
```bash
NEW_REDIS_PASSWORD=$(openssl rand -base64 24 | tr -d "=+/" | cut -c1-24)
```

**2. Update Redis Configuration**
```bash
# Update docker-compose.yml
vim docker-compose.yml
# Change REDIS_PASSWORD under redis service

# Or update redis.conf
echo "requirepass $NEW_REDIS_PASSWORD" >> /etc/redis/redis.conf
```

**3. Update Application Configuration**
```bash
# Update .env
REDIS_URL="redis://:$NEW_REDIS_PASSWORD@redis:6379/0"
```

**4. Restart Redis (Will Invalidate Sessions)**
```bash
docker compose restart redis
```

**5. Restart Application Services**
```bash
docker compose restart app ui
```

**6. Verification**
```bash
# Test connection
redis-cli -h localhost -p 6379 -a "$NEW_REDIS_PASSWORD" PING
# Expected: PONG
```

---

### 4. JWT Signing Key Rotation

**When**: Quarterly or on compromise  
**Impact**: All JWT tokens invalidated immediately  
**Downtime**: None (but all users must re-authenticate)

⚠️ **WARNING**: This will invalidate ALL active sessions

#### Steps

**1. Generate New Key Pair**
```bash
# Generate new RS256 private key
openssl genpkey -algorithm RSA -out jwt_private_new.pem -pkeyopt rsa_keygen_bits:2048

# Extract public key
openssl rsa -pubout -in jwt_private_new.pem -out jwt_public_new.pem

# Or for HS256 (symmetric)
NEW_JWT_SECRET=$(openssl rand -base64 64 | tr -d "=+/" | cut -c1-64)
```

**2. Implement Dual-Key Validation (Recommended)**
```python
# In your JWT validation code
def validate_token(token):
    # Try new key first
    try:
        return jwt.decode(token, NEW_PUBLIC_KEY, algorithms=['RS256'])
    except jwt.InvalidSignatureError:
        # Fall back to old key during transition
        return jwt.decode(token, OLD_PUBLIC_KEY, algorithms=['RS256'])
```

**3. Update Environment**
```bash
# Update .env
JWT_PRIVATE_KEY_PATH=/path/to/jwt_private_new.pem
JWT_PUBLIC_KEY_PATH=/path/to/jwt_public_new.pem
# Or for HS256
JWT_SECRET_KEY=$NEW_JWT_SECRET
```

**4. Deploy with Dual-Key Support**
```bash
# Deploy new version with dual-key validation
./scripts/deploy-production.sh production
```

**5. Monitor Token Usage**
```bash
# Monitor which key is being used
docker compose logs app | grep "JWT validation" | grep "key_version"
```

**6. Remove Old Key (After 7 Days)**
```bash
# Once old tokens expired (check JWT expiry time)
# Remove old key from code and redeploy
```

---

### 5. TLS Certificate Rotation

**When**: Before expiration (30-60 days)  
**Impact**: HTTPS connections (brief interruption)  
**Downtime**: <1 minute with proper configuration

#### Steps

**1. Generate Certificate Signing Request (CSR)**
```bash
# Create private key
openssl genrsa -out platform_new.key 2048

# Create CSR
openssl req -new -key platform_new.key -out platform_new.csr \
  -subj "/C=IT/ST=Lazio/L=Rome/O=Cineca/CN=platform.example.com"
```

**2. Submit CSR to Certificate Authority**
```bash
# Submit to Let's Encrypt, DigiCert, etc.
# Or use certbot for Let's Encrypt
certbot certonly --standalone -d platform.example.com
```

**3. Install New Certificate**
```bash
# Copy new certificate and key
sudo cp platform_new.crt /etc/ssl/certs/
sudo cp platform_new.key /etc/ssl/private/
sudo chmod 600 /etc/ssl/private/platform_new.key
```

**4. Update Web Server Configuration**

**Nginx Example**:
```nginx
# Update nginx.conf
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/platform_new.crt;
    ssl_certificate_key /etc/ssl/private/platform_new.key;
    # ... rest of config
}
```

**5. Test Configuration**
```bash
# Test nginx config
nginx -t

# Or for Apache
apachectl configtest
```

**6. Reload (No Downtime)**
```bash
# Nginx graceful reload
nginx -s reload

# Or Apache
systemctl reload apache2
```

**7. Verify**
```bash
# Check certificate
openssl s_client -connect platform.example.com:443 -servername platform.example.com < /dev/null | openssl x509 -noout -dates

# Or use online tools
curl -vI https://platform.example.com
```

---

## 🔧 Automation Scripts

### Automated Rotation Script

Create `/scripts/rotate-secrets.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Secrets Rotation Automation Script
# Usage: ./scripts/rotate-secrets.sh [secret-type]

SECRET_TYPE="${1:-all}"
BACKUP_DIR="/var/backups/secrets/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="/var/log/secrets-rotation.log"

# Function: Log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Function: Backup current secrets
backup_secrets() {
    log "Creating backup in $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp .env "$BACKUP_DIR/.env"
    cp docker-compose.yml "$BACKUP_DIR/docker-compose.yml"
    log "Backup completed"
}

# Function: Generate strong password
generate_password() {
    local length="${1:-32}"
    openssl rand -base64 48 | tr -d "=+/" | cut -c1-"$length"
}

# Function: Rotate PostgreSQL password
rotate_postgres() {
    log "Starting PostgreSQL password rotation"
    
    NEW_PG_PASSWORD=$(generate_password 32)
    
    # Create new user
    docker compose exec -T postgres psql -U postgres <<EOF
CREATE USER cineca_app_$(date +%Y%m%d) WITH PASSWORD '$NEW_PG_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE cineca_platform TO cineca_app_$(date +%Y%m%d);
EOF
    
    # Update .env
    sed -i.bak "s|DATABASE_URL=.*|DATABASE_URL=postgresql://cineca_app_$(date +%Y%m%d):$NEW_PG_PASSWORD@postgres:5432/cineca_platform|" .env
    
    log "PostgreSQL password rotated successfully"
}

# Function: Rotate Redis password
rotate_redis() {
    log "Starting Redis password rotation"
    
    NEW_REDIS_PASSWORD=$(generate_password 24)
    
    # Update .env
    sed -i.bak "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$NEW_REDIS_PASSWORD|" .env
    sed -i.bak "s|REDIS_URL=.*|REDIS_URL=redis://:$NEW_REDIS_PASSWORD@redis:6379/0|" .env
    
    # Update docker-compose.yml
    sed -i.bak "s|REDIS_PASSWORD:.*|REDIS_PASSWORD: $NEW_REDIS_PASSWORD|" docker-compose.yml
    
    log "Redis password rotated successfully"
}

# Function: Send notification
notify() {
    local message="$1"
    # Send to Slack, email, etc.
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"text\":\"$message\"}" \
    #   "$SLACK_WEBHOOK_URL"
    log "Notification: $message"
}

# Main execution
main() {
    log "=== Secrets Rotation Started ==="
    
    backup_secrets
    
    case "$SECRET_TYPE" in
        postgres|database)
            rotate_postgres
            ;;
        redis)
            rotate_redis
            ;;
        all)
            rotate_postgres
            rotate_redis
            ;;
        *)
            log "ERROR: Unknown secret type: $SECRET_TYPE"
            log "Usage: $0 [postgres|redis|all]"
            exit 1
            ;;
    esac
    
    log "Restarting services..."
    docker compose up -d --no-deps --force-recreate app ui
    
    log "=== Secrets Rotation Completed ==="
    notify "Secrets rotation completed successfully for: $SECRET_TYPE"
}

main "$@"
```

Make it executable:
```bash
chmod +x scripts/rotate-secrets.sh
```

---

## 📅 Rotation Schedule

### Quarterly Rotation (Every 90 Days)
- [ ] Auth0 Client Secret
- [ ] PostgreSQL Password
- [ ] Redis Password
- [ ] JWT Signing Key
- [ ] Memgraph Password

### Annual Rotation (Every 365 Days)
- [ ] SSH Keys
- [ ] External API Keys
- [ ] Service Account Tokens

### As-Needed Rotation
- [ ] TLS Certificates (60 days before expiry)
- [ ] Compromised credentials (immediately)

### Rotation Calendar Template

```
Q1 (Jan-Mar): All quarterly secrets
Q2 (Apr-Jun): All quarterly secrets  
Q3 (Jul-Sep): All quarterly secrets + Annual review
Q4 (Oct-Dec): All quarterly secrets

TLS Certificates: Monitor expiry dates, rotate 60 days before
```

---

## ✅ Post-Rotation Checklist

After each rotation:

- [ ] All services restarted successfully
- [ ] Health checks passing
- [ ] Authentication working
- [ ] Database connections active
- [ ] Cache functioning properly
- [ ] Logs reviewed for errors
- [ ] Old secrets documented
- [ ] Backup verified
- [ ] Team notified
- [ ] Incident response plan updated
- [ ] Rotation documented in change log

---

## 🚨 Emergency Rotation (Compromised Secrets)

If a secret is compromised:

1. **Immediate Actions** (within 15 minutes):
   - Rotate the compromised secret
   - Revoke old credentials
   - Restart affected services
   - Monitor for unauthorized access

2. **Investigation** (within 1 hour):
   - Review access logs
   - Identify scope of compromise
   - Document timeline
   - Notify security team

3. **Remediation** (within 24 hours):
   - Rotate all related secrets
   - Update security controls
   - Implement additional monitoring
   - Conduct post-incident review

4. **Documentation**:
   - Create incident report
   - Update rotation procedures
   - Train team on findings

---

## 🔒 Security Best Practices

### Secrets Storage
- ✅ **DO**: Use secrets managers (AWS Secrets Manager, HashiCorp Vault)
- ✅ **DO**: Encrypt secrets at rest
- ✅ **DO**: Use environment-specific secrets
- ❌ **DON'T**: Commit secrets to version control
- ❌ **DON'T**: Share secrets in plain text
- ❌ **DON'T**: Hardcode secrets in application code

### Access Control
- Implement least privilege access
- Use role-based access control (RBAC)
- Enable multi-factor authentication (MFA)
- Audit secret access regularly
- Rotate admin credentials more frequently

### Monitoring
- Log all secret access attempts
- Alert on unusual access patterns
- Monitor certificate expiration
- Track rotation compliance
- Review access logs weekly

---

## 📚 References

- [OWASP Secret Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [NIST Special Publication 800-57](https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final)
- [CIS Controls v8](https://www.cisecurity.org/controls/v8)

---

**Security Contact**: security@example.com  
**Last Rotation**: See `/var/log/secrets-rotation.log`  
**Next Scheduled Rotation**: [Calculate based on last rotation + 90 days]
