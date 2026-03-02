"""
HTTP client and API endpoint wrappers.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import jwt
import requests
import streamlit as st
from state import Token, add_error, get_active_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/ui.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def mask_token(token: str) -> str:
    """Mask token for logging."""
    if len(token) < 20:
        return "***"
    return f"{token[:8]}...{token[-8:]}"


# API Configuration
API_BASE_PATH = "/v1"  # Centralized base path


def get_api_base() -> str:
    """Get API base URL from environment or secrets."""
    # Try environment first, then secrets, then default
    env_url = os.getenv("API_BASE_URL")
    if env_url:
        return env_url
    try:
        return st.secrets.get("API_BASE_URL", "http://localhost:8000")
    except Exception:
        return "http://localhost:8000"


def normalize_endpoint(endpoint: str) -> str:
    """
    Normalize endpoint to ensure it starts with /v1.
    Prevents manual path concatenation errors.
    """
    # Remove leading/trailing slashes
    endpoint = endpoint.strip("/")

    # If already starts with v1, add leading slash
    if endpoint.startswith("v1/") or endpoint == "v1":
        return f"/{endpoint}"

    # If starts with /, check if v1 is next
    if endpoint.startswith("/v1/") or endpoint == "/v1":
        return endpoint

    # Otherwise prepend /v1/
    return f"{API_BASE_PATH}/{endpoint}"


def is_safe_path(path: str) -> bool:
    """
    Validate that path is safe (only allows /v1/* paths).
    Prevents SSRF and host override attacks.
    """
    normalized = normalize_endpoint(path)
    return normalized.startswith("/v1/") or normalized == "/v1"


def get_headers(tenant_id: str | None = None) -> dict[str, str]:
    """
    Build request headers with auth and tenant context.

    Args:
        tenant_id: Explicit tenant ID to use. If None, uses tenant from session state.
    """
    headers = {"Content-Type": "application/json"}

    # Add auth token
    token = get_active_token()
    if token and not token.is_expired:
        headers["Authorization"] = f"Bearer {token.access_token}"

    # Add tenant context - use explicit tenant_id or get from state
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    else:
        # Try to get tenant from session state
        from state import get_state

        try:
            state = get_state()
            if state.tenant.current:
                headers["X-Tenant-ID"] = state.tenant.current
        except Exception:
            pass  # No tenant context available

    return headers


def is_transient_error(status_code: int) -> bool:
    """Check if HTTP status code represents a transient error that can be retried."""
    return status_code >= 500 or status_code in {429, 408}


def handle_response(
    response: requests.Response, endpoint: str = "", allow_retry: bool = True
) -> tuple[bool, dict[str, Any] | None, str | None, bool]:
    """
    Handle API response and return (success, data, error_message, is_retryable).
    Provides detailed error messages with context.

    Args:
        response: The requests Response object
        endpoint: The endpoint path for context in error messages
        allow_retry: Whether to mark transient errors as retryable

    Returns:
        Tuple of (success, data, error_message, is_retryable)
    """
    try:
        trace_id = response.headers.get("X-Trace-ID") or response.headers.get("X-Correlation-ID")
        is_retryable = allow_retry and is_transient_error(response.status_code)

        if response.status_code in {200, 201}:
            # Check content type to determine how to parse response
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return True, response.json(), None, False
            else:
                # For text/plain responses (like health/live), return text in a dict
                return True, {"result": response.text}, None, False
        elif response.status_code == 204:
            return True, None, None, False
        elif response.status_code == 401:
            # Detailed unauthorized error
            try:
                data = response.json() if response.text else {}
            except:
                data = {}

            error_parts = ["🔒 **Unauthorized** (HTTP 401)"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")

            error_detail = data.get("detail", "Authentication required")
            error_parts.append(f"**Reason:** {error_detail}")

            # Get tenant from current state if available
            from state import get_state

            try:
                state = get_state()
                if state.tenant.current:
                    error_parts.append(f"**Tenant:** `{state.tenant.current}`")
            except:
                pass

            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_parts.append("\n💡 **Tip:** Ensure you're logged in and have a valid token")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, False

        elif response.status_code == 403:
            # Detailed forbidden error with required scopes
            try:
                data = response.json() if response.text else {}
            except:
                data = {}

            required = data.get("required_scopes", [])

            error_parts = ["🚫 **Forbidden** (HTTP 403)"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")

            if required:
                error_parts.append(f"**Required Scopes:** `{', '.join(required)}`")

            error_detail = data.get("detail", "Insufficient permissions")
            error_parts.append(f"**Reason:** {error_detail}")

            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_parts.append("\n💡 **Tip:** Contact your admin to request the required permissions")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, False

        elif response.status_code == 404:
            # Detailed not found error
            try:
                data = response.json() if response.text else {}
            except:
                data = {}

            error_parts = ["🔍 **Not Found** (HTTP 404)"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")

            error_detail = data.get("detail", "Resource not found")
            error_parts.append(f"**Reason:** {error_detail}")

            # Get tenant from current state if available
            from state import get_state

            try:
                state = get_state()
                if state.tenant.current:
                    error_parts.append(f"**Tenant:** `{state.tenant.current}`")
            except:
                pass

            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_parts.append("\n💡 **Tip:** Verify the resource exists and you have access to the correct tenant")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, False

        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            error_parts = ["⏸️ **Rate Limit Exceeded** (HTTP 429)", f"**Retry After:** {retry_after} seconds"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")
            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, is_retryable

        elif response.status_code >= 500:
            # Server error with context
            try:
                data = response.json() if response.text else {}
            except:
                data = {}

            error_parts = [f"⚠️ **Service Error** (HTTP {response.status_code})"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")

            error_detail = data.get("detail", "Internal server error")
            error_parts.append(f"**Reason:** {error_detail}")

            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_parts.append("\n💡 **Tip:** Please try again later or contact support with the Trace ID")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, is_retryable
        else:
            # Generic error with full context
            error_parts = [f"❌ **Request Failed** (HTTP {response.status_code})"]
            if endpoint:
                error_parts.append(f"**Endpoint:** `{endpoint}`")
            if trace_id:
                error_parts.append(f"**Trace ID:** `{trace_id}`")

            error_msg = "\n".join(error_parts)
            add_error(error_msg, response.text, trace_id)
            return False, None, error_msg, False
    except Exception as e:
        error_msg = f"Response parsing error: {e!s}"
        add_error(error_msg)
        return False, None, error_msg, False


def make_request(
    method: str,
    endpoint: str,
    data: dict | None = None,
    params: dict | None = None,
    tenant_id: str | None = None,
    timeout: int = 30,
) -> tuple[bool, dict[str, Any] | None, str | None, bool]:
    """
    Make HTTP request with standard error handling.
    Automatically normalizes endpoint to include /v1 prefix.

    Returns:
        Tuple of (success, data, error_message, is_retryable)
    """
    # Normalize endpoint to ensure /v1 prefix
    normalized_endpoint = normalize_endpoint(endpoint)

    # Security check
    if not is_safe_path(normalized_endpoint):
        error_msg = f"Invalid endpoint path: {endpoint}. Only /v1/* paths are allowed."
        add_error(error_msg)
        return False, None, error_msg, False

    base_url = get_api_base()
    url = f"{base_url}{normalized_endpoint}"
    headers = get_headers(tenant_id)

    # Log request (with masked token)
    masked_headers = headers.copy()
    if "Authorization" in masked_headers:
        masked_headers["Authorization"] = f"Bearer {mask_token(headers['Authorization'].split(' ')[1])}"
    logger.info(f"{method} {url} - Headers: {masked_headers}")

    try:
        response = requests.request(method=method, url=url, json=data, params=params, headers=headers, timeout=timeout)
        return handle_response(response, normalized_endpoint)
    except requests.Timeout:
        error_msg = f"⏱️ **Request Timeout**\n**Endpoint:** `{normalized_endpoint}`\n**Timeout:** {timeout}s"
        add_error(error_msg)
        return False, None, error_msg, True  # Timeouts are retryable
    except requests.ConnectionError:
        error_msg = f"🔌 **Connection Error**\n**Endpoint:** `{normalized_endpoint}`\n💡 **Tip:** Is the API running at {base_url}?"
        add_error(error_msg)
        return False, None, error_msg, True  # Connection errors are retryable
    except Exception as e:
        error_msg = f"❌ **Request Failed**\n**Endpoint:** `{normalized_endpoint}`\n**Error:** {e!s}"
        add_error(error_msg)
        return False, None, error_msg, False


def make_request_compat(
    method: str,
    endpoint: str,
    data: dict | None = None,
    params: dict | None = None,
    tenant_id: str | None = None,
    timeout: int = 30,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Compatibility wrapper that returns 3-tuple for backward compatibility.
    Use make_request() directly if you need retry information.
    """
    success, data, error, _ = make_request(method, endpoint, data, params, tenant_id, timeout)
    return success, data, error


# Auth0 Token Functions
def fetch_auth0_token(
    grant_type: str,
    client_id: str,
    client_secret: str,
    username: str | None = None,
    password: str | None = None,
    scope: str | None = None,
) -> tuple[bool, Token | None, str | None]:
    """Fetch token from Auth0."""
    # Try environment first, then secrets
    domain = os.getenv("AUTH0_DOMAIN")
    audience = os.getenv("AUTH0_AUDIENCE")

    # Fallback to secrets if env vars not set
    try:
        if not domain:
            domain = st.secrets.get("AUTH0_DOMAIN")
        if not audience:
            audience = st.secrets.get("AUTH0_AUDIENCE")
    except Exception:
        pass  # Secrets file may not exist

    if not domain or not audience:
        return False, None, "Auth0 configuration missing (AUTH0_DOMAIN and AUTH0_AUDIENCE required)"

    url = f"https://{domain}/oauth/token"

    if grant_type == "password":
        payload = {
            "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
            "username": username,
            "password": password,
            "audience": audience,
            "realm": "Username-Password-Authentication",
            "scope": scope,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    else:  # client_credentials
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            access_token = data["access_token"]
            expires_in = data["expires_in"]

            # Decode token to get claims
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            subject = decoded.get("sub", "")
            scopes = decoded.get("scope", "").split() if decoded.get("scope") else []
            expires_at = datetime.now() + timedelta(seconds=expires_in)

            token = Token(access_token=access_token, expires_at=expires_at, subject=subject, scopes=scopes)

            logger.info(f"Token fetched successfully for {subject}")
            return True, token, None
        else:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error_description", error_data.get("error", "Token fetch failed"))
            logger.error(f"Auth0 token fetch failed: {error_msg}")
            return False, None, error_msg
    except Exception as e:
        error_msg = f"Auth0 request failed: {e!s}"
        logger.error(error_msg)
        return False, None, error_msg


# API Endpoint Wrappers


# Health Endpoints
def get_health_live() -> tuple[bool, dict | None, str | None]:
    """Get liveness health check."""
    return make_request_compat("GET", "/health/live")


def get_health_ready() -> tuple[bool, dict | None, str | None]:
    """Get readiness health check."""
    return make_request_compat("GET", "/health/ready")


def get_health_startup() -> tuple[bool, dict | None, str | None]:
    """Get startup health check."""
    return make_request_compat("GET", "/health/startup")


def get_health_components() -> tuple[bool, dict | None, str | None]:
    """Get detailed component health checks."""
    return make_request_compat("GET", "/health/components")


def get_health_component(name: str) -> tuple[bool, dict | None, str | None]:
    """Get specific component health check."""
    return make_request_compat("GET", f"/health/components/{name}")


# Auth Endpoints
def get_auth_me() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/auth/me")


# Tenants Endpoints (Admin)
def list_tenants(page: int = 1, size: int = 50) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/tenants", params={"page": page, "size": size})


def create_tenant(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/tenants", data=data)


def get_tenant(tenant_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/admin/tenants/{tenant_id}")


def update_tenant(tenant_id: str, data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("PATCH", f"/admin/tenants/{tenant_id}", data=data)


def delete_tenant(tenant_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/admin/tenants/{tenant_id}")


# Models & Providers Endpoints
def list_providers() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/models/providers")


def register_provider(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/models/providers/register", data=data)


def set_default_provider(provider_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("PUT", "/admin/models/providers/default", data={"provider_id": provider_id})


def get_main_provider() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/models/providers/main")


def get_provider(provider_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/admin/models/providers/{provider_id}")


def update_provider(provider_id: str, data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("PATCH", f"/admin/models/providers/{provider_id}", data=data)


def delete_provider(provider_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/admin/models/providers/{provider_id}")


# Model Instances
def list_model_instances(params: dict | None = None) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/models/instances", params=params)


def create_model_instance(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/models/instances", data=data)


def get_model_instance(instance_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/models/instances/{instance_id}")


def delete_model_instance(instance_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/models/instances/{instance_id}")


def test_model_instance(instance_id: str, data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", f"/models/instances/{instance_id}/tests", data=data)


def get_model_defaults() -> tuple[bool, dict | None, str | None]:
    # Debug: Log token info before making request
    token = get_active_token()
    if token:
        logger.info(
            f"get_model_defaults: Using token with scopes: {token.scopes}, expires at: {token.expires_at}, is_expired: {token.is_expired}"
        )
    else:
        logger.warning("get_model_defaults: No active token found!")

    return make_request_compat("GET", "/models/defaults")


def set_model_defaults(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("PATCH", "/models/defaults", data=data)


# Tools Endpoints
def list_tools() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/tools")


def get_tool_schema(tool_name: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/tools/{tool_name}")


def invoke_tool(tool_name: str, data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", f"/tools/{tool_name}/invocations", data=data)


def get_tool_invocation(tool_name: str, eid: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/tools/{tool_name}/invocations/{eid}")


# Agent Sessions & Runs
def create_agent_session(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/agents/sessions", data=data)


def list_agent_sessions(params: dict | None = None) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/agents/sessions", params=params)


def get_agent_session(session_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/agents/sessions/{session_id}")


def cancel_agent_session(session_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/agents/sessions/{session_id}")


def list_session_steps(session_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/agents/sessions/{session_id}/steps")


def add_session_step(session_id: str, data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", f"/agents/sessions/{session_id}/steps", data=data)


def send_agent_message(
    session_id: str, message: str, token: str | None = None
) -> tuple[bool, dict | None, str | None]:
    """Send a message to an agent session."""
    data = {"message": message}
    return make_request_compat("POST", f"/agents/sessions/{session_id}/messages", data=data)


# Agent Runs
def create_agent_run(data: dict, tenant_id: str | None = None) -> tuple[bool, dict | None, str | None]:
    """Create an agent run. Auto-resolves default model if not specified."""
    return make_request_compat("POST", "/agent-runs", data=data, tenant_id=tenant_id)


def get_agent_run(run_id: str, tenant_id: str | None = None) -> tuple[bool, dict | None, str | None]:
    """Get agent run status and results."""
    return make_request_compat("GET", f"/agent-runs/{run_id}", tenant_id=tenant_id)


# Jobs Endpoints
def list_jobs(params: dict | None = None) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/jobs", params=params)


def create_job(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/jobs", data=data)


def get_job(job_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/jobs/{job_id}")


def cancel_job(job_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/jobs/{job_id}")


def get_job_events(job_id: str, last_event_id: str | None = None) -> tuple[bool, dict | None, str | None]:
    params = {"last_event_id": last_event_id} if last_event_id else None
    return make_request_compat("GET", f"/jobs/{job_id}/events", params=params)


# Admin Jobs
def list_admin_jobs(params: dict | None = None) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/jobs", params=params)


def create_admin_job(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/jobs", data=data)


def cancel_admin_job(job_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/admin/jobs/{job_id}")


# Admin Processes
def list_processes() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/processes")


def stop_process(pid: int) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/admin/processes/{pid}")


def get_manifest_history() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/processes/history/manifests")


def get_process_history() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/processes/history/processes")


# Admin Ops
def auto_start_override(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/ops/auto-start-override", data=data)


def preview_staged_manifests() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/ops/preview-staged")


# Built-in Manifests
def list_builtin_manifests() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/models/manifests/builtins")


def stage_builtin_manifest(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/models/manifests/builtins/staged", data=data)


def activate_builtin_manifest(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/models/manifests/builtins/activations", data=data)


def rollback_builtin_manifest(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/models/manifests/builtins/rollbacks", data=data)


def get_builtin_manifest_history() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/models/manifests/builtins/history")


# Admin DB Operations
def create_db_job(data: dict) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("POST", "/admin/db/jobs", data=data)


def get_db_job(job_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", f"/admin/db/jobs/{job_id}")


def cancel_db_job(job_id: str) -> tuple[bool, dict | None, str | None]:
    return make_request_compat("DELETE", f"/admin/db/jobs/{job_id}")


def get_db_counts() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/admin/db/counts")


# Explore
def get_root() -> tuple[bool, dict | None, str | None]:
    """Get API root - note this endpoint doesn't have /v1 prefix."""
    # Root endpoint is an exception - it's at / not /v1/
    base_url = get_api_base()
    url = f"{base_url}/v1/"
    try:
        response = requests.get(url, timeout=5)
        success, data, error, _ = handle_response(response)  # Unpack 4 values, ignore is_retryable
        return success, data, error
    except Exception as e:
        return False, None, f"Failed to connect to API root: {e!s}"


def get_openapi_spec() -> tuple[bool, dict | None, str | None]:
    return make_request_compat("GET", "/openapi.json")


# Health & Connectivity Test
def run_self_test() -> tuple[bool, list[str]]:
    """
    Run self-test to verify API connectivity.
    Returns (success, list_of_messages).

    FIXED: Improved error handling and connection resilience.
    """
    messages = []
    all_ok = True

    base_url = get_api_base()
    messages.append(f"🔍 Testing API at: {base_url}")

    # Test 1: Check /v1/health/live (most basic check)
    success, data, error = get_health_live()
    if success:
        messages.append("✅ Health check (/v1/health/live) passed")
    else:
        error_msg = str(error) if error else "Unknown error"
        # Check if it's a connection error
        if "Connection" in error_msg or "refused" in error_msg.lower():
            messages.append(f"🔌 **Connection Error**: Cannot reach API at {base_url}")
            messages.append("💡 **Troubleshooting**:")
            messages.append("   - Check if API service is running: `docker compose ps app`")
            messages.append("   - Verify API_BASE_URL is correct")
            messages.append("   - Check network connectivity between UI and API containers")
        elif "Timeout" in error_msg or "timed out" in error_msg.lower():
            messages.append(f"⏱️ **Timeout Error**: API at {base_url} is not responding")
            messages.append("💡 **Troubleshooting**:")
            messages.append("   - API may be starting up (wait a few moments)")
            messages.append("   - Check API logs: `docker compose logs app`")
        else:
            messages.append(f"❌ Health check failed: {error_msg}")
        all_ok = False

    # Test 2: Check /v1/ root (only if health check passed)
    if all_ok:
        success, _data, error = get_root()
        if success:
            messages.append("✅ API root (/v1/) reachable")
        else:
            error_msg = str(error) if error else "Unknown error"
            messages.append(f"⚠️ API root check failed: {error_msg}")
            # Don't fail overall if root fails but health passed
            # This allows the UI to work even if root endpoint has issues

    # If all checks failed, provide helpful guidance
    if not all_ok:
        messages.append("")
        messages.append("📋 **Next Steps:**")
        messages.append("1. Verify API service is running: `docker compose ps app`")
        messages.append("2. Check API logs: `docker compose logs app`")
        messages.append("3. Verify API_BASE_URL environment variable")
        messages.append("4. Try rebuilding: `docker compose up -d --build --remove-orphans app`")

    return all_ok, messages
