"""
Configuration Integration Tests

Verifies platform defaults and configuration are properly set.
Tests default provider, model instance, and system settings.

Acceptance Checklist Item: #2
"""
import pytest


class TestDefaultConfiguration:
    """Test platform default configuration."""

    def test_default_provider_is_set(self, client, bearer_headers):
        """Platform should have a default LLM provider configured."""
        response = client.get("/v1/providers", headers=bearer_headers)
        assert response.status_code == 200

        providers = response.json()
        assert isinstance(providers, list), "Providers should be a list"

        # Find default provider
        default_providers = [p for p in providers if p.get("is_default")]

        assert len(default_providers) > 0, "No default provider set. At least one provider must be marked as default."

        assert (
            len(default_providers) == 1
        ), f"Multiple default providers found: {len(default_providers)}. Only one should be default."

        default_provider = default_providers[0]
        assert default_provider.get("name"), "Default provider must have a name"
        assert default_provider.get("type"), "Default provider must have a type"

    def test_default_model_instance_exists(self, client, bearer_headers):
        """Platform should have at least one enabled model instance."""
        response = client.get("/v1/model-instances", headers=bearer_headers)
        assert response.status_code == 200

        instances = response.json()
        assert isinstance(instances, list), "Model instances should be a list"

        # Find enabled instances
        enabled_instances = [i for i in instances if i.get("enabled")]

        assert len(enabled_instances) > 0, "No enabled model instances found. At least one instance must be enabled."

        # Verify first enabled instance has required fields
        instance = enabled_instances[0]
        assert instance.get("model_id"), "Model instance must have model_id"
        assert instance.get("provider_id"), "Model instance must have provider_id"
        assert instance.get("enabled") is True, "Model instance must be enabled"

    def test_default_model_instance_is_usable(self, client, bearer_headers):
        """Default model instance should be ready for agent runs."""
        response = client.get("/v1/model-instances", headers=bearer_headers)
        instances = response.json()

        enabled_instances = [i for i in instances if i.get("enabled")]
        assert len(enabled_instances) > 0

        instance = enabled_instances[0]

        # Should have deployment details or be ready to use
        assert instance.get("model_id"), "Instance must have model_id"

        # Should not have error fields
        assert "error" not in instance, "Instance should not have errors"
        assert instance.get("enabled") is True, "Instance must be enabled"
