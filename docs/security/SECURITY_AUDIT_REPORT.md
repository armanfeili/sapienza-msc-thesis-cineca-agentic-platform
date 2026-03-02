# Security Audit Report

## Summary

- **Files Scanned**: 157
- **Total Findings**: 105
- **Critical**: 0
- **High**: 56
- **Medium**: 47
- **Low**: 2
- **Info**: 0

## HIGH Severity (56)

### Dangerous Function (48)

**1. app.py:544**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `mod = __import__(module_path, fromlist=[router_name])`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**2. app.py:596**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `mod = __import__("src.routers.agent_runs", fromlist=["router"])`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**3. app.py:1217**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `VERSION_PREFIX_RE = re.compile(r"^/v\d+(?:/|$)")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**4. routers/admin.py:35**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `mod = __import__(module_path, fromlist=[router_name])  # type: ignore`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**5. security/intent_filter.py:68**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_PROMPT_INJECTION = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**6. security/intent_filter.py:73**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_SECRETS = re.compile(r"(?i)\b(api[_ -]?key|secret|password|token|ssh[_ -]?key)\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**7. security/intent_filter.py:76**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_PII = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**8. security/intent_filter.py:81**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_SHELL = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**9. security/intent_filter.py:86**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_SQL_DROP = re.compile(r"(?i)\b(drop\s+(database|table)\b|truncate\s+table\b)")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**10. security/intent_filter.py:89**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_CYPHER_DANGER = re.compile(r"(?i)\b(detach\s+delete\b|drop\s+graph\b)")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**11. security/intent_filter.py:92**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_CYPHER_UNBOUNDED = re.compile(r"-\s*\[\s*\*\s*\]\s*-|(\*){3,}")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**12. security/intent_filter.py:95**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_EXFIL = re.compile(r"(?i)\b(dump|export|download)\b.*\b(all|everything|entire|database|db)\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**13. security/intent_filter.py:98**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_EXPLOIT = re.compile(r"(?i)\b(buffer overflow|exploit|rce|reverse shell)\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**14. security/validators.py:89**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_STRIP_RE = re.compile(r"\s+")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**15. security/validators.py:242**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**16. security/output_guard.py:78**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_RETURN = re.compile(r"(?is)\bRETURN\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**17. security/output_guard.py:79**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_LIMIT = re.compile(r"(?is)\bLIMIT\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**18. security/output_guard.py:80**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_WRITE = re.compile(r"(?is)\b(CREATE|MERGE|SET|DELETE|DETACH\s+DELETE|REMOVE)\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**19. security/output_guard.py:81**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_DROP_GRAPH = re.compile(r"(?is)\bDROP\s+GRAPH\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**20. security/output_guard.py:82**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_LOAD = re.compile(r"(?is)\bLOAD\s+CSV\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**21. security/output_guard.py:83**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_CALL_WRITEY = re.compile(r"(?is)\bCALL\b.*\b(write|create|delete|update)\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**22. security/output_guard.py:84**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `RE_UNBOUNDED = re.compile(r"-\s*\[\s*\*\s*(?:\d*\s*\.\.\s*\d*)?\s*\]\s*-")  # -[*]->  or -[*..]-> etc.`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**23. security/pii_scrubber.py:106**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**24. security/pii_scrubber.py:107**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `PHONE_RE = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**25. security/pii_scrubber.py:116**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `IPV4_RE = re.compile(r"\b(?:(?:\d{1,3}\.){3}\d{1,3})\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**26. security/pii_scrubber.py:117**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `SSN_US_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**27. security/pii_scrubber.py:118**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**28. security/pii_scrubber.py:120**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `CC_RAW_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**29. security/secrets.py:93**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `(re.compile(r'(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)'), r'eyJ***...[MASKED]'),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**30. security/secrets.py:95**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `(re.compile(r'([A-Za-z0-9]{32,})'), r'***[MASKED]'),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**31. security/secrets.py:97**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `(re.compile(r'(Bearer\s+[A-Za-z0-9_.-]+)', re.IGNORECASE), r'Bearer ***[MASKED]'),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**32. security/secrets.py:99**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `(re.compile(r'(Basic\s+[A-Za-z0-9+/=]+)', re.IGNORECASE), r'Basic ***[MASKED]'),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**33. security/secrets.py:101**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `(re.compile(r'(://[^:]+:)([^@]+)(@)'), r'\1***[MASKED]\3'),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**34. security/secrets.py:195**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `pattern = re.compile(r'(://[^:]+:)([^@]+)(@)')`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**35. security/tenants.py:88**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `TENANT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**36. health/policy.py:117**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `rate_limit_backend = getattr(__import__("src.config").config.settings, "RATE_LIMIT_BACKEND", "redis")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**37. mcp/tools/security/audit.py:74**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**38. mcp/tools/security/audit.py:75**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**39. mcp/tools/graph/secure_query.py:179**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_WRITE_PAT = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**40. mcp/tools/graph/secure_query.py:195**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_FORBIDDEN_PAT = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**41. mcp/tools/graph/query.py:85**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_WRITE_PAT = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**42. mcp/tools/graph/search.py:116**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_WRITE_PAT = re.compile(`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**43. mcp/tools/output/summarize.py:117**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_SENT_SPLIT_RE = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=[.!?])\s+|\n{2,}")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**44. mcp/tools/output/summarize.py:118**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `_WORD_RE = re.compile(r"[A-Za-z0-9_']+")`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**45. mcp/tools/system/health.py:287**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `"python": "{}.{}.{}".format(*(__import__("sys").version_info[:3])),`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**46. services/orchestrator.py:192**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `llm_module = __import__("src.adapters.llm", fromlist=["LLMClient"])  # type: ignore`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**47. services/orchestrator.py:862**

