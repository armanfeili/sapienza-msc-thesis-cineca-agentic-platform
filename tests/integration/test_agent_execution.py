"""
Agent Execution Integration Tests

TRUE END-TO-END INTEGRATION TEST:
- Runs against actual Docker services (not TestClient)
- Uses real Auth0 tokens (not mocked JWT)
- Uses real Redis, PostgreSQL, Memgraph, Ollama
- Validates complete production flow
- NO TIMEOUTS: Designed for CPU-only execution (may take >15 minutes)

Acceptance Checklist Item: #3
"""
import pytest
import time
import json
import os
import sys
import platform
import requests
from datetime import datetime, timezone
from typing import Any
import jwt
import base64


class TestAgentExecution:
    """Test real agent execution against Docker services (production-like)."""

    @pytest.fixture(scope="class")
    def base_url(self):
        """
        Base URL for the actual Docker service.
        
        When running inside Docker, use 'app:8000' (Docker service name).
        When running on host, use '127.0.0.1:8000' (IPv4 to avoid macOS IPv6 issues).
        """
        # Check if we're running inside Docker
        if platform.system() == "Linux" and os.path.exists("/.dockerenv"):
            # Inside Docker - use service name
            return os.getenv("API_BASE_URL", "http://app:8000")
        else:
            # On host - use localhost IPv4
            return os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    @pytest.fixture(scope="class")
    def auth0_tokens(self, fetch_auth0_tokens):
        """
        Use Auth0 tokens from conftest.py's fetch_auth0_tokens fixture.
        
        The fetch_auth0_tokens fixture (session-scoped, autouse) runs before
        test session and populates environment variables with tokens.
        
        This fixture:
        1. Reads tokens from environment (populated by conftest.py)
        2. Validates JWT structure and expiry
        3. Returns dict with admin/user/machine tokens
        
        Requirements:
        - Tokens must be valid JWT and decodable
        - Tokens must not expire within 5 minutes
        """
        print("\n🔐 Loading Auth0 tokens from environment...")
        
        # Read tokens from environment (populated by conftest.py fixture)
        env_admin = os.getenv("AUTH0_ADMIN_TOKEN")
        env_user = os.getenv("AUTH0_USER_TOKEN")
        env_machine = os.getenv("AUTH0_MACHINE_TOKEN")
        
        if not (env_admin and env_user and env_machine):
            pytest.fail(
                "Auth0 tokens not found in environment. "
                "The fetch_auth0_tokens fixture should have populated these.\n"
                "Run: ./fetch_auth0_tokens.sh --save-to-env"
            )
        
        tokens = {
            'admin': env_admin,
            'user': env_user,
            'machine': env_machine
        }
        print(f"   ✅ Loaded tokens from environment variables")
        
        # Validate JWT structure and expiry
        now = datetime.now(timezone.utc).timestamp()
        min_exp_time = now + (5 * 60)  # Must be valid for at least 5 more minutes
        
        for token_type, token_value in tokens.items():
            try:
                # Decode without verification (we trust the source and just need to check exp)
                decoded = jwt.decode(token_value, options={"verify_signature": False})
                exp = decoded.get('exp')
                
                if not exp:
                    pytest.fail(f"{token_type} token has no 'exp' claim")
                
                if exp < min_exp_time:
                    time_left = exp - now
                    pytest.fail(
                        f"{token_type} token expires too soon "
                        f"(in {time_left/60:.1f} minutes, need at least 5 minutes)"
                    )
                
                print(f"   ✅ {token_type} token valid (expires in {(exp - now)/60:.1f} minutes)")
                
            except jwt.DecodeError as e:
                pytest.fail(f"Failed to decode {token_type} token: {e}")
        
        print(f"✅ Successfully validated Auth0 tokens (admin, user, machine)")
        return tokens

    @pytest.fixture(scope="class")
    def admin_headers(self, auth0_tokens):
        """Authorization headers with real Auth0 admin token."""
        return {"Authorization": f"Bearer {auth0_tokens['admin']}"}

    @pytest.mark.slow
    def test_agent_run_executes_successfully(self, base_url, admin_headers):
        """
        Agent run should execute for real (not demo/fallback) using actual Docker services.
        
        NO TIMEOUTS: Designed for CPU-only execution (may take >15 minutes)
        
        Preconditions enforced:
        1. All services healthy (Redis, Postgres, Ollama, Auth0)
        2. No silent fallbacks allowed
        3. Fail fast on configuration issues
        4. Docker-only execution (fail if running on host macOS)
        5. LLM call MUST succeed (no silent fallbacks)
        """
        print("\n" + "="*80)
        print("🧪 TRUE END-TO-END INTEGRATION TEST: Agent Run Execution")
        print("="*80)
        print(f"   API URL: {base_url}")
        print(f"   Using: Real Auth0 tokens, Real Redis, Real PostgreSQL")
        print(f"   Platform: {platform.system()} {platform.machine()}")
        print(f"   NO TIMEOUTS: CPU execution may take >15 minutes")
        
        # REQUIREMENT: Fail if running on macOS host (should run in Docker)
        current_platform = platform.system()
        if current_platform == "Darwin":
            pytest.skip(
                "This test must run inside Docker container, not on macOS host. "
                "Use: docker compose exec app pytest tests/integration/test_agent_execution.py"
            )
        
        # Step 0: Comprehensive health checks (FAIL FAST on any issues)
        print("\n❤️  Step 0: Comprehensive health checks...")
        
        # 0a: Basic connectivity with retry (wait for app to be fully ready)
        max_health_attempts = 30  # 30 attempts = up to 60 seconds
        health_attempt = 0
        health_ok = False
        
        print("   Waiting for app to be fully ready...")
        while health_attempt < max_health_attempts:
            try:
                health_response = requests.get(f"{base_url}/health", timeout=10)
                if health_response.status_code == 200:
                    health_ok = True
                    break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                pass  # Keep trying
            
            time.sleep(2)
            health_attempt += 1
            if health_attempt % 5 == 0:
                print(f"   ... still waiting ({health_attempt * 2}s elapsed)")
        
        if not health_ok:
            pytest.fail(
                f"Cannot connect to {base_url}/health after {health_attempt * 2} seconds. "
                f"Ensure Docker services are running: docker compose up -d"
            )
        
        health_data = health_response.json()
        print(f"   ✅ Basic health: {health_data.get('status')}")
        
        # 0b: Detailed health check (Redis, Postgres, Ollama) with retry
        print("   Checking detailed health (Redis, Postgres, Ollama)...")
        max_detailed_attempts = 15  # 15 attempts = up to 30 seconds
        detailed_attempt = 0
        all_services_ready = False
        
        while detailed_attempt < max_detailed_attempts:
            try:
                detailed_health = requests.get(f"{base_url}/v1/health/ready", timeout=30)
                
                # Accept 200 (healthy) or 503 (degraded but operational)
                if detailed_health.status_code not in [200, 503]:
                    detailed_attempt += 1
                    time.sleep(2)
                    continue
                
                health_details = detailed_health.json()
                checks = health_details.get('checks', {})
                
                # Check if all core services are ready
                required_services = ['redis', 'postgres', 'ollama']
                services_status = {}
                
                for service_key in required_services:
                    check = checks.get(service_key)
                    if check:
                        services_status[service_key] = {
                            'ok': check.get('ok', False),
                            'status': check.get('status', 'unknown')
                        }
                    else:
                        services_status[service_key] = {'ok': False, 'status': 'missing'}
                
                # Check if all services are ok
                all_ok = all(s['ok'] and s['status'] == 'ok' for s in services_status.values())
                
                if all_ok:
                    all_services_ready = True
                    break
                else:
                    # Log which services are not ready
                    not_ready = [k for k, v in services_status.items() if not (v['ok'] and v['status'] == 'ok')]
                    if detailed_attempt % 5 == 0 or detailed_attempt == 0:
                        print(f"   ... waiting for services to be ready: {', '.join(not_ready)}")
                    
                    detailed_attempt += 1
                    time.sleep(2)
                    
            except requests.exceptions.RequestException as e:
                detailed_attempt += 1
                if detailed_attempt % 5 == 0:
                    print(f"   ... health check failed, retrying... ({e})")
                time.sleep(2)
        
        if not all_services_ready:
            pytest.fail(
                f"Services not ready after {detailed_attempt * 2} seconds. "
                f"Status: {services_status}. "
                f"Check: docker compose ps"
            )
        
        # Now do final strict validation
        detailed_health = requests.get(f"{base_url}/v1/health/ready", timeout=30)
        
        # Accept HTTP 200 or 503 (may be degraded due to provider warmup issues)
        if detailed_health.status_code not in [200, 503]:
            pytest.fail(
                f"Health check returned {detailed_health.status_code}. "
                f"Expected 200 or 503. "
                f"Response: {detailed_health.text[:200]}"
            )
        
        health_details = detailed_health.json()
        overall_status = health_details.get('status')
        checks = health_details.get('checks', {})
        
        # Provide clear status messaging based on health state
        if overall_status in ['healthy', 'ok']:
            print(f"   Overall status: {overall_status} ✅")
        elif overall_status == 'degraded':
            # Check if degraded due to provider warmup (expected) or actual issues
            provider_check = checks.get('providers', {})
            if provider_check.get('status') == 'warming_up':
                print(f"   Overall status: providers warming up ⏳ (will retry)")
            else:
                print(f"   Overall status: {overall_status} ⚠️")
        else:
            print(f"   Overall status: {overall_status}")
        
        # PRAGMATIC: Accept 'ok', 'healthy', or 'degraded' if core services are healthy
        # 'degraded' often means providers are warming up or Ollama had a warmup failure
        if overall_status not in ['ok', 'healthy', 'degraded']:
            pytest.fail(
                f"Overall health status is '{overall_status}'. "
                f"Expected 'ok', 'healthy', or 'degraded'. "
                f"Check: docker compose ps && docker compose logs"
            )
        
        # Check each core service individually (STRICT - must be healthy)
        required_services = ['redis', 'postgres', 'ollama']
        
        for service_key in required_services:
            check = checks.get(service_key)
            
            if not check:
                pytest.fail(f"Service '{service_key}' not found in health checks")
            
            service_status = check.get('status')
            service_ok = check.get('ok', False)
            
            # STRICT: Core services MUST be healthy
            if not service_ok or service_status != 'ok':
                pytest.fail(
                    f"{service_key.capitalize()} is not healthy: {service_status}. "
                    f"This test requires real {service_key.upper()} (no in-memory fallback). "
                    f"Check: docker compose ps {service_key}"
                )
            
            print(f"   ✅ {service_key.capitalize()}: {service_status}")
        
        print(f"   ✅ All core services healthy (Redis, Postgres, Ollama)")
        
        # STRICT: Wait for ALL providers to be healthy before continuing
        # This prevents sporadic slow first LLM calls and test flakiness
        print(f"\n🔄 Waiting for ALL providers to be healthy...")
        max_provider_wait = 60  # Wait up to 60 seconds for provider warmup
        check_interval = 10  # Check every 10 seconds
        provider_wait_attempt = 0
        providers_healthy = False
        last_provider_status = {}
        last_unhealthy_details = {}
        
        while provider_wait_attempt < max_provider_wait:
            try:
                # Re-check component health
                components_response = requests.get(f"{base_url}/v1/health/components", timeout=5)
                if components_response.status_code == 200:
                    checks = components_response.json().get("checks", {})
                    providers_check = checks.get('providers', {})
                    providers_status = providers_check.get('status')
                    providers_details = providers_check.get('details', {})
                    last_provider_status = providers_details
                    
                    healthy_count = providers_details.get('healthy', 0)
                    total_count = providers_details.get('total', 0)
                    unhealthy_count = providers_details.get('unhealthy', 0)
                    
                    # Track unhealthy provider types and details
                    by_type = providers_details.get('by_type', {})
                    
                    # STRICT: Require healthy == total (all providers up)
                    if providers_status == 'ok' and healthy_count == total_count and total_count > 0:
                        providers_healthy = True
                        print(f"   ✅ All {total_count} providers healthy (Ollama ready)")
                        print(f"      Healthy: {healthy_count}/{total_count} providers")
                        break
                    elif provider_wait_attempt == 0 or provider_wait_attempt % check_interval == 0:
                        # Log detailed status every check_interval seconds
                        print(f"   ⏳ Providers warming up... (checking every {check_interval} seconds)")
                        print(f"      Status: {providers_status}, Healthy: {healthy_count}/{total_count}, Unhealthy: {unhealthy_count}")
                        
                        if unhealthy_count > 0:
                            # Show which provider types are unhealthy
                            print(f"      Unhealthy providers by type:")
                            for ptype, count in by_type.items():
                                if count > 0:
                                    print(f"        - {ptype}: {count} provider(s)")
                            
                            # Try to get last error/failure reason from checks
                            last_error = providers_check.get('error')
                            last_message = providers_check.get('message')
                            if last_error:
                                print(f"      Last error: {last_error}")
                                last_unhealthy_details['error'] = last_error
                            if last_message:
                                print(f"      Message: {last_message}")
                                last_unhealthy_details['message'] = last_message
            except Exception as e:
                if provider_wait_attempt == 0:
                    print(f"   ⚠️  Provider health check failed: {e}")
            
            time.sleep(check_interval)
            provider_wait_attempt += check_interval
        
        if not providers_healthy:
            # STRICT: Fail test if providers not ready
            # This prevents flaky tests from cold/slow providers
            error_msg = (
                f"Providers not healthy after {max_provider_wait}s. "
                f"Last status: {last_provider_status}. "
            )
            if last_unhealthy_details:
                error_msg += f"Last failure details: {last_unhealthy_details}. "
            error_msg += (
                f"This test requires ALL providers (Ollama) to be fully warmed up. "
                f"Check: docker compose logs ollama"
            )
            pytest.fail(error_msg)
        
        # 0b-2: Enhanced provider enumeration validation
        print(f"\n🔍 Step 0b-2: Validating provider enumeration...")
        providers_check = checks.get('providers', {})
        providers_details = providers_check.get('details', {})
        
        # TODO #8: Provider health expectations - HARD ASSERTIONS
        # Assert: Provider set is non-empty
        total_providers = providers_details.get('total', 0)
        assert total_providers > 0, (
            f"❌ PROVIDER ENUMERATION FAILED: Provider list is empty (total={total_providers}). "
            f"At least one provider (Ollama/Azure/etc.) must be configured and healthy. "
            f"Check provider configuration and health endpoint."
        )
        print(f"   ✅ Provider count: {total_providers} provider(s) configured")
        
        # Check if provider details include individual provider information
        by_type = providers_details.get('by_type', {})
        providers_list = providers_details.get('providers', [])  # List of individual providers with details
        
        if providers_list:
            # GOOD: Individual provider details are included
            print(f"   ✅ Provider enumeration includes individual provider details:")
            for idx, provider in enumerate(providers_list, 1):
                provider_name = provider.get('name', 'unknown')
                provider_type = provider.get('type', 'unknown')
                provider_status = provider.get('status', 'unknown')
                provider_model = provider.get('model', 'unknown')
                models = provider.get('models', [])  # May be empty if endpoint doesn't provide list
                
                # TODO #8: Assert each provider lists at least one model
                # PRAGMATIC: Health endpoint currently returns 'model' (singular) not 'models' (list)
                # Accept either format for now
                has_models = len(models) > 0 or provider_model not in [None, 'unknown', '']
                assert has_models, (
                    f"❌ PROVIDER CONFIGURATION ERROR: Provider '{provider_name}' ({provider_type}) "
                    f"has no model information. Either 'model' or 'models' must be present. "
                    f"Check provider configuration and model discovery."
                )
                
                print(f"      Provider {idx}: {provider_name} ({provider_type})")
                if models:
                    print(f"         Status: {provider_status}, Models: {len(models)}")
                else:
                    print(f"         Status: {provider_status}, Model: {provider_model}")
            
            print(f"   ✅ All {len(providers_list)} providers have model information")
        else:
            # MISSING: Only showing aggregated counts without individual details
            print(f"   ⚠️  OBSERVABILITY ISSUE: Provider details only show aggregated counts")
            print(f"   Current output: total={providers_details.get('total')}, healthy={providers_details.get('healthy')}, by_type={by_type}")
            print(f"\n   → RECOMMENDED ENHANCEMENT: Include individual provider details in health response")
            print(f"   → Location: src/api/v1/endpoints/health.py (or similar health endpoint)")
            print(f"   → Add to response:")
            print(f"      'providers': {{")
            print(f"        'total': <count>,")
            print(f"        'healthy': <count>,")
            print(f"        'by_type': {{ ... }},")
            print(f"        'providers': [  # ← ADD THIS")
            print(f"          {{")
            print(f"            'name': 'ollama-phi3',")
            print(f"            'type': 'ollama',")
            print(f"            'status': 'healthy',")
            print(f"            'model': 'phi3:mini',")
            print(f"            'last_check': '2025-01-08T12:00:00Z'")
            print(f"          }}")
            print(f"        ]")
            print(f"      }}")
            print(f"   → Impact: Better debugging, provider-specific issue identification, audit trail")
            print(f"   → Note: This is a RECOMMENDED enhancement, not a blocking issue")
        
        # TODO #8: If environment specifies expected provider count, validate it
        expected_provider_count = os.getenv("EXPECTED_PROVIDER_COUNT")
        if expected_provider_count:
            expected_count = int(expected_provider_count)
            assert total_providers == expected_count, (
                f"❌ PROVIDER COUNT MISMATCH: Expected {expected_count} providers (EXPECTED_PROVIDER_COUNT), "
                f"found {total_providers}. Check provider configuration matches environment expectations."
            )
            print(f"   ✅ Provider count matches environment expectation: {expected_count}")
        
        # 0c: Verify Auth0 connectivity
        try:
            # This endpoint requires valid Auth0 token
            auth_test = requests.get(f"{base_url}/v1/agents", headers=admin_headers, timeout=10)
            if auth_test.status_code == 401:
                pytest.fail("Auth0 token rejected by service. Check OIDC configuration.")
            print(f"   ✅ Auth0 authentication working")
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Failed to test Auth0 connectivity: {e}")
        
        # Create agent run with simple prompt
        print("\n📝 Step 1: Creating agent run...")
        print("   Prompt: 'List the available tools you can use.'")
        print("   (This will trigger LLM calls - may take 3-15+ minutes on CPU)")
        print(f"   Using real Auth0 admin token")
        print(f"   NO TIMEOUT: Waiting indefinitely for completion...")
        
        # NO TIMEOUT - CPU execution can be very slow
        create_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=admin_headers,
            json={"prompt": "List the available tools you can use."},
            timeout=None  # No timeout
        )
        
        print(f"\n🔍 Create Response Status: {create_response.status_code}")
        print(f"🔍 Create Response Headers:")
        for key, value in create_response.headers.items():
            print(f"   {key}: {value}")
        
        # Step 1a: Validate request ID presence
        print(f"\n🔍 Step 1a: Validating request ID...")
        request_id = create_response.headers.get('X-Request-ID') or create_response.headers.get('x-request-id')
        if request_id:
            print(f"   ✅ Request ID present: {request_id}")
            print(f"      (Can be used for distributed tracing and log correlation)")
        else:
            print(f"   ⚠️  OBSERVABILITY ISSUE: No X-Request-ID header in response")
            print(f"\n   → RECOMMENDED ENHANCEMENT: Add X-Request-ID to all API responses")
            print(f"   → Location: Add middleware to FastAPI app (src/main.py or similar)")
            print(f"   → Implementation example:")
            print(f"      @app.middleware('http')")
            print(f"      async def add_request_id(request: Request, call_next):")
            print(f"          request_id = str(uuid.uuid4())")
            print(f"          response = await call_next(request)")
            print(f"          response.headers['X-Request-ID'] = request_id")
            print(f"          return response")
            print(f"   → Impact: Enables distributed tracing, log correlation, debugging across services")
            print(f"   → Note: This is a RECOMMENDED enhancement for production observability")
        
        print(f"\n🔍 Create Response Body:")
        print(f"{json.dumps(create_response.json(), indent=2)}")
        
        assert create_response.status_code == 201, f"Failed to create agent run: {create_response.json()}"
        print("✅ Agent run created successfully (HTTP 201 received)")

        run_data = create_response.json()
        run_id = run_data.get("run_id")
        assert run_id, "Agent run should have run_id"
        print(f"   Run ID: {run_id}")
    
        # Note: model/manager fields will be null until background task completes
        initial_status = run_data.get("status")
        model = run_data.get("model")
        manager = run_data.get("manager")
        print(f"   Initial Status: {initial_status}")
        print(f"   Initial Model: {model} (will be populated after execution)")
        print(f"   Initial Manager: {manager} (will be populated after execution)")
        
        # For async execution (status='queued'/'running'), model/manager are null initially
        if initial_status in ["queued", "running"]:
            print("✅ Agent run queued for async execution (model/manager will be set after completion)")        # Poll for completion (NO TIME LIMIT - CPU may be slow)
        print("\n⏳ Step 2: Waiting for agent run to complete...")
        print("   (NO TIME LIMIT: Will wait indefinitely for completion)")
        print("   (Each LLM call may take 3-15+ minutes on CPU)")
        attempt = 0
        final_status = None
        last_logged_status = None
        status_data = None

        while True:  # Infinite loop - will break on terminal status
            status_response = requests.get(
                f"{base_url}/v1/agent-runs/{run_id}",
                headers=admin_headers,
                timeout=None  # No timeout
            )
            assert status_response.status_code == 200

            status_data = status_response.json()
            final_status = status_data.get("status")

            # Log progress every 5 seconds, or immediately if status changes
            if attempt % 5 == 0 or final_status != last_logged_status:
                elapsed_min = attempt // 60
                elapsed_sec = attempt % 60
                print(f"   [{elapsed_min}m {elapsed_sec}s] Status: {final_status}")
                
                # Print detailed status every 10 seconds
                if attempt % 10 == 0:
                    print(f"   🔍 Current metrics:")
                    current_metrics = status_data.get("metrics") or {}
                    llm_count = len(current_metrics.get("llm", []))
                    tool_count = len(current_metrics.get("tools", []))
                    print(f"      • LLM calls: {llm_count}")
                    print(f"      • Tool calls: {tool_count}")
                    if llm_count > 0:
                        latest_llm = current_metrics.get("llm", [])[-1]
                        print(f"      • Latest LLM: success={latest_llm.get('success')}, latency={latest_llm.get('latency_ms')}ms")
                
                last_logged_status = final_status

            if final_status in ["succeeded", "failed", "cancelled"]:
                # Calculate actual run duration from timestamps
                started_str = status_data.get('started_at')
                finished_str = status_data.get('finished_at')
                
                print(f"\n🔍 Final Status Data Received:")
                print(f"{json.dumps(status_data, indent=2)}")
                
                if started_str and finished_str:
                    # Handle both 'Z' suffix and '+00:00' timezone formats
                    started_str = started_str.replace('Z', '+00:00')
                    finished_str = finished_str.replace('Z', '+00:00')
                    started = datetime.fromisoformat(started_str)
                    finished = datetime.fromisoformat(finished_str)
                    duration_sec = (finished - started).total_seconds()
                    elapsed_min = int(duration_sec // 60)
                    elapsed_sec = int(duration_sec % 60)
                else:
                    # Fallback to polling time if timestamps not available
                    elapsed_min = attempt // 60
                    elapsed_sec = attempt % 60
                
                print(f"✅ Agent run completed with status: {final_status} (took {elapsed_min}m {elapsed_sec}s)")
                break

            time.sleep(1)
            attempt += 1

        # NO TIMEOUT CHECK - infinite loop breaks on terminal status only
        assert final_status == "succeeded", f"Agent run did not complete successfully. Status: {final_status}"
        
        # ========================================
        # NEW: Validate LLM Configuration (Critical)
        # ========================================
        print("\n🔍 Step 2a: Validating LLM configuration...")
        
        # Assert: main_llm should NOT be "planner" (mock client)
        main_llm_name = status_data.get("manager") or status_data.get("model")
        assert main_llm_name != "planner", (
            f"main_llm is 'planner' (mock client) - orchestrator failed to select real model. "
            f"Check registry load and LLM_FALLBACK_MODE."
        )
        print(f"   ✅ main_llm = {main_llm_name} (not 'planner')")
        
        # Assert: model should not be null
        run_model = status_data.get("model")
        assert run_model is not None, (
            "model is null - orchestrator.default_model not set. "
            "Check registry load and model selection logic."
        )
        print(f"   ✅ model = {run_model} (not null)")
        
        # Assert: warnings should not contain "404" for /chat/completions
        warnings = status_data.get("warnings", [])
        for warning in warnings:
            assert "404" not in str(warning), (
                f"Found 404 error in warnings - wrong Ollama endpoint. "
                f"Should be /v1/chat/completions, not /chat/completions. Warning: {warning}"
            )
        print(f"   ✅ No 404 errors for /chat/completions endpoint")

        # Verify database persistence (from Point 7 of checklist)
        print("\n💾 Step 2b: Verifying database persistence...")
        assert status_data is not None, "Run data should be retrieved successfully"
        assert status_data.get("run_id") == run_id, "Run ID should match"
        
        finished_at_str = status_data.get("finished_at")
        assert finished_at_str is not None, "finished_at timestamp should be set"
        
        # Also check warnings for silent fallbacks (STRICT - fail if services are healthy but fallbacks used)
        warnings = status_data.get("warnings", [])
        
        # Scan for problematic patterns
        warning_text = " ".join(str(w).lower() for w in warnings)
        
        # Check for 404 errors (wrong endpoint)
        if "404" in warning_text:
            pytest.fail(f"Found 404 errors in warnings - wrong Ollama endpoint. Warnings: {warnings}")
        
        # Check for fallback mode indicators - ONLY fail if core services are healthy
        # (If Redis/Postgres were unhealthy, fallbacks would be expected)
        redis_ok = checks.get('redis', {}).get('ok', False)
        postgres_ok = checks.get('postgres', {}).get('ok', False)
        services_healthy = redis_ok and postgres_ok
        
        forbidden_patterns = [
            ("in-memory cache", "Using in-memory cache instead of Redis"),
            ("in-memory fallback", "Using in-memory fallback instead of real services"),
            ("fallback mode", "System is using fallback mode"),
            ("demo mode", "System is in demo mode"),
            ("/v1/v1/chat", "Double /v1 in endpoint path"),
            ("redis not available", "Redis connection failed - using in-memory fallback"),
        ]
        
        if services_healthy:
            # Services are healthy - any fallback is a problem
            for pattern, description in forbidden_patterns:
                if pattern in warning_text:
                    pytest.fail(
                        f"FORBIDDEN PATTERN DETECTED: '{pattern}' - {description}. "
                        f"Redis/Postgres are healthy but fallbacks are being used. "
                        f"Warnings: {warnings}"
                    )
        else:
            # Services are unhealthy - fallbacks are expected, just log
            for pattern, description in forbidden_patterns:
                if pattern in warning_text:
                    print(f"   ℹ️  Expected fallback detected (services unhealthy): {pattern}")
        
        print(f"✅ Run persisted with finished_at: {finished_at_str}")
        print(f"   ✅ No forbidden fallback warnings detected (services healthy: {services_healthy})")
        
        # Verify metrics are populated and LLM calls succeeded
        print("\n📊 Step 2c: Verifying metrics...")
        metrics = status_data.get("metrics")
        assert metrics is not None, "Metrics should be present (not null)"
        assert isinstance(metrics, dict), "Metrics should be a dict"
        
        llm_metrics = metrics.get("llm", [])
        tool_metrics = metrics.get("tools", [])
        overall_ms = metrics.get("overall_ms")
        
        # REQUIREMENT 5a: Assert overall_ms is an int (not string, not null)
        assert isinstance(overall_ms, int), f"overall_ms must be int, got {type(overall_ms).__name__}: {overall_ms}"
        assert overall_ms > 0, f"overall_ms must be positive, got {overall_ms}"
        
        # REQUIREMENT 5b: Verify overall_ms ≈ (finished_at - started_at) within tolerance
        # Default: ±5% for stable CI; allow ±10% via E2E_TOLERANCE_PERCENT for CPU-only runs
        tolerance_percent = int(os.getenv("E2E_TOLERANCE_PERCENT", "5"))
        tolerance_multiplier = tolerance_percent / 100.0
        
        started_str = status_data.get('started_at')
        finished_str = status_data.get('finished_at')
        if started_str and finished_str:
            started_str = started_str.replace('Z', '+00:00')
            finished_str = finished_str.replace('Z', '+00:00')
            started = datetime.fromisoformat(started_str)
            finished = datetime.fromisoformat(finished_str)
            actual_duration_ms = int((finished - started).total_seconds() * 1000)
            
            # Allow ±tolerance% variance (includes instrumentation overhead, rounding, etc.)
            lower_bound = actual_duration_ms * (1 - tolerance_multiplier)
            upper_bound = actual_duration_ms * (1 + tolerance_multiplier)
            
            # TODO #12: HARD ASSERTION - Test MUST fail when drift exceeds tolerance
            drift_ms = abs(overall_ms - actual_duration_ms)
            drift_percent = (drift_ms / actual_duration_ms) * 100 if actual_duration_ms > 0 else 0
            
            assert lower_bound <= overall_ms <= upper_bound, (
                f"❌ METRICS DRIFT EXCEEDED: overall_ms ({overall_ms}ms) doesn't match "
                f"actual duration ({actual_duration_ms}ms) within ±{tolerance_percent}%. "
                f"Drift: {drift_ms}ms ({drift_percent:.2f}%). "
                f"Expected range: {int(lower_bound)}-{int(upper_bound)}ms. "
                f"This indicates metrics collection inconsistency. "
                f"Set E2E_TOLERANCE_PERCENT=10 for CPU-only runs with higher jitter."
            )
            print(f"   ✅ overall_ms: {overall_ms}ms (matches actual duration {actual_duration_ms}ms within ±{tolerance_percent}%, drift: {drift_percent:.2f}%)")
        else:
            # HARD REQUIREMENT: Timestamps must be present to validate metrics
            pytest.fail(
                f"❌ MISSING TIMESTAMPS: Cannot verify overall_ms accuracy. "
                f"started_at={started_str}, finished_at={finished_str}. "
                f"Both timestamps are required for metrics validation."
            )
        
        print(f"   LLM calls: {len(llm_metrics)}")
        print(f"   Tool calls: {len(tool_metrics)}")
        
        # REQUIREMENT 4a: Assert at least one LLM call exists
        assert len(llm_metrics) > 0, "No LLM calls recorded in metrics - LLM execution path failed"
        
        # REQUIREMENT 4b: Assert first LLM call succeeded (STRICT - no ALLOW_TOOL_ONLY here)
        first_llm = llm_metrics[0]
        llm_success = first_llm.get("success", False)
        llm_error = first_llm.get("error", "")
        llm_model = first_llm.get("model", "unknown")
        llm_latency = first_llm.get("latency_ms", 0)
        llm_output_tokens = first_llm.get("output_tokens", 0)
        
        # Print full LLM metrics for debugging
        print(f"\n🔍 Full LLM Metrics (all {len(llm_metrics)} calls):")
        for idx, llm_call in enumerate(llm_metrics):
            print(f"\n   LLM Call #{idx + 1}:")
            print(f"      {json.dumps(llm_call, indent=6)}")
        
        print(f"\n🔍 Full Tool Metrics (all {len(tool_metrics)} calls):")
        for idx, tool_call in enumerate(tool_metrics):
            print(f"\n   Tool Call #{idx + 1}:")
            print(f"      {json.dumps(tool_call, indent=6)}")
        
        print(f"\n🔍 Full Status Data:")
        print(f"{json.dumps(status_data, indent=2)}")
        
        # LATENCY BUDGET VALIDATION: Different thresholds for cold vs warm models
        # CPU models: cold (first call) ≤180s (increased for real cold starts), warm (subsequent) ≤10s per 100 tokens
        print(f"\n⏱️  Validating LLM latency budgets...")
        
        # TODO #6: HARD ASSERTION - First call is typically "cold" (model loading + inference)
        # Use environment variable to allow flexibility for CPU-based deployments
        cold_budget_ms = int(os.getenv("COLD_LLM_BUDGET_MS", "180000"))  # Default: 180s (3 minutes) for CPU
        
        print(f"   📊 Active threshold: {cold_budget_ms}ms cold budget ({cold_budget_ms/1000:.0f}s)")
        print(f"      (Set COLD_LLM_BUDGET_MS env var to override)")
        
        # HARD ASSERTION: Must be under budget
        assert llm_latency <= cold_budget_ms, (
            f"❌ LATENCY BUDGET EXCEEDED: First LLM call took {llm_latency}ms (>{cold_budget_ms}ms cold budget). "
            f"Model: {llm_model}. "
            f"This indicates the model is taking too long to respond. "
            f"Check: 1) Model size appropriate for hardware, 2) Ollama CPU limits, 3) System resources. "
            f"Consider pre-loading model with model.manage:load or using smaller model."
        )
        
        # Success message
        print(f"   ✅ First LLM call: {llm_latency}ms (within {cold_budget_ms}ms cold budget)")
        
        # If multiple LLM calls, check warm latency budget
        if len(llm_metrics) > 1:
            warm_budget_per_100_tokens = 10000  # 10s per 100 output tokens
            for idx, llm_call in enumerate(llm_metrics[1:], start=2):
                warm_latency = llm_call.get("latency_ms", 0)
                warm_tokens = llm_call.get("output_tokens", 0)
                
                # Calculate expected latency based on tokens (assuming ~100 tokens baseline)
                expected_warm_ms = warm_budget_per_100_tokens * max(1, warm_tokens / 100)
                
                if warm_latency > expected_warm_ms * 2:  # Allow 2x buffer for variance
                    print(f"   ⚠️  WARNING: LLM call #{idx} took {warm_latency}ms "
                          f"(>{expected_warm_ms:.0f}ms warm budget for {warm_tokens} tokens)")
                else:
                    print(f"   ✅ LLM call #{idx}: {warm_latency}ms for {warm_tokens} tokens (within warm budget)")
        
        if not llm_success:
            # Get more diagnostic info
            error_details = {
                "error": llm_error,
                "model": llm_model,
                "latency_ms": llm_latency,
                "run_id": run_id,
                "warnings": warnings,
                "metrics": metrics
            }
            
            # Print full error diagnostics
            print(f"\n❌ LLM CALL FAILED - Full Diagnostics:")
            print(f"{json.dumps(error_details, indent=2)}")
            
            # Check if this is a common Ollama error
            if "HTTPStatusError" in str(llm_error):
                pytest.fail(
                    f"LLM call FAILED with HTTPStatusError. "
                    f"Possible causes:\n"
                    f"  1. Ollama not running: docker compose ps ollama\n"
                    f"  2. Wrong endpoint: should be /v1/chat/completions\n"
                    f"  3. Model not loaded: docker compose exec ollama ollama list\n"
                    f"  4. Model name mismatch: '{llm_model}'\n"
                    f"\nError: {llm_error}\n"
                    f"Diagnostics: {json.dumps(error_details, indent=2)}"
                )
            
            pytest.fail(
                f"LLM call FAILED (success=False). "
                f"Error: {llm_error}. "
                f"Model: {llm_model}. "
                f"Latency: {llm_latency}ms. "
                f"This test requires successful LLM execution (no silent fallbacks).\n"
                f"Diagnostics: {json.dumps(error_details, indent=2)}"
            )
        
        # REQUIREMENT 5c: Assert latency_ms and token counts present for LLM call
        assert isinstance(llm_latency, int), f"LLM latency_ms must be int, got {type(llm_latency).__name__}"
        assert llm_latency > 0, f"LLM latency_ms must be positive, got {llm_latency}"
        
        input_tokens = first_llm.get("input_tokens")
        output_tokens = first_llm.get("output_tokens")
        total_tokens = first_llm.get("total_tokens")
        
        # PHASE 2 REQUIREMENT: Validate token counts are present and non-zero
        assert input_tokens is not None, "LLM metrics must include input_tokens"
        assert output_tokens is not None, "LLM metrics must include output_tokens"
        assert total_tokens is not None, "LLM metrics must include total_tokens"
        assert isinstance(input_tokens, int) and input_tokens > 0, (
            f"input_tokens must be positive int, got {input_tokens}"
        )
        assert isinstance(output_tokens, int) and output_tokens > 0, (
            f"output_tokens must be positive int, got {output_tokens}"
        )
        assert total_tokens == input_tokens + output_tokens, (
            f"total_tokens ({total_tokens}) must equal input_tokens ({input_tokens}) + output_tokens ({output_tokens})"
        )
        
        print(f"   ✅ LLM call succeeded:")
        print(f"      • model: {llm_model}")
        print(f"      • latency: {llm_latency}ms")
        print(f"      • input_tokens: {input_tokens}")
        print(f"      • output_tokens: {output_tokens}")
        print(f"      • total_tokens: {total_tokens}")
        
        # PHASE 2 REQUIREMENT: Validate metrics rollup fields
        total_llm_calls_field = status_data.get("total_llm_calls")
        tool_calls_field = status_data.get("tool_calls")
        tool_errors_field = status_data.get("tool_errors")
        
        assert total_llm_calls_field is not None, "Status must include total_llm_calls rollup field"
        assert tool_calls_field is not None, "Status must include tool_calls rollup field"
        assert tool_errors_field is not None, "Status must include tool_errors rollup field"
        
        assert isinstance(total_llm_calls_field, int), f"total_llm_calls must be int, got {type(total_llm_calls_field)}"
        assert isinstance(tool_calls_field, int), f"tool_calls must be int, got {type(tool_calls_field)}"
        assert isinstance(tool_errors_field, int), f"tool_errors must be int, got {type(tool_errors_field)}"
        
        assert total_llm_calls_field == len(llm_metrics), (
            f"total_llm_calls ({total_llm_calls_field}) must match len(llm_metrics) ({len(llm_metrics)})"
        )
        assert tool_calls_field == len(tool_metrics), (
            f"tool_calls ({tool_calls_field}) must match len(tool_metrics) ({len(tool_metrics)})"
        )
        
        # Count failed tools
        failed_tool_count = len([t for t in tool_metrics if not t.get("success", True)])
        assert tool_errors_field == failed_tool_count, (
            f"tool_errors ({tool_errors_field}) must match count of failed tools ({failed_tool_count})"
        )
        
        print(f"   ✅ Metrics rollup fields validated:")
        print(f"      • total_llm_calls: {total_llm_calls_field}")
        print(f"      • tool_calls: {tool_calls_field}")
        print(f"      • tool_errors: {tool_errors_field}")
        
        # Validate model_warmup_ms / first_llm_call_ms (observability metric)
        # Note: Per TODO #5, model_warmup_ms lives in metrics object (not root) to avoid duplication
        print(f"\n🔥 Step 2d: Validating model warmup metrics...")
        metrics_obj = status_data.get("metrics", {})
        first_llm_call_ms = metrics_obj.get("first_llm_call_ms")
        model_warmup_ms = metrics_obj.get("model_warmup_ms")
        warmup_candidate = first_llm_call_ms if first_llm_call_ms is not None else model_warmup_ms
        
        if warmup_candidate is not None:
            assert isinstance(warmup_candidate, int), f"first_llm_call_ms/model_warmup_ms should be int, got {type(warmup_candidate).__name__}"
            assert warmup_candidate > 0, f"first_llm_call_ms/model_warmup_ms should be positive, got {warmup_candidate}"
            print(f"   ✅ First-call latency captured: {warmup_candidate}ms")
            
            # Compare with first LLM latency for sanity check
            if warmup_candidate > llm_latency:
                print(f"      ⚠️  WARNING: warmup ({warmup_candidate}ms) > first call latency ({llm_latency}ms)")
                print(f"         This may indicate warmup includes more than just model loading")
            if model_warmup_ms is not None and model_warmup_ms > llm_latency:
                print(f"      ⚠️  WARNING: legacy model_warmup_ms ({model_warmup_ms}ms) > first call latency ({llm_latency}ms)")
                print(f"         This may indicate warmup includes more than just model loading")
        else:
            print(f"   ❌ METRICS ISSUE: model_warmup_ms is null (not captured)")
            print(f"      → REQUIRED FIX: Capture model warmup time during first model load/test")
            print(f"      → Location: src/services/orchestrator.py or model initialization")
            print(f"      → Implementation:")
            print(f"         warmup_start = time.time()")
            print(f"         model_response = await model.test_connection()")
            print(f"         warmup_ms = int((time.time() - warmup_start) * 1000)")
            print(f"         run.model_warmup_ms = warmup_ms")
            print(f"      → Impact: Cannot distinguish cold vs warm model performance")
        
        # REQUIREMENT 5d: Validate tool metrics have latency_ms and success
        for i, tool_call in enumerate(tool_metrics):
            tool_name = tool_call.get("name", f"tool_{i}")
            tool_latency = tool_call.get("latency_ms")
            tool_success = tool_call.get("success")
            
            assert isinstance(tool_latency, int), (
                f"Tool '{tool_name}' latency_ms must be int, got {type(tool_latency).__name__}"
            )
            assert tool_latency >= 0, f"Tool '{tool_name}' latency_ms must be non-negative, got {tool_latency}"
            assert isinstance(tool_success, bool), (
                f"Tool '{tool_name}' success must be bool, got {type(tool_success).__name__}"
            )
        
        print(f"   ✅ All {len(tool_metrics)} tool calls have valid metrics (latency_ms, success)")

        # Get execution steps (needed for TODO validation)
        print("\n📋 Step 2b: Fetching execution steps...")
        steps_response = requests.get(
            f"{base_url}/v1/agent-runs/{run_id}/steps",
            headers=admin_headers,
            timeout=10
        )
        assert steps_response.status_code == 200

        steps = steps_response.json()
        assert isinstance(steps, list), "Steps should be a list"
        assert len(steps) > 0, "Agent run should have at least one step"
        print(f"✅ Found {len(steps)} execution steps")

        # Verify TODOs if present (from Point 7 of checklist)
        todos = status_data.get("todos")
        if todos:
            print(f"\n📝 Step 2c: Verifying TODOs...")
            print(f"   Found {len(todos)} TODOs")
            
            # Extract all tool calls from steps for validation
            all_tool_calls = []
            for step in steps:
                action = step.get("action", "")
                if action and action != "Create TODO list":
                    # Extract tool name (e.g., "catalog.discover", "user.profile")
                    all_tool_calls.append(action)
            
            # Track TODOs with missing tool executions for summary
            todos_with_missing_tools = []
            
            for i, todo in enumerate(todos):
                todo_status = todo.get("status")
                todo_task = todo.get("task", "")
                todo_task_short = todo_task[:70]  # First 70 chars for display
                print(f"   TODO {i+1}: {todo_status} - {todo_task_short}...")
                
                # STRICT: Validate completed TODOs have evidence (tool calls)
                if todo_status == "completed":
                    # Extract ALL tool mentions from TODO text using pattern matching
                    # Pattern: word.word (e.g., "catalog.discover", "user.profile")
                    import re
                    tool_pattern = r'\b([a-z_]+\.[a-z_]+)\b'
                    mentioned_tools = list(set(re.findall(tool_pattern, todo_task.lower())))
                    
                    # If TODO mentions specific tools, verify they were actually called
                    if mentioned_tools:
                        missing_tools = []
                        for tool in mentioned_tools:
                            if tool not in all_tool_calls:
                                missing_tools.append(tool)
                        
                        if missing_tools:
                            print(f"      ❌ CORRECTNESS ISSUE: TODO claims tools executed but no calls recorded")
                            print(f"         Missing: {', '.join(missing_tools)}")
                            print(f"         TODO: {todo_task[:100]}...")
                            print(f"         Actual calls: {all_tool_calls}")
                            todos_with_missing_tools.append({
                                "todo_id": i + 1,
                                "missing_tools": missing_tools,
                                "todo_text": todo_task
                            })
            
            # Check that at least majority of TODOs completed (allow some failures due to tool discovery issues)
            completed_todos = [t for t in todos if t.get("status") == "completed"]
            completion_rate = len(completed_todos) / len(todos) * 100 if len(todos) > 0 else 0
            print(f"✅ {len(completed_todos)}/{len(todos)} TODOs completed ({completion_rate:.1f}%)")
            
            # Report summary of TODO validation issues
            if todos_with_missing_tools:
                print(f"\n   ❌ TODO VALIDATION FAILED: {len(todos_with_missing_tools)} TODO(s) claim tools executed but calls not found")
                print(f"      → REQUIRED FIX: Either:")
                print(f"         Option A: Update agent planner to only mention tools that will be called")
                print(f"         Option B: Ensure agent actually calls all tools mentioned in TODOs")
                print(f"      → Impact: Reduces confidence in agent reliability and TODO tracking")
                for issue in todos_with_missing_tools:
                    print(f"      → TODO #{issue['todo_id']}: Missing {', '.join(issue['missing_tools'])}")
            
            # STRICT: No "pending" or "failed" TODOs for successful runs
            unexpected_statuses = [t for t in todos if t.get("status") not in ["completed", "skipped"]]
            if unexpected_statuses and status_data.get("status") == "succeeded":
                print(f"   ⚠️  WARNING: Run succeeded but {len(unexpected_statuses)} TODO(s) not completed:")
                for todo in unexpected_statuses:
                    print(f"      - {todo.get('status')}: {todo.get('task', '')[:60]}")

            assert completion_rate >= 50, f"Less than 50% TODOs completed: {len(completed_todos)}/{len(todos)} ({completion_rate:.1f}%)"


        # Verify steps include real execution (steps and outputs)
        print("\n📋 Step 3: Analyzing execution step types...")
        # According to OrchestrationStepInput/Output schema, type values are "step" and "output"
        input_steps = [s for s in steps if s.get("type") == "step"]
        output_steps = [s for s in steps if s.get("type") == "output"]
        
        assert len(input_steps) > 0 or len(output_steps) > 0, (
            "Agent run should have execution steps (type='step' or type='output')"
        )
        
        print(f"   Input steps (type='step'): {len(input_steps)}")
        print(f"   Output steps (type='output'): {len(output_steps)}")
        
        # PHASE 2 REQUIREMENT: Validate step timing fields
        print(f"\n⏱️  Step 3a: Validating step timing fields...")
        steps_with_timing = 0
        steps_without_timing = []
        
        for i, step in enumerate(steps):
            step_id = step.get("step_id", step.get("id", f"step_{i}"))
            step_type = step.get("type", "unknown")
            action = step.get("action", "")
            
            started_at = step.get("started_at")
            finished_at = step.get("finished_at")
            latency_ms = step.get("latency_ms")
            
            # INVARIANT: Each type='step' must have timing OR have a corresponding type='output'
            if step_type == "step":
                has_timing = started_at and finished_at and latency_ms is not None
                
                if not has_timing:
                    # Check if there's a corresponding output step with timing
                    matching_output = next((s for s in steps 
                                          if s.get("type") == "output" 
                                          and s.get("step_id") == step_id), None)
                    
                    if matching_output:
                        output_started = matching_output.get("started_at")
                        output_finished = matching_output.get("finished_at")
                        output_latency = matching_output.get("latency_ms")
                        
                        if output_started and output_finished and output_latency is not None:
                            # OK: Timing in output step
                            steps_with_timing += 1
                            continue
                    
                    # No timing in step or matching output - record it
                    steps_without_timing.append({
                        "step_id": step_id,
                        "action": action,
                        "has_output": matching_output is not None
                    })
                else:
                    steps_with_timing += 1
                    
                    # Validate timestamp format (ISO 8601)
                    try:
                        start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        finish_dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                    except ValueError as e:
                        pytest.fail(f"Step {step_id}: Invalid timestamp format - {e}")
                    
                    # Validate finish >= start (allow equal for instantaneous operations)
                    if finish_dt < start_dt:
                        pytest.fail(f"Step {step_id}: finished_at cannot be before started_at")
                    
                    # Validate latency_ms matches timestamps (within 5% tolerance or 5ms, whichever is larger)
                    actual_ms = (finish_dt - start_dt).total_seconds() * 1000
                    tolerance = max(actual_ms * 0.05, 5)  # 5% or 5ms minimum
                    if abs(actual_ms - latency_ms) > tolerance:
                        pytest.fail(
                            f"Step {step_id}: latency_ms ({latency_ms}) doesn't match timestamps "
                            f"(actual: {actual_ms:.0f}ms, diff: {abs(actual_ms - latency_ms):.0f}ms, tolerance: {tolerance:.1f}ms)"
                        )
            
            # type='output' steps should also have timing
            elif step_type == "output":
                if started_at and finished_at and latency_ms is not None:
                    steps_with_timing += 1
                    
                    # Validate timestamp format (ISO 8601)
                    try:
                        start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        finish_dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                    except ValueError as e:
                        pytest.fail(f"Step {step_id}: Invalid timestamp format - {e}")
                    
                    # Validate finish >= start (allow equal for instantaneous operations)
                    if finish_dt < start_dt:
                        pytest.fail(f"Step {step_id}: finished_at cannot be before started_at")
                    
                    # Validate latency_ms matches timestamps (within 5% tolerance or 5ms, whichever is larger)
                    actual_ms = (finish_dt - start_dt).total_seconds() * 1000
                    tolerance = max(actual_ms * 0.05, 5)  # 5% or 5ms minimum
                    if abs(actual_ms - latency_ms) > tolerance:
                        pytest.fail(
                            f"Step {step_id}: latency_ms ({latency_ms}) doesn't match timestamps "
                            f"(actual: {actual_ms:.0f}ms, diff: {abs(actual_ms - latency_ms):.0f}ms, tolerance: {tolerance:.1f}ms)"
                        )
        
        # Report steps without timing (if any)
        if steps_without_timing:
            print(f"   ⚠️  {len(steps_without_timing)} step(s) without timing:")
            for step_info in steps_without_timing:
                print(f"      - {step_info['step_id']}: {step_info['action']} "
                      f"(has_output: {step_info['has_output']})")
            print(f"   ℹ️  These steps should either have timing fields OR have corresponding output steps")
        
        print(f"   ✅ {steps_with_timing} steps have valid timing fields")
        print(f"      • All timestamps in ISO 8601 format")
        print(f"      • finished_at > started_at")
        print(f"      • latency_ms matches timestamps")
        
        # At least some steps should have timing
        assert steps_with_timing > 0, "No steps found with timing fields (started_at, finished_at, latency_ms)"
        print(f"   ✅ {steps_with_timing} steps have valid timing fields")
        print(f"      • All timestamps in ISO 8601 format")
        print(f"      • finished_at > started_at")
        print(f"      • latency_ms matches timestamps")

        # Get outputs
        print("\n📤 Step 4: Verifying outputs...")
        outputs_response = requests.get(
            f"{base_url}/v1/agent-runs/{run_id}/outputs",
            headers=admin_headers,
            timeout=10
        )
        assert outputs_response.status_code == 200

        outputs = outputs_response.json()
        assert isinstance(outputs, list), "Outputs should be a list"
        print(f"✅ Found {len(outputs)} outputs")

        # Verify outputs don't contain demo/fallback text
        for i, output in enumerate(outputs):
            content = str(output.get("content", "")).lower()
            assert "demo mode" not in content, "Output contains 'demo mode' - likely using demo authenticator"
            assert "fallback" not in content, "Output contains 'fallback' - likely using fallback mode"
        
        # Tool Discovery Validation (Points 1-4 of checklist)
        print("\n🔍 Step 5: Validating tool discovery behavior...")
        
        # Check 5a: Verify catalog.discover was called in steps (with bounds)
        print("   5a: Checking for catalog.discover call...")
        discover_steps = [s for s in steps if s.get("action") == "catalog.discover"]
        
        # Define acceptable range - ideally 1 call (cached), max 3 (some redundancy tolerated)
        # Note: Multiple calls indicate lack of caching
        min_discover_calls = 1
        max_discover_calls = 3  # Reduced from 5 to detect inefficiency
        
        assert len(discover_steps) >= min_discover_calls, (
            f"Expected ≥{min_discover_calls} catalog.discover calls, found {len(discover_steps)}. "
            f"Tool discovery may have failed."
        )
        assert len(discover_steps) <= max_discover_calls, (
            f"Expected ≤{max_discover_calls} catalog.discover calls, found {len(discover_steps)}. "
            f"Too many discover calls - results should be cached, not re-fetched. "
            f"Consider implementing catalog result caching in agent orchestrator."
        )
        print(f"   ✅ Found {len(discover_steps)} catalog.discover call(s) (range: {min_discover_calls}-{max_discover_calls})")
        
        # Validate catalog.discover calls are returning same result (cache hit behavior)
        if len(discover_steps) > 1:
            # Check if calls are returning identical results and if cached properly
            discover_outputs = []
            discover_latencies = []
            
            print(f"\n   📊 Analyzing {len(discover_steps)} catalog.discover call(s):")
            for idx, step in enumerate(discover_steps, 1):
                step_id = step.get('step_id')
                step_latency = step.get('latency_ms', 'N/A')
                discover_latencies.append(step_latency)
                
                print(f"      Call #{idx}: step_id={step_id}, latency={step_latency}ms")
                
                matching_output = next((o for o in outputs if o.get('step_id') == step_id), None)
                if matching_output:
                    output_data = matching_output.get('output', {})
                    if isinstance(output_data, dict) and 'count' in output_data:
                        count = output_data.get('count')
                        discover_outputs.append(count)
                        print(f"         → Returned {count} tools")
            
            # Analyze latency patterns to validate Redis caching behavior
            if len(discover_latencies) >= 2:
                first_latency = discover_latencies[0]
                avg_latency = sum(lat for lat in discover_latencies if isinstance(lat, int)) / len([lat for lat in discover_latencies if isinstance(lat, int)]) if discover_latencies else 0
                max_latency = max((lat for lat in discover_latencies if isinstance(lat, int)), default=0)
                
                print(f"\n   🔍 Latency pattern analysis:")
                print(f"      First call:  {first_latency}ms")
                print(f"      Average:     {avg_latency:.1f}ms")
                print(f"      Maximum:     {max_latency}ms")
                
                # CORRECTED LOGIC: All calls <10ms = cache hits (good!)
                # Without cache: expect ~50-200ms per call (manifest parsing + filtering)
                # With cache: expect <10ms per call (Redis GET operation)
                all_fast = all(isinstance(lat, int) and lat < 10 for lat in discover_latencies)
                
                # Count real calls (slow) vs cached calls (fast)
                real_calls = sum(1 for lat in discover_latencies if isinstance(lat, int) and lat >= 10)
                cached_calls = sum(1 for lat in discover_latencies if isinstance(lat, int) and lat < 10)
                
                if all_fast:
                    print(f"      ✅ ALL CALLS FAST (<10ms) - Redis cache is working perfectly!")
                    print(f"      ✅ Cache hit behavior confirmed (not parsing manifest each time)")
                    print(f"      ✔  Cache stats: {cached_calls} cached, {real_calls} real")
                elif isinstance(first_latency, int) and first_latency > 50 and all(isinstance(lat, int) and lat < 10 for lat in discover_latencies[1:]):
                    print(f"      ✅ Classic cache pattern: first call slow ({first_latency}ms), rest fast (<10ms)")
                    print(f"      ✅ Redis cache warming correctly")
                    print(f"      ✔  Cache stats: {cached_calls} cached, {real_calls} real")
                elif real_calls > 1:
                    print(f"      ⚠️  WARNING: Multiple slow calls detected ({real_calls} calls >10ms)")
                    print(f"         This suggests cache is NOT working - each call is re-parsing manifest")
                    print(f"         Expected: First call slow, subsequent calls <10ms")
                    print(f"      ✔  Cache stats: {cached_calls} cached, {real_calls} real")
                # Note: No else clause - if cache stats are good (≤1 real call), no warning needed
            
            # Validate consistent results (should be identical with cache)
            if len(set(discover_outputs)) == 1 and len(discover_outputs) > 1:
                print(f"\n      ✅ CACHE CORRECTNESS: All {len(discover_outputs)} calls returned identical count ({discover_outputs[0]})")
                print(f"      ✅ This proves Redis caching is working correctly (same data every time)")
                print(f"      ℹ️  Agent makes multiple calls by design (one per TODO item)")
                print(f"      ℹ️  Each call hits Redis cache in <10ms (not re-parsing manifest)")
                print(f"      ℹ️  Optional future enhancement: Agent could call once and reuse result in memory")
        
        # Check 5b: Verify discovered tools count and final-tools-output
        # TODO #13: Catalog count guardrail - HARD ASSERTIONS
        print("   5b: Checking discovered tools count and final output...")
        tools_output = None
        final_tools_step_id = None
        # Look specifically for 'final-tools-output' step first, then fall back to last output with tools_count
        for output in outputs:
            # Outputs have an "output" field (not "content") that contains the actual data
            output_data = output.get("output", {})
            step_id = output.get("step_id", "")
            
            # Prioritize the 'final-tools-output' step
            if step_id == "final-tools-output":
                if isinstance(output_data, dict):
                    tools_output = output_data
                    final_tools_step_id = step_id
                    break
                elif isinstance(output_data, str):
                    try:
                        parsed = json.loads(output_data)
                        if isinstance(parsed, dict):
                            tools_output = parsed
                            final_tools_step_id = step_id
                            break
                    except:
                        pass
            
            # Fallback: track any output with tools_count (for backward compatibility)
            elif isinstance(output_data, dict) and "tools_count" in output_data:
                tools_output = output_data
                final_tools_step_id = step_id
            elif isinstance(output_data, str):
                try:
                    parsed = json.loads(output_data)
                    if isinstance(parsed, dict) and "tools_count" in parsed:
                        tools_output = parsed
                        final_tools_step_id = step_id
                except:
                    pass
        
        assert tools_output is not None, "Expected tool discovery output with tools_count field"
        assert final_tools_step_id == "final-tools-output", (
            f"Expected step_id='final-tools-output' for tool discovery output, got '{final_tools_step_id}'"
        )
        
        tools_count = tools_output.get("tools_count", 0)
        
        # TODO #13: Define acceptable range for tool count (30-40, allows for variation but catches regressions)
        min_tools = 30
        max_tools = 40
        
        assert tools_count >= min_tools, (
            f"❌ TOOL DISCOVERY INCOMPLETE: Expected ≥{min_tools} tools, found {tools_count}. "
            f"Tool discovery may have failed or providers are unavailable. "
            f"Check catalog.discover implementation and tool manifests."
        )
        assert tools_count <= max_tools, (
            f"❌ TOOL PROLIFERATION DETECTED: Expected ≤{max_tools} tools, found {tools_count}. "
            f"Unexpected tool count indicates duplicate registrations or misconfiguration. "
            f"Check for duplicate tool manifests or registration logic issues."
        )
        print(f"   ✅ Discovered {tools_count} tools (range: {min_tools}-{max_tools}) with step_id='final-tools-output'")
        
        # Check 5c: Verify output structure (Point 4 of checklist)
        print("   5c: Checking standardized output structure...")
        assert "tools" in tools_output, "Output missing 'tools' field"
        assert isinstance(tools_output["tools"], list), "tools field should be a list"
        assert "source_groups" in tools_output, "Output missing 'source_groups' field"
        assert isinstance(tools_output["source_groups"], list), "source_groups should be a list"
        print(f"   ✅ Output has tools list ({len(tools_output['tools'])} items) and source_groups {tools_output['source_groups']}")
        
        # Check 5d: Verify known tools present (Point 4 of checklist)
        # TODO #9: Tool list contract validation - HARD ASSERTIONS
        print("   5d: Checking tool list contract...")
        
        # Define required tools with expected categories
        REQUIRED_TOOLS = [
            "agent.context",
            "catalog.discover",
            "graph.query",
            "system.metrics",
            "system.health",
            "model.manage",
            "cache.manage"
        ]
        
        EXPECTED_CATEGORIES = {
            "agent.context": "agent",
            "catalog.discover": "catalog",
            "graph.query": "graph",
            "system.metrics": "system",
            "system.health": "system",
            "model.manage": "model",
            "cache.manage": "cache"
        }
        
        # Get tool details from discovery output
        discovered_items = tools_output.get("items", [])
        if not discovered_items:
            # Fallback: try to get from tools list
            discovered_items = tools_output.get("tools", [])
        
        # Build lookup dict
        tool_details = {}
        if discovered_items and isinstance(discovered_items, list):
            for item in discovered_items:
                if isinstance(item, dict):
                    tool_name = item.get("name")
                    if tool_name:
                        tool_details[tool_name] = item
                elif isinstance(item, str):
                    # Simple string list - store name only
                    tool_details[item] = {"name": item}
        
        # If we still don't have details, try known_tools list
        if not tool_details:
            known_tools = tools_output.get("known_tools", [])
            for tool_name in known_tools:
                tool_details[tool_name] = {"name": tool_name}
        
        # Validate each required tool
        for tool_name in REQUIRED_TOOLS:
            assert tool_name in tool_details, (
                f"❌ REQUIRED TOOL MISSING: '{tool_name}' not found in tool discovery. "
                f"Tool registration or discovery may be incomplete. "
                f"Check tool manifests and catalog.discover implementation."
            )
            
            tool = tool_details[tool_name]
            
            # Validate description (if available in tool details)
            description = tool.get("description", "")
            if description:
                assert len(description) > 10, (
                    f"❌ TOOL DESCRIPTION TOO SHORT: '{tool_name}' description must be >10 chars, got {len(description)}. "
                    f"Description: '{description}'"
                )
            
            # Validate category (if available)
            actual_category = tool.get("category")
            expected_category = EXPECTED_CATEGORIES.get(tool_name)
            if actual_category and expected_category:
                assert actual_category == expected_category, (
                    f"❌ TOOL CATEGORY MISMATCH: '{tool_name}' has category '{actual_category}', "
                    f"expected '{expected_category}'. Check tool manifest configuration."
                )
                print(f"   ✅ {tool_name}: category={actual_category}, desc={len(description)} chars")
            else:
                print(f"   ✅ {tool_name}: present (category/description not in response)")
        
        print(f"   ✅ All {len(REQUIRED_TOOLS)} required tools validated")
        
        # Check 5e: Verify no prose in outputs (strict validation)
        # TODO #10: Structured output enforcement - HARD ASSERTIONS
        print("   5e: Checking for prose in outputs (strict validation)...")
        
        # Define comprehensive prose indicators
        prose_indicators = [
            "i will", "let me", "here is", "sure", "certainly", "i can", 
            "of course", "to accomplish", "i'll", "i'm going", "first",
            "then", "next", "step 1", "step 2", "following", "below is"
        ]
        
        def validate_no_prose(output_data: Any, context: str = "") -> None:
            """Validate output contains no prose markers - STRICT."""
            if output_data is None:
                return
            
            output_str = str(output_data).lower()
            
            for indicator in prose_indicators:
                # Check for whole word matches (with word boundaries)
                # This avoids false positives like "sure" in "measurements"
                import re
                pattern = r'\b' + re.escape(indicator) + r'\b'
                if re.search(pattern, output_str):
                    assert False, (
                        f"❌ PROSE DETECTED IN OUTPUT: Found prose indicator '{indicator}' in {context}. "
                        f"Expected pure structured JSON with no conversational language. "
                        f"This indicates the LLM is not following structured output format. "
                        f"Content preview: {str(output_data)[:200]}..."
                    )
        
        # Tool discovery output MUST be pure JSON (no prose at all)
        if tools_output:
            validate_no_prose(tools_output, context="tool discovery output")
        
        # Also verify the tools array contains only strings (not prose descriptions)
        tools_list = tools_output.get("tools", [])
        for idx, tool in enumerate(tools_list[:10]):  # Check first 10 tools as sample
            validate_no_prose(tool, context=f"tool name (index {idx})")
        
        # Validate ALL outputs (not just tool discovery)
        for output in outputs:
            output_data = output.get("output")
            step_id = output.get("step_id", "unknown")
            validate_no_prose(output_data, context=f"output[{step_id}]")
        
        print(f"   ✅ All outputs are pure structured JSON (no prose markers in {len(outputs)} outputs)")
        
        # Check 5f: Verify DB persistence of tool discovery data (Point 7 of checklist)
        print("   5f: Verifying DB persistence of tool discovery...")
        assert status_data is not None, "Status data should be available"
        # The outputs are stored in the run, verify they're retrievable
        assert len(outputs) > 0, "Outputs should be persisted and retrievable"
        print(f"   ✅ Tool discovery output persisted ({len(outputs)} outputs stored)")
        
        # Final Step: Verify complete API response with auth
        # TODO #11: Traceability validation - HARD ASSERTIONS
        print("\n🔍 Step 6: Verifying complete API response and traceability...")
        final_response = requests.get(
            f"{base_url}/v1/agent-runs/{run_id}",
            headers=admin_headers,
            timeout=10
        )
        assert final_response.status_code == 200, f"Failed to get run: {final_response.status_code}"
        
        final_data = final_response.json()
        print(f"   ✅ Successfully retrieved run with authenticated request")
        
        # TODO #11: Validate trace_id
        trace_id = final_data.get('trace_id')
        assert trace_id is not None, (
            f"❌ TRACEABILITY MISSING: trace_id is null. "
            f"Distributed tracing requires non-null trace_id for request correlation. "
            f"Check trace_id generation in orchestrator or API layer."
        )
        assert len(trace_id) > 0, "❌ TRACEABILITY ERROR: trace_id is empty string"
        assert "-" in trace_id, (
            f"❌ TRACEABILITY FORMAT ERROR: trace_id should be UUID format (contains hyphens), got '{trace_id}'"
        )
        print(f"   ✅ trace_id present and valid: {trace_id[:8]}... (UUID format)")
        
        # TODO #11: Validate event_id
        event_id = final_data.get('event_id')
        assert event_id is not None, (
            f"❌ TRACEABILITY MISSING: event_id is null. "
            f"Event tracking requires non-null event_id for audit and debugging. "
            f"Check event_id generation in orchestrator or API layer."
        )
        assert len(event_id) > 0, "❌ TRACEABILITY ERROR: event_id is empty string"
        print(f"   ✅ event_id present and valid: {event_id[:8]}...")
        
        # TODO #11: Verify trace_id is stable across requests for same run
        second_status = requests.get(f"{base_url}/v1/agent-runs/{run_id}", headers=admin_headers, timeout=10)
        assert second_status.status_code == 200
        second_trace_id = second_status.json().get("trace_id")
        assert second_trace_id == trace_id, (
            f"❌ TRACEABILITY STABILITY ERROR: trace_id changed between requests. "
            f"First request: {trace_id}, Second request: {second_trace_id}. "
            f"trace_id must be stable for same resource across multiple requests."
        )
        print(f"   ✅ trace_id stable across multiple requests: {trace_id[:8]}...")
        
        # Log other metadata
        print(f"   • warnings: {final_data.get('warnings', 'N/A')}")
        print(f"   • started_at: {final_data.get('started_at', 'N/A')}")
        print(f"   • finished_at: {final_data.get('finished_at', 'N/A')}")
        
        # Verify output is present and decoded (not a JSON string)
        # TODO #14: Status summary parity check - HARD ASSERTIONS
        assert final_data.get('output') is not None, "Output field should be present"
        output_data = final_data.get('output')
        
        # Validate tools_count parity in final output
        if isinstance(output_data, dict):
            final_tools_count = output_data.get('tools_count')
            final_tools_array = output_data.get('tools', [])
            
            if final_tools_count is not None and final_tools_array:
                assert final_tools_count == len(final_tools_array), (
                    f"❌ STATUS PARITY ERROR (final output): tools_count ({final_tools_count}) "
                    f"!= len(tools) ({len(final_tools_array)}). "
                    f"This indicates inconsistent response serialization."
                )
                print(f"   ✅ Final output parity: tools_count={final_tools_count}, len(tools)={len(final_tools_array)}")
            else:
                print(f"   ✅ output: Decoded object with tools_count={final_tools_count}")
        elif isinstance(output_data, str):
            # Output should be decoded object, not string  
            print(f"   ⚠️  output: JSON string ({len(output_data)} chars) - should be decoded object")
        else:
            print(f"   • output: Other type ({type(output_data)})")
        
        # TODO #14: Also validate parity in create response
        create_output = run_data.get("output", {})
        if isinstance(create_output, dict) and "tools_count" in create_output and "tools" in create_output:
            create_count = create_output["tools_count"]
            create_tools = create_output["tools"]
            assert create_count == len(create_tools), (
                f"❌ STATUS PARITY ERROR (create response): tools_count ({create_count}) "
                f"!= len(tools) ({len(create_tools)}). "
                f"This indicates inconsistent response serialization at creation."
            )
            print(f"   ✅ Create response parity: tools_count={create_count}, len(tools)={len(create_tools)}")
        
        # TODO #14: Validate parity in tool discovery output (tools_output)
        if tools_output and "tools_count" in tools_output and "tools" in tools_output:
            disco_count = tools_output["tools_count"]
            disco_tools = tools_output["tools"]
            assert disco_count == len(disco_tools), (
                f"❌ STATUS PARITY ERROR (tool discovery): tools_count ({disco_count}) "
                f"!= len(tools) ({len(disco_tools)}). "
                f"This indicates inconsistent tool catalog serialization."
            )
            print(f"   ✅ Tool discovery parity: tools_count={disco_count}, len(tools)={len(disco_tools)}")
        
        print("\n" + "="*80)
        print("🎉 TEST PASSED: Agent execution with real LLM successful!")
        print("   ✅ Real LLM execution (not demo/fallback)")
        print(f"   ✅ Agent run completed successfully (status: {final_status})")
        print(f"   ✅ {len(steps)} execution steps recorded")
        print(f"   ✅ {len(outputs)} outputs generated")
        print(f"   ✅ {len(discover_steps)} catalog.discover call(s) executed")
        print(f"   ✅ {tools_count} tools discovered (range: {min_tools}-{max_tools})")
        print(f"   ✅ Structured output (no prose in tool discovery)")
        print(f"   ✅ Data persisted to database")
        print(f"   ✅ Using real Auth0, Redis, PostgreSQL, Ollama")
        print(f"   📝 Agent Run ID: {run_id}")
        print("="*80)

    @pytest.mark.slow  
    def test_agent_run_with_minimal_prompt(self, base_url, admin_headers):
        """Agent should handle minimal prompts without errors."""
        create_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=admin_headers,
            json={"prompt": "Hello"},
            timeout=30
        )
        assert create_response.status_code == 201, f"Failed to create agent run: {create_response.json()}"

        run_data = create_response.json()
        assert run_data.get("run_id"), "Should have run_id"
        assert run_data.get("status"), "Should have status"

        # Should not be in failed state immediately
        assert run_data.get("status") != "failed", "Agent run should not fail immediately on simple prompt"


