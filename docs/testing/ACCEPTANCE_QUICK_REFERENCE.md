# 🎯 Acceptance Testing - Quick Reference

## 🚀 One-Command Test

```bash
./scripts/run_acceptance_tests.sh
```

---

## 📋 Checklist (16 Items)

### ✅ Automated (9 items) - Run Script Above

- [x] 1. Health components (postgres, redis, memgraph, LLM)
- [x] 2. Defaults set (provider + model instance)
- [x] 3. Agent run executes (real, not demo)
- [x] 6. Sessions CRUD
- [x] 7. Jobs + events
- [x] 10. Explorer URL safety
- [x] 11. Error messages with trace IDs
- [x] 12. Role guards (admin vs user)
- [x] 13. Auth /me endpoint

### 📝 Manual (7 items) - See Guide Below

- [ ] 4. Tools Playground - "Test All Tools" works
- [ ] 5. NL → Cypher - Generate/execute/export
- [ ] 8. Processes/Manifests/DB Ops - Admin actions
- [ ] 9. Providers & Instances - CRUD operations
- [ ] 14. Developer Mode - Internal endpoints hidden
- [ ] 15. Security & Secrets - No hardcoded credentials
- [ ] 16. Docs completeness - README accurate

**Manual Guide**: `docs/MANUAL_ACCEPTANCE_TESTING_GUIDE.md`

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `tests/acceptance/test_acceptance_checklist.py` | Automated test suite |
| `docs/MANUAL_ACCEPTANCE_TESTING_GUIDE.md` | Manual testing steps |
| `scripts/run_acceptance_tests.sh` | Quick-start script |
| `docs/ACCEPTANCE_TESTING_COMPLETE.md` | Full documentation |

---

## 🔧 Prerequisites

**Automated Tests**:
```bash
docker-compose up -d  # Services running
pytest --version      # pytest installed
```

**Manual Tests**:
- UI accessible: http://localhost:3000
- Admin token (scopes: `read:all`, `write:all`)
- User token (scopes: `read:own`, `write:own`)

Get tokens:
```bash
python fetch_tokens.py
```

---

## 📊 Expected Results

### Automated Tests
```
test_1_health_components_all_ok PASSED
test_2_default_provider_set PASSED
test_2_default_model_instance_set PASSED
test_3_agent_run_prompt_only_real_execution PASSED
test_6_sessions_crud_operations PASSED
test_7_jobs_create_and_events_streaming PASSED
test_10_explore_inspector_url_handling PASSED
test_11_error_messages_include_trace_ids PASSED
test_12_role_guards_hide_admin_actions PASSED
test_13_auth_me_shows_claims PASSED

======================== 10 passed in 15.23s ========================
```

### Manual Tests
Follow guide, check off each item:
- ✅ Verify expected behavior
- ❌ Document any failures
- 📝 Note any UX issues

---

## 🆘 Quick Troubleshooting

**Services not running?**
```bash
docker-compose up -d
docker-compose ps  # Check health
```

**No default provider?**
→ Set via admin UI: Settings → Providers → Mark as Default

**Tests time out?**
→ Check logs: `docker-compose logs -f api`

**Agent run never completes?**
→ Verify LLM provider API key valid

---

## ✅ Success Criteria

1. **All automated tests pass** (9/9)
2. **All manual items verified** (7/7)
3. **No critical issues** found
4. **Documentation accurate** matches behavior

---

## 📈 Progress Tracking

Mark items as you complete them:

**Automated**: ⬜ → Run script → ✅ if all pass  
**Manual**: ⬜ → Follow guide → ✅ each item

**Total**: 0/16 → ... → 16/16 ✅

---

## 🎓 Next Steps

### After All Tests Pass ✅
1. Update `ACCEPTANCE_CHECKLIST_EXECUTION.md`
2. Create final sign-off report
3. Platform ready! 🚀

### If Tests Fail ❌
1. Document the failure
2. Fix the issue
3. Re-run: `./scripts/run_acceptance_tests.sh`
4. Repeat until all pass

---

**Ready to start? Run the script!**

```bash
./scripts/run_acceptance_tests.sh
```
