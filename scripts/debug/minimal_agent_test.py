"""
Minimal agent test - Quick verification of agent functionality
Tests: Orchestrator → LLM → TODO creation → Execution
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.services.orchestrator import Orchestrator, OrchestrationContext

async def minimal_test():
    """
    Minimal test: Create and execute a simple agent task.
    Goal: "Say hello" - should be quick and simple.
    """
    print("\n" + "="*80)
    print("🧪 MINIMAL AGENT TEST: Quick End-to-End Verification")
    print("="*80)
    
    # Step 1: Initialize orchestrator
    print("\n📝 Step 1: Initializing orchestrator...")
    try:
        orch = Orchestrator.from_env()
        print(f"✅ Orchestrator initialized")
        print(f"   - LLM clients: {len(orch.llm_clients)}")
        print(f"   - Main LLM: {orch.main_llm_name}")
        print(f"   - Default model: {orch.default_model}")
        print(f"   - Tools: {len(orch.tools)}")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return False
    
    # Step 2: Run agent with simple goal
    print(f"\n📝 Step 2: Running agent with simple goal...")
    print(f"   Goal: 'Say hello'")
    print(f"   (This should be fast - creating 1-2 simple TODOs)")
    
    try:
        result = await orch.run(
            goal="Say hello",
            user_id="test-user",
            session_id="test-session",
            tenant_id="default"
        )
        
        if not result.ok:
            print(f"❌ Agent run failed: {result.error}")
            return False
        
        print(f"✅ Agent run completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during agent run: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 3: Verify results
    print(f"\n📝 Step 3: Verifying results...")
    
    data = result.data or {}
    todos = data.get('todos', [])
    output = data.get('output', '')
    
    print(f"   - TODOs created: {len(todos)}")
    if todos:
        for i, todo in enumerate(todos, 1):
            task = todo.get('task', 'N/A')
            status = todo.get('status', 'N/A')
            print(f"     {i}. [{status}] {task}")
    
    if output:
        print(f"   - Output length: {len(output)} chars")
        print(f"   - Output preview: {output[:100]}...")
    
    # Verify success
    if not todos:
        print("⚠️  Warning: No TODOs created")
    
    completed_count = sum(1 for t in todos if t.get('status') == 'completed')
    if completed_count == len(todos) and len(todos) > 0:
        print(f"✅ All {len(todos)} TODOs completed successfully!")
    else:
        print(f"⚠️  Only {completed_count}/{len(todos)} TODOs completed")
    
    print("\n" + "="*80)
    print("🎉 TEST PASSED: Minimal agent test successful!")
    print("="*80 + "\n")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(minimal_test())
    sys.exit(0 if success else 1)
