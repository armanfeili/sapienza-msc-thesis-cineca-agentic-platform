#!/usr/bin/env python3
"""Quick script to debug agent run execution."""
import httpx
import time
import sys

# Use the admin token from environment or hardcode for testing
ADMIN_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjI0MzY1MzQsImV4cCI6MTc2MjUyMjkzNCwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.IQp9QcGAg-64iwwPDGV4MK0a0ZaD5Q2L4_EGJBMxeJB0IRROiOfr9vN8Lm3EJpRCAiNY3ZkooU14gixp_z3QvPEjxxjru1vGxJ0bJC5pTzTv53NqDwS48nfWVq3rp8FzXki90fe-OWk9L5H0LEFWFajDMle8ZmB0Jz2bX1F1llcseEZXZHUEt2vW9S3kPkF1bNtY5_rVvNllGarr1NbAgxVGtKcYmXS80t1VCfXwYzWBvhYqRaHGtck84hjBuqKWv0MJ4lxJQgfQPTyEGn2P6d7ihDL48wt0zam12XIafhvdsswFKkt4-JvSt1fFaTUWTiXM5oIRjallBPM1AHwGrw"

BASE_URL = "http://localhost:8000"

def main():
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    
    print("🔧 Creating agent run...")
    try:
        response = httpx.post(
            f"{BASE_URL}/v1/agent-runs",
            headers=headers,
            json={"prompt": "List the available tools you can use."},
            timeout=180.0  # 3 minutes to allow for LLM processing
        )
        response.raise_for_status()
        data = response.json()
        run_id = data.get("run_id")
        print(f"✅ Created run: {run_id}")
        print(f"   Status: {data.get('status')}")
        print(f"   Model: {data.get('model')}")
        print(f"   Manager: {data.get('manager')}")
    except Exception as e:
        print(f"❌ Failed to create: {e}")
        return
    
    # Poll for completion
    print("\n⏳ Polling for completion...")
    for i in range(60):
        try:
            response = httpx.get(f"{BASE_URL}/v1/agent-runs/{run_id}", headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            
            if i % 5 == 0:
                print(f"   [{i}s] Status: {status}")
            
            if status in ["succeeded", "failed", "cancelled"]:
                print(f"\n✅ Completed with status: {status}")
                
                # Get steps
                steps_resp = httpx.get(f"{BASE_URL}/v1/agent-runs/{run_id}/steps", headers=headers)
                if steps_resp.status_code == 200:
                    steps = steps_resp.json()
                    print(f"   Steps: {len(steps)}")
                    for step in steps[:3]:
                        print(f"     - {step.get('type')}: {step.get('content', '')[:100]}")
                
                # Get outputs
                outputs_resp = httpx.get(f"{BASE_URL}/v1/agent-runs/{run_id}/outputs", headers=headers)
                if outputs_resp.status_code == 200:
                    outputs = outputs_resp.json()
                    print(f"   Outputs: {len(outputs)}")
                    for output in outputs[:2]:
                        print(f"     - {str(output.get('content', ''))[:150]}")
                
                break
        except Exception as e:
            print(f"   Error polling: {e}")
        
        time.sleep(1)
    else:
        print(f"\n⏰ Timeout after 60s")

if __name__ == "__main__":
    main()
