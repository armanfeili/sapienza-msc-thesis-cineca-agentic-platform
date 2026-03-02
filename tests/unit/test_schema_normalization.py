"""
Test suite for schema normalization implementation.

This test verifies that all Pydantic models have been correctly moved from
routers to schemas, and that backward compatibility is maintained.

Tests cover:
1. Schema imports work correctly
2. Model validation and serialization
3. Backward compatibility (field aliases, type aliases)
4. Enum definitions
5. No BaseModel definitions remain in routers
"""

import inspect
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestSchemaImports:
    """Test that all schemas can be imported correctly."""

    def test_import_auth_schemas(self):
        """Test importing auth schemas."""
        from schemas.auth import UserInfo

        assert UserInfo is not None
        assert hasattr(UserInfo, "model_fields")

    def test_import_job_schemas(self):
        """Test importing job schemas."""
        from schemas.jobs import JobCreateRequest, JobResponse, JobListResponse

        assert JobCreateRequest is not None
        assert JobResponse is not None
        assert JobListResponse is not None

    def test_import_tool_schemas(self):
        """Test importing tool schemas."""
        from schemas.tools import (
            ToolInfo,
            ToolInvokeRequest,
            ToolInvokeResponse,
            ToolsListResponse,
        )

        assert ToolInfo is not None
        assert ToolInvokeRequest is not None
        assert ToolInvokeResponse is not None
        assert ToolsListResponse is not None

    def test_import_batch_schemas(self):
        """Test importing batch schemas."""
        from schemas.batch import (
            BatchOperation,
            BatchOperationResult,
            BatchRequest,
            BatchResponse,
        )

        assert BatchOperation is not None
        assert BatchRequest is not None
        assert BatchOperationResult is not None
        assert BatchResponse is not None

    def test_import_model_schemas(self):
        """Test importing all model management schemas."""
        from schemas.models import (
            ActionResponse,
            ChatRequest,
            CompletionRequest,
            CompletionResponse,
            EmbeddingRequest,
            EmbeddingResponse,
            EmbeddingVector,
            GetDefaultResponse,
            InstanceCreateRequest,
            InstanceDetail,
            ListInstancesResponse,
            LoadInstanceRequest,
            LoadInstanceResponse,
            Modality,
            ModelInfo,
            SetDefaultRequest,
            SetDefaultResponse,
            TestInstanceRequest,
            TestInstanceResponse,
            TestRequest,
            TestResponse,
            Usage,
        )

        # Verify all models are Pydantic BaseModel classes
        assert all(
            hasattr(model, "model_fields")
            for model in [
                ModelInfo,
                LoadInstanceRequest,
                LoadInstanceResponse,
                ListInstancesResponse,
                GetDefaultResponse,
                SetDefaultRequest,
                SetDefaultResponse,
                InstanceDetail,
                TestRequest,
                TestInstanceRequest,
                TestResponse,
                TestInstanceResponse,
                Usage,
                CompletionRequest,
                CompletionResponse,
                EmbeddingRequest,
                EmbeddingVector,
                EmbeddingResponse,
                ChatRequest,
                ActionResponse,
                InstanceCreateRequest,
            ]
        )

        # Verify Modality is an Enum
        from enum import Enum

        assert issubclass(Modality, Enum)
        assert hasattr(Modality, "TEXT")
        assert hasattr(Modality, "VISION")
        assert hasattr(Modality, "AUDIO")
        assert hasattr(Modality, "TOOL")

    def test_import_provider_schemas(self):
        """Test importing provider schemas."""
        from schemas.providers import (
            AuthConfig,
            Paths,
            ProviderConfig,
            RequestTemplates,
            ResponseExtract,
            TLSConfig,
            Timeouts,
        )

        assert all(
            hasattr(model, "model_fields")
            for model in [
                AuthConfig,
                Paths,
                ProviderConfig,
                RequestTemplates,
                ResponseExtract,
                TLSConfig,
                Timeouts,
            ]
        )

    def test_import_tenant_schemas(self):
        """Test importing tenant schemas."""
        from schemas.tenants import CreateTenantRequest, Tenant, UpdateTenantRequest

        assert Tenant is not None
        assert CreateTenantRequest is not None
        assert UpdateTenantRequest is not None


