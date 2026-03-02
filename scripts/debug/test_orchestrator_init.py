#!/usr/bin/env python3
"""Test script to verify Orchestrator initialization."""

import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.services.orchestrator import Orchestrator

def main():
    print("=" * 60)
    print("Testing Orchestrator Initialization")
    print("=" * 60)
    print()
    
    try:
        print("Creating orchestrator from environment...")
        orch = Orchestrator.from_env()
        
        print("✅ Orchestrator created successfully!\n")
        
        print(f"LLM clients: {list(orch.llm_clients.keys())}")
        print(f"Main LLM name: {getattr(orch, 'main_llm_name', None)}")
        print(f"Has main LLM: {getattr(orch, 'main_llm_name', None) is not None}")
        print(f"Default model: {orch.default_model}")
        print(f"Tools registered: {len(orch.tools)}")
        
        if orch.tools:
            print(f"\nAvailable tools (first 10):")
            for i, tool_name in enumerate(list(orch.tools.keys())[:10], 1):
                print(f"  {i}. {tool_name}")
            if len(orch.tools) > 10:
                print(f"  ... and {len(orch.tools) - 10} more")
        
        print("\n" + "=" * 60)
        if getattr(orch, 'main_llm_name', None):
            print(f"✅ SUCCESS: Main LLM configured: {orch.main_llm_name}")
        elif orch.llm_clients:
            print(f"✅ SUCCESS: {len(orch.llm_clients)} LLM clients available")
        else:
            print("⚠️  WARNING: No LLM clients configured")
        
        if len(orch.tools) > 0:
            print(f"✅ SUCCESS: {len(orch.tools)} tools registered")
        else:
            print("⚠️  WARNING: No tools registered")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to initialize orchestrator")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
