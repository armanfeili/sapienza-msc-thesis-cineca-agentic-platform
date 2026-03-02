"""
Test for Issue #9: Tenant ID Sometimes Missing

Ensures that:
1. tenant_id must be non-empty string
2. Empty string tenant_id rejected
3. Whitespace-only tenant_id rejected
4. Valid tenant_id accepted
"""

import pytest
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError


def test_valid_tenant_id():
    """Test that valid tenant_id is accepted."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "tenant-123",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    }
    
    response = RunResponse(**data)
    assert response.tenant_id == "tenant-123"


def test_empty_string_tenant_id_rejected():
    """Test that empty string tenant_id is rejected."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "",  # Empty string
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    }
    
    with pytest.raises(ValidationError) as exc_info:
        RunResponse(**data)
    
    assert "tenant_id must be non-empty" in str(exc_info.value)


def test_whitespace_only_tenant_id_rejected():
    """Test that whitespace-only tenant_id is rejected."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "   ",  # Whitespace only
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    }
    
    with pytest.raises(ValidationError) as exc_info:
        RunResponse(**data)
    
    assert "tenant_id must be non-empty" in str(exc_info.value)


def test_tenant_id_with_spaces_accepted():
    """Test that tenant_id with valid spaces is accepted."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "tenant 123",  # Valid with space
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    }
    
    response = RunResponse(**data)
    assert response.tenant_id == "tenant 123"


def test_tenant_id_special_chars():
    """Test that tenant_id with special characters is accepted."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "tenant-123_test@org",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
    }
    
    response = RunResponse(**data)
    assert response.tenant_id == "tenant-123_test@org"
