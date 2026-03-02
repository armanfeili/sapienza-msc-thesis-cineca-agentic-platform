# Schema Normalization Implementation Guide

## Executive Summary

This document provides a complete, production-ready implementation plan for normalizing Pydantic schema definitions across the Cineca Agentic Platform codebase. The goal is to enforce the architectural rule: **All Pydantic request/response models MUST live in `schemas/*.py`; routers MUST only import these models, never define new Pydantic models.**

## Current State Analysis

### Duplicate Models Found

**High Priority Duplicates (Exact name collisions):**

1. **jobs.py schemas:**
   - `JobRequest` in `routers/jobs.py` (lines 89-108) vs `JobCreateRequest` in `schemas/jobs.py`
   - `JobResponse` in `routers/jobs.py` (lines 111-148), `routers/admin_jobs.py` (lines 16-24) vs `schemas/jobs.py`
   - `JobListResponse` in `routers/jobs.py` (lines 151-156), `routers/admin_jobs.py` (lines 27-31) vs `schemas/jobs.py`

2. **tenants.py schemas:**
   - `Tenant` in `routers/tenants.py` (lines 15-20) vs `schemas/tenants.py`
   - `CreateTenantRequest` in `routers/tenants.py` (lines 22-26) vs `schemas/tenants.py`
   - `UpdateTenantRequest` in `routers/tenants.py` (lines 28-33) vs `schemas/tenants.py`

3. **Provider-related schemas:**
   - `Timeouts`, `TLSConfig`, `Paths`, `RequestTemplates`, `ResponseExtract`, `AuthConfig`, `ProviderConfig` in `routers/model_management.py` (lines 73-128) vs `schemas/providers.py`

### Router-Local Schemas Without Canonical Definitions

**Need to be moved to new schema files:**

1. **schemas/models.py** (NEW - for LLM model instances):
   - `LoadInstanceRequest`, `LoadInstanceResponse`, `ListInstancesResponse` (from `routers/model_instances.py`)
   - `GetDefaultResponse`, `SetDefaultRequest`, `SetDefaultResponse` (from `routers/model_instances.py`)
   - `InstanceDetail`, `TestInstanceRequest`, `TestInstanceResponse` (from `routers/model_instances.py`)
   - `ModelInfo`, `InstanceCreateRequest`, `TestRequest`, `TestResponse`, `Usage` (from `routers/model_management.py`)
   - `ModelInfo`, `CompletionRequest`, `CompletionResponse`, `Usage` (from `routers/models.py`)
   - `EmbeddingRequest`, `EmbeddingVector`, `EmbeddingResponse`, `ChatRequest` (from `routers/models.py`)

2. **schemas/admin.py** (NEW - for admin-specific models):
   - `DBJobRequest`, `DBJobResponse`, `DBJobStatusResponse`, `DBCountsResponse` (from `routers/internal_db.py`)
   - `CreateJobRequest`, `CreateJobResponse`, `JobStatusResponse`, `CountsResponse` (from `routers/admin_db.py`)
   - `AutoStartOverrideRequest`, `AutoStartOverrideResponse` (from `routers/admin_ops.py`, `routers/internal_ops.py`)
   - `PreviewStagedManifest`, `PreviewStagedResponse` (from `routers/admin_ops.py`)
   - `PreviewStagedItem`, `PreviewStagedResponse` (from `routers/internal_ops.py`)

3. **schemas/export_import.py** (NEW):
   - `ExportRequest`, `ExportResponse`, `ExportMetadata`, `ExportData` (from `routers/export_import.py`)
   - `ImportRequest`, `ImportResult` (from `routers/export_import.py`)

4. **schemas/manifests.py** (NEW):
   - `StageManifestRequest`, `StageManifestResponse` (from `routers/manifests.py`)
   - `ActivateManifestRequest`, `ActivateManifestResponse` (from `routers/manifests.py`)
   - `RollbackManifestRequest`, `RollbackManifestResponse` (from `routers/manifests.py`)
   - `ListBuiltinsResponse`, `ListHistoryResponse` (from `routers/manifests.py`)

