"""
JSON serialization utilities for database persistence.

Ensures all data stored in JSONB columns is fully JSON-serializable.
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


def to_jsonable(obj: Any) -> Any:
    """
    Convert an object to a JSON-serializable form.
    
    Handles common non-serializable types:
    - datetime/date -> ISO format string
    - UUID -> string
    - Decimal -> float
    - Enum -> value
    - set -> list
    - Path -> string
    
    Recursively processes dicts and lists.
    
    Args:
        obj: Object to convert
        
    Returns:
        JSON-serializable version of obj
    """
    # Handle None and primitives
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    
    # Handle datetime/date
    if isinstance(obj, datetime):
        # Normalize to RFC3339 with Z suffix (UTC)
        if obj.tzinfo is None:
            # Assume UTC if naive
            obj = obj.replace(tzinfo=__import__('datetime').timezone.utc)
        # Convert to UTC and format with Z
        utc_dt = obj.astimezone(__import__('datetime').timezone.utc)
        return utc_dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    if isinstance(obj, date):
        return obj.isoformat()
    
    # Handle UUID
    if isinstance(obj, UUID):
        return str(obj)
    
    # Handle Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    
    # Handle Enum
    if isinstance(obj, Enum):
        return obj.value
    
    # Handle Path
    if isinstance(obj, Path):
        return str(obj)
    
    # Handle set
    if isinstance(obj, set):
        return [to_jsonable(item) for item in obj]
    
    # Handle dict
    if isinstance(obj, dict):
        return {key: to_jsonable(value) for key, value in obj.items()}
    
    # Handle list/tuple
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    
    # Handle objects with __dict__
    if hasattr(obj, "__dict__"):
        return to_jsonable(obj.__dict__)
    
    # Fallback: convert to string
    return str(obj)