class TestModelValidation:
    """Test that models validate correctly."""

    def test_user_info_validation(self):
        """Test UserInfo model validation."""
        from schemas.auth import UserInfo

        # Valid UserInfo
        user = UserInfo(
            sub="user123",
            username="testuser",
            tenant_id="tenant1",
            scopes=["read", "write"],
            roles=["user"],
            permissions=["jobs:read"],
        )
        assert user.sub == "user123"
        assert user.username == "testuser"
        assert "read" in user.scopes

    def test_completion_request_validation(self):
        """Test CompletionRequest validation."""
        from schemas.models import CompletionRequest

        # Valid request
        req = CompletionRequest(prompt="Hello world", temperature=0.7, max_tokens=100)
        assert req.prompt == "Hello world"
        assert req.temperature == 0.7
        assert req.max_tokens == 100

        # Test defaults
        req_defaults = CompletionRequest(prompt="Test")
        assert req_defaults.temperature == 0.2
        assert req_defaults.max_tokens == 256

        # Test validation (temperature out of range)
        with pytest.raises(ValidationError):
            CompletionRequest(prompt="Test", temperature=3.0)  # > 2.0

    def test_usage_model(self):
        """Test Usage model."""
        from schemas.models import Usage

        usage = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

        # Test defaults
        usage_default = Usage()
        assert usage_default.prompt_tokens == 0
        assert usage_default.completion_tokens == 0
        assert usage_default.total_tokens == 0

    def test_model_info_validation(self):
        """Test ModelInfo validation."""
        from schemas.models import ModelInfo

        model = ModelInfo(
            name="gpt-4",
            provider="openai",
            context_window=8192,
            modalities=["text"],
            description="GPT-4 model",
        )
        assert model.name == "gpt-4"
        assert model.provider == "openai"
        assert model.enabled is True  # default
        assert model.default is False  # default

    def test_load_instance_request_validation(self):
        """Test LoadInstanceRequest validation."""
        from schemas.models import LoadInstanceRequest

        req = LoadInstanceRequest(
            provider_id="provider-uuid",
            instance_name="my-model",
            model_id="gpt-4",
            parameters={"temperature": 0.7},
            context_window=8192,
            modalities=["text", "vision"],
        )
        assert req.provider_id == "provider-uuid"
        assert req.instance_name == "my-model"
        assert req.model_id == "gpt-4"
        assert req.modalities == ["text", "vision"]

        # Test context_window constraint (ge=1024)
        with pytest.raises(ValidationError):
            LoadInstanceRequest(
                provider_id="provider-uuid",
                instance_name="my-model",
                model_id="gpt-4",
                context_window=512,  # < 1024
            )

    def test_modality_enum(self):
        """Test Modality enum values."""
        from schemas.models import Modality

        assert Modality.TEXT.value == "text"
        assert Modality.VISION.value == "vision"
        assert Modality.AUDIO.value == "audio"
        assert Modality.TOOL.value == "tool"

        # Test enum comparison
        assert Modality.TEXT == Modality.TEXT
        assert Modality.TEXT != Modality.VISION


class TestBackwardCompatibility:
    """Test backward compatibility features."""

    def test_job_owner_alias(self):
        """Test JobResponse owner_sub field accepts 'owner' alias on input."""
        from schemas.jobs import JobResponse

        # In Pydantic v2, alias="owner" means:
        # - Input JSON key: "owner"
        # - Model attribute: owner_sub
        # - Output JSON key: "owner_sub" (unless populate_by_name=True or serialization_alias set)

        # Test with input using alias 'owner'
        job_data = {
            "id": "job123",
            "type": "agent.run",
            "owner": "user456",  # Using INPUT alias
            "tenant_id": "tenant1",
            "status": "pending",
            "created_at": "2025-01-01T00:00:00Z",
            "priority": 0,
            "etag": "etag456",
        }
        job = JobResponse(**job_data)
        assert job.owner_sub == "user456"
        
        # Verify the model attribute is owner_sub
        assert hasattr(job, "owner_sub")
        
        # When serialized, uses the model field name by default
        serialized = job.model_dump()
        assert "owner_sub" in serialized or "owner" in serialized  # Depends on config

    def test_list_instances_response_aliases(self):
        """Test ListInstancesResponse backward-compatible aliases."""
        from schemas.models import ListInstancesResponse

        response = ListInstancesResponse(
            items=[{"id": "instance1", "name": "model1"}],
            total=1,
            etag="etag123",
            next_page_token=None,
        )

        # New fields
        assert response.items == [{"id": "instance1", "name": "model1"}]
        assert response.total == 1

        # Backward-compatible aliases
        assert response.instances == response.items
        assert response.count == response.total

    def test_set_default_request_forbids_extra(self):
        """Test SetDefaultRequest rejects extra fields."""
        from schemas.models import SetDefaultRequest

        # Valid request
        req = SetDefaultRequest(chat={"instance_id": "uuid123"})
        assert req.chat == {"instance_id": "uuid123"}

        # Should reject extra fields (model_config has extra="forbid")
        with pytest.raises(ValidationError):
            SetDefaultRequest(chat={"instance_id": "uuid123"}, invalid_field="value")


