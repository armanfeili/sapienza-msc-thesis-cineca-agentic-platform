# Security Documentation

This directory contains security documentation, authentication guides, and security audit reports for the Cineca Agentic Platform.

## 📚 Security Documentation

### Core Security Guides
- **security.md** - Main security overview and policies
- **SECURITY_REFERENCE.md** - Security reference documentation
- **AUTH_GUIDE.md** - Comprehensive authentication guide
- **AUTH0_INTEGRATION.md** - Auth0 integration documentation

### Access Control
- **RBAC_MATRIX.md** - Role-Based Access Control matrix
- **PERMISSION_SIMPLIFICATION_SUMMARY.md** - Permission system overview

### Token Management
- **REAL_TOKENS_INTEGRATION.md** - Real tokens integration guide
- Token lifecycle and management

### Security Audits
- **SECURITY_AUDIT_REPORT.md** - Comprehensive security audit findings
- **SECURITY_INCIDENT_2025-10-22.md** - Security incident report and remediation

---

## 🔒 Security Topics

### Authentication & Authorization
1. **Auth0 Integration**
   - Setup: [AUTH0_INTEGRATION.md](./AUTH0_INTEGRATION.md)
   - Best practices: [AUTH_GUIDE.md](./AUTH_GUIDE.md)

2. **RBAC (Role-Based Access Control)**
   - Matrix: [RBAC_MATRIX.md](./RBAC_MATRIX.md)
   - Implementation: See [AUTH_GUIDE.md](./AUTH_GUIDE.md)

3. **Token Management**
   - Real tokens: [REAL_TOKENS_INTEGRATION.md](./REAL_TOKENS_INTEGRATION.md)

### Security Compliance
1. **Security Audits**
   - Latest audit: [SECURITY_AUDIT_REPORT.md](./SECURITY_AUDIT_REPORT.md)
   - Incident response: [SECURITY_INCIDENT_2025-10-22.md](./SECURITY_INCIDENT_2025-10-22.md)

2. **Security Reference**
   - Security guidelines: [SECURITY_REFERENCE.md](./SECURITY_REFERENCE.md)
   - Security policies: [security.md](./security.md)

---

## 🎯 Quick Start for Security

### For Developers
1. Read [AUTH_GUIDE.md](./AUTH_GUIDE.md) for authentication implementation
2. Review [RBAC_MATRIX.md](./RBAC_MATRIX.md) for permission structure
3. Check [SECURITY_REFERENCE.md](./SECURITY_REFERENCE.md) for security best practices

### For Operators
1. Review [security.md](./security.md) for security policies
2. Implement monitoring from [SECURITY_AUDIT_REPORT.md](./SECURITY_AUDIT_REPORT.md)
3. Follow incident response procedures

### For Auditors
1. Start with [SECURITY_AUDIT_REPORT.md](./SECURITY_AUDIT_REPORT.md)
2. Review [SECURITY_INCIDENT_2025-10-22.md](./SECURITY_INCIDENT_2025-10-22.md)
3. Check [RBAC_MATRIX.md](./RBAC_MATRIX.md) for access controls

---

## 🔐 Security Features

The platform implements:

- ✅ **Auth0 Integration** - Enterprise-grade authentication
- ✅ **RBAC** - Fine-grained role-based access control
- ✅ **Token Management** - Secure token lifecycle
- ✅ **Rate Limiting** - API rate limiting (see [../api/](../api/))
- ✅ **Security Auditing** - Regular security audits
- ✅ **Incident Response** - Documented incident procedures

---

## 🔗 Related Documentation

### Security Implementation
- [API Security](../api/) - API security and rate limiting
- [Operations Security](../operations/) - Operational security

### Feature Security
- [Agents Security](../features/agents/) - Agent security
- [Internal Endpoints](../features/internal-endpoints/) - Internal endpoint security
- [User Access](../features/user-access/) - User access controls

### Testing
- [Security Testing](../testing/) - Security testing procedures
- [Status Reports](../status-reports/) - Security completion reports

---

## 📊 Security Metrics

For security metrics and monitoring:
- See [../operations/monitoring/](../operations/monitoring/) for observability
- Check [../operations/monitoring/SLO.md](../operations/monitoring/SLO.md) for SLOs

---

## 🚨 Incident Response

For security incidents:
1. Follow [../operations/monitoring/INCIDENT_RESPONSE.md](../operations/monitoring/INCIDENT_RESPONSE.md)
2. Review [SECURITY_INCIDENT_2025-10-22.md](./SECURITY_INCIDENT_2025-10-22.md) for past incidents
3. Document findings and remediation

---

*For the complete documentation structure, see [00_DOCUMENTATION_STRUCTURE.md](../00_DOCUMENTATION_STRUCTURE.md)*

