# MCP Tools Registry Documentation Index

**Last Updated:** October 24, 2025  
**Registry Status:** ✅ Production-Ready  
**Total Tools:** 32

---

## Quick Links

### 📋 Essential Documents

1. **[Manifest File](../src/mcp/manifest.json)**
   - The authoritative registry of all 32 MCP tools
   - Includes metadata, input schemas, capabilities, and scopes

2. **[Tools Reference Documentation](./MCP_TOOLS_REFERENCE.md)**
   - Comprehensive guide to all MCP tools
   - Action tables, payload examples, return shapes
   - Usage patterns and best practices

3. **[Final Report](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md)**
   - Complete implementation summary
   - Verification results (all checks passing)
   - Next steps and recommendations

4. **[Policies Configuration](../src/mcp/policies.yaml)**
   - RBAC scope definitions
   - Role mappings (user, operator, admin)
   - Security guardrails and rate limits

5. **[Changelog](../CHANGELOG.md)**
   - Detailed change history
   - New tools, updates, breaking changes
   - Migration guides

---

## 🆕 New Tools (v1.0)

### `graph.secure_query@1` ⭐ Flagship Feature

**Purpose:** Safely answer user prompts over Memgraph with NL→Cypher translation, validation, and secure execution.

**Key Features:**
- End-to-end natural language querying
- Read-only enforcement with forbidden clause detection
- Principal & tenant-scoped permission checks
- Rate limiting (10/min recommended), timeout protection (5s), row limits (1000)
- Multi-format output (rows, JSON, CSV, Markdown)

