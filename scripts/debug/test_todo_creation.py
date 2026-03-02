#!/usr/bin/env python3
"""Test script to verify TODO list creation."""

import asyncio
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.services.orchestrator import Orchestrator, OrchestrationContext

async def test_todo_creation():
    print("=" * 60)
    print("Testing TODO List Creation")
    print("=" * 60)
    print()
    
    try:
        print("Creating orchestrator...")
        orch = Orchestrator.from_env()
        print(f"✅ Orchestrator created with {len(orch.llm_clients)} LLM clients\n")
        
        ctx = OrchestrationContext(
            goal="List all available tools",
            user_id="test-user",
            session_id="test-session",
            tenant_id=None
        )
        
        print("Creating TODO list for goal: 'List all available tools'")
        print("(This may take 1-3 minutes on first LLM call...)\n")
        
        todos = await orch._create_agent_todo_list(
            goal="List all available tools",
            ctx=ctx
        )
        
        print(f"\n✅ TODO list created: {len(todos)} items\n")
        
        for i, todo in enumerate(todos, 1):
            status_icon = "✓" if todo.get("status") == "completed" else "○"
            print(f"{status_icon} {i}. {todo.get('task', 'Unknown task')} (status: {todo.get('status', 'unknown')})")
        
        print("\n" + "=" * 60)
        if len(todos) >= 3:
            print("✅ SUCCESS: TODO list has appropriate number of tasks")
        else:
            print(f"⚠️  WARNING: TODO list only has {len(todos)} tasks (expected 3-7)")
        print("=" * 60)
        
        return todos
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to create TODO list")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_todo_creation())
