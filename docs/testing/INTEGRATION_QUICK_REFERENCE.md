# 🎯 Integration Testing - Quick Reference

## 🚀 One-Command Test

```bash
./scripts/run_integration_tests.sh
```

---

## 📂 Test Structure (Modular & Reusable)

```
tests/integration/
├── test_platform_health.py      # Health checks (4 tests)
├── test_configuration.py        # Defaults (3 tests)
├── test_agent_execution.py      # Real LLM (2 tests, slow)
├── test_sessions_lifecycle.py   # Sessions (6 tests)
├── test_jobs_lifecycle.py       # Jobs (6 tests)
├── test_api_safety.py           # Safety (6 tests)
├── test_rbac.py                 # Permissions (6 tests)
└── test_auth_integration.py     # Auth (7 tests)
```

**Total**: 40 automated tests

---

## 📋 Acceptance Checklist (16 Items)

### ✅ Automated (9 items)

- [x] **#1** - Health components (postgres, redis, memgraph, LLM)
- [x] **#2** - Defaults set (provider + model instance)
- [x] **#3** - Agent run executes (real, not demo)
- [x] **#6** - Sessions CRUD
- [x] **#7** - Jobs + events
- [x] **#10** - Explorer URL safety
- [x] **#11** - Error messages with trace IDs
- [x] **#12** - Role guards (admin vs user)
- [x] **#13** - Auth /me endpoint

### 📝 Manual (7 items)

- [ ] **#4** - Tools Playground
- [ ] **#5** - NL → Cypher
- [ ] **#8** - Processes/Manifests/DB Ops
- [ ] **#9** - Providers & Instances
- [ ] **#14** - Developer Mode
- [ ] **#15** - Security & Secrets
- [ ] **#16** - Docs completeness

**Manual Guide**: `docs/MANUAL_TESTING_GUIDE.md`

---

## 🎯 Run Specific Tests

### All Tests
```bash
pytest tests/integration/ -v
```

### Single Module
```bash
pytest tests/integration/test_platform_health.py -v
```

### Fast Tests Only (Skip Agent Execution)
```bash
pytest tests/integration/ -v -m "not slow"
```

### Slow Tests Only (Agent Execution)
```bash
pytest tests/integration/ -v -m "slow"
```

### By Functional Area

**Health & Config**:
```bash
pytest tests/integration/test_platform_health.py tests/integration/test_configuration.py -v
```

**Security (RBAC + Auth)**:
```bash
pytest tests/integration/test_rbac.py tests/integration/test_auth_integration.py -v
```

**Workflows (Sessions + Jobs)**:
```bash
pytest tests/integration/test_sessions_lifecycle.py tests/integration/test_jobs_lifecycle.py -v
```

---

## 🔧 Prerequisites

**Automated Tests**:
```bash
docker-compose up -d  # Services running
```

**Manual Tests**:
- UI: http://localhost:3000
- Admin token (scopes: `read:all`, `write:all`)
- User token (scopes: `read:own`, `write:own`)

Get tokens:
```bash
python fetch_tokens.py
```

---

## 📊 Module Breakdown

| Module | Tests | Focus | Items |
|--------|-------|-------|-------|
| `test_platform_health.py` | 4 | Service connectivity | #1 |
| `test_configuration.py` | 3 | Default settings | #2 |
| `test_agent_execution.py` | 2 | Real LLM calls | #3 |
| `test_sessions_lifecycle.py` | 6 | Session CRUD | #6 |
| `test_jobs_lifecycle.py` | 6 | Job workflows | #7 |
| `test_api_safety.py` | 6 | URL/error safety | #10, #11 |
| `test_rbac.py` | 6 | Permissions | #12 |
| `test_auth_integration.py` | 7 | Auth flows | #13 |

---

## 🆘 Quick Troubleshooting

**Services not running?**
```bash
docker-compose up -d
docker-compose ps
```

**No default provider?**
→ Admin UI: Settings → Providers → Mark as Default

**Tests timeout?**
→ Check: `docker-compose logs -f api`

**Agent never completes?**
→ Verify LLM API key valid

---

## ✅ Success Criteria

1. ✅ All 40 automated tests pass
2. ✅ All 7 manual items verified
3. ✅ No critical issues
4. ✅ Docs accurate

---

## 🏗️ Architecture Benefits

### ✅ Modular
Each test file focuses on one area - easy to run specific tests

### ✅ Reusable
Shared fixtures (`client`, `bearer_headers`, `mint_token`) - no duplication

### ✅ Maintainable
Clear naming - `test_rbac.py` obviously tests permissions

### ✅ Extensible
Easy to add new test modules:
```python
# tests/integration/test_new_feature.py
class TestNewFeature:
    def test_it_works(self, client, bearer_headers):
        # Your test here
        pass
```

---

## 📈 Next Steps

### After Tests Pass ✅
1. Update execution tracking doc
2. Create sign-off report
3. Platform ready! 🚀

### If Tests Fail ❌
1. Document failure
2. Fix issue
3. Re-run: `./scripts/run_integration_tests.sh`

---

**Ready? Run the tests!**

```bash
./scripts/run_integration_tests.sh
```
