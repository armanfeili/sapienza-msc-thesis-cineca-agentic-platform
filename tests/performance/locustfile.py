"""
Load Testing for Cineca Agentic Platform

Run with:
    locust -f tests/performance/locustfile.py --host=http://localhost:8000

Web UI: http://localhost:8089
"""

from locust import HttpUser, task, between, events
import random
import os

# Sample test data
SAMPLE_MODELS = [
    "gpt-4", "gpt-3.5-turbo", "claude-2", "llama-2-70b"
]

SAMPLE_AGENT_CONFIGS = [
    {
        "name": "Test Agent",
        "description": "Load test agent",
        "system_prompt": "You are a helpful assistant",
        "model": "gpt-4",
        "temperature": 0.7
    }
]


class CinecaPlatformUser(HttpUser):
    """Simulates a typical platform user"""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a user starts - authenticate"""
        # In real tests, use actual OAuth2 flow
        # For load testing, we use a test token
        self.token = os.getenv("TEST_AUTH_TOKEN", "test-token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.tenant_id = os.getenv("TEST_TENANT_ID", "test-tenant")
        self.agent_ids = []
        
    @task(10)
    def health_check(self):
        """10% - Check health endpoints"""
        self.client.get("/v1/health/live")
        
    @task(5)
    def health_ready(self):
        """5% - Check readiness"""
        self.client.get("/v1/health/ready")
        
    @task(20)
    def list_models(self):
        """20% - List available models"""
        self.client.get("/v2/models", headers=self.headers)
        
    @task(10)
    def get_model_details(self):
        """10% - Get specific model details"""
        model_id = random.choice(SAMPLE_MODELS)
        self.client.get(f"/v2/models/{model_id}", headers=self.headers)
        
    @task(15)
    def list_agents(self):
        """15% - List user's agents"""
        self.client.get("/v2/agents", headers=self.headers)
        
    @task(5)
    def create_agent(self):
        """5% - Create new agent"""
        agent_config = SAMPLE_AGENT_CONFIGS[0].copy()
        agent_config["name"] = f"Agent-{random.randint(1000, 9999)}"
        
        response = self.client.post(
            "/v2/agents",
            headers=self.headers,
            json=agent_config,
            name="/v2/agents [CREATE]"
        )
        
        # Store agent ID for later use
        if response.status_code == 201:
            try:
                agent_data = response.json()
                self.agent_ids.append(agent_data.get("id"))
            except Exception:
                pass  # Ignore JSON parsing errors
            
    @task(10)
    def get_agent_details(self):
        """10% - Get agent details"""
        if self.agent_ids:
            agent_id = random.choice(self.agent_ids)
            self.client.get(f"/v2/agents/{agent_id}", headers=self.headers)
            
    @task(8)
    def update_agent(self):
        """8% - Update agent configuration"""
        if self.agent_ids:
            agent_id = random.choice(self.agent_ids)
            update_data = {
                "temperature": random.uniform(0.5, 1.0),
                "max_tokens": random.randint(500, 2000)
            }
            self.client.put(
                f"/v2/agents/{agent_id}",
                headers=self.headers,
                json=update_data,
                name="/v2/agents/{id} [UPDATE]"
            )
            
    @task(12)
    def run_agent(self):
        """12% - Execute agent run"""
        if self.agent_ids:
            agent_id = random.choice(self.agent_ids)
            run_data = {
                "input": "What is the capital of France?",
                "max_iterations": 3
            }
            self.client.post(
                f"/v2/agents/{agent_id}/runs",
                headers=self.headers,
                json=run_data,
                name="/v2/agents/{id}/runs [CREATE]"
            )
            
    @task(5)
    def list_runs(self):
        """5% - List agent runs"""
        if self.agent_ids:
            agent_id = random.choice(self.agent_ids)
            self.client.get(
                f"/v2/agents/{agent_id}/runs",
                headers=self.headers
            )


class AdminUser(HttpUser):
    """Simulates admin user accessing admin endpoints"""
    
    wait_time = between(3, 8)  # Admins wait longer between actions
    weight = 1  # 1:10 ratio vs normal users
    
    def on_start(self):
        """Authenticate as admin"""
        self.token = os.getenv("TEST_ADMIN_TOKEN", "test-admin-token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
    @task(30)
    def list_processes(self):
        """30% - List system processes"""
        self.client.get("/admin/processes", headers=self.headers)
        
    @task(20)
    def get_process_details(self):
        """20% - Get process details"""
        # Assume PIDs 1-1000
        pid = random.randint(1, 1000)
        self.client.get(f"/admin/processes/{pid}", headers=self.headers)
        
    @task(15)
    def list_tenants(self):
        """15% - List all tenants"""
        self.client.get("/admin/tenants", headers=self.headers)
        
    @task(10)
    def get_system_metrics(self):
        """10% - Get system metrics"""
        self.client.get("/admin/metrics", headers=self.headers)
        
    @task(25)
    def list_audit_logs(self):
        """25% - Query audit logs"""
        params = {
            "limit": 50,
            "offset": 0
        }
        self.client.get("/admin/audit-logs", headers=self.headers, params=params)


# Event handlers for custom metrics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    print("🚀 Load test starting...")
    print(f"Target host: {environment.host}")
    

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    print("\n✅ Load test completed!")
    print("\nQuick Summary:")
    stats = environment.stats
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Total failures: {stats.total.num_failures}")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"Requests/sec: {stats.total.total_rps:.2f}")
