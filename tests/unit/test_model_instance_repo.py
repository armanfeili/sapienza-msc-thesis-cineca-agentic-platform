"""
Unit tests for model_instance_repo.get_default().

Tests cover:
- Returns correct LLMModelConfig when default exists
- Raises ValueError when multiple defaults exist (single-default invariant)
- Returns None when no default exists
- Handles tenant_id NULL correctly
- Handles scope correctly (global vs tenant)

Note: Uses real database models with SQLite for isolated testing.
"""

from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Mock psycopg2 before any imports that depend on it
sys.modules["psycopg2"] = Mock()
sys.modules["psycopg2.extras"] = Mock()

from db.postgres_control.database import Base
from db.postgres_control.models.model_instance import ModelDefault, ModelInstance
from db.postgres_control.models.provider import Provider
from src.models.llm_config import LLMModelConfig


# Patch UUID to String for SQLite compatibility
def patch_uuid_columns_for_sqlite():
    """Replace PostgreSQL-specific types and constraints for SQLite compatibility."""
    from sqlalchemy import String, Text
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
    
    for table in Base.metadata.tables.values():
        # Remove PostgreSQL-specific CHECK constraints
        if hasattr(table, '__table_args__'):
            # Filter out check constraints that use PostgreSQL functions
            if isinstance(table.__table_args__, tuple):
                new_args = []
                for arg in table.__table_args__:
                    if hasattr(arg, 'sqltext'):
                        # Skip constraints with PostgreSQL-specific functions
                        constraint_text = str(arg.sqltext)
                        if 'char_length' not in constraint_text.lower() and 'gen_random_uuid' not in constraint_text.lower():
                            new_args.append(arg)
                    else:
                        new_args.append(arg)
                # Update the table args
                if new_args:
                    table.__table_args__ = tuple(new_args)
        
        # Patch column types
        for column in table.columns:
            # Handle UUID columns
            if hasattr(column.type, '__class__'):
                type_name = column.type.__class__.__name__
                if type_name == 'UUID' or isinstance(column.type, PG_UUID):
                    column.type = String(36)
                # Handle JSONB columns  
                elif type_name == 'JSONB' or isinstance(column.type, JSONB):
                    column.type = Text()
            
            # Remove PostgreSQL-specific server defaults
            if column.server_default:
                default_text = str(column.server_default.arg) if hasattr(column.server_default, 'arg') else str(column.server_default)
                # Remove PostgreSQL casts (::jsonb, ::uuid, etc.) and functions (gen_random_uuid())
                if '::' in default_text or 'gen_random_uuid' in default_text or 'now()' in default_text:
                    column.server_default = None


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database with patched schema for testing."""
    # Patch UUID/JSONB columns before creating tables
    patch_uuid_columns_for_sqlite()
    
    engine = create_engine("sqlite:///:memory:")
    
    # Only create the tables we need for testing (avoid PostgreSQL-specific constraints in other tables)
    tables_to_create = [
        Base.metadata.tables['providers'],
        Base.metadata.tables['model_instances'],
        Base.metadata.tables['model_defaults'],
    ]
    
    for table in tables_to_create:
        table.create(engine, checkfirst=True)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()
    for table in reversed(tables_to_create):
        table.drop(engine, checkfirst=True)


@pytest.fixture
def sample_provider(db_session):
    """Create a sample provider for testing."""
    provider = Provider(
        id=str(uuid4()),
        name="Test Provider",
        type="openai_compatible",  # Required field
        base_url="http://test-ollama:11434/v1",  # Provider's base URL
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(provider)
    db_session.commit()
    return provider


@pytest.fixture
def sample_instance(db_session, sample_provider):
    """Create a sample model instance for testing."""
    instance = ModelInstance(
        id=str(uuid4()),
        provider_id=sample_provider.id,
        instance_name="test-model",
        model_id="phi3:mini",
        model_uri="http://test-ollama:11434/v1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        etag="test-etag-instance",
    )
    db_session.add(instance)
    db_session.commit()
    return instance


class TestGetDefault:
    """Test suite for model_instance_repo.get_default()."""
    
    def test_returns_config_when_default_exists(self, db_session, sample_instance):
        """Test that get_default() returns LLMModelConfig when a default exists."""
        # Arrange: Create default with scope=global, tenant_id=NULL
        default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=sample_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-1",
        )
        db_session.add(default)
        db_session.commit()
        
        # Act: Get default with mocked get_db
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
        
        # Assert: Returns LLMModelConfig with correct values
        assert result is not None
        assert isinstance(result, LLMModelConfig)
        assert result.instance_id == sample_instance.id
        assert result.instance_name == "test-model"
        assert result.provider_model_id == "phi3:mini"
        assert result.base_url == "http://test-ollama:11434/v1"
        assert result.provider_name == "Test Provider"
        assert result.source == "db_default"
    
    def test_raises_error_when_multiple_defaults_exist(self, db_session, sample_instance):
        """Test that get_default() raises ValueError when multiple defaults exist."""
        # Arrange: Create two defaults for same scope (violates invariant)
        default1 = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=sample_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-1",
        )
        
        # Create second instance for second default
        instance2 = ModelInstance(
            id=str(uuid4()),
            provider_id=sample_instance.provider_id,
            instance_name="test-model-2",
            model_id="phi3:latest",
            model_uri="http://test-ollama:11434/v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-inst2",
        )
        db_session.add(instance2)
        db_session.commit()
        
        default2 = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=instance2.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-2",
        )
        
        db_session.add_all([default1, default2])
        db_session.commit()
        
        # Act & Assert: Should raise ValueError
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            
            with pytest.raises(ValueError) as exc_info:
                model_instance_repo.get_default(scope="global", tenant_id=None)
            
            # Verify error message contains useful info
            error_msg = str(exc_info.value)
            assert "Multiple default models" in error_msg
            assert "scope='global'" in error_msg
            assert "tenant_id='None'" in error_msg
            assert "Found 2 defaults" in error_msg
    
    def test_returns_none_when_no_default_exists(self, db_session):
        """Test that get_default() returns None when no default exists."""
        # Arrange: No defaults in database
        
        # Act: Get default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
        
        # Assert: Returns None
        assert result is None
    
    def test_handles_tenant_id_null_correctly(self, db_session, sample_instance):
        """Test that get_default() correctly handles tenant_id=NULL vs specific tenant."""
        # Arrange: Create global default (scope=global, tenant_id=NULL)
        global_default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=sample_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-global",
        )
        db_session.add(global_default)
        
        # Create tenant-specific instance and default
        tenant_instance = ModelInstance(
            id=str(uuid4()),
            provider_id=sample_instance.provider_id,
            instance_name="tenant-model",
            model_id="phi3:14b",
            model_uri="http://test-ollama:11434/v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-tenant-inst",
        )
        db_session.add(tenant_instance)
        db_session.commit()
        
        tenant_default = ModelDefault(
            scope="tenant",
            tenant_id="test-tenant",
            instance_id=tenant_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-tenant",
        )
        db_session.add(tenant_default)
        db_session.commit()
        
        # Act & Assert: Get global default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            
            global_result = model_instance_repo.get_default(scope="global", tenant_id=None)
            assert global_result is not None
            assert global_result.instance_name == "test-model"
        
        # Act & Assert: Get tenant default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            tenant_result = model_instance_repo.get_default(scope="tenant", tenant_id="test-tenant")
            assert tenant_result is not None
            assert tenant_result.instance_name == "tenant-model"
        
        # Act & Assert: Non-existent tenant returns None
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            nonexistent_result = model_instance_repo.get_default(scope="tenant", tenant_id="nonexistent")
            assert nonexistent_result is None
    
    def test_returns_none_when_provider_missing(self, db_session):
        """Test that get_default() returns None when provider is missing."""
        # Arrange: Create instance without provider (orphaned)
        orphaned_instance = ModelInstance(
            id=str(uuid4()),
            provider_id=str(uuid4()),  # Non-existent provider
            instance_name="orphaned-model",
            model_id="orphaned:model",
            model_uri="http://test-ollama:11434/v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-orphaned-inst",
        )
        db_session.add(orphaned_instance)
        db_session.commit()
        
        default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=orphaned_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-orphaned",
        )
        db_session.add(default)
        db_session.commit()
        
        # Act: Get default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
        
        # Assert: Returns None (logged warning internally)
        assert result is None
    
    def test_returns_none_when_instance_missing(self, db_session):
        """Test that get_default() returns None when instance is missing."""
        # Arrange: Create default pointing to nonexistent instance
        default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=str(uuid4()),  # Non-existent instance
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-missing",
        )
        db_session.add(default)
        db_session.commit()
        
        # Act: Get default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
        
        # Assert: Returns None
        assert result is None
    
    def test_config_immutability(self, db_session, sample_instance):
        """Test that returned LLMModelConfig is immutable (frozen dataclass)."""
        # Arrange: Create default
        default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=sample_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-immut",
        )
        db_session.add(default)
        db_session.commit()
        
        # Act: Get default
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
        
        # Assert: Cannot modify frozen dataclass
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            result.instance_name = "modified"
    
    def test_config_to_dict_compatibility(self, db_session, sample_instance):
        """Test that LLMModelConfig.to_dict() maintains backward compatibility."""
        # Arrange: Create default
        default = ModelDefault(
            scope="global",
            tenant_id=None,
            instance_id=sample_instance.id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            etag="test-etag-dict",
        )
        db_session.add(default)
        db_session.commit()
        
        # Act: Get default and convert to dict
        with patch("db.postgres_control.repositories.model_instance_repo.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db_session])
            
            from db.postgres_control.repositories import model_instance_repo
            result = model_instance_repo.get_default(scope="global", tenant_id=None)
            result_dict = result.to_dict()
        
        # Assert: Dict contains expected keys for backward compatibility
        assert "instance_id" in result_dict
        assert "instance_name" in result_dict
        assert "model_id" in result_dict  # Backward compatibility alias
        assert "provider_model_id" in result_dict
        assert "base_url" in result_dict
        assert "provider_name" in result_dict
        assert "provider_id" in result_dict
        assert "config_source" in result_dict  # Backward compatibility alias
        assert "source" in result_dict
        
        # Verify values
        assert result_dict["instance_id"] == sample_instance.id
        assert result_dict["instance_name"] == "test-model"
        assert result_dict["model_id"] == "phi3:mini"
        assert result_dict["provider_model_id"] == "phi3:mini"
        assert result_dict["config_source"] == "db_default"
        assert result_dict["source"] == "db_default"


class TestLLMModelConfigDataclass:
    """Test suite for LLMModelConfig dataclass functionality."""
    
    def test_from_dict_creation(self):
        """Test creating LLMModelConfig from dictionary."""
        # Arrange: Dictionary from DB query
        data = {
            "instance_id": "inst-123",
            "instance_name": "phi3-mini",
            "model_id": "phi3:mini",
            "base_url": "http://ollama:11434/v1",
            "provider_name": "Local Ollama",
            "provider_id": "ollama-local",
        }
        
        # Act: Create from dict
        config = LLMModelConfig.from_dict(data)
        
        # Assert: Correct values
        assert config.instance_name == "phi3-mini"
        assert config.provider_model_id == "phi3:mini"
        assert config.base_url == "http://ollama:11434/v1"
        assert config.provider_name == "Local Ollama"
        assert config.provider_id == "ollama-local"
        assert config.instance_id == "inst-123"
        assert config.source == "db_default"
    
    def test_from_dict_supports_provider_model_id(self):
        """Test from_dict() supports both 'model_id' and 'provider_model_id' keys."""
        # Test with provider_model_id (new)
        data1 = {
            "instance_id": "test-instance",
            "instance_name": "test",
            "provider_model_id": "test:model",
            "base_url": "http://test:11434/v1",
            "provider_name": "Test",
            "provider_id": "test-id",
        }
        config1 = LLMModelConfig.from_dict(data1)
        assert config1.provider_model_id == "test:model"
        
        # Test with model_id (legacy)
        data2 = {
            "instance_name": "test",
            "model_id": "test:model",
            "base_url": "http://test:11434/v1",
            "provider_name": "Test",
            "provider_id": "test-id",
        }
        config2 = LLMModelConfig.from_dict(data2)
        assert config2.provider_model_id == "test:model"
    
    def test_from_dict_raises_on_missing_model_id(self):
        """Test from_dict() raises ValueError when both model_id keys missing."""
        data = {
            "instance_name": "test",
            # Missing both model_id and provider_model_id
            "base_url": "http://test:11434/v1",
            "provider_name": "Test",
            "provider_id": "test-id",
        }
        
        with pytest.raises(ValueError) as exc_info:
            LLMModelConfig.from_dict(data)
        
        assert "Missing 'model_id' or 'provider_model_id'" in str(exc_info.value)
    
    def test_repr_output(self):
        """Test __repr__() produces readable output for logging."""
        config = LLMModelConfig(
            instance_id="repr-instance",
            instance_name="phi3-mini",
            provider_model_id="phi3:mini",
            base_url="http://ollama:11434/v1",
            provider_name="Local Ollama",
            provider_id="ollama-local",
        )
        
        repr_str = repr(config)
        assert "LLMModelConfig" in repr_str
        assert "instance_id=repr-instance" in repr_str
        assert "instance=phi3-mini" in repr_str
        assert "model=phi3:mini" in repr_str
        assert "provider=Local Ollama" in repr_str
        assert "base_url=http://ollama:11434/v1" in repr_str
