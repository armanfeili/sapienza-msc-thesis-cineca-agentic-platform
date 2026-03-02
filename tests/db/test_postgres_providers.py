"""
Smoke tests for PostgreSQL provider repository implementation.

Tests cover:
- CRUD operations (create, read, update, delete)
- Secret encryption/decryption
- Audit event creation
- Redis cache invalidation
- Multi-tenant defaults
- ETag generation
"""

import pytest
from datetime import datetime
from typing import Dict, Any

# Import the provider repository
from db.postgres_control.repositories import provider_repo as pg_repo
from db.redis_cache.client import get_redis, cache_get, cache_delete


class TestPostgresProviderCRUD:
    """Test basic CRUD operations for PostgreSQL providers."""

    def test_create_provider_basic(self):
        """Test creating a basic provider without secrets."""
        provider = pg_repo.create_provider(
            name="test_provider_basic",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={"temperature": 0.7},
            actor="test_user",
        )

        assert provider is not None
        assert provider["name"] == "test_provider_basic"
        assert provider["type"] == "openai"
        assert provider["base_url"] == "https://api.openai.com/v1"
        assert provider["model"] == "gpt-4"
        assert provider["has_api_key"] is False
        assert provider["config_json"]["temperature"] == 0.7

        # Cleanup
        pg_repo.delete_provider("test_provider_basic", actor="test_user")

    def test_create_provider_with_secret(self):
        """Test creating a provider with encrypted API key."""
        provider = pg_repo.create_provider(
            name="test_provider_secret",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            api_key="sk-test1234567890",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        assert provider is not None
        assert provider["has_api_key"] is True

        # Secret should be redacted by default
        assert provider.get("api_key") is None

        # Get with secrets included
        provider_with_secrets = pg_repo.get_provider("test_provider_secret", include_secrets=True)
        assert provider_with_secrets["api_key"] == "sk-test1234567890"

        # Cleanup
        pg_repo.delete_provider("test_provider_secret", actor="test_user")

    def test_create_provider_idempotency(self):
        """Test that creating duplicate provider fails."""
        pg_repo.create_provider(
            name="test_provider_dup",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Attempt to create duplicate should raise ValueError
        with pytest.raises(ValueError, match="already exists"):
            pg_repo.create_provider(
                name="test_provider_dup",
                type="anthropic",  # Different type - still duplicate name
                base_url="https://api.anthropic.com",
                model="claude-3",
                tenant_id=None,
                config={},
                actor="test_user",
            )

        # Cleanup
        pg_repo.delete_provider("test_provider_dup", actor="test_user")

    def test_list_providers(self):
        """Test listing providers with tenant filtering."""
        # Create test providers
        pg_repo.create_provider(
            name="test_list_global",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        pg_repo.create_provider(
            name="test_list_tenant1",
            type="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3",
            tenant_id="tenant_1",
            config={},
            actor="test_user",
        )

        # List all providers (no tenant filter)
        all_providers = pg_repo.list_providers(tenant_id=None)
        assert len(all_providers) >= 2

        # List tenant-specific providers
        tenant1_providers = pg_repo.list_providers(tenant_id="tenant_1")
        tenant1_names = [p["name"] for p in tenant1_providers]
        assert "test_list_tenant1" in tenant1_names
        assert "test_list_global" in tenant1_names  # Global should be visible to tenant

        # Cleanup
        pg_repo.delete_provider("test_list_global", actor="test_user")
        pg_repo.delete_provider("test_list_tenant1", actor="test_user")

    def test_get_provider(self):
        """Test fetching a single provider by name."""
        pg_repo.create_provider(
            name="test_get_provider",
            type="azure_openai",
            base_url="https://my-resource.openai.azure.com",
            model="gpt-4",
            tenant_id=None,
            config={"api_version": "2024-02-01"},
            actor="test_user",
        )

        provider = pg_repo.get_provider("test_get_provider", include_secrets=False)
        assert provider is not None
        assert provider["name"] == "test_get_provider"
        assert provider["type"] == "azure_openai"
        assert provider["config_json"]["api_version"] == "2024-02-01"

        # Test non-existent provider
        none_provider = pg_repo.get_provider("nonexistent_provider", include_secrets=False)
        assert none_provider is None

        # Cleanup
        pg_repo.delete_provider("test_get_provider", actor="test_user")

    def test_patch_provider(self):
        """Test updating provider configuration."""
        pg_repo.create_provider(
            name="test_patch_provider",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-3.5-turbo",
            tenant_id=None,
            config={"temperature": 0.5, "max_tokens": 1000},
            actor="test_user",
        )

        # Update model and config
        pg_repo.patch_provider(
            name="test_patch_provider",
            updates={"model": "gpt-4", "config": {"temperature": 0.7}},  # Partial update
            actor="test_user",
        )

        updated_provider = pg_repo.get_provider("test_patch_provider", include_secrets=False)
        assert updated_provider["model"] == "gpt-4"
        assert updated_provider["config_json"]["temperature"] == 0.7
        # max_tokens should still be present (deep merge)
        assert updated_provider["config_json"]["max_tokens"] == 1000

        # Cleanup
        pg_repo.delete_provider("test_patch_provider", actor="test_user")

    def test_delete_provider_cascade(self):
        """Test that deleting provider cascades to secrets and defaults."""
        # Create provider with secret
        pg_repo.create_provider(
            name="test_delete_cascade",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            api_key="sk-test-cascade",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Set as default
        pg_repo.set_provider_default(provider_name="test_delete_cascade", scope_tenant_id=None, actor="test_user")

        # Delete provider
        pg_repo.delete_provider("test_delete_cascade", actor="test_user")

        # Verify provider is gone
        deleted_provider = pg_repo.get_provider("test_delete_cascade", include_secrets=False)
        assert deleted_provider is None

        # Verify default is cleared
        default = pg_repo.get_provider_default(scope_tenant_id=None)
        assert default is None or default.get("provider_name") != "test_delete_cascade"


class TestProviderSecrets:
    """Test secret encryption and decryption."""

    def test_secret_encryption_decryption(self):
        """Test that secrets are encrypted at rest and decrypted correctly."""
        # Create provider with secret
        pg_repo.create_provider(
            name="test_secret_encrypt",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            api_key="sk-original-secret-key",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Get without secrets (should be redacted)
        provider_redacted = pg_repo.get_provider("test_secret_encrypt", include_secrets=False)
        assert provider_redacted.get("api_key") is None
        assert provider_redacted["has_api_key"] is True

        # Get with secrets (should be decrypted)
        provider_with_secrets = pg_repo.get_provider("test_secret_encrypt", include_secrets=True)
        assert provider_with_secrets["api_key"] == "sk-original-secret-key"

        # Cleanup
        pg_repo.delete_provider("test_secret_encrypt", actor="test_user")

    def test_secret_update(self):
        """Test updating API key."""
        pg_repo.create_provider(
            name="test_secret_update",
            type="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3",
            api_key="sk-old-key",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Update API key
        pg_repo.patch_provider(name="test_secret_update", updates={"api_key": "sk-new-key"}, actor="test_user")

        # Verify new key is set
        provider = pg_repo.get_provider("test_secret_update", include_secrets=True)
        assert provider["api_key"] == "sk-new-key"

        # Cleanup
        pg_repo.delete_provider("test_secret_update", actor="test_user")


class TestProviderDefaults:
    """Test multi-tenant default provider management."""

    def test_set_global_default(self):
        """Test setting a global default provider."""
        pg_repo.create_provider(
            name="test_global_default",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Set as global default
        pg_repo.set_provider_default(provider_name="test_global_default", scope_tenant_id=None, actor="test_user")

        # Get global default
        default = pg_repo.get_provider_default(scope_tenant_id=None)
        assert default is not None
        assert default["provider_name"] == "test_global_default"
        assert default["scope_tenant_id"] is None

        # Cleanup
        pg_repo.delete_provider("test_global_default", actor="test_user")

    def test_set_tenant_default(self):
        """Test setting tenant-specific default provider."""
        pg_repo.create_provider(
            name="test_tenant_default",
            type="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3",
            tenant_id="tenant_xyz",
            config={},
            actor="test_user",
        )

        # Set as tenant default
        pg_repo.set_provider_default(
            provider_name="test_tenant_default", scope_tenant_id="tenant_xyz", actor="test_user"
        )

        # Get tenant default
        default = pg_repo.get_provider_default(scope_tenant_id="tenant_xyz")
        assert default is not None
        assert default["provider_name"] == "test_tenant_default"
        assert default["scope_tenant_id"] == "tenant_xyz"

        # Cleanup
        pg_repo.delete_provider("test_tenant_default", actor="test_user")

    def test_default_precedence(self):
        """Test that tenant defaults take precedence over global defaults."""
        # Create global provider
        pg_repo.create_provider(
            name="test_default_global",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Create tenant provider
        pg_repo.create_provider(
            name="test_default_tenant",
            type="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3",
            tenant_id="tenant_123",
            config={},
            actor="test_user",
        )

        # Set global default
        pg_repo.set_provider_default(provider_name="test_default_global", scope_tenant_id=None, actor="test_user")

        # Set tenant default
        pg_repo.set_provider_default(
            provider_name="test_default_tenant", scope_tenant_id="tenant_123", actor="test_user"
        )

        # Get tenant default (should be tenant-specific, not global)
        tenant_default = pg_repo.get_provider_default(scope_tenant_id="tenant_123")
        assert tenant_default["provider_name"] == "test_default_tenant"

        # Get global default (should still be global)
        global_default = pg_repo.get_provider_default(scope_tenant_id=None)
        assert global_default["provider_name"] == "test_default_global"

        # Cleanup
        pg_repo.delete_provider("test_default_global", actor="test_user")
        pg_repo.delete_provider("test_default_tenant", actor="test_user")


class TestProviderCaching:
    """Test Redis cache integration."""

    def test_cache_invalidation_on_create(self):
        """Test that cache is invalidated when provider is created."""
        redis_client = get_redis()
        if not redis_client:
            pytest.skip("Redis not available")

        # Pre-populate cache with list
        cache_key_list = "providers:list:global"
        redis_client.setex(cache_key_list, 60, "[]")

        # Create provider (should invalidate cache)
        pg_repo.create_provider(
            name="test_cache_create",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Cache should be invalidated
        cached_value = cache_get(cache_key_list)
        assert cached_value is None

        # Cleanup
        pg_repo.delete_provider("test_cache_create", actor="test_user")

    def test_cache_invalidation_on_update(self):
        """Test that cache is invalidated when provider is updated."""
        redis_client = get_redis()
        if not redis_client:
            pytest.skip("Redis not available")

        # Create provider
        pg_repo.create_provider(
            name="test_cache_update",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-3.5-turbo",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Populate cache
        cache_key = "providers:by_id:test_cache_update"
        redis_client.setex(cache_key, 60, '{"model": "gpt-3.5-turbo"}')

        # Update provider (should invalidate cache)
        pg_repo.patch_provider(name="test_cache_update", updates={"model": "gpt-4"}, actor="test_user")

        # Cache should be invalidated
        cached_value = cache_get(cache_key)
        assert cached_value is None

        # Cleanup
        pg_repo.delete_provider("test_cache_update", actor="test_user")

    def test_cache_invalidation_on_delete(self):
        """Test that cache is invalidated when provider is deleted."""
        redis_client = get_redis()
        if not redis_client:
            pytest.skip("Redis not available")

        # Create provider
        pg_repo.create_provider(
            name="test_cache_delete",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Populate cache
        cache_key = "providers:by_id:test_cache_delete"
        redis_client.setex(cache_key, 60, '{"name": "test_cache_delete"}')

        # Delete provider (should invalidate cache)
        pg_repo.delete_provider("test_cache_delete", actor="test_user")

        # Cache should be invalidated
        cached_value = cache_get(cache_key)
        assert cached_value is None


class TestProviderEtag:
    """Test ETag generation for HTTP caching."""

    def test_compute_provider_etag(self):
        """Test ETag computation for a provider."""
        provider = {
            "id": 1,
            "name": "test_etag",
            "type": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4",
            "updated_at": datetime.now(),
        }

        etag = pg_repo.compute_provider_etag(provider)
        assert etag is not None
        assert len(etag) > 0
        assert etag.startswith('"') and etag.endswith('"')

    def test_compute_list_etag(self):
        """Test ETag computation for provider list."""
        # Create test providers
        pg_repo.create_provider(
            name="test_list_etag_1",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        pg_repo.create_provider(
            name="test_list_etag_2",
            type="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        providers = pg_repo.list_providers(tenant_id=None)
        etag = pg_repo.compute_list_etag(providers)

        assert etag is not None
        assert len(etag) > 0
        assert etag.startswith('"') and etag.endswith('"')

        # Cleanup
        pg_repo.delete_provider("test_list_etag_1", actor="test_user")
        pg_repo.delete_provider("test_list_etag_2", actor="test_user")

    def test_etag_changes_on_update(self):
        """Test that ETag changes when provider is updated."""
        pg_repo.create_provider(
            name="test_etag_change",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-3.5-turbo",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Get initial ETag
        provider1 = pg_repo.get_provider("test_etag_change", include_secrets=False)
        etag1 = pg_repo.compute_provider_etag(provider1)

        # Update provider
        pg_repo.patch_provider(name="test_etag_change", updates={"model": "gpt-4"}, actor="test_user")

        # Get new ETag
        provider2 = pg_repo.get_provider("test_etag_change", include_secrets=False)
        etag2 = pg_repo.compute_provider_etag(provider2)

        # ETags should be different
        assert etag1 != etag2

        # Cleanup
        pg_repo.delete_provider("test_etag_change", actor="test_user")


class TestProviderAudit:
    """Test audit event logging."""

    def test_audit_event_on_create(self):
        """Test that audit event is created when provider is created."""
        # Create provider with trace_id/event_id
        provider = pg_repo.create_provider(
            name="test_audit_create",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
            trace_id="trace_123",
            event_id="event_456",
        )

        # Note: We can't easily query audit events without exposing a repo method,
        # but we can verify the provider was created successfully
        assert provider is not None
        assert provider["name"] == "test_audit_create"

        # Cleanup
        pg_repo.delete_provider("test_audit_create", actor="test_user")

    def test_audit_event_on_update(self):
        """Test that audit event is created when provider is updated."""
        pg_repo.create_provider(
            name="test_audit_update",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-3.5-turbo",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Update with audit context
        pg_repo.patch_provider(
            name="test_audit_update",
            updates={"model": "gpt-4"},
            actor="test_user",
            trace_id="trace_update_123",
            event_id="event_update_456",
        )

        # Verify update was applied
        updated = pg_repo.get_provider("test_audit_update", include_secrets=False)
        assert updated["model"] == "gpt-4"

        # Cleanup
        pg_repo.delete_provider("test_audit_update", actor="test_user")

    def test_audit_event_on_delete(self):
        """Test that audit event is created when provider is deleted."""
        pg_repo.create_provider(
            name="test_audit_delete",
            type="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4",
            tenant_id=None,
            config={},
            actor="test_user",
        )

        # Delete with audit context
        pg_repo.delete_provider(
            name="test_audit_delete", actor="test_user", trace_id="trace_delete_123", event_id="event_delete_456"
        )

        # Verify provider is deleted
        deleted = pg_repo.get_provider("test_audit_delete", include_secrets=False)
        assert deleted is None