class TestModelSerialization:
    """Test model serialization (model_dump)."""

    def test_completion_response_serialization(self):
        """Test CompletionResponse can be serialized."""
        from schemas.models import CompletionResponse, Usage

        response = CompletionResponse(
            model="gpt-4",
            output="Hello, world!",
            usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
            latency_ms=150,
            trace_id="trace123",
            event_id="event456",
        )

        data = response.model_dump()
        assert data["model"] == "gpt-4"
        assert data["output"] == "Hello, world!"
        assert data["usage"]["prompt_tokens"] == 5
        assert data["latency_ms"] == 150

    def test_embedding_response_serialization(self):
        """Test EmbeddingResponse serialization."""
        from schemas.models import EmbeddingResponse, EmbeddingVector, Usage

        response = EmbeddingResponse(
            data=[
                EmbeddingVector(index=0, embedding=[0.1, 0.2, 0.3], model="text-embedding-ada-002")
            ],
            latency_ms=100,
            trace_id="trace789",
            event_id="event012",
            usage=Usage(prompt_tokens=10, completion_tokens=0, total_tokens=10),
        )

        data = response.model_dump()
        assert len(data["data"]) == 1
        assert data["data"][0]["embedding"] == [0.1, 0.2, 0.3]
        assert data["usage"]["prompt_tokens"] == 10


class TestRouterCleanup:
    """Test that routers no longer contain BaseModel definitions."""

    def test_no_basemodel_in_routers(self):
        """Verify no BaseModel classes defined in core router files."""
        import ast
        import os

        routers_path = Path(__file__).parent.parent.parent / "src" / "routers"
        
        # Core routers that MUST have been migrated to schemas
        core_routers = [
            "model_management.py",
            "model_instances.py",
            "models.py",
            "jobs.py",
            "admin_jobs.py",
            "tenants.py",
            "auth.py",
            "tools.py",
            "batch.py",
        ]

        basemodel_violations = []

        for router_name in core_routers:
            router_file = routers_path / router_name
            if not router_file.exists():
                continue

            with open(router_file, "r") as f:
                content = f.read()

            # Parse AST to find class definitions
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check if class inherits from BaseModel
                        for base in node.bases:
                            if isinstance(base, ast.Name) and base.id == "BaseModel":
                                basemodel_violations.append(
                                    f"{router_name}:{node.lineno} - class {node.name}(BaseModel)"
                                )
            except SyntaxError:
                # Skip files with syntax errors
                pass

        # Assert no violations found in core routers
        assert (
            len(basemodel_violations) == 0
        ), f"Found BaseModel definitions in core routers:\n" + "\n".join(basemodel_violations)

    def test_routers_import_from_schemas(self):
        """Verify routers import models from schemas."""
        import os

        routers_path = Path(__file__).parent.parent.parent / "src" / "routers"

        # Key routers that should import from schemas
        key_routers = [
            "model_management.py",
            "model_instances.py",
            "models.py",
            "jobs.py",
            "admin_jobs.py",
            "tenants.py",
            "auth.py",
            "tools.py",
            "batch.py",
        ]

        for router_file in key_routers:
            router_path = routers_path / router_file
            if not router_path.exists():
                continue

            with open(router_path, "r") as f:
                content = f.read()

            # Check for schema imports
            assert (
                "from schemas." in content
            ), f"{router_file} should import from schemas"


