#!/usr/bin/env python3
"""
Simple test to verify Ollama is working with native API.
"""
import asyncio
import httpx
import json

async def test_ollama_native():
    """Test Ollama with native /api/generate endpoint."""
    
    print("=" * 80)
    print("🧪 TESTING OLLAMA NATIVE API")
    print("=" * 80)
    
    # Test with native Ollama API (not OpenAI-compatible)
    print("\n📝 Testing native /api/generate endpoint...")
    print("   Using Mistral 7B (main planner model)...")
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print("Sending request to Ollama...")
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": "mistral:7b-instruct",
                    "prompt": "Say hello in one word.",
                    "stream": False,
                    "options": {
                        "num_predict": 5,
                        "temperature": 0.0
                    }
                }
            )
            
            print(f"Status code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success!")
                print(f"   Response: {result.get('response', '')[:100]}")
                print(f"   Done: {result.get('done', False)}")
                print(f"   Total duration: {result.get('total_duration', 0) / 1e9:.2f}s")
                return True
            else:
                print(f"❌ Failed with status {response.status_code}")
                print(f"   Body: {response.text[:200]}")
                return False
                
        except asyncio.TimeoutError:
            print("❌ Request timed out after 120 seconds")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = asyncio.run(test_ollama_native())
    exit(0 if success else 1)