- **Description**: Unsafe: Dynamic imports can be exploited
- **Code**: `llm_module = __import__("src.adapters.llm", fromlist=["LLMClient"])  # type: ignore`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

**48. services/archive.py:323**

- **Description**: Unsafe: compile() can execute arbitrary code
- **Code**: `rx = re.compile(pattern)`
- **Recommendation**: Avoid using this function or ensure input is strictly validated
- **CWE**: CWE-95

### Sql Injection (8)

**1. adapters/db_memgraph.py:190**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `execute(f"CREATE INDEX ON :`{label}`(`{prop}`)")`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**2. adapters/db_memgraph.py:210**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `execute(`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**3. adapters/db_memgraph.py:243**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `execute(`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**4. services/etl.py:291**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{start_label}) ON (n.{start_id_col})")`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**5. services/etl.py:296**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{end_label}) ON (n.{end_id_col})")`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**6. services/etl.py:316**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{start_label}) ON (n.{start_id_col})")`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**7. services/etl.py:321**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `self.db.execute(f"CREATE INDEX IF NOT EXISTS FOR (n:{end_label}) ON (n.{end_id_col})")`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

**8. services/etl.py:382**

- **Description**: Potential SQL injection: String formatting/concatenation in SQL query
- **Code**: `self.db.execute(f"CREATE INDEX ON :`{lbl}`(`orig_id`)")  # type: ignore[attr-defined]`
- **Recommendation**: Use parameterized queries or ORM (SQLAlchemy) instead of string formatting
- **CWE**: CWE-89

## MEDIUM Severity (47)

### Missing Auth (47)