class TestSchemaPackage:
    """Test schemas package structure."""

    def test_schemas_init_exports(self):
        """Test schemas/__init__.py exports common models."""
        import schemas

        # Should have __all__ defined
        assert hasattr(schemas, "__all__")

        # Common exports should be available (verify a subset)
        expected_exports = [
            "JobCreateRequest",
            "JobResponse",
        ]

        for export in expected_exports:
            assert (
                export in schemas.__all__
            ), f"{export} should be in schemas.__all__"
            
        # Verify models can still be imported directly from submodules
        from schemas.auth import UserInfo
        from schemas.tools import ToolInfo
        from schemas.batch import BatchRequest
        
        assert UserInfo is not None
        assert ToolInfo is not None
        assert BatchRequest is not None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_usage(self):
        """Test Usage model with defaults."""
        from schemas.models import Usage

        usage = Usage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_optional_fields(self):
        """Test models with optional fields."""
        from schemas.models import ModelInfo

        # Minimal ModelInfo
        model = ModelInfo(name="test-model")
        assert model.name == "test-model"
        assert model.provider is None
        assert model.context_window is None
        assert model.modalities == ["text"]  # default factory

    def test_embedding_request_minimal(self):
        """Test EmbeddingRequest with minimal data."""
        from schemas.models import EmbeddingRequest

        req = EmbeddingRequest(input="Hello world")
        assert req.input == "Hello world"
        assert req.model is None

    def test_chat_request_validation(self):
        """Test ChatRequest validation."""
        from schemas.models import ChatRequest

        req = ChatRequest(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
        )
        assert len(req.messages) == 2
        assert req.model is None  # optional

    def test_action_response(self):
        """Test ActionResponse model."""
        from schemas.models import ActionResponse

        response = ActionResponse(
            ok=True,
            message="Operation successful",
            trace_id="trace123",
            event_id="event456",
        )
        assert response.ok is True
        assert response.message == "Operation successful"
        assert response.details == {}  # default factory


class TestProductionScenarios:
    """Test production-level scenarios."""

    def test_load_instance_with_all_fields(self):
        """Test LoadInstanceRequest with all fields populated."""
        from schemas.models import LoadInstanceRequest

        req = LoadInstanceRequest(
            provider_id="provider-uuid-123",
            instance_name="production-gpt4",
            model_id="gpt-4-turbo",
            model_uri="https://api.openai.com/v1/models/gpt-4-turbo",
            tenant_id="tenant-production",
            parameters={
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 1.0,
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            },
            context_window=128000,
            modalities=["text", "vision"],
            description="Production GPT-4 Turbo instance with multimodal support",
        )

        # Serialize and deserialize
        data = req.model_dump()
        req_restored = LoadInstanceRequest(**data)

        assert req_restored.provider_id == req.provider_id
        assert req_restored.instance_name == req.instance_name
        assert req_restored.parameters == req.parameters
        assert req_restored.context_window == req.context_window

    def test_test_response_with_full_data(self):
        """Test TestResponse with complete data."""
        from schemas.models import TestResponse, Usage

        response = TestResponse(
            model="llama3.2:3b-instruct",
            output="Quantum computing uses quantum mechanics to perform calculations.",
            usage=Usage(prompt_tokens=15, completion_tokens=12, total_tokens=27),
            trace_id="trace-abc123",
            event_id="event-def456",
            provider="ollama-local",
            provider_base_url="http://ollama:11434",
            latency_ms=1234.5,
            parameters={"temperature": 0.0, "max_tokens": 32},
        )

        assert response.model == "llama3.2:3b-instruct"
        assert response.usage.total_tokens == 27
        assert response.provider == "ollama-local"
        assert response.latency_ms == 1234.5

    def test_instance_detail_complete(self):
        """Test InstanceDetail with all metadata."""
        from schemas.models import InstanceDetail

        detail = InstanceDetail(
            id="instance-uuid-789",
            instance_name="gpt-4o-production",
            provider_id="provider-uuid-456",
            model_id="gpt-4o",
            model_uri=None,
            tenant_id=None,  # Global instance
            parameters={"temperature": 0.7, "max_tokens": 4096},
            context_window=128000,
            modalities=["text", "vision", "audio"],
            description="GPT-4 Omni for production workloads",
            enabled=True,
            loaded=True,
            created_at="2025-01-15T10:30:00Z",
            updated_at="2025-01-15T10:30:00Z",
            created_by="admin@example.com",
        )

        data = detail.model_dump()
        assert data["id"] == "instance-uuid-789"
        assert data["context_window"] == 128000
        assert len(data["modalities"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