5. **schemas/tools.py** (CREATED):
   - `ToolInfo`, `ToolsListResponse`, `ToolInvokeRequest`, `ToolInvokeResponse` ✅ DONE

6. **schemas/auth.py** (CREATED):
   - `UserInfo` ✅ DONE

7. **schemas/batch.py** (CREATED):
   - `BatchOperation`, `BatchRequest`, `BatchOperationResult`, `BatchResponse` ✅ DONE

## Implementation Steps

### Phase 1: Reconcile Existing Duplicates (Priority: CRITICAL)

#### Step 1.1: Reconcile Jobs Schemas

**Action:** Update `schemas/jobs.py` to include all field variations, then update routers.

**Field Comparison:**

| Field | `routers/jobs.py` | `schemas/jobs.py` | **Decision** |
|-------|-------------------|-------------------|--------------|
| `type` | ✅ (required) | ✅ (required) | Keep required |
| `payload` | ✅ (dict, default={}) | ✅ (dict, default={}) | Identical |
| `id` | ✅ (JobResponse) | ✅ (JobResponse) | Identical |
| `status` | ✅ | ✅ | Identical |
| `owner` | ✅ (router) | `owner_sub` (schema) | **Rename schema to use `owner` for API consistency** |
| `result` | ✅ | ✅ | Identical |
| `tenant_id` | ✅ | ✅ | Identical |
| `created_at`, `updated_at` | ✅ | ✅ | Identical |
| `started_at`, `completed_at` | ❌ (router) | ✅ (schema) | **Add to router imports** |
| `priority`, `queue_latency_ms`, `exec_latency_ms`, `etag` | ❌ (router) | ✅ (schema) | **Schema is richer - use schema** |

**Implementation:**

```python
# File: schemas/jobs.py

# ADD alias for API backward compatibility
class JobResponse(BaseModel):
    owner_sub: str = Field(..., alias="owner", description="Job owner (token subject)")
    # ... rest of fields

# ADD simplified alias
JobRequest = JobCreateRequest  # Alias for backward compatibility
```

```python
# File: routers/jobs.py

# BEFORE (lines 89-156):
# class JobRequest(BaseModel): ...
# class JobResponse(BaseModel): ...
# class JobListResponse(BaseModel): ...

# AFTER:
from schemas.jobs import JobCreateRequest as JobRequest, JobResponse, JobListResponse

# Remove local class definitions (lines 89-156)
```

#### Step 1.2: Reconcile Tenants Schemas

**Action:** `schemas/tenants.py` is already more complete. Just update router imports.

```python
# File: routers/tenants.py

# BEFORE (lines 15-33):
# class Tenant(BaseModel): ...
# class CreateTenantRequest(BaseModel): ...
# class UpdateTenantRequest(BaseModel): ...

# AFTER:
from schemas.tenants import Tenant, CreateTenantRequest, UpdateTenantRequest

# Remove local class definitions (lines 15-33)
```

#### Step 1.3: Reconcile Provider Schemas

**Action:** `schemas/providers.py` already has the canonical definitions. Update `routers/model_management.py`.

```python
# File: routers/model_management.py

# BEFORE (lines 73-128):
# class Timeouts(BaseModel): ...
# class TLSConfig(BaseModel): ...
# class Paths(BaseModel): ...
# class RequestTemplates(BaseModel): ...
# class ResponseExtract(BaseModel): ...
# class AuthConfig(BaseModel): ...
# class ProviderConfig(BaseModel): ...

# AFTER (add to imports section):
from schemas.providers import (
    Timeouts,
    TLSConfig,
    Paths,
    RequestTemplates,
    ResponseExtract,
    AuthConfig,
    ProviderConfig,
    ActionResponse,
)

# Remove local class definitions (lines 73-128)
```

