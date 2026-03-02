"""
Simple example script demonstrating Orchestrator planning with a manager LLM
and delegating steps to worker LLMs via llm_clients. This script uses the
Orchestrator.from_env() behavior and expects environment variables like
LLM_CLIENTS to be set or will fall back to a single LLM if configured.

Run locally with a configured LLM adapter or use mocked LLM clients.
"""

import asyncio
import os
import json

from src.services import get_orchestrator


async def main():
    Orchestrator = get_orchestrator()
    orch = Orchestrator.from_env()

    # Example goal
    goal = "Create a 2-step plan: first outline the dataset, then produce a short summary."

    # Provide context so planner can pick an assignee if it recognizes available workers
    ctx = {
        "available_workers": list(orch.llm_clients.keys()),
    }

    result = await orch.run(goal, session_id="demo-session", context_vars=ctx)
    print(json.dumps(result.data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
