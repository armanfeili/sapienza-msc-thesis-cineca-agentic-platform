"""
LLM Model Configuration Dataclass

Provides type-safe configuration for LLM models loaded from the database.
Step B.5: Replace dict usage with frozen dataclass for immutability and type safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LLMModelConfig:
    """
    Immutable configuration for an LLM model instance.
    
    This dataclass represents the complete configuration for an LLM model
    as retrieved from the database (model_defaults + model_instances + providers).
    
    Attributes:
        instance_id: Primary key for the model instance row
        instance_name: Human-readable name for the model instance (e.g., "phi3-mini")
        provider_model_id: Provider-specific model identifier (e.g., "phi3:mini" for Ollama)
        base_url: Provider API endpoint (e.g., "http://ollama:11434/v1")
        provider_name: Name of the provider (e.g., "Local Ollama", "OpenAI")
        provider_id: Database ID of the provider
        source: Configuration source (always "db_default" for DB-driven config)
    
    Example:
        >>> config = LLMModelConfig(
        ...     instance_id="b0b1c3de-1234-5678-9123-abcdef012345",
        ...     instance_name="phi3-mini",
        ...     provider_model_id="phi3:mini",
        ...     base_url="http://ollama:11434/v1",
        ...     provider_name="Local Ollama",
        ...     provider_id="ollama-local",
        ...     source="db_default"
        ... )
        >>> config.instance_name
        'phi3-mini'
    """
    
    instance_name: str
    provider_model_id: str
    base_url: str
    provider_name: str
    provider_id: str
    instance_id: str | None = None
    source: Literal["db_default"] = "db_default"
    
    def to_dict(self) -> dict[str, str]:
        """
        Convert to dictionary format for backward compatibility.
        
        Returns:
            Dictionary with all configuration fields
        """
        return {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "model_id": self.provider_model_id,  # Alias for backward compatibility
            "provider_model_id": self.provider_model_id,
            "base_url": self.base_url,
            "provider_name": self.provider_name,
            "provider_id": self.provider_id,
            "config_source": self.source,  # Alias for backward compatibility
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> LLMModelConfig:
        """
        Create LLMModelConfig from dictionary (typically from DB query result).
        
        Args:
            data: Dictionary with model configuration fields
                  Expected keys: instance_name, model_id (or provider_model_id),
                  base_url, provider_name, provider_id
        
        Returns:
            LLMModelConfig instance
        
        Raises:
            KeyError: If required fields are missing
            ValueError: If data types are invalid
        
        Example:
            >>> db_row = {
            ...     "instance_name": "phi3-mini",
            ...     "model_id": "phi3:mini",
            ...     "base_url": "http://ollama:11434/v1",
            ...     "provider_name": "Local Ollama",
            ...     "provider_id": "ollama-local"
            ... }
            >>> config = LLMModelConfig.from_dict(db_row)
        """
        # Support both 'model_id' (legacy) and 'provider_model_id' (new)
        provider_model_id = data.get("provider_model_id") or data.get("model_id")
        
        if not provider_model_id:
            raise ValueError("Missing 'model_id' or 'provider_model_id' in data")
        
        return cls(
            instance_id=data.get("instance_id"),
            instance_name=data["instance_name"],
            provider_model_id=provider_model_id,
            base_url=data["base_url"],
            provider_name=data["provider_name"],
            provider_id=data["provider_id"],
            source="db_default"
        )
    
    def __repr__(self) -> str:
        """String representation for logging and debugging."""
        return (
            f"LLMModelConfig(instance_id={self.instance_id}, instance={self.instance_name}, "
            f"model={self.provider_model_id}, "
            f"provider={self.provider_name}, "
            f"base_url={self.base_url})"
        )