**Documentation:**
- [Reference Guide](./MCP_TOOLS_REFERENCE.md#graphsecure_query) - Full documentation with examples
- [Implementation](../src/mcp/tools/graph/secure_query.py) - Source code (600+ lines)
- [Manifest Entry](../src/mcp/manifest.json) - Tool metadata and schema

**Actions:**
- `ask` - End-to-end (generate → validate → execute)
- `generate` - NL→Cypher translation only
- `validate` - Safety checks only
- `execute` - Execute pre-validated query

**Quick Example:**
```json
{
  "action": "ask",
  "prompt": "Show me all active users",
  "principal": "alice@example.org",
  "tenant": "default",
  "return_format": "markdown"
}
```

### Other New Tools

- **`data.archive@1`** - Data archival operations (mark, restore, purge, list)
- **`data.quality@1`** - Data quality checks on graph nodes/relationships
- **`errors.report@1`** - Structured error reporting with audit trails
- **`viz.render@1`** - Visualization rendering (Mermaid, DOT, Markdown, sparklines)

---

## 📚 Documentation Structure

### By Audience

**For Developers:**
1. [Tools Reference](./MCP_TOOLS_REFERENCE.md) - API documentation for all 32 tools
2. [Implementation Guide](../src/mcp/tools/) - Source code organization
3. [Verification Script](../scripts/verify_manifest.py) - Quality checks

**For Architects:**
1. [Final Report](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md) - Complete system overview
2. [RBAC Model](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md#rbac-scope-model) - Security architecture
3. [Policies Config](../src/mcp/policies.yaml) - Permission model

**For Operators:**
1. [Changelog](../CHANGELOG.md) - What's new and changed
2. [Deployment Checklist](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md#next-steps-recommended) - Rollout guide
3. [Monitoring Setup](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md#4-monitoring) - Observability

**For Users:**
1. [Tools Reference](./MCP_TOOLS_REFERENCE.md) - How to use each tool
2. [Quick Start Examples](./MCP_TOOLS_REFERENCE.md#tool-catalog) - Common patterns
3. [Secure Query Guide](./MCP_TOOLS_REFERENCE.md#graphsecure_query) - Natural language queries

---

## 🔍 Tool Categories

| Category | Count | Key Tools |
|----------|-------|-----------|
| **Graph** | 8 | `graph.secure_query` ⭐, `graph.query`, `graph.crud`, `graph.search` |
| **System** | 4 | `system.health`, `system.metrics`, `system.status`, `system.backup` |
| **Security** | 3 | `security.audit`, `security.check`, `security.permissions` |
| **Data** | 2 | `data.archive`, `data.quality` |
| **Model** | 2 | `model.manage`, `model.test` |
| **Output** | 2 | `output.format`, `output.summarize` |
| **Single Tools** | 11 | agent, cache, catalog, db, errors, privacy, ratelimit, session, tenancy, user, viz |

**Total:** 32 tools across 17 categories

---

## 🔒 RBAC Scopes

### `tools:basic` (19 tools)
**Access Level:** Read-only, safe operations  
**Assigned To:** user, analyst, operator roles

**Key Tools:**
- `graph.secure_query` - Secure NL queries ⭐
- `graph.schema` - Schema discovery
- `graph.search` - Search operations
- `system.health` - Health checks
- `system.metrics` - Prometheus metrics
- `catalog.discover` - Tool discovery

### `tools:all` (10 tools)
**Access Level:** Write/admin-light operations  
**Assigned To:** operator, admin roles

**Key Tools:**
- `graph.query` - Ad-hoc Cypher (write-capable)
- `graph.crud` - Create/update/delete
- `graph.bulk` - Bulk operations
- `data.archive` - Data archival
- `system.backup` - Backup operations

### `admin:all` (3 tools)
**Access Level:** Security & tenancy administration  
**Assigned To:** admin role only

**Tools:**
- `security.audit` - Audit event management
- `security.permissions` - Permission resolution
- `tenancy.manage` - Tenant administration

---

## ✅ Verification & Quality

### Manifest Verification

Run the verification script:
```bash
python scripts/verify_manifest.py
```

**Expected Output:**
```
✅ ALL CHECKS PASSED
  - 32 tools registered
  - 17 categories
  - 20 unique capabilities
  - 3 unique scopes
  - 2 long-running tools
  - 28 action-aware tools
```

### JSON Validation

Validate manifest format:
```bash
python -m json.tool src/mcp/manifest.json > /dev/null && echo "✅ Valid JSON"
```

### Current Status

- ✅ Tool count: 32/32
- ✅ Metadata completeness: 100%
- ✅ Action-aware schemas: 28/32 (87.5%)
- ✅ ID format: 100% compliant
- ✅ Module paths: 100% valid
- ✅ JSON format: Valid
- ✅ Documentation: Complete

---

## 🚀 Implementation Status

### Production-Ready Tools (32/32)

All 32 tools have:
- ✅ Manifest entries with complete metadata
- ✅ Action-aware input schemas (28 tools)
- ✅ Module implementations
- ✅ Documentation in reference guide
- ✅ RBAC scope assignments

### Recently Implemented (v1.0)

- ✅ `graph.secure_query` - Full implementation (600+ lines)
- ✅ `data.archive` - Complete with long-running support
- ✅ `data.quality` - All quality check actions
- ✅ `errors.report` - Structured error handling
- ✅ `viz.render` - Multi-format visualization

---

## 📖 How to Use This Index

### I want to...

**...understand what tools are available**
→ See [Tools Reference](./MCP_TOOLS_REFERENCE.md) or [Tool Categories](#-tool-categories)

**...use natural language to query the graph**
→ See [`graph.secure_query` documentation](./MCP_TOOLS_REFERENCE.md#graphsecure_query)

**...understand the security model**
→ See [RBAC Scopes](#-rbac-scopes) or [Policies Config](../src/mcp/policies.yaml)

**...verify the registry is correct**
→ Run [verification script](#manifest-verification)

**...see what's new**
→ Check [Changelog](../CHANGELOG.md) or [New Tools](#-new-tools-v10)

**...deploy to production**
→ Review [Next Steps](./MCP_TOOLS_REGISTRY_FINAL_REPORT.md#next-steps-recommended)

**...contribute a new tool**
→ Study [existing implementations](../src/mcp/tools/) and [manifest structure](../src/mcp/manifest.json)

---

## 🔗 Related Documentation

- [Architecture Overview](./architecture.md)
- [API Documentation](./API_DOCUMENTATION_COMPLETE.md)
- [Security Guide](./SECURITY.md)
- [Database Reference - Memgraph](./DATABASE_MEMGRAPH_REFERENCE.md)
- [Deployment Guide](./deployment.md)

---

## 📞 Support & Feedback

- **Issues:** Report bugs or request features via GitHub Issues
- **Documentation:** Suggest improvements to MCP_TOOLS_REFERENCE.md
- **Security:** Report security concerns following SECURITY.md guidelines

---

**Registry Status:** ✅ Production-Ready  
**Last Verification:** October 24, 2025  
**Next Review:** After runtime integration testing