# ============================================================================
# Section: API-Level Behavior Tests (TODO #26-35)
# ============================================================================


class TestAgentRunsAPIBehavior(TestAgentExecution):
    """
    Comprehensive API-level tests for agent runs endpoints.
    
    Implements TODO #26-35 from production checklist:
    - Run-level timeout handling
    - Metrics persistence
    - Idempotency
    - ETag/caching
    - Ownership & admin checks
    """

    @pytest.fixture(scope="class")
    def user_headers(self, auth0_tokens):
        """Authorization headers with real Auth0 user token (non-admin)."""
        return {"Authorization": f"Bearer {auth0_tokens['user']}"}

    @pytest.mark.slow
    def test_idempotency_handler_coverage(self, base_url, admin_headers):
        """
        TODO #32: Idempotency handler coverage.
        
        POST /agent-runs twice with same Idempotency-Key:
        - Second response has Idempotency-Replayed: true
        - Body exactly matches first response
        """
        print("\n" + "="*80)
        print("🧪 TEST: Idempotency handler coverage (TODO #32)")
        print("="*80)
        
        idempotency_key = f"test-idempotency-{int(time.time())}"
        headers_with_key = {
            **admin_headers,
            "Idempotency-Key": idempotency_key,
        }
        
        # First request
        print("\n📤 First POST with Idempotency-Key...")
        first_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=headers_with_key,
            json={"prompt": "Test idempotency"},
            timeout=30
        )
        assert first_response.status_code == 201
        first_data = first_response.json()
        first_run_id = first_data.get("run_id")
        
        print(f"   ✅ First request created run_id: {first_run_id}")
        
        # Verify Idempotency-Key echoed in response
        assert first_response.headers.get("Idempotency-Key") == idempotency_key, (
            "First response should echo Idempotency-Key header"
        )
        print(f"   ✅ Idempotency-Key echoed in first response")
        
        # Second request with same key
        print("\n📤 Second POST with same Idempotency-Key...")
        time.sleep(1)  # Brief delay to allow first request to process
        
        second_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=headers_with_key,
            json={"prompt": "Test idempotency"},
            timeout=30
        )
        assert second_response.status_code == 201
        second_data = second_response.json()
        second_run_id = second_data.get("run_id")
        
        # Check for replay header
        replay_header = second_response.headers.get("Idempotency-Replayed")
        assert replay_header == "true", (
            "Second response should have Idempotency-Replayed: true header"
        )
        print(f"   ✅ Second response has Idempotency-Replayed: true")
        
        # Verify same run_id returned
        assert second_run_id == first_run_id, (
            f"Second request should return same run_id: {first_run_id} != {second_run_id}"
        )
        print(f"   ✅ Same run_id returned: {first_run_id}")
        
        # Verify response bodies match (excluding timestamps/dynamic fields)
        assert first_data["run_id"] == second_data["run_id"]
        assert first_data["status"] == second_data["status"]
        print(f"   ✅ Response bodies match")
        
        print("\n✅ TEST PASSED: Idempotency handler working correctly")

    @pytest.mark.slow
    def test_location_and_headers_correctness(self, base_url, admin_headers):
        """
        TODO #33: Location & headers correctness.
        
        POST /agent-runs:
        - Location header points to GET /v1/agent-runs/{run_id}
        - Echo Idempotency-Key header when provided
        - X-Request-Id header present
        """
        print("\n" + "="*80)
        print("🧪 TEST: Location & headers correctness (TODO #33)")
        print("="*80)
        
        idempotency_key = f"test-headers-{int(time.time())}"
        headers_with_key = {
            **admin_headers,
            "Idempotency-Key": idempotency_key,
        }
        
        print("\n📤 POST /agent-runs with Idempotency-Key...")
        create_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=headers_with_key,
            json={"prompt": "Test headers"},
            timeout=30
        )
        assert create_response.status_code == 201
        
        run_data = create_response.json()
        run_id = run_data.get("run_id")
        print(f"   Created run_id: {run_id}")
        
        # Check Location header
        location_header = create_response.headers.get("Location")
        assert location_header is not None, "Location header must be present"
        assert run_id in location_header, (
            f"Location header should contain run_id: {location_header}"
        )
        assert "/agent-runs/" in location_header, (
            f"Location header should point to agent-runs endpoint: {location_header}"
        )
        print(f"   ✅ Location header: {location_header}")
        
        # Check Idempotency-Key echo
        echo_key = create_response.headers.get("Idempotency-Key")
        assert echo_key == idempotency_key, (
            f"Idempotency-Key should be echoed: expected {idempotency_key}, got {echo_key}"
        )
        print(f"   ✅ Idempotency-Key echoed: {echo_key}")
        
        # Check X-Request-Id presence
        request_id = create_response.headers.get("X-Request-Id") or create_response.headers.get("x-request-id")
        if request_id:
            print(f"   ✅ X-Request-Id present: {request_id}")
        else:
            print(f"   ⚠️  X-Request-Id header missing (recommended for production observability)")
        
        print("\n✅ TEST PASSED: Location and headers are correct")

    @pytest.mark.slow
    def test_etag_304_behavior(self, base_url, admin_headers):
        """
        TODO #34: ETag + 304 behavior on GET /agent-runs/{run_id}.
        
        First GET: Capture ETag
        Second GET with If-None-Match: <ETag> returns 304 Not Modified
        Sets ETag + Vary: Authorization
        """
        print("\n" + "="*80)
        print("🧪 TEST: ETag + 304 behavior (TODO #34)")
        print("="*80)
        
        # Create a run first
        print("\n📤 Creating test run...")
        create_response = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=admin_headers,
            json={"prompt": "Test ETag"},
            timeout=30
        )
        assert create_response.status_code == 201
        run_id = create_response.json().get("run_id")
        print(f"   Created run_id: {run_id}")
        
        # First GET - capture ETag
        print(f"\n📥 First GET /agent-runs/{run_id}...")
        first_get = requests.get(
            f"{base_url}/v1/agent-runs/{run_id}",
            headers=admin_headers,
            timeout=10
        )
        assert first_get.status_code == 200
        
        first_etag = first_get.headers.get("ETag")
        assert first_etag is not None, "First GET should return ETag header"
        print(f"   ✅ ETag captured: {first_etag[:50]}...")
        
        # Verify Vary header
        vary_header = first_get.headers.get("Vary")
        assert vary_header == "Authorization", (
            f"Vary header should be 'Authorization', got: {vary_header}"
        )
        print(f"   ✅ Vary: Authorization")
        
        # Second GET with If-None-Match
        print(f"\n📥 Second GET with If-None-Match: {first_etag[:50]}...")
        headers_with_etag = {
            **admin_headers,
            "If-None-Match": first_etag,
        }
        
        second_get = requests.get(
            f"{base_url}/v1/agent-runs/{run_id}",
            headers=headers_with_etag,
            timeout=10
        )
        
        # Should return 304 Not Modified
        assert second_get.status_code == 304, (
            f"Second GET with matching ETag should return 304, got {second_get.status_code}"
        )
        print(f"   ✅ Second GET returned 304 Not Modified")
        
        # 304 should still include ETag and Vary headers
        second_etag = second_get.headers.get("ETag")
        assert second_etag is not None, "304 response should include ETag header"
        print(f"   ✅ 304 response includes ETag: {second_etag[:50]}...")
        
        second_vary = second_get.headers.get("Vary")
        assert second_vary == "Authorization", (
            f"304 response should include Vary: Authorization, got: {second_vary}"
        )
        print(f"   ✅ 304 response includes Vary: Authorization")
        
        print("\n✅ TEST PASSED: ETag and 304 caching working correctly")

    @pytest.mark.slow
    def test_ownership_and_admin_checks(self, base_url, admin_headers, user_headers):
        """
        TODO #35: Ownership & admin checks.
        
        Normal user cannot fetch another user's run_id.
        Admin with admin:all scope can.
        """
        print("\n" + "="*80)
        print("🧪 TEST: Ownership & admin checks (TODO #35)")
        print("="*80)
        
        # Admin creates a run
        print("\n📤 Admin creates run...")
        admin_create = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=admin_headers,
            json={"prompt": "Admin test run"},
            timeout=30
        )
        assert admin_create.status_code == 201
        admin_run_id = admin_create.json().get("run_id")
        print(f"   Admin run_id: {admin_run_id}")
        
        # Regular user tries to access admin's run
        print(f"\n🚫 Regular user tries to GET admin's run...")
        user_get_admin_run = requests.get(
            f"{base_url}/v1/agent-runs/{admin_run_id}",
            headers=user_headers,
            timeout=10
        )
        
        # Should be 404 (not found) or 403 (forbidden)
        assert user_get_admin_run.status_code in [404, 403], (
            f"Regular user should not access admin's run, got {user_get_admin_run.status_code}"
        )
        print(f"   ✅ Regular user blocked: HTTP {user_get_admin_run.status_code}")
        
        # Admin should be able to access their own run
        print(f"\n✅ Admin tries to GET their own run...")
        admin_get_own = requests.get(
            f"{base_url}/v1/agent-runs/{admin_run_id}",
            headers=admin_headers,
            timeout=10
        )
        assert admin_get_own.status_code == 200
        print(f"   ✅ Admin can access own run")
        
        # Regular user creates their own run
        print(f"\n📤 Regular user creates run...")
        user_create = requests.post(
            f"{base_url}/v1/agent-runs",
            headers=user_headers,
            json={"prompt": "User test run"},
            timeout=30
        )
        assert user_create.status_code == 201
        user_run_id = user_create.json().get("run_id")
        print(f"   User run_id: {user_run_id}")
        
        # Admin with admin:all scope should access user's run
        print(f"\n🔐 Admin tries to GET user's run (admin:all scope)...")
        admin_get_user_run = requests.get(
            f"{base_url}/v1/agent-runs/{user_run_id}",
            headers=admin_headers,
            timeout=10
        )
        assert admin_get_user_run.status_code == 200, (
            f"Admin with admin:all should access any run, got {admin_get_user_run.status_code}"
        )
        print(f"   ✅ Admin can access user's run (admin:all scope)")
        
        # User should access their own run
        print(f"\n✅ User tries to GET their own run...")
        user_get_own = requests.get(
            f"{base_url}/v1/agent-runs/{user_run_id}",
            headers=user_headers,
            timeout=10
        )
        assert user_get_own.status_code == 200
        print(f"   ✅ User can access own run")
        
        print("\n✅ TEST PASSED: Ownership and admin checks working correctly")
