#!/usr/bin/env python3
"""Quick Ollama test with shorter timeout and simpler prompt."""
import asyncio
import httpx

async def test_ollama():
    print("=" * 80)
    print("🧪 TESTING OLLAMA WITH RESOURCE LIMITS")
    print("=" * 80)
    
    # Test 1: Check if Ollama is responding
    print("\n1️⃣ Testing Ollama API availability...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://ollama:11434/api/tags")
            print(f"✅ Ollama API responding: {response.status_code}")
            data = response.json()
            models = data.get("models", [])
            print(f"   Models available: {len(models)}")
            for model in models:
                print(f"   - {model['name']}")
    except Exception as e:
        print(f"❌ Ollama API error: {e}")
        return False
    
    # Test 2: Simple generation with very short prompt
    print("\n2️⃣ Testing simple text generation...")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            print("   Sending request to Ollama...")
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "mistral:7b-instruct",  # Main planner model
                    "prompt": "Hi",
                    "stream": False,
                    "options": {
                        "num_predict": 5,  # Generate 5 tokens
                        "temperature": 0.0,
                        "num_ctx": 512  # Small context window
                    }
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                output = result.get("response", "")
                print(f"✅ Ollama generated response: '{output}'")
                print(f"   Total duration: {result.get('total_duration', 0) / 1e9:.2f}s")
                print(f"   Load duration: {result.get('load_duration', 0) / 1e9:.2f}s")
                print(f"   Eval count: {result.get('eval_count', 0)} tokens")
                return True
            else:
                print(f"❌ Ollama returned status {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except asyncio.TimeoutError:
        print("❌ Request timed out after 60 seconds")
        return False
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_ollama())
    print("\n" + "=" * 80)
    if success:
        print("🎉 SUCCESS: Ollama is working correctly!")
    else:
        print("❌ FAILED: Ollama is not responding properly")
    print("=" * 80)