**1. routers/auth.py:118**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**2. routers/tenants_admin.py:48**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**3. routers/tenants_admin.py:580**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**4. routers/tenants_admin.py:715**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.patch(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**5. routers/model_processes.py:89**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**6. routers/model_processes.py:372**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**7. routers/model_processes.py:524**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**8. routers/internal_ops.py:123**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post("/auto-start-override", response_model=AutoStartOverrideResponse,`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**9. routers/internal_ops.py:300**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get("/preview-staged", response_model=PreviewStagedResponse,`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**10. routers/models.py:401**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**11. routers/models.py:451**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**12. routers/models.py:916**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**13. routers/models.py:1280**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**14. routers/agent_runs.py:339**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**15. routers/agent_runs.py:359**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**16. routers/health.py:50**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**17. routers/tools.py:317**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**18. routers/tools.py:1059**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**19. routers/tools.py:1306**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**20. routers/jobs.py:168**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**21. routers/jobs.py:541**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.delete(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**22. routers/jobs.py:1649**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**23. routers/admin_jobs.py:34**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**24. routers/admin_jobs.py:266**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**25. routers/admin_jobs.py:297**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**26. routers/agent.py:403**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**27. routers/agent.py:503**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**28. routers/agent.py:715**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**29. routers/internal_db.py:970**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**30. routers/tenants.py:34**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get("", response_model=List[Tenant], summary="List tenants", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**31. routers/tenants.py:93**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get("/{tenant_id}", response_model=Tenant, summary="Get tenant by id", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**32. routers/tenants.py:115**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.patch("/{tenant_id}", response_model=Tenant, summary="Patch tenant", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**33. routers/tenants.py:138**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.delete("/{tenant_id}", response_model=Dict[str, bool], summary="Delete tenant", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**34. routers/model_management.py:359**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.get("/instances", response_model=List[ModelInfo], tags=["models-instances"], summary="List model instances (registry-only)", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**35. routers/model_management.py:649**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.get("/instances/{instance_id}", response_model=Dict[str, Any], tags=["models-instances"], summary="Get a model instance (admin)", description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**36. routers/model_management.py:718**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.post(`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**37. routers/model_management.py:1340**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.get("/manifests/builtins") - REMOVED, see src/routers/manifests.py`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**38. routers/model_management.py:1341**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.post("/manifests/builtins/staged") - REMOVED, see src/routers/manifests.py`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**39. routers/model_management.py:1342**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.post("/manifests/builtins/activations") - REMOVED, see src/routers/manifests.py`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**40. routers/model_management.py:1343**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.post("/manifests/builtins/rollbacks") - REMOVED, see src/routers/manifests.py`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**41. routers/model_management.py:1344**

- **Description**: Route may be missing authentication dependency
- **Code**: `# @router.get("/manifests/builtins/history") - REMOVED, see src/routers/manifests.py`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**42. routers/model_management.py:1368**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get('/providers', response_model=ProviderListResponse, tags=["models-providers"], summary='List runtime LLM providers', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**43. routers/model_management.py:1472**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.post('/providers/register', response_model=ActionResponse, tags=["models-providers"], summary='Register a runtime LLM provider', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**44. routers/model_management.py:1646**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get('/providers/main', response_model=GetMainProviderResponse, tags=["models-providers"], summary='Get resolved main LLM provider for a tenant (or global if none)', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**45. routers/model_management.py:1738**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.get('/providers/{provider_id}', tags=["models-providers"], summary='Get provider details', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**46. routers/model_management.py:1820**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.patch('/providers/{provider_id}', response_model=ActionResponse, tags=["models-providers"], summary='Patch provider details', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

**47. routers/model_management.py:2023**

- **Description**: Route may be missing authentication dependency
- **Code**: `@router.put('/providers/default', response_model=ActionResponse, tags=["models-providers"], summary='Set a provider as default/global (or per-tenant)', description="""`
- **Recommendation**: Add Depends(get_current_user) or other auth dependency if endpoint should be protected
- **CWE**: CWE-306

## LOW Severity (2)

### Insecure Assert (2)

**1. background.py:115**

- **Description**: Assert statement used for security check (can be disabled with -O flag)
- **Code**: `assert self.scheduler is not None`
- **Recommendation**: Use explicit if/raise for security checks instead of assert
- **CWE**: CWE-703

**2. background/__init__.py:110**

- **Description**: Assert statement used for security check (can be disabled with -O flag)
- **Code**: `assert self.scheduler is not None`
- **Recommendation**: Use explicit if/raise for security checks instead of assert
- **CWE**: CWE-703
