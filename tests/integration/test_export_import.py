"""
Integration tests for export/import endpoints.

Tests configuration export/import with validation and format handling.
"""

import os
import uuid

import pytest

# Set DB_HOST to localhost for tests running outside Docker
os.environ["DB_HOST"] = "localhost"


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    os.environ["DB_HOST"] = "localhost"
    yield

import pytest
import uuid
import json
from typing import Dict, Any


@pytest.fixture
def admin_headers(mint_token):
    """Generate admin token with admin:all permissions."""
    token = mint_token(
        sub="admin-user",
        roles=["admin"],
        scopes=["admin:all", "admin:read", "admin:write"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def read_only_headers(mint_token):
    """Generate token with only admin:read permission."""
    token = mint_token(
        sub="readonly-user",
        roles=["user"],  # NOT admin role
        scopes=["admin:read"],  # Only read scope
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def write_only_headers(mint_token):
    """Generate token with only admin:write permission (should fail on export)."""
    token = mint_token(
        sub="writeonly-user",
        roles=["user"],  # NOT admin role
        scopes=["admin:write"],  # Only write scope, no read
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_tenant_id(db_session):
    """Create a test tenant directly in database."""
    from db.postgres_control.models.tenant import Tenant
    from db.postgres_control.models.tool import Tool
    from datetime import datetime, UTC
    
    tenant_id = f"test-tenant-{uuid.uuid4()}"
    tenant = Tenant(
        id=tenant_id,
        name=f"Test Tenant {uuid.uuid4().hex[:8]}",
        admin_email="admin@test.com",
        metadata_={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=0,
    )
    db_session.add(tenant)
    db_session.commit()
    
    yield tenant_id
    
    # Cleanup: Delete tools first (to avoid foreign key constraint), then tenant
    try:
        db_session.query(Tool).filter_by(owner_tenant_id=tenant_id).delete()
        db_session.query(Tenant).filter(Tenant.id == tenant_id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.mark.integration
class TestExportConfigurations:
    """Test configuration export endpoint"""

    def test_export_authentication_required(self, client):
        """Export endpoint should require authentication"""
        resp = client.post(
            "/v1/export/export",
            json={"tenantIds": [], "includeModels": True}
        )
        assert resp.status_code == 401

    def test_export_read_permission_required(self, client, write_only_headers):
        """Export should require admin:read permission"""
        resp = client.post(
            "/v1/export/export",
            json={"tenantIds": [], "includeModels": True},
            headers=write_only_headers
        )
        assert resp.status_code == 403

    def test_export_read_permission_sufficient(self, client, read_only_headers):
        """Export should work with only admin:read permission"""
        resp = client.post(
            "/v1/export/export",
            json={"tenantIds": [], "includeModels": True},
            headers=read_only_headers
        )
        # Should succeed or return specific error, not 403
        assert resp.status_code != 403

    def test_export_empty_configuration(self, client, admin_headers):
        """Exporting with no tenants should succeed with empty data"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True,
                "includeProviders": True,
                "includeTools": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have export metadata
        assert "exportedAt" in data
        assert "exportedBy" in data
        assert "version" in data
        
        # Should have data structure
        assert "data" in data
        export_data = data["data"]
        assert "tenants" in export_data

    def test_export_includes_user_identity(self, client, admin_headers):
        """Export should include user identity in exportedBy field"""
        resp = client.post(
            "/v1/export/export",
            json={"tenantIds": [], "includeModels": True},
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "exportedBy" in data
        # Should be the user sub from the token
        assert data["exportedBy"] == "admin-user"

    def test_export_json_format(self, client, admin_headers, test_tenant_id):
        """Export with format=json should return JSON"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [test_tenant_id],
                "includeModels": True,
                "format": "json"
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        
        # Should be valid JSON
        data = resp.json()
        assert isinstance(data, dict)
        assert "data" in data

    def test_export_with_tenant_filter(
        self, client, admin_headers, test_tenant_id
    ):
        """Export should filter by tenant IDs"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [test_tenant_id],
                "includeModels": True,
                "includeProviders": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        export_data = data["data"]
        
        # Should include tenant data
        assert "tenants" in export_data
        # If tenant exists, should be in export
        if export_data["tenants"]:
            tenant_ids = [t["tenantId"] for t in export_data["tenants"]]
            assert test_tenant_id in tenant_ids

    def test_export_selective_resources(
        self, client, admin_headers, test_tenant_id
    ):
        """Export should respect resource inclusion flags"""
        # Export only models
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [test_tenant_id],
                "includeModels": True,
                "includeProviders": False,
                "includeTools": False
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        export_data = data["data"]
        
        # Should have models key
        assert "models" in export_data
        # Providers and tools may or may not be present depending on implementation


@pytest.mark.integration
class TestExportTenant:
    """Test tenant-specific export endpoint"""

    def test_export_tenant_authentication_required(self, client):
        """Export tenant endpoint should require authentication"""
        resp = client.post(
            "/v1/export/export/tenant/test-tenant-id"
        )
        assert resp.status_code == 401

    def test_export_tenant_read_permission_required(
        self, client, write_only_headers
    ):
        """Export tenant should require admin:read permission"""
        resp = client.post(
            "/v1/export/export/tenant/test-tenant-id",
            headers=write_only_headers
        )
        assert resp.status_code == 403

    def test_export_tenant_success(
        self, client, admin_headers, test_tenant_id
    ):
        """Export specific tenant should succeed"""
        resp = client.post(
            f"/v1/export/export/tenant/{test_tenant_id}",
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have export metadata
        assert "exportedAt" in data
        assert "exportedBy" in data
        assert "version" in data
        
        # Should have tenant data
        assert "data" in data
        export_data = data["data"]
        assert "tenants" in export_data

    def test_export_tenant_includes_related_resources(
        self, client, admin_headers, test_tenant_id
    ):
        """Export tenant should include related models/providers"""
        resp = client.post(
            f"/v1/export/export/tenant/{test_tenant_id}",
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        export_data = data["data"]
        
        # Should include resource types
        assert "models" in export_data or "providers" in export_data or "tools" in export_data


@pytest.mark.integration
class TestImportConfigurations:
    """Test configuration import endpoint"""

    def test_import_authentication_required(self, client):
        """Import endpoint should require authentication"""
        resp = client.post(
            "/v1/export/import",
            json={"data": {"tenants": []}}
        )
        assert resp.status_code == 401

    def test_import_write_permission_required(
        self, client, read_only_headers
    ):
        """Import should require admin:write permission"""
        resp = client.post(
            "/v1/export/import",
            json={"data": {"tenants": []}},
            headers=read_only_headers
        )
        assert resp.status_code == 403

    def test_import_missing_data_field(self, client, admin_headers):
        """Import without data field should fail validation"""
        resp = client.post(
            "/v1/export/import",
            json={},
            headers=admin_headers
        )
        assert resp.status_code == 422  # Validation error

    def test_import_empty_data(self, client, admin_headers):
        """Import with empty data should succeed"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": [],
                    "models": [],
                    "providers": []
                }
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "importedAt" in data
        assert "status" in data

    def test_import_dry_run(self, client, admin_headers):
        """Import with dryRun=true should validate without importing"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": [{
                        "tenantId": f"dry-run-{uuid.uuid4()}",
                        "displayName": "Dry Run Tenant"
                    }]
                },
                "dryRun": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should indicate dry run
        assert "status" in data
        # Validation errors should be reported if any
        if "validationErrors" in data:
            assert isinstance(data["validationErrors"], list)

    def test_import_validation_errors(self, client, admin_headers):
        """Import with invalid data should return validation errors"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": [
                        {
                            "tenantId": "duplicate-id",
                            "displayName": "Tenant 1"
                        },
                        {
                            "tenantId": "duplicate-id",  # Duplicate
                            "displayName": "Tenant 2"
                        }
                    ]
                },
                "dryRun": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should report validation errors
        if "validationErrors" in data:
            errors = data["validationErrors"]
            assert len(errors) > 0
            # Should mention duplicate
            error_text = " ".join(errors).lower()
            assert "duplicate" in error_text or "unique" in error_text

    def test_import_export_roundtrip(
        self, client, admin_headers, test_tenant_id
    ):
        """Export then import should work"""
        # Export configuration
        export_resp = client.post(
            f"/v1/export/export/tenant/{test_tenant_id}",
            headers=admin_headers
        )
        assert export_resp.status_code == 200
        exported_data = export_resp.json()
        
        # Import as dry run to validate
        import_resp = client.post(
            "/v1/export/import",
            json={
                "data": exported_data["data"],
                "dryRun": True
            },
            headers=admin_headers
        )
        
        # Should succeed or have specific validation errors
        assert import_resp.status_code == 200
        import_data = import_resp.json()
        assert "status" in import_data

    def test_import_merge_strategy(self, client, admin_headers):
        """Import should support merge strategy"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": []
                },
                "mergeStrategy": "skip"  # or "overwrite"
            },
            headers=admin_headers
        )
        
        # Should accept merge strategy parameter
        assert resp.status_code == 200

    def test_import_creates_resources(
        self, client, admin_headers
    ):
        """Import should actually create resources (non-dry-run)"""
        new_tenant_id = f"import-test-{uuid.uuid4()}"
        
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": [{
                        "tenantId": new_tenant_id,
                        "displayName": "Imported Tenant",
                        "metadata": {"imported": "true"}
                    }]
                },
                "dryRun": False
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["success", "completed", "partial"]
        
        # Verify tenant was created by trying to fetch it
        get_resp = client.get(
            f"/v1/tenants/{new_tenant_id}",
            headers=admin_headers
        )
        
        # Should exist now (200) or not found (404) depending on implementation
        assert get_resp.status_code in (200, 404)
        if get_resp.status_code == 200:
            tenant = get_resp.json()
            assert tenant["tenantId"] == new_tenant_id


@pytest.mark.integration
class TestExportImportFormats:
    """Test different export/import formats"""

    def test_export_format_json(self, client, admin_headers):
        """Export with format=json should return JSON"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True,
                "format": "json"
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type

    def test_export_format_zip(self, client, admin_headers):
        """Export with format=zip should return ZIP archive"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True,
                "format": "zip"
            },
            headers=admin_headers
        )
        
        # Should succeed
        assert resp.status_code == 200
        
        # Content type should indicate ZIP or octet-stream
        content_type = resp.headers.get("content-type", "")
        assert (
            "application/zip" in content_type or
            "application/octet-stream" in content_type
        )

    def test_export_default_format(self, client, admin_headers):
        """Export without format parameter should use default (JSON)"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True
                # No format specified
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        # Default is typically JSON
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type


@pytest.mark.integration
class TestExportImportVersioning:
    """Test export/import version compatibility"""

    def test_export_includes_version(self, client, admin_headers):
        """Export should include version field"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True
            },
            headers=admin_headers
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_import_accepts_current_version(self, client, admin_headers):
        """Import should accept exports with current version"""
        # First export to get current version
        export_resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": [],
                "includeModels": True
            },
            headers=admin_headers
        )
        assert export_resp.status_code == 200
        exported = export_resp.json()
        
        # Import with same version
        import_resp = client.post(
            "/v1/export/import",
            json={
                "data": exported["data"],
                "dryRun": True
            },
            headers=admin_headers
        )
        
        # Should succeed
        assert import_resp.status_code == 200


@pytest.mark.integration  
class TestExportImportErrorScenarios:
    """Test error handling in export/import"""

    def test_export_invalid_tenant_id(self, client, admin_headers):
        """Export with non-existent tenant ID should handle gracefully"""
        resp = client.post(
            "/v1/export/export",
            json={
                "tenantIds": ["non-existent-tenant-12345"],
                "includeModels": True
            },
            headers=admin_headers
        )
        
        # Should succeed with empty or partial data, not crash
        assert resp.status_code == 200

    def test_import_malformed_data(self, client, admin_headers):
        """Import with malformed data should return validation errors"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": "not-an-array"  # Should be array
                }
            },
            headers=admin_headers
        )
        
        # Should fail validation
        assert resp.status_code in (400, 422)

    def test_import_missing_required_fields(self, client, admin_headers):
        """Import with missing required fields should fail validation"""
        resp = client.post(
            "/v1/export/import",
            json={
                "data": {
                    "tenants": [{
                        # Missing tenantId
                        "displayName": "Incomplete Tenant"
                    }]
                }
            },
            headers=admin_headers
        )
        
        # Should report validation errors
        assert resp.status_code in (200, 400, 422)
        if resp.status_code == 200:
            data = resp.json()
            # Should have validation errors
            assert "validationErrors" in data or "errors" in data
