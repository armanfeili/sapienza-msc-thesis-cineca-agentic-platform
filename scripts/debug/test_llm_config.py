#!/usr/bin/env python3
"""
Test script to verify LLM configuration knobs (LLM_DEVICE, LLM_MAX_TOKENS, LLM_MAX_STEPS)

Usage:
    python scripts/debug/test_llm_config.py
    
    # Or with environment overrides:
    LLM_DEVICE=gpu LLM_MAX_TOKENS=1024 LLM_MAX_STEPS=5 python scripts/debug/test_llm_config.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.config import settings

def test_llm_config():
    """Test that LLM configuration is properly loaded from environment"""
    
    print("=" * 80)
    print("LLM CONFIGURATION TEST")
    print("=" * 80)
    print()
    
    # Test 1: Check config values
    print("✅ Configuration Values:")
    print(f"   LLM_DEVICE:      {settings.LLM_DEVICE}")
    print(f"   LLM_MAX_TOKENS:  {settings.LLM_MAX_TOKENS}")
    print(f"   LLM_MAX_STEPS:   {settings.LLM_MAX_STEPS}")
    print()
    
    # Test 2: Verify defaults are correct
    expected_defaults = {
        "LLM_DEVICE": "cpu",
        "LLM_MAX_TOKENS": 2048,
        "LLM_MAX_STEPS": 10
    }
    
    # If environment variables are set, use those as expected values
    if "LLM_DEVICE" in os.environ:
        expected_defaults["LLM_DEVICE"] = os.environ["LLM_DEVICE"]
    if "LLM_MAX_TOKENS" in os.environ:
        expected_defaults["LLM_MAX_TOKENS"] = int(os.environ["LLM_MAX_TOKENS"])
    if "LLM_MAX_STEPS" in os.environ:
        expected_defaults["LLM_MAX_STEPS"] = int(os.environ["LLM_MAX_STEPS"])
    
    all_correct = True
    for key, expected_value in expected_defaults.items():
        actual_value = getattr(settings, key)
        if actual_value == expected_value:
            print(f"✅ {key}: {actual_value} (correct)")
        else:
            print(f"❌ {key}: {actual_value} (expected: {expected_value})")
            all_correct = False
    
    print()
    
    # Test 3: Test orchestrator integration (if available)
    print("✅ Orchestrator Integration:")
    try:
        from src.services.orchestrator import Orchestrator
        
        # Don't actually call from_env() as it requires DB/Redis/etc.
        # Just test direct instantiation
        orch = Orchestrator(
            llm_device=settings.LLM_DEVICE,
            llm_max_tokens=settings.LLM_MAX_TOKENS,
            llm_max_steps=settings.LLM_MAX_STEPS
        )
        
        print(f"   orchestrator.llm_device:      {orch.llm_device}")
        print(f"   orchestrator.llm_max_tokens:  {orch.llm_max_tokens}")
        print(f"   orchestrator.llm_max_steps:   {orch.llm_max_steps}")
        print()
        
        # Verify orchestrator values match settings
        if (orch.llm_device == settings.LLM_DEVICE and
            orch.llm_max_tokens == settings.LLM_MAX_TOKENS and
            orch.llm_max_steps == settings.LLM_MAX_STEPS):
            print("✅ Orchestrator values match settings")
        else:
            print("❌ Orchestrator values do NOT match settings")
            all_correct = False
        
    except Exception as e:
        print(f"❌ Orchestrator integration FAILED: {e}")
        print()
        all_correct = False
        # Re-raise to show full traceback
        raise
    
    print()
    print("=" * 80)
    if all_correct:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)
    
    return 0 if all_correct else 1

if __name__ == "__main__":
    sys.exit(test_llm_config())
