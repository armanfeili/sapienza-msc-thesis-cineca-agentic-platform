#!/usr/bin/env python3
"""Test all models in our hybrid setup."""
import asyncio
import httpx

async def test_model(model_name: str, role: str):
    """Test a single model."""
    print(f"\n{'='*60}")
    print(f"🧪 Testing {role}: {model_name}")
    print(f"{'='*60}")
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            print(f"   Sending request...")
            response = await client.post(
                "http://ollama:11434/api/generate",
                json={
                    "model": model_name,
                    "prompt": "Hi",
                    "stream": False,
                    "options": {
                        "num_predict": 3,
                        "temperature": 0.0,
                        "num_ctx": 512
                    }
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                output = result.get("response", "")
                duration = result.get("total_duration", 0) / 1e9
                print(f"   ✅ SUCCESS!")
                print(f"   Response: '{output.strip()}'")
                print(f"   Duration: {duration:.2f}s")
                return True
            else:
                print(f"   ❌ Failed: HTTP {response.status_code}")
                return False
    except asyncio.TimeoutError:
        print(f"   ❌ TIMEOUT after 90s")
        return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False

async def main():
    print("="*80)
    print("🧪 TESTING HYBRID LLM SETUP")
    print("="*80)
    
    models = [
        ("mistral:7b-instruct", "Planner/Manager (Main)"),
        ("phi3:mini-instruct", "Worker (Primary)"),
        ("llama3.2:3b-instruct", "Fallback (Long Context)"),
        ("qwen2.5:3b-instruct", "Fallback (Strict JSON)"),
    ]
    
    results = {}
    for model, role in models:
        results[model] = await test_model(model, role)
        await asyncio.sleep(2)  # Brief pause between tests
    
    print("\n" + "="*80)
    print("📊 RESULTS SUMMARY")
    print("="*80)
    for model, role in models:
        status = "✅ PASS" if results.get(model) else "❌ FAIL"
        print(f"   {status} - {role}: {model}")
    
    success_count = sum(1 for v in results.values() if v)
    print(f"\n   Total: {success_count}/{len(models)} models working")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
