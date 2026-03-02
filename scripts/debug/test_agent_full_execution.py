#!/usr/bin/env python3
"""Test script to verify full agent execution with detailed output."""

import asyncio
import sys
import json
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.services.orchestrator import Orchestrator, OrchestrationContext

async def test_full_agent_execution():
    print("\n" + "=" * 80)
    print("🤖 FULL AGENT EXECUTION TEST")
    print("=" * 80)
    print()
    
    try:
        # Step 1: Create orchestrator
        print("📦 Step 1: Creating orchestrator...")
        orch = Orchestrator.from_env()
        print(f"   ✅ Orchestrator created")
        print(f"   - LLM clients: {len(orch.llm_clients)}")
        print(f"   - Tools: {len(orch.tools)}")
        print(f"   - Main LLM: {orch.main_llm_name}")
        print()
        
        # Step 2: Define the goal/prompt
        goal = "List all available tools you can use and explain what they do"
        print(f"📝 Step 2: Agent prompt")
        print(f"   Goal: '{goal}'")
        print()
        
        # Step 3: Create orchestration context
        ctx = OrchestrationContext(
            goal=goal,
            user_id="test-user",
            session_id="test-session",
            tenant_id=None
        )
        
        # Step 4: Run the full orchestration
        print("🚀 Step 3: Running full agent orchestration...")
        print("   (This may take 5-15 minutes for LLM inference + tool execution)")
        print()
        
        result = await orch.run(ctx)
        
        # Step 5: Display TODOs created
        print("\n" + "=" * 80)
        print("📋 TODOS CREATED BY AGENT")
        print("=" * 80)
        
        todos = result.data.get("todos", [])
        if todos:
            for i, todo in enumerate(todos, 1):
                status = todo.get("status", "unknown")
                status_icon = "✅" if status == "completed" else "⏳" if status == "running" else "○"
                print(f"\n{status_icon} TODO {i}: {todo.get('task', 'Unknown task')}")
                print(f"   Status: {status}")
        else:
            print("⚠️  No TODOs found in result")
        
        # Step 6: Display execution steps
        print("\n" + "=" * 80)
        print("🔄 EXECUTION STEPS")
        print("=" * 80)
        
        steps = result.data.get("steps", [])
        if steps:
            for i, step in enumerate(steps, 1):
                print(f"\nStep {i}:")
                print(f"   Action: {step.get('action', 'unknown')}")
                step_input = step.get('input', {})
                if step_input:
                    print(f"   Input: {json.dumps(step_input, indent=6)[:200]}...")
        else:
            print("⚠️  No steps found in result")
        
        # Step 7: Display outputs from each TODO execution
        print("\n" + "=" * 80)
        print("📤 OUTPUTS FROM TODO EXECUTION")
        print("=" * 80)
        
        outputs = result.data.get("outputs", [])
        if outputs:
            for i, output in enumerate(outputs, 1):
                print(f"\n--- Output {i} ---")
                output_data = output.get("output", "")
                if isinstance(output_data, str):
                    # Truncate very long outputs
                    if len(output_data) > 500:
                        print(output_data[:500] + "... (truncated)")
                    else:
                        print(output_data)
                else:
                    print(json.dumps(output_data, indent=2)[:500])
        else:
            print("⚠️  No outputs found in result")
        
        # Step 8: Display final aggregated output
        print("\n" + "=" * 80)
        print("🎯 FINAL AGENT RESPONSE")
        print("=" * 80)
        
        final_output = result.data.get("output", "")
        if final_output:
            print(f"\n{final_output}\n")
        else:
            print("⚠️  No final output generated")
        
        # Step 9: Summary
        print("\n" + "=" * 80)
        print("📊 EXECUTION SUMMARY")
        print("=" * 80)
        print(f"✅ Status: {result.status}")
        print(f"✅ TODOs created: {len(todos)}")
        print(f"✅ TODOs completed: {sum(1 for t in todos if t.get('status') == 'completed')}")
        print(f"✅ Steps executed: {len(steps)}")
        print(f"✅ Outputs generated: {len(outputs)}")
        print(f"✅ Manager: {result.data.get('manager', 'unknown')}")
        print("=" * 80)
        print()
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR: Agent execution failed")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_full_agent_execution())
