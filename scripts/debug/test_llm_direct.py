#!/usr/bin/env python3
"""
Test LLM directly to debug the issue.
"""
import asyncio
import httpx

async def test_ollama_direct():
    """Test Ollama API directly."""
    
    print("=" * 80)
    print("🧪 TESTING OLLAMA DIRECTLY")
    print("=" * 80)
    
    # Test 1: Check if Ollama is responding
    print("\n📝 Step 1: Checking Ollama health...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get("http://ollama:11434/api/version")
            print(f"✅ Ollama version: {response.json()}")
        except Exception as e:
            print(f"❌ Failed to get version: {e}")
            return
    
    # Test 2: List models
    print("\n📝 Step 2: Listing available models...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get("http://ollama:11434/api/tags")
            models = response.json().get("models", [])
            print(f"✅ Found {len(models)} models")
            for model in models[:5]:
                print(f"   - {model['name']}")
        except Exception as e:
            print(f"❌ Failed to list models: {e}")
            return
    
    # Test 3: Simple completion (using /api/generate endpoint)
    print("\n📝 Step 3: Testing simple completion with /api/generate...")
    print("   Using Mistral 7B (main planner model)...")
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "mistral:7b-instruct",
                    "prompt": "Say hello",
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 10
                    }
                }
            )
            result = response.json()
            print(f"✅ Completion successful!")
            print(f"   Response: {result.get('response', '')[:100]}")
        except Exception as e:
            print(f"❌ Failed completion: {e}")
            return
    
    # Test 4: Chat completion (using OpenAI-compatible endpoint)
    print("\n📝 Step 4: Testing chat completion with /v1/chat/completions...")
    print("   Using Mistral 7B (main planner model)...")
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                "http://ollama:11434/v1/chat/completions",
                json={
                    "model": "mistral:7b-instruct",
                    "messages": [
                        {"role": "user", "content": "Say hello"}
                    ],
                    "max_tokens": 10,
                    "temperature": 0.0,
                    "stream": False
                }
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Chat completion successful!")
                print(f"   Response: {result}")
            else:
                print(f"❌ Chat completion failed: {response.status_code}")
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"❌ Failed chat completion: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ OLLAMA TESTING COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_ollama_direct())
