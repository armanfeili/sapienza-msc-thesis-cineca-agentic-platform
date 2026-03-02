# Schema Normalization Progress Report

## Executive Summary

**Status:** Phase 1 Complete (44% overall progress)  
**Completed:** 10/18 tasks  
**Validation:** ✅ All migrated schemas import successfully  

## Completed Work

### Phase 1: Core Schema Migration ✅

1. **Created schemas/__init__.py** (132 lines)
   - Architectural documentation
   - Common exports for UserInfo, JobRequest, etc.
   - Package initialization

2. **Created schemas/tools.py** (67 lines)
   - ToolInfo, ToolsListResponse
   - ToolInvokeRequest, ToolInvokeResponse

3. **Created schemas/auth.py** (16 lines)
   - UserInfo model
   - Used by 9+ files across codebase

4. **Created schemas/batch.py** (44 lines)
   - BatchOperation, BatchRequest
   - BatchOperationResult, BatchResponse

5. **Reconciled schemas/jobs.py**
   - Added `owner_sub: str = Field(..., alias="owner")` for backward compatibility
   - Added `JobRequest = JobCreateRequest` alias

### Updated Routers

1. **routers/jobs.py** - Removed 67 lines of local models
2. **routers/admin_jobs.py** - Removed 15 lines
3. **routers/tenants.py** - Removed 18 lines
4. **routers/auth.py** - Removed UserInfo definition
5. **routers/tools.py** - Removed tool models
6. **routers/batch.py** - Removed batch models (37 lines)
7. **routers/model_management.py** - Removed provider config models (56 lines)

### Global Import Updates

Updated **9 files** to import UserInfo from schemas.auth:
- routers/agent_runs.py
- routers/export_import.py
- routers/model_instances.py
- routers/models.py
- routers/manifests.py
- routers/tenants_admin.py
- routers/agent.py
- security/model_perms.py
- tests/unit/test_model_management_instance.py

### Validation Results

```bash
✅ Import test passed
python -c "
import sys
sys.path.insert(0, 'src')
from schemas.auth import UserInfo
from schemas.jobs import JobRequest, JobResponse
from schemas.tools import ToolInfo
from schemas.batch import BatchRequest
print('✅ All schema imports successful')
"
```

## Remaining Work

### Phase 2: Create Large Schema Files

#### Priority 1: schemas/models.py (Estimated 400+ lines)
**Status:** NOT STARTED  
**Complexity:** HIGH  
**Estimated Time:** 4-6 hours

Must extract and merge from:
- routers/model_management.py (lines 193-320)
- routers/model_instances.py (lines 106-435)
- routers/models.py (lines 367-1486)

Models to create:
- ModelInfo (merge duplicates)
- InstanceCreateRequest, LoadInstanceRequest, LoadInstanceResponse
- ListInstancesResponse, GetDefaultResponse
- SetDefaultRequest, SetDefaultResponse
- InstanceDetail, TestInstanceRequest, TestInstanceResponse
- TestRequest, TestResponse, Usage
- CompletionRequest, CompletionResponse
- EmbeddingRequest, EmbeddingVector, EmbeddingResponse
- ChatRequest, ChatMessage, ChatResponse

#### Priority 2: schemas/admin.py (Estimated 80-120 lines)
**Status:** NOT STARTED  
**Complexity:** MEDIUM  
**Estimated Time:** 1-2 hours

Extract from:
- routers/admin_jobs.py
- routers/admin_ops.py
- routers/admin_db.py
- routers/internal_ops.py
- routers/internal_db.py

Models:
- DBJobRequest, CreateJobRequest
- AutoStartOverrideRequest
- PreviewStagedManifest

#### Priority 3: schemas/export_import.py (Estimated 60-80 lines)
**Status:** NOT STARTED  
**Complexity:** LOW  
**Estimated Time:** 1 hour

Extract from routers/export_import.py (lines 29-101):
- ExportRequest, ExportResponse
- ExportMetadata, ExportData
- ImportRequest, ImportResult

#### Priority 4: schemas/manifests.py (Estimated 100-120 lines)
**Status:** NOT STARTED  
**Complexity:** MEDIUM  
**Estimated Time:** 1-2 hours

Extract from routers/manifests.py (lines 45-139):
- StageManifestRequest/Response
- ActivateManifestRequest/Response
- RollbackManifestRequest/Response
- ListBuiltinsResponse, ListHistoryResponse

### Phase 3: Update Remaining Routers

After creating schema files above:
1. Update routers/model_instances.py
2. Update routers/models.py
3. Update routers/export_import.py
4. Update routers/manifests.py
5. Update admin routers (4-5 files)

### Phase 4: Validation & Testing

1. **Verify no BaseModel in routers:**
   ```bash
   grep -n 'class.*BaseModel' src/routers/*.py
   ```

2. **Run pytest:**
   ```bash
   pytest tests/ -x --tb=short
   ```

3. **Fix any breaking changes identified**

## Key Architectural Rules

1. ✅ **ALL Pydantic models MUST live in schemas/**
2. ✅ **Routers MUST only import schemas, never define BaseModel**
3. ✅ **Use Pydantic Field aliases for backward compatibility**
4. ✅ **Import pattern: `from schemas.X import Y` (not `from src.schemas.X`)**

## Risk Assessment

### Completed Mitigations ✅
- Backward compatibility via Pydantic aliases (owner_sub/owner)
- Type aliases for naming compatibility (JobRequest = JobCreateRequest)
- Systematic grep-based import discovery and updates
- Import validation test before proceeding

### Remaining Risks ⚠️
- Large models.py file (~400 lines) requires careful merge of duplicates
- Breaking API changes if field names differ in duplicates
- Service layer imports may need updates (not yet validated)
- Test failures may reveal hidden dependencies

## Next Steps

1. **Immediate:** Create schemas/models.py (examine 3 router files)
2. **Then:** Create schemas/admin.py, export_import.py, manifests.py
3. **Then:** Update remaining routers to import from new schemas
4. **Finally:** Run pytest and fix any breaking changes

## Time Estimate

- Completed: ~12 hours (Phase 1)
- Remaining: ~14-20 hours
- **Total Project:** 26-32 hours

**Estimated Completion:** 2-3 additional work days
