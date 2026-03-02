"""
Test for Issue #2: Model Name Format Inconsistency

Ensures that:
1. Ollama model names are normalized to colon format
2. phi3-mini becomes phi3:mini
3. llama3-8b becomes llama3:8b
4. OpenAI model names (gpt-4) stay unchanged
5. Normalization is idempotent (phi3:mini stays phi3:mini)
"""

import pytest
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4


def test_normalize_phi3_mini():
    """Test that phi3-mini is normalized to phi3:mini."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "phi3-mini",  # Kebab-case input
    }
    
    response = RunResponse(**data)
    assert response.model == "phi3:mini"  # Colon-separated output


def test_normalize_llama3_8b():
    """Test that llama3-8b is normalized to llama3:8b."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "llama3-8b",
    }
    
    response = RunResponse(**data)
    assert response.model == "llama3:8b"


def test_normalize_mistral():
    """Test that mistral-7b is normalized to mistral:7b."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "mistral-7b",
    }
    
    response = RunResponse(**data)
    assert response.model == "mistral:7b"


def test_openai_models_unchanged():
    """Test that OpenAI model names (gpt-4) are not normalized."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "gpt-4",  # OpenAI model stays as-is
    }
    
    response = RunResponse(**data)
    assert response.model == "gpt-4"  # Unchanged


def test_normalization_idempotent():
    """Test that already-normalized model names stay unchanged."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "phi3:mini",  # Already colon-separated
    }
    
    response = RunResponse(**data)
    assert response.model == "phi3:mini"  # Stays the same


def test_null_model_unchanged():
    """Test that null model is handled gracefully."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "model": None,  # Null model
    }
    
    response = RunResponse(**data)
    assert response.model is None


def test_multiple_dashes_only_first_replaced():
    """Test that only the first dash is replaced for Ollama models."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "phi3-mini-instruct",  # Multiple dashes
    }
    
    response = RunResponse(**data)
    assert response.model == "phi3:mini-instruct"  # Only first dash replaced


def test_unknown_model_unchanged():
    """Test that unknown model formats are unchanged."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "model": "custom-model-v1",  # Unknown format
    }
    
    response = RunResponse(**data)
    assert response.model == "custom-model-v1"  # Unchanged