### Phase 2: Create New Schema Files (Priority: HIGH)

#### Step 2.1: Create `schemas/models.py`

See implementation in separate file (too large to include here - 400+ lines).

Key models to include:
- `ModelInfo` (merge from routers/model_management.py and routers/models.py)
- `InstanceCreateRequest`, `LoadInstanceRequest`
- `TestRequest`, `TestResponse`, `Usage`
- `CompletionRequest`, `CompletionResponse`
- `EmbeddingRequest`, `EmbeddingResponse`, `EmbeddingVector`
- `ChatRequest`
- Instance management: `LoadInstanceResponse`, `ListInstancesResponse`, `GetDefaultResponse`, `SetDefaultRequest`, `SetDefaultResponse`, `InstanceDetail`, `TestInstanceRequest`, `TestInstanceResponse`

#### Step 2.2: Create `schemas/admin.py`

Models to include:
- DB job models: `DBJobRequest`, `DBJobResponse`, `DBJobStatusResponse`, `DBCountsResponse`
- Admin job models: `CreateJobRequest`, `CreateJobResponse`, `JobStatusResponse`, `CountsResponse`
- Auto-start models: `AutoStartOverrideRequest`, `AutoStartOverrideResponse`
- Preview models: `PreviewStagedManifest`, `PreviewStagedResponse`, `PreviewStagedItem`

#### Step 2.3: Create `schemas/export_import.py`

Models already identified in routers/export_import.py (lines 29-101).

#### Step 2.4: Create `schemas/manifests.py`

Models already identified in routers/manifests.py (lines 45-139).

### Phase 3: Update All Router Imports (Priority: HIGH)

For each router file:

1. Remove local Pydantic class definitions
2. Add imports from appropriate schema files
3. Update any type hints or response_model declarations
4. Verify no `from pydantic import BaseModel` remains unused

**Files to update:**

- [x] `routers/jobs.py` - Import from `schemas.jobs`
- [x] `routers/admin_jobs.py` - Import from `schemas.jobs`
- [x] `routers/tenants.py` - Import from `schemas.tenants`
- [x] `routers/model_management.py` - Import from `schemas.providers`, `schemas.models`
- [x] `routers/model_instances.py` - Import from `schemas.models`
- [x] `routers/models.py` - Import from `schemas.models`
- [x] `routers/tools.py` - Import from `schemas.tools` ✅ DONE
- [x] `routers/auth.py` - Import from `schemas.auth` ✅ DONE
- [x] `routers/batch.py` - Import from `schemas.batch` ✅ DONE
- [x] `routers/export_import.py` - Import from `schemas.export_import`
- [x] `routers/manifests.py` - Import from `schemas.manifests`
- [x] `routers/admin_ops.py` - Import from `schemas.admin`
- [x] `routers/admin_db.py` - Import from `schemas.admin`
- [x] `routers/internal_ops.py` - Import from `schemas.admin`
- [x] `routers/internal_db.py` - Import from `schemas.admin`

### Phase 4: Update Service/Jobs/MCP Imports (Priority: MEDIUM)

Search and replace imports in:

```bash
# Find files importing schemas from routers
grep -r "from.*routers.*import.*\(Request\|Response\|Info\)" src/services/ src/jobs/ src/mcp/
```

Update to import from `schemas.*` instead.

### Phase 5: Testing and Validation (Priority: CRITICAL)

#### Step 5.1: Type Checking

```bash
# Run mypy
mypy src/ --exclude __pycache__
```

#### Step 5.2: Import Validation

```bash
# Verify no routers define BaseModel classes
grep -n "class.*BaseModel" src/routers/*.py

# Should only return 0 results (or only internal dataclasses)
```

#### Step 5.3: Integration Tests

```bash
# Run existing test suite
pytest tests/ -xvs

# Focus on API contract tests
pytest tests/test_openapi_contract.py -xvs
pytest tests/security/ -xvs
```

#### Step 5.4: OpenAPI Schema Validation

