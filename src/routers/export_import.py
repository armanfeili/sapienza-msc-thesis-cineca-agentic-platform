"""
Export/Import functionality for platform configurations.

Allows users to backup and restore tenant configurations, agent setups, and tool definitions.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import zipfile
import io
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from src.schemas.auth import UserInfo
from src.routers.auth import get_current_user
from src.security.perm import require_perms

# Create router without prefix (prefix added when mounting in app.py)
router = APIRouter(tags=["Export/Import"])


# ============================================================================
# Models
# ============================================================================

class ExportRequest(BaseModel):
    """Request to export configurations"""
    
    tenantIds: Optional[List[str]] = Field(
        None,
        description="Specific tenant IDs to export (omit for all)"
    )
    includeModels: bool = Field(True, description="Include model configurations")
    includeProviders: bool = Field(True, description="Include provider configurations")
    includeTools: bool = Field(True, description="Include tool definitions")
    includeAgents: bool = Field(True, description="Include agent configurations")
    includeJobs: bool = Field(False, description="Include job history (may be large)")
    format: str = Field("json", description="Export format: json or zip")


class ExportResponse(BaseModel):
    """Response from export endpoint"""
    
    exportedAt: str
    exportedBy: str
    version: str
    tenantCount: int
    itemCount: int
    format: str
    data: Dict[str, Any]


class ExportMetadata(BaseModel):
    """Metadata about export"""
    
    exportedAt: str
    exportedBy: str
    platformVersion: str
    itemCount: int
    tenantCount: int
    format: str


class ExportData(BaseModel):
    """Complete export data structure"""
    
    metadata: ExportMetadata
    tenants: List[Dict[str, Any]] = Field(default_factory=list)
    models: List[Dict[str, Any]] = Field(default_factory=list)
    providers: List[Dict[str, Any]] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    jobs: List[Dict[str, Any]] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """Request to import configurations"""
    
    data: Dict[str, Any] = Field(..., description="Export data to import")
    overwriteExisting: bool = Field(
        False,
        description="Overwrite existing resources with same IDs"
    )
    skipErrors: bool = Field(
        True,
        description="Continue importing even if some items fail"
    )
    dryRun: bool = Field(
        False,
        description="Validate import without making changes"
    )
    mergeStrategy: Optional[str] = Field(
        None,
        description="Merge strategy: skip or overwrite"
    )


class ImportResult(BaseModel):
    """Result of import operation"""
    
    importedAt: str
    importedBy: str
    status: str  # "success", "partial", "failed"
    success: bool
    itemsProcessed: int
    itemsImported: int
    itemsSkipped: int
    itemsFailed: int
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    importedResources: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of imported resources by type"
    )


# ============================================================================
# Export Endpoints
# ============================================================================

@router.post(
    "/export",
    summary="Export platform configurations",
    description="""
    Export tenant configurations, models, tools, and agents.
    
    Returns either:
    - JSON file with all configurations
    - ZIP file with multiple JSON files (one per resource type)
    
    **Use Cases**:
    - Backup before major changes
    - Migrate configurations between environments
    - Share agent setups with team
    - Disaster recovery
    
    **Export Formats**:
    - `json`: Single JSON file with all data
    - `zip`: ZIP archive with separate files per resource type
    
    **Example**:
    ```json
    {
      "includeModels": true,
      "includeProviders": true,
      "includeTools": true,
      "includeAgents": true,
      "format": "json"
    }
    ```
    """,
)
async def export_configurations(
    request: ExportRequest,
    user: UserInfo = Depends(require_perms(["admin:read"])),
    db: Session = Depends(get_db),
):
    """Export platform configurations - requires admin:read permission"""
    
    # Build export data
    export_data = ExportData(
        metadata=ExportMetadata(
            exportedAt=datetime.utcnow().isoformat(),
            exportedBy=user.sub if hasattr(user, 'sub') else "admin",
            platformVersion="1.0.0",
            itemCount=0,
            tenantCount=0,
            format=request.format
        )
    )
    
    # Export tenants
    if request.tenantIds:
        # Export specific tenants
        for tenant_id in request.tenantIds:
            tenant_data = await _export_tenant(tenant_id)
            export_data.tenants.append(tenant_data)
    else:
        # Export all tenants
        all_tenants = await _export_all_tenants()
        export_data.tenants.extend(all_tenants)
    
    export_data.metadata.tenantCount = len(export_data.tenants)
    
    # Export models
    if request.includeModels:
        models = await _export_models(request.tenantIds)
        export_data.models.extend(models)
    
    # Export providers
    if request.includeProviders:
        providers = await _export_providers(request.tenantIds)
        export_data.providers.extend(providers)
    
    # Export tools
    if request.includeTools:
        tools = await _export_tools(request.tenantIds)
        export_data.tools.extend(tools)
    
    # Export agents
    if request.includeAgents:
        agents = await _export_agents(request.tenantIds)
        export_data.agents.extend(agents)
    
    # Export jobs (optional, may be large)
    if request.includeJobs:
        jobs = await _export_jobs(request.tenantIds)
        export_data.jobs.extend(jobs)
    
    # Calculate total items
    export_data.metadata.itemCount = (
        len(export_data.tenants) +
        len(export_data.models) +
        len(export_data.providers) +
        len(export_data.tools) +
        len(export_data.agents) +
        len(export_data.jobs)
    )
    
    # Generate export file
    if request.format == "zip":
        # Create ZIP with separate files
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("metadata.json", export_data.metadata.model_dump_json(indent=2))
            if export_data.tenants:
                zip_file.writestr("tenants.json", json.dumps(export_data.tenants, indent=2))
            if export_data.models:
                zip_file.writestr("models.json", json.dumps(export_data.models, indent=2))
            if export_data.providers:
                zip_file.writestr("providers.json", json.dumps(export_data.providers, indent=2))
            if export_data.tools:
                zip_file.writestr("tools.json", json.dumps(export_data.tools, indent=2))
            if export_data.agents:
                zip_file.writestr("agents.json", json.dumps(export_data.agents, indent=2))
            if export_data.jobs:
                zip_file.writestr("jobs.json", json.dumps(export_data.jobs, indent=2))
        
        zip_buffer.seek(0)
        filename = f"export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    else:
        # Return JSON response with expected structure
        return ExportResponse(
            exportedAt=export_data.metadata.exportedAt,
            exportedBy=export_data.metadata.exportedBy,
            version=export_data.metadata.platformVersion,
            tenantCount=export_data.metadata.tenantCount,
            itemCount=export_data.metadata.itemCount,
            format=export_data.metadata.format,
            data={
                "tenants": export_data.tenants,
                "models": export_data.models,
                "providers": export_data.providers,
                "tools": export_data.tools,
                "agents": export_data.agents,
                "jobs": export_data.jobs
            }
        )


@router.post(
    "/export/tenant/{tenant_id}",
    summary="Export single tenant configuration",
    description="Export all configurations for a specific tenant",
)
async def export_tenant(
    tenant_id: str,
    user: UserInfo = Depends(require_perms(["admin:read"])),
    db: Session = Depends(get_db),
):
    """Export single tenant configuration - requires admin:read permission"""
    
    request = ExportRequest(
        tenantIds=[tenant_id],
        includeModels=True,
        includeProviders=True,
        includeTools=True,
        includeAgents=True,
        format="json"
    )
    
    return await export_configurations(request, user, db)


# ============================================================================
# Import Endpoints
# ============================================================================

@router.post(
    "/import",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
    summary="Import platform configurations",
    description="""
    Import previously exported configurations.
    
    **Import Modes**:
    - `overwriteExisting=false`: Skip resources that already exist
    - `overwriteExisting=true`: Replace existing resources
    - `dryRun=true`: Validate import without making changes
    
    **Conflict Resolution**:
    - By default, existing resources are preserved
    - Set `overwriteExisting=true` to replace
    - Use `dryRun=true` to preview changes
    
    **Error Handling**:
    - `skipErrors=true`: Continue importing even if some items fail
    - `skipErrors=false`: Stop on first error
    
    **Example**:
    ```json
    {
      "data": { ... exported data ... },
      "overwriteExisting": false,
      "skipErrors": true,
      "dryRun": false
    }
    ```
    """,
)
async def import_configurations(
    request: ImportRequest,
    user: UserInfo = Depends(require_perms(["admin:write"])),
    db: Session = Depends(get_db),
) -> ImportResult:
    """Import platform configurations - requires admin:write permission"""
    
    # Extract data from request
    data = request.data
    
    # Validate data structure
    validation_errors = await _validate_import_data_dict(data)
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Validation failed",
                "errors": validation_errors
            }
        )
    
    tenants = data.get("tenants", [])
    providers = data.get("providers", [])
    models = data.get("models", [])
    tools = data.get("tools", [])
    agents = data.get("agents", [])
    
    result = ImportResult(
        importedAt=datetime.utcnow().isoformat(),
        importedBy=user.sub if hasattr(user, 'sub') else "admin",
        status="success",
        success=True,
        itemsProcessed=0,
        itemsImported=0,
        itemsSkipped=0,
        itemsFailed=0,
        importedResources={}
    )
    
    # Validate import data
    validation_errors = await _validate_import_data_dict(data)
    if validation_errors:
        result.errors.extend(validation_errors)
        if not request.skipErrors:
            result.success = False
            result.status = "failed"
            return result
    
    # Import tenants first (dependencies)
    for tenant_data in tenants:
        try:
            result.itemsProcessed += 1
            
            if not request.dryRun:
                imported = await _import_tenant(
                    tenant_data,
                    overwrite=request.overwriteExisting
                )
                
                if imported:
                    result.itemsImported += 1
                    result.importedResources["tenants"] = \
                        result.importedResources.get("tenants", 0) + 1
                else:
                    result.itemsSkipped += 1
                    result.warnings.append(
                        f"Tenant {tenant_data.get('tenantId')} already exists, skipped"
                    )
            
        except Exception as e:
            result.itemsFailed += 1
            error_msg = f"Failed to import tenant {tenant_data.get('tenantId')}: {str(e)}"
            result.errors.append(error_msg)
            
            if not request.skipErrors:
                result.success = False
                return result
    
    # Import providers
    for provider_data in providers:
        try:
            result.itemsProcessed += 1
            
            if not request.dryRun:
                imported = await _import_provider(
                    provider_data,
                    overwrite=request.overwriteExisting
                )
                
                if imported:
                    result.itemsImported += 1
                    result.importedResources["providers"] = \
                        result.importedResources.get("providers", 0) + 1
                else:
                    result.itemsSkipped += 1
            
        except Exception as e:
            result.itemsFailed += 1
            result.errors.append(f"Failed to import provider: {str(e)}")
            
            if not request.skipErrors:
                result.success = False
                result.status = "failed"
                return result
    
    # Import models
    for model_data in models:
        try:
            result.itemsProcessed += 1
            
            if not request.dryRun:
                imported = await _import_model(
                    model_data,
                    overwrite=request.overwriteExisting
                )
                
                if imported:
                    result.itemsImported += 1
                    result.importedResources["models"] = \
                        result.importedResources.get("models", 0) + 1
                else:
                    result.itemsSkipped += 1
            
        except Exception as e:
            result.itemsFailed += 1
            result.errors.append(f"Failed to import model: {str(e)}")
            
            if not request.skipErrors:
                result.success = False
                result.status = "failed"
                return result
    
    # Import tools
    for tool_data in tools:
        try:
            result.itemsProcessed += 1
            
            if not request.dryRun:
                imported = await _import_tool(
                    tool_data,
                    overwrite=request.overwriteExisting
                )
                
                if imported:
                    result.itemsImported += 1
                    result.importedResources["tools"] = \
                        result.importedResources.get("tools", 0) + 1
                else:
                    result.itemsSkipped += 1
            
        except Exception as e:
            result.itemsFailed += 1
            result.errors.append(f"Failed to import tool: {str(e)}")
            
            if not request.skipErrors:
                result.success = False
                result.status = "failed"
                return result
    
    # Import agents
    for agent_data in agents:
        try:
            result.itemsProcessed += 1
            
            if not request.dryRun:
                imported = await _import_agent(
                    agent_data,
                    overwrite=request.overwriteExisting
                )
                
                if imported:
                    result.itemsImported += 1
                    result.importedResources["agents"] = \
                        result.importedResources.get("agents", 0) + 1
                else:
                    result.itemsSkipped += 1
            
        except Exception as e:
            result.itemsFailed += 1
            result.errors.append(f"Failed to import agent: {str(e)}")
            
            if not request.skipErrors:
                result.success = False
                result.status = "failed"
                return result
    
    # Set overall success and status
    if result.itemsFailed > 0:
        result.status = "partial" if result.itemsImported > 0 else "failed"
        result.success = result.itemsImported > 0
    else:
        result.status = "success"
        result.success = True
    
    return result


# ============================================================================
# Helper Functions
# ============================================================================

async def _export_tenant(tenant_id: str) -> Dict[str, Any]:
    """Export single tenant"""
    # Placeholder - implement actual export logic
    return {
        "tenantId": tenant_id,
        "displayName": f"Tenant {tenant_id}",
        "metadata": {}
    }


async def _export_all_tenants() -> List[Dict[str, Any]]:
    """Export all tenants"""
    # Placeholder - implement actual export logic
    return []


async def _export_models(tenant_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Export models"""
    # Placeholder
    return []


