# Testing Documentation

This directory contains comprehensive testing documentation for the Cineca Agentic Platform.

## 📚 Testing Guides

### Core Testing Documentation
- **TESTING_GUIDE.md** - Main testing guide and overview
- **MANUAL_TESTING_GUIDE.md** - Manual testing procedures and checklists

### Quick References
- **ACCEPTANCE_QUICK_REFERENCE.md** - Acceptance testing quick reference
- **INTEGRATION_QUICK_REFERENCE.md** - Integration testing quick reference

---

## 🧪 Test Types

### Acceptance Testing
Documentation for acceptance testing:
- **ACCEPTANCE_CHECKLIST_EXECUTION.md** - Acceptance test execution
- **ACCEPTANCE_QUICK_REFERENCE.md** - Quick reference guide
- **BUILTINS_MANIFESTS_ACCEPTANCE_REPORT.md** - Built-ins acceptance report

### Integration Testing
Documentation for integration testing:
- **INTEGRATION_QUICK_REFERENCE.md** - Integration testing guide
- **INTEGRATION_TESTS_REORGANIZATION.md** - Test reorganization details

### Feature-Specific Testing
- **AGENT_TESTS_AUTH0_VERIFICATION.md** - Agent Auth0 testing
- **INTERNAL_ENDPOINTS_RBAC_TESTING.md** - RBAC testing (see [features/internal-endpoints/](../features/internal-endpoints/))
- **RATE_LIMITING_TEST_FIX.md** - Rate limiting tests

### Test Quality and Validation
- **PATCH_DEFAULTS_VALIDATION_REPORT.md** - Validation reports
- **TEST_ENDPOINT_DOCUMENTATION_UPDATE.md** - Test endpoint documentation

---

## 🎯 Testing Workflow

### 1. Getting Started with Testing
```bash
# Start here
1. Read: TESTING_GUIDE.md
2. Review: MANUAL_TESTING_GUIDE.md
3. Check relevant feature testing docs
```

### 2. Running Acceptance Tests
```bash
# Follow this process
1. Review: ACCEPTANCE_QUICK_REFERENCE.md
2. Execute: ACCEPTANCE_CHECKLIST_EXECUTION.md
3. Verify: Results against acceptance criteria
```

### 3. Running Integration Tests
```bash
# Integration testing workflow
1. Check: INTEGRATION_QUICK_REFERENCE.md
2. Run integration test suites
3. Review: INTEGRATION_TESTS_REORGANIZATION.md for test structure
```

### 4. Manual Testing
```bash
# Manual testing procedure
1. Follow: MANUAL_TESTING_GUIDE.md
2. Execute manual test scenarios
3. Document results
```

---

## 📊 Test Reports and Results

Historical test reports are located in:
- **[../status-reports/](../status-reports/)** - Test completion and status reports
  - ALL_TESTS_GREEN_FINAL.md
  - Test execution summaries
  - Test status reports

---

## 🔗 Related Documentation

### Feature Testing
- [Agents Testing](../features/agents/) - Agent-specific testing
- [Jobs Testing](../features/jobs/) - Job-specific testing
- [API Testing](../api/) - API testing documentation

### Infrastructure
- [Security Testing](../security/) - Security and authentication testing
- [Database Testing](../database/) - Database testing procedures

### Operations
- [Performance Testing](../operations/monitoring/PERFORMANCE_TESTING.md) - Performance tests
- [Deployment Testing](../operations/deployment/) - Deployment validation

---

## 📝 Test Coverage Areas

The platform has test coverage for:

1. **API Endpoints** - All REST API endpoints
2. **Authentication** - Auth0 integration and RBAC
3. **Features** - All major features (agents, jobs, models, etc.)
4. **Database** - PostgreSQL, Redis, Memgraph
5. **Integration** - Cross-component integration
6. **Performance** - Load and performance testing
7. **Security** - Security audit and compliance

---

## 🚦 Test Status

For current test status and results:
- See [../status-reports/](../status-reports/) for historical test reports
- Check CI/CD pipeline for latest test runs
- Review feature-specific test documentation

---

*For the complete documentation structure, see [00_DOCUMENTATION_STRUCTURE.md](../00_DOCUMENTATION_STRUCTURE.md)*

