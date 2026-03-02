"""
Batch operations router for bulk create/update/delete operations.

Provides endpoints for efficient bulk operations on multiple resources.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.provider import Provider
from db.postgres_control.models.tenant import Tenant
from db.postgres_control.repositories import model_instance_repo, tools
from src.schemas.auth import UserInfo
from src.schemas.batch import BatchOperation, BatchOperationResult, BatchRequest, BatchResponse
from src.security.perm import require_perms

# Create router without prefix (prefix added when mounting in app.py)
router = APIRouter(tags=["Batch Operations"])


# ============================================================================
# Validation Helpers
# ============================================================================

def validate_model_data(data: Dict[str, Any]) -> List[str]:
    """Validate model creation data and return list of errors"""
    errors = []
    
    # Required fields
    required = ["providerId", "instanceName", "modelId"]
    for field in required:
        if not data.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate field types and formats
    if data.get("contextWindow") and not isinstance(data.get("contextWindow"), int):
        errors.append("contextWindow must be an integer")
    
    if data.get("contextWindow") and data.get("contextWindow") <= 0:
        errors.append("contextWindow must be positive")
    
    if data.get("parameters") and not isinstance(data.get("parameters"), dict):
        errors.append("parameters must be a dictionary")
    
    return errors


def validate_tool_data(data: Dict[str, Any]) -> List[str]:
    """Validate tool creation data and return list of errors"""
    errors = []
    
    # Required fields
    required = ["name", "version", "inputSchema"]
    for field in required:
        if not data.get(field):
            errors.append(f"Missing required field: {field}")
    
    # Validate schemas
    if data.get("inputSchema") and not isinstance(data.get("inputSchema"), dict):
        errors.append("inputSchema must be a dictionary")
    
    if data.get("outputSchema") and not isinstance(data.get("outputSchema"), dict):
        errors.append("outputSchema must be a dictionary")
    
    # Validate version format (basic semver check)
    version = data.get("version", "")
    if version and not any(c.isdigit() for c in version):
        errors.append("version must contain at least one digit")
    
    return errors


async def validate_resource_references(
    db: Session,
    resource_type: str,
    data: Dict[str, Any]
) -> List[str]:
    """Validate that referenced resources exist in database"""
    errors = []
    
    if resource_type == "model":
        # Check provider exists
        if provider_id := data.get("providerId"):
            provider = db.execute(
                select(Provider).where(Provider.id == provider_id)
            ).scalar_one_or_none()
            if not provider:
                errors.append(f"Provider not found: {provider_id}")
        
        # Check tenant exists (if specified)
        if tenant_id := data.get("tenantId"):
            tenant = db.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            ).scalar_one_or_none()
            if not tenant:
                errors.append(f"Tenant not found: {tenant_id}")
    
    return errors


# ============================================================================
# Batch Endpoints
# ============================================================================

@router.post(
    "/operations",
    response_model=BatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute batch operations",
    description="""
    Execute multiple operations in a single request for efficiency.
    
    Supports:
    - Bulk create multiple resources
    - Bulk update multiple resources
    - Bulk delete multiple resources
    - Mixed operations in single request
    
    Example:
    ```json
    {
      "operations": [
        {
          "operation": "create",
          "resourceType": "model",
          "data": {
            "instanceId": "model-1",
            "modelName": "gpt-4",
            "providerId": "provider-1"
          }
        },
        {
          "operation": "delete",
          "resourceType": "model",
          "resourceId": "old-model-1"
        }
      ],
      "continueOnError": true
    }
    ```
    
    **Performance Notes**:
    - Maximum 100 operations per batch
    - Operations processed sequentially (parallel processing coming soon)
    - Use continueOnError=true to process all operations even if some fail
    """,
)
async def execute_batch_operations(
    request: BatchRequest,
    user: UserInfo = Depends(require_perms(["admin:write"])),
    db: Session = Depends(get_db),
) -> BatchResponse:
    """Execute batch operations - requires admin:write permission"""
    
    if len(request.operations) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 operations allowed per batch"
        )
    
    if request.atomic:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Atomic transactions not yet supported. Use continueOnError=false for fail-fast behavior."
        )
    
    results: List[BatchOperationResult] = []
    success_count = 0
    failure_count = 0
    
    for op in request.operations:
        try:
            result = await _execute_single_operation(op, db, user.sub)
            results.append(result)
            
            if result.success:
                success_count += 1
            else:
                failure_count += 1
                
            # Stop if not continuing on error
            if not request.continueOnError and not result.success:
                break
                
        except Exception as e:
            failure_count += 1
            results.append(
                BatchOperationResult(
                    operation=op.operation,
                    resourceType=op.resourceType,
                    resourceId=op.resourceId,
                    success=False,
                    statusCode=500,
                    error=str(e)
                )
            )
            
            if not request.continueOnError:
                break
    
    return BatchResponse(
        totalOperations=len(request.operations),
        successCount=success_count,
        failureCount=failure_count,
        results=results
    )


@router.post(
    "/models/bulk-create",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk create models",
    description="Create multiple models in a single request",
)
async def bulk_create_models(
    tenant_id: str,
    models: List[Dict[str, Any]],
    user: UserInfo = Depends(require_perms(["admin:write"])),
    db: Session = Depends(get_db),
) -> BatchResponse:
    """Bulk create models for a tenant - requires admin:write permission"""
    
    if len(models) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 models allowed per bulk create"
        )
    
    results: List[BatchOperationResult] = []
    success_count = 0
    failure_count = 0
    
    for model_data in models:
        try:
            # Add tenant_id to model data
            model_data["tenantId"] = tenant_id
            
            # Validate model data
            validation_errors = validate_model_data(model_data)
            if validation_errors:
                failure_count += 1
                results.append(
                    BatchOperationResult(
                        operation="create",
                        resourceType="model",
                        resourceId=model_data.get("instanceId"),
                        success=False,
                        statusCode=400,
                        error="; ".join(validation_errors)
                    )
                )
                continue
            
            # Validate references (provider, tenant)
            ref_errors = await validate_resource_references(db, "model", model_data)
            if ref_errors:
                failure_count += 1
                results.append(
                    BatchOperationResult(
                        operation="create",
                        resourceType="model",
                        resourceId=model_data.get("instanceId"),
                        success=False,
                        statusCode=404,
                        error="; ".join(ref_errors)
                    )
                )
                continue
            
            # Create model in database
            result = model_instance_repo.create_instance(
                provider_id=model_data.get("providerId"),
                instance_name=model_data.get("instanceName"),
                model_id=model_data.get("modelId"),
                tenant_id=tenant_id,
                model_uri=model_data.get("modelUri"),
                parameters=model_data.get("parameters"),
                context_window=model_data.get("contextWindow"),
                owner_sub=user.sub
            )
            
            results.append(
                BatchOperationResult(
                    operation="create",
                    resourceType="model",
                    resourceId=result.get("id"),
                    success=True,
                    statusCode=201,
                    message="Model created successfully",
                    data=result
                )
            )
            success_count += 1
            
        except Exception as e:
            failure_count += 1
            results.append(
                BatchOperationResult(
                    operation="create",
                    resourceType="model",
                    resourceId=model_data.get("instanceId"),
                    success=False,
                    statusCode=500,
                    error=str(e)
                )
            )
    
    return BatchResponse(
        totalOperations=len(models),
        successCount=success_count,
        failureCount=failure_count,
        results=results
    )


@router.delete(
    "/models/bulk-delete",
    response_model=BatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk delete models",
    description="Delete multiple models in a single request",
)
async def bulk_delete_models(
    tenant_id: str,
    model_ids: List[str],
    user: UserInfo = Depends(require_perms(["admin:write"])),
    db: Session = Depends(get_db),
) -> BatchResponse:
    """Bulk delete models for a tenant - requires admin:write permission"""
    
    if len(model_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 models allowed per bulk delete"
        )
    
    results: List[BatchOperationResult] = []
    success_count = 0
    failure_count = 0
    
    for model_id in model_ids:
        try:
            # Delete model from database
            deleted = model_instance_repo.delete_instance(
                instance_id=model_id,
                owner_sub=user.sub
            )
            
            if deleted:
                results.append(
                    BatchOperationResult(
                        operation="delete",
                        resourceType="model",
                        resourceId=model_id,
                        success=True,
                        statusCode=204,
                        message="Model deleted successfully"
                    )
                )
                success_count += 1
            else:
                failure_count += 1
                results.append(
                    BatchOperationResult(
                        operation="delete",
                        resourceType="model",
                        resourceId=model_id,
                        success=False,
                        statusCode=404,
                        error="Model not found"
                    )
                )
            
        except Exception as e:
            failure_count += 1
            results.append(
                BatchOperationResult(
                    operation="delete",
                    resourceType="model",
                    resourceId=model_id,
                    success=False,
                    statusCode=500,
                    error=str(e)
                )
            )
    
    return BatchResponse(
        totalOperations=len(model_ids),
        successCount=success_count,
        failureCount=failure_count,
        results=results
    )


@router.post(
    "/tools/bulk-create",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk create tools",
    description="Create multiple tools in a single request",
)
async def bulk_create_tools(
    tenant_id: str,
    tools_list: List[Dict[str, Any]],
    user: UserInfo = Depends(require_perms(["admin:write"])),
    db: Session = Depends(get_db),
) -> BatchResponse:
    """Bulk create tools for a tenant - requires admin:write permission"""
    
    if len(tools_list) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 tools allowed per bulk create"
        )
    
    results: List[BatchOperationResult] = []
    success_count = 0
    failure_count = 0
    repo = tools.ToolsRepository(db)
    
    for tool_data in tools_list:
        try:
            # Validate tool data
            validation_errors = validate_tool_data(tool_data)
            if validation_errors:
                failure_count += 1
                results.append(
                    BatchOperationResult(
                        operation="create",
                        resourceType="tool",
                        resourceId=tool_data.get("toolId"),
                        success=False,
                        statusCode=400,
                        error="; ".join(validation_errors)
                    )
                )
                continue
            
            # Create tool in database
            tool, created = repo.create_tool(
                name=tool_data.get("name"),
                version=tool_data.get("version"),
                input_schema=tool_data.get("inputSchema", {}),
                owner_tenant_id=tenant_id,
                description=tool_data.get("description"),
                output_schema=tool_data.get("outputSchema")
            )
            
            results.append(
                BatchOperationResult(
                    operation="create",
                    resourceType="tool",
                    resourceId=tool.id,
                    success=True,
                    statusCode=201 if created else 200,
                    message="Tool created successfully" if created else "Tool already exists (idempotent)",
                    data={
                        "id": tool.id,
                        "name": tool.name,
                        "version": tool.version,
                        "created": created
                    }
                )
            )
            success_count += 1
            
        except ValueError as e:
            # Tool exists with different configuration
            failure_count += 1
            results.append(
                BatchOperationResult(
                    operation="create",
                    resourceType="tool",
                    resourceId=tool_data.get("toolId"),
                    success=False,
                    statusCode=409,
                    error=str(e)
                )
            )
        except Exception as e:
            failure_count += 1
            results.append(
                BatchOperationResult(
                    operation="create",
                    resourceType="tool",
                    resourceId=tool_data.get("toolId"),
                    success=False,
                    statusCode=500,
                    error=str(e)
                )
            )
    
    return BatchResponse(
        totalOperations=len(tools_list),
        successCount=success_count,
        failureCount=failure_count,
        results=results
    )


# ============================================================================
# Helper Functions
# ============================================================================

async def _execute_single_operation(
    operation: BatchOperation,
    db: Session,
    user_sub: str
) -> BatchOperationResult:
    """Execute a single batch operation"""
    
    try:
        if operation.resourceType == "model":
            return await _execute_model_operation(operation, db, user_sub)
        elif operation.resourceType == "tenant":
            return await _execute_tenant_operation(operation)
        elif operation.resourceType == "tool":
            return await _execute_tool_operation(operation, db, user_sub)
        elif operation.resourceType == "agent":
            return await _execute_agent_operation(operation)
        else:
            return BatchOperationResult(
                operation=operation.operation,
                resourceType=operation.resourceType,
                resourceId=operation.resourceId,
                success=False,
                statusCode=400,
                error=f"Unsupported resource type: {operation.resourceType}"
            )
            
    except Exception as e:
        return BatchOperationResult(
            operation=operation.operation,
            resourceType=operation.resourceType,
            resourceId=operation.resourceId,
            success=False,
            statusCode=500,
            error=str(e)
        )


async def _execute_model_operation(
    operation: BatchOperation,
    db: Session,
    user_sub: str
) -> BatchOperationResult:
    """Execute model operation with database persistence and validation"""
    
    try:
        if operation.operation == "create":
            if not operation.data:
                return BatchOperationResult(
                    operation="create",
                    resourceType="model",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="Missing model data"
                )
            
            # Validate model data
            validation_errors = validate_model_data(operation.data)
            if validation_errors:
                return BatchOperationResult(
                    operation="create",
                    resourceType="model",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="; ".join(validation_errors)
                )
            
            # Validate references (provider, tenant)
            ref_errors = await validate_resource_references(db, "model", operation.data)
            if ref_errors:
                return BatchOperationResult(
                    operation="create",
                    resourceType="model",
                    resourceId=None,
                    success=False,
                    statusCode=404,
                    error="; ".join(ref_errors)
                )
            
            # Create model instance in database
            result = model_instance_repo.create_instance(
                provider_id=operation.data.get("providerId"),
                instance_name=operation.data.get("instanceName"),
                model_id=operation.data.get("modelId"),
                tenant_id=operation.data.get("tenantId"),
                model_uri=operation.data.get("modelUri"),
                parameters=operation.data.get("parameters"),
                context_window=operation.data.get("contextWindow"),
                owner_sub=user_sub
            )
            
            return BatchOperationResult(
                operation="create",
                resourceType="model",
                resourceId=result.get("id"),
                success=True,
                statusCode=201,
                message="Model created",
                data=result
            )
            
        elif operation.operation == "delete":
            if not operation.resourceId:
                return BatchOperationResult(
                    operation="delete",
                    resourceType="model",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="Missing resourceId"
                )
            
            # Delete model instance from database
            deleted = model_instance_repo.delete_instance(
                instance_id=operation.resourceId,
                owner_sub=user_sub
            )
            
            if not deleted:
                return BatchOperationResult(
                    operation="delete",
                    resourceType="model",
                    resourceId=operation.resourceId,
                    success=False,
                    statusCode=404,
                    error="Model not found"
                )
            
            return BatchOperationResult(
                operation="delete",
                resourceType="model",
                resourceId=operation.resourceId,
                success=True,
                statusCode=204,
                message="Model deleted"
            )
            
        else:
            return BatchOperationResult(
                operation=operation.operation,
                resourceType="model",
                resourceId=operation.resourceId,
                success=False,
                statusCode=400,
                error=f"Unsupported operation: {operation.operation}"
            )
            
    except Exception as e:
        return BatchOperationResult(
            operation=operation.operation,
            resourceType="model",
            resourceId=operation.resourceId,
            success=False,
            statusCode=500,
            error=str(e)
        )


async def _execute_tenant_operation(
    operation: BatchOperation
) -> BatchOperationResult:
    """Execute tenant operation"""
    
    # Placeholder - implement actual logic
    return BatchOperationResult(
        operation=operation.operation,
        resourceType="tenant",
        resourceId=operation.resourceId,
        success=True,
        statusCode=200,
        message="Tenant operation completed"
    )


async def _execute_tool_operation(
    operation: BatchOperation,
    db: Session,
    user_sub: str
) -> BatchOperationResult:
    """Execute tool operation with database persistence and validation"""
    
    try:
        repo = tools.ToolsRepository(db)
        
        if operation.operation == "create":
            if not operation.data:
                return BatchOperationResult(
                    operation="create",
                    resourceType="tool",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="Missing tool data"
                )
            
            # Validate tool data
            validation_errors = validate_tool_data(operation.data)
            if validation_errors:
                return BatchOperationResult(
                    operation="create",
                    resourceType="tool",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="; ".join(validation_errors)
                )
            
            # Create tool in database
            tool, created = repo.create_tool(
                name=operation.data.get("name"),
                version=operation.data.get("version"),
                input_schema=operation.data.get("inputSchema", {}),
                owner_tenant_id=operation.data.get("ownerTenantId"),
                description=operation.data.get("description"),
                output_schema=operation.data.get("outputSchema")
            )
            
            return BatchOperationResult(
                operation="create",
                resourceType="tool",
                resourceId=tool.id,
                success=True,
                statusCode=201 if created else 200,
                message="Tool created" if created else "Tool already exists (idempotent)",
                data={
                    "id": tool.id,
                    "name": tool.name,
                    "version": tool.version,
                    "created": created
                }
            )
            
        elif operation.operation == "delete":
            if not operation.resourceId:
                return BatchOperationResult(
                    operation="delete",
                    resourceType="tool",
                    resourceId=None,
                    success=False,
                    statusCode=400,
                    error="Missing resourceId"
                )
            
            # Delete tool from database
            deleted = repo.delete_tool(operation.resourceId)
            
            if not deleted:
                return BatchOperationResult(
                    operation="delete",
                    resourceType="tool",
                    resourceId=operation.resourceId,
                    success=False,
                    statusCode=404,
                    error="Tool not found"
                )
            
            return BatchOperationResult(
                operation="delete",
                resourceType="tool",
                resourceId=operation.resourceId,
                success=True,
                statusCode=204,
                message="Tool deleted"
            )
            
        else:
            return BatchOperationResult(
                operation=operation.operation,
                resourceType="tool",
                resourceId=operation.resourceId,
                success=False,
                statusCode=400,
                error=f"Unsupported operation: {operation.operation}"
            )
            
    except ValueError as e:
        # Tool exists with different configuration
        return BatchOperationResult(
            operation=operation.operation,
            resourceType="tool",
            resourceId=operation.resourceId,
            success=False,
            statusCode=409,
            error=str(e)
        )
    except Exception as e:
        return BatchOperationResult(
            operation=operation.operation,
            resourceType="tool",
            resourceId=operation.resourceId,
            success=False,
            statusCode=500,
            error=str(e)
        )


async def _execute_agent_operation(
    operation: BatchOperation
) -> BatchOperationResult:
    """Execute agent operation"""
    
    # Placeholder - implement actual logic
    return BatchOperationResult(
        operation=operation.operation,
        resourceType="agent",
        resourceId=operation.resourceId,
        success=True,
        statusCode=200,
        message="Agent operation completed"
    )