async def _export_providers(tenant_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Export providers"""
    # Placeholder
    return []


async def _export_tools(tenant_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Export tools"""
    # Placeholder
    return []


async def _export_agents(tenant_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Export agents"""
    # Placeholder
    return []


async def _export_jobs(tenant_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Export jobs"""
    # Placeholder
    return []


async def _validate_import_data_dict(data: Dict[str, Any]) -> List[str]:
    """Validate import data from dict"""
    errors = []
    
    # Validate tenants is an array or missing
    tenants = data.get("tenants", [])
    if not isinstance(tenants, list):
        errors.append("tenants must be an array")
    
    # Validate providers is an array or missing
    providers = data.get("providers", [])
    if not isinstance(providers, list):
        errors.append("providers must be an array")
    
    # Validate models is an array or missing
    models = data.get("models", [])
    if not isinstance(models, list):
        errors.append("models must be an array")
    
    # Validate tools is an array or missing
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        errors.append("tools must be an array")
    
    # Validate agents is an array or missing
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        errors.append("agents must be an array")
    
    # Validate tenant IDs are unique
    tenant_ids = [t.get("tenantId") for t in tenants if isinstance(t, dict) and t.get("tenantId")]
    if len(tenant_ids) != len(set(tenant_ids)):
        errors.append("Duplicate tenant IDs found")
    
    return errors


async def _validate_import_data(data: ExportData) -> List[str]:
    """Validate import data"""
    errors = []
    
    # Check required fields in metadata
    if not data.metadata.exportedAt:
        errors.append("Missing exportedAt in metadata")
    
    # Validate tenant IDs are unique
    tenant_ids = [t.get("tenantId") for t in data.tenants]
    if len(tenant_ids) != len(set(tenant_ids)):
        errors.append("Duplicate tenant IDs found")
    
    return errors


async def _import_tenant(data: Dict[str, Any], overwrite: bool) -> bool:
    """Import tenant"""
    # Placeholder - implement actual import logic
    # Return True if imported, False if skipped
    return True


async def _import_provider(data: Dict[str, Any], overwrite: bool) -> bool:
    """Import provider"""
    # Placeholder
    return True


async def _import_model(data: Dict[str, Any], overwrite: bool) -> bool:
    """Import model"""
    # Placeholder
    return True


async def _import_tool(data: Dict[str, Any], overwrite: bool) -> bool:
    """Import tool"""
    # Placeholder
    return True


async def _import_agent(data: Dict[str, Any], overwrite: bool) -> bool:
    """Import agent"""
    # Placeholder
    return True