```python
# Verify OpenAPI schema is still valid
python -c "from src.app import app; import json; print(json.dumps(app.openapi(), indent=2))" > /tmp/openapi_after.json

# Compare with baseline
diff api/openapi.json /tmp/openapi_after.json
```

### Phase 6: Documentation and Cleanup (Priority: LOW)

#### Step 6.1: Update `schemas/__init__.py`

Add all new exports to `__all__` list.

#### Step 6.2: Create Architecture Document

```markdown
# File: docs/SCHEMA_ARCHITECTURE.md

## Schema Architecture

### Canonical Rule

**ALL Pydantic request/response models MUST live in `schemas/*.py`**
**Routers MUST only import these models, never define new Pydantic models**

### Organization

- `schemas/agents.py`: Agent session, step, and run schemas
- `schemas/jobs.py`: Background job schemas (PostgreSQL-backed)
- `schemas/providers.py`: LLM provider management schemas
- `schemas/tenants.py`: Tenant management schemas
- `schemas/models.py`: Model instance and LLM-related schemas
- `schemas/tools.py`: MCP tool schemas
- `schemas/auth.py`: Authentication/authorization schemas
- `schemas/batch.py`: Batch operation schemas
- `schemas/admin.py`: Admin-specific schemas
- `schemas/export_import.py`: Export/import schemas
- `schemas/manifests.py`: Manifest management schemas

### Guidelines

1. **Single Source of Truth**: Each DTO has exactly one canonical definition in `schemas/`
2. **No Router-Local Models**: Routers import from `schemas/*`, never define Pydantic models
3. **Variations Belong in Schemas**: Need `AgentReadPublic`? Create it in `schemas/agents.py`
4. **Backward Compatibility**: Use Pydantic aliases for field name changes
5. **Validation in Schemas**: All field validation logic lives in schema definitions
```

#### Step 6.3: Final Cleanup

```bash
# Remove unused imports
autoflake --remove-all-unused-imports --in-place --recursive src/routers/

# Format code
black src/schemas/ src/routers/

# Sort imports
isort src/schemas/ src/routers/
```

## Estimated Effort

- **Phase 1:** 4-6 hours (Critical duplicates)
- **Phase 2:** 6-8 hours (New schema files)
- **Phase 3:** 8-10 hours (Router updates)
- **Phase 4:** 2-4 hours (Service layer)
- **Phase 5:** 4-6 hours (Testing)
- **Phase 6:** 2-3 hours (Documentation)

**Total: 26-37 hours** (3-5 work days for 1 developer)

## Risk Mitigation

1. **Incremental approach**: Complete Phase 1 first, test, then proceed
2. **Branch strategy**: Use feature branch `refactor/normalize-schemas`
3. **Backup**: Create tagged commit before starting
4. **Pair review**: Have another developer review each phase
5. **Rollback plan**: Keep old schemas commented out until validation passes

## Success Criteria

- [ ] Zero Pydantic `BaseModel` definitions in `routers/*.py` (except internal helpers converted to dataclasses)
- [ ] All tests pass
- [ ] OpenAPI schema unchanged (or intentional improvements documented)
- [ ] No circular import errors
- [ ] Mypy passes with no new errors
- [ ] Documentation updated

## Commands for Execution

```bash
# Create feature branch
git checkout -b refactor/normalize-schemas

# Create backup tag
git tag -a before-schema-normalization -m "Backup before schema normalization refactor"

# After each phase
git add -A
git commit -m "refactor(schemas): Phase X - <description>"

# Run validation
pytest tests/ -xvs && mypy src/

# Final commit
git commit -m "refactor(schemas): Complete schema normalization - all DTOs in schemas/"
```

---

**Status**: 🚧 In Progress
**Started**: 2025-11-16
**Last Updated**: 2025-11-16
**Completion**: 15% (schemas/__init__.py, schemas/tools.py, schemas/auth.py, schemas/batch.py created)
