#!/usr/bin/env python3
"""Quick test to verify malformed data validation"""

import asyncio
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.routers.export_import import _validate_import_data_dict

async def test_validation():
    # Test 1: Valid data (all arrays)
    valid_data = {
        "tenants": [],
        "providers": [],
        "models": [],
        "tools": [],
        "agents": []
    }
    errors = await _validate_import_data_dict(valid_data)
    assert len(errors) == 0, f"Valid data should not have errors, got: {errors}"
    print("✓ Test 1: Valid data passes")
    
    # Test 2: Malformed tenants (string instead of array)
    malformed_data = {
        "tenants": "not-an-array"
    }
    errors = await _validate_import_data_dict(malformed_data)
    assert len(errors) > 0, "Malformed data should have errors"
    assert any("tenants must be an array" in e for e in errors), f"Expected tenants error, got: {errors}"
    print("✓ Test 2: Malformed tenants detected")
    
    # Test 3: Malformed providers (number instead of array)
    malformed_data = {
        "providers": 123
    }
    errors = await _validate_import_data_dict(malformed_data)
    assert len(errors) > 0, "Malformed data should have errors"
    assert any("providers must be an array" in e for e in errors), f"Expected providers error, got: {errors}"
    print("✓ Test 3: Malformed providers detected")
    
    # Test 4: Duplicate tenant IDs
    malformed_data = {
        "tenants": [
            {"tenantId": "tenant1"},
            {"tenantId": "tenant1"}
        ]
    }
    errors = await _validate_import_data_dict(malformed_data)
    assert len(errors) > 0, "Duplicate tenant IDs should be detected"
    assert any("Duplicate" in e for e in errors), f"Expected duplicate error, got: {errors}"
    print("✓ Test 4: Duplicate tenant IDs detected")
    
    print("\n✅ All validation tests passed!")

if __name__ == "__main__":
    asyncio.run(test_validation())
