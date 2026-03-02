"""
Configuration for the Cineca Agentic Platform.

Values are loaded from environment variables (and `.env` if present)
using pydantic-settings. Sensible defaults are provided for local dev.
"""

from __future__ import annotations

import json
import os
from contextlib import suppress
from typing import Any

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:  # pragma: no cover - optional dependency already in requirements.txt
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:  # pragma: no cover - guard against runtime import issues
    with suppress(Exception):
        load_dotenv()


class Settings(BaseSettings):
    # ---------------- App ----------------
    APP_ENV: str = Field(default="dev", description="Environment name (dev/stage/prod)")
    APP_HOST: str = Field(default="0.0.0.0")  # nosec B104
    APP_PORT: int = Field(default=8000)
    LOG_LEVEL: str = Field(default="INFO")
    ENABLE_DOCS: bool = Field(default=True, description="Enable Swagger/Redoc in non-prod")

    # ---------------- CORS ----------------
    # Comma-separated strings; FastAPI app splits them
    CORS_ALLOWED_ORIGINS: str = Field(default="*")
    CORS_ALLOWED_METHODS: str = Field(default="GET,POST,PUT,DELETE,OPTIONS")
    CORS_ALLOWED_HEADERS: str = Field(default="Authorization,Content-Type")

    # ---------------- Memgraph ----------------
    MG_HOST: str = Field(default="memgraph")
    MG_PORT: int = Field(default=7687)
    MG_USER: str = Field(default="")
    MG_PASSWORD: str = Field(default="")
    MG_TLS: bool = Field(default=False)

    # ---------------- PostgreSQL ----------------
    DB_HOST: str = Field(default="postgres", description="PostgreSQL host")
    DB_PORT: int = Field(default=5432, description="PostgreSQL port")
    DB_NAME: str = Field(default="cineca_platform", description="Database name")
    DB_USER: str = Field(default="cineca_user", description="Database user")
    DB_PASSWORD: str = Field(default="change_me_now", description="Database password - CHANGE IN PRODUCTION!")
    DB_SSLMODE: str = Field(
        default="disable", description="SSL mode: disable, allow, prefer, require, verify-ca, verify-full"
    )
    DB_POOL_SIZE: int = Field(default=10, description="Connection pool size")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Connection pool timeout (seconds)")
    DB_ECHO: bool = Field(default=False, description="Echo SQL statements (debug)")
    DB_POOL_RECYCLE: int = Field(default=3600, description="Recycle connections after N seconds")
    DB_POOL_PRE_PING: bool = Field(default=True, description="Test connections before checkout")

    # ---------------- Cache / Rate-limit ----------------
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    RATE_LIMIT_BACKEND: str = Field(default="redis", description="memory | redis")
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable global rate limiting middleware and helpers")
    RATE_LIMIT_DEFAULT_LIMIT: int = Field(default=60, description="Default requests per window")
    RATE_LIMIT_DEFAULT_WINDOW: int = Field(default=60, description="Default window length in seconds")

    # ---------------- Production Security ----------------
    ENABLE_SECURITY_HEADERS: bool = Field(default=True, description="Enable security headers middleware")
    ENABLE_HSTS: bool = Field(default=True, description="Enable Strict-Transport-Security header")
    HSTS_MAX_AGE: int = Field(default=31536000, description="HSTS max-age in seconds (default: 1 year)")
    CSP_POLICY: str | None = Field(
        default=None, description="Content-Security-Policy header value (default: restrictive)"
    )
    SECURE_COOKIES: bool = Field(default=False, description="Enable secure flag on cookies (set true in production)")
    TRUST_PROXY: bool = Field(default=False, description="Trust X-Forwarded-* headers from reverse proxy")

    # ---------------- Observability ----------------
    PROMETHEUS_METRICS_ENABLED: bool = Field(default=True)
    OTEL_SERVICE_NAME: str = Field(default="cineca-agentic-platform")
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    OTEL_TRACES_SAMPLER: str = Field(default="parentbased_always_on")
    OTEL_RESOURCE_ATTRIBUTES: str | None = Field(default=None)

    # ---------------- Security / Auth ----------------
    # Legacy local JWT settings (deprecated when using OIDC)
    JWT_SECRET: str = Field(default="REPLACE_ME")  # replace in production
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    # OIDC Resource Server Settings
    OIDC_ISSUER: str | None = Field(default=None, description="OIDC issuer URL (iss) to validate against")
    OIDC_AUDIENCE: str | None = Field(default=None, description="API audience to validate (aud)")
    OIDC_JWKS_URL: str | None = Field(
        default=None, description="JWKS URL for issuer (https://issuer/.well-known/jwks.json or file path in tests)"
    )
    OIDC_TIMEOUT_S: int = Field(default=5, description="Timeout (seconds) for OIDC HTTP calls")
    DOCS_AUTH: str = Field(default="internal", description="internal|public — controls Swagger 'Try it out'")
    ENABLE_BFF: bool = Field(default=False, description="Enable browser-oriented login/logout redirect endpoints")

    # ---------------- Admin Audit ----------------
    ADMIN_DEFAULT_TENANT_ID: str = Field(
        default="tenant-admin-root",
        description="Default tenant ID for admin audit context (X-Tenant-Id header). Used when header is not explicitly provided.",
    )

    # Whether to enable demo auth routes (refresh/logout). Deprecated; no-op.
    ENABLE_AUTH_DEMO_ROUTES: bool = Field(default=False, description="[Deprecated] Demo auth endpoints are removed")
    # Header name used for request id propagation
    REQUEST_ID_HEADER: str = Field(default="X-Request-ID", description="Header name for propagated request id")
    # Optional JWT hardening: expected issuer and audience for incoming tokens. If set, tokens must match.
    JWT_ISSUER: str | None = Field(
        default=None, description="Expected 'iss' claim value for JWTs (enforce when set)"
    )
    JWT_AUDIENCE: str | None = Field(
        default=None, description="Expected 'aud' claim value for JWTs (enforce when set)"
    )

    INTENT_FILTER_ENABLED: bool = Field(default=True)
    OUTPUT_GUARD_ENABLED: bool = Field(default=True)
    PII_SCRUBBING_ENABLED: bool = Field(default=True)

    # ---------------- Authorization / Permissions ----------------
    # Comma-separated allowlist of tool short names considered safe for basic users
    SAFE_TOOLS: str = Field(
        default="system.health,system.status,system.metrics,graph.schema,graph.search",
        description="Comma-separated list of tool names allowed with tools:basic",
    )

    # ---------------- LLM / Models (optional) ----------------
    LLM_PROVIDER: str | None = Field(default=None)  # e.g., "openai"
    LLM_MODEL: str | None = Field(default=None)  # e.g., "gpt-4o-mini"
    OPENAI_API_KEY: str | None = Field(default=None)
    # Local model discovery directory (mounted into container). We purposely keep this
    # simple (string path) instead of a list for now; discovery logic will ignore when
    # directory does not exist.
    MODELS_DIR: str = Field(
        default="/models", description="Filesystem directory containing discoverable local model artifacts (.gguf etc.)"
    )
    DEMO_MODE: bool = Field(
        default=False, description="Enable demo fallback responses when no providers are registered"
    )

    # Egress controls
    EGRESS_ALLOWLIST: str | None = Field(
        default=None, description="Comma-separated host[:port] allow-list for outbound provider base_url calls"
    )
    HAS_GPU: bool = Field(default=False, description="Whether this host has GPU available (set True on GPU servers)")
    # Comma-separated list of named LLM endpoints in the form "name=url",
    # e.g. "planner=http://planner:8000,workerA=http://worker-a:8000".
    # Parsed by Orchestrator.from_env() to create multiple clients.
    LLM_CLIENTS: str | None = Field(
        default=None, description="Comma-separated named LLM endpoints, e.g. 'planner=http://...,workerA=http://...'')"
    )

    # Optional richer configuration fields (accept JSON or simple key=value lists)
    # Mapping of tool/action -> preferred LLM name
    LLM_TOOL_PREFERENCES: dict | None = Field(
        default=None,
        description='JSON or comma-separated mapping, e.g. "{"search":"workerA"}" or "search=workerA,generate=workerB"',
    )
    # Mapping of agent role -> system prompt prefix (string)
    LLM_AGENT_ROLES: dict | None = Field(default=None, description="JSON mapping of role->system_prompt")
    # ACL mapping: either client->tools (pipe separated) or tool->clients
    LLM_TOOL_ACL: dict | None = Field(
        default=None, description="ACL mapping as JSON or comma pairs, use | to separate list items"
    )

    # ---------------- Ollama integration ----------------
    OLLAMA_BASE_URL: str | None = Field(
        default=None, description="Override base URL for Ollama provider (defaults vary for container vs host)"
    )
    OLLAMA_TIMEOUT_SECS: int = Field(default=180, description="Connect/read timeout (seconds) for Ollama HTTP calls - increased for model loading")
    LLM_WARMUP_TIMEOUT: int = Field(default=300, description="Warmup timeout (seconds) for first LLM call - needs to be high for cold model loads")
    OLLAMA_MODEL_MAP: dict | None = Field(
        default=None, description="JSON mapping of logical model ids to Ollama tags"
    )
    DEFAULT_MODEL_NAME: str = Field(
        default="phi3:mini",
        description=(
            "EMERGENCY FALLBACK ONLY: Used when PostgreSQL is unreachable. "
            "Normal operation uses PostgreSQL model_instances table as the single source of truth. "
            "When this fallback is active, health will be marked as degraded and WARN logs will be emitted."
        )
    )
    
    # Default Model Resolver (DMR) configuration
    DEFAULT_MODEL_CACHE_TTL_SECONDS: int = Field(
        default=900, description="Redis cache TTL for default model resolution (seconds, default: 15 min)"
    )
    DEFAULT_MODEL_ALLOW_ENV_FALLBACK: bool = Field(
        default=True, description="Allow fallback to DEFAULT_MODEL_NAME when DB unreachable (emergency mode)"
    )
    
    # Model Warmup configuration
    LLM_WARMUP_RETRY_MAX: int = Field(
        default=3, description="Maximum number of warmup retry attempts on failure"
    )
    LLM_WARMUP_RETRY_DELAY: int = Field(
        default=10, description="Delay between warmup retry attempts (seconds)"
    )
    
    # Provider Health configuration
    PROVIDER_HEALTH_REFRESH_INTERVAL: int = Field(
        default=3600, description="Interval for background provider health refresh (seconds, default: 1 hour)"
    )
    PROVIDER_HEALTH_TTL: int = Field(
        default=7200, description="TTL for provider health in Redis (seconds, default: 2 hours)"
    )
    
    # ---------------- LLM Execution Limits ----------------
    LLM_DEVICE: str = Field(
        default="cpu",
        description="Device for LLM execution: 'cpu' or 'gpu'. Affects performance and resource usage."
    )
    LLM_MAX_TOKENS: int = Field(
        default=2048,
        description="Maximum tokens per LLM request. Limits response length and prevents excessive costs/latency."
    )
    LLM_MAX_STEPS: int = Field(
        default=10,
        description="Maximum orchestration steps per agent run. Prevents infinite loops and excessive LLM calls."
    )
    
    # ---------------- Memgraph Response Builder Configuration ----------------
    # Production vs Test Configuration Guidelines:
    #
    # PRODUCTION (recommended):
    #   MEMGRAPH_RESPONSE_MODE=llm-best-effort (default)
    #   MEMGRAPH_BUILDER_LLM_TIMEOUT_MS=5000 (5s, fast fallback)
    #   - Provides best UX: tries LLM for rich responses, falls back gracefully
    #   - degraded=True and used_fallback=True flags indicate fallback was used
    #
    # TESTING:
    #   Option A: MEMGRAPH_RESPONSE_MODE=fallback-only
    #     - Fast, deterministic tests with 0 LLM calls
    #     - Validates graph queries without LLM latency
    #
    #   Option B: MEMGRAPH_RESPONSE_MODE=llm-required
    #     - Strict validation that LLM is functioning
    #     - Timeout causes step/run failure (status="failed")
    #
    #   Option C: llm-best-effort with MEMGRAPH_BUILDER_LLM_TIMEOUT_MS=500
    #     - Very short timeout forces fallback, validates fallback path
    #
    MEMGRAPH_RESPONSE_MODE: str = Field(
        default="llm-best-effort",
        description=(
            "Memgraph response builder mode. Valid values:\n"
            "  'fallback-only' - Never call LLM, always use deterministic summarizer.\n"
            "                    Metrics: llm_attempted_calls=0, llm_successful_calls=0\n"
            "  'llm-best-effort' - Try LLM with timeout, fall back on failure (DEFAULT).\n"
            "                      Sets degraded=True, used_fallback=True on fallback.\n"
            "  'llm-required' - LLM is required; timeout/error marks step as failed.\n"
            "                   status='failed' if LLM fails."
        )
    )
    MEMGRAPH_BUILDER_LLM_TIMEOUT_MS: int = Field(
        default=180000,
        description=(
            "Timeout (ms) for memgraph response builder LLM calls.\n"
            "Separate from run/step timeouts. Default: 180000ms (3 minutes).\n"
            "\n"
            "Recommended values:\n"
            "  CPU environments: 120000-180000ms (2-3 minutes for slow inference)\n"
            "  GPU environments: 10000-30000ms (10-30s for fast inference)\n"
            "  Testing fallback: 500-1000ms (force fallback path testing)\n"
            "\n"
            "In llm-best-effort mode, exceeding this timeout triggers fallback.\n"
            "In llm-required mode, exceeding this timeout causes failure."
        )
    )

    @field_validator("MEMGRAPH_RESPONSE_MODE", mode="before")
    @classmethod
    def validate_memgraph_response_mode(cls, v: Any) -> str:
        """Validate MEMGRAPH_RESPONSE_MODE is one of the allowed values."""
        valid_modes = {"fallback-only", "llm-best-effort", "llm-required"}
        if v is None:
            return "llm-best-effort"
        normalized = str(v).strip().lower()
        if normalized not in valid_modes:
            import structlog
            log = structlog.get_logger()
            log.warning(
                "config.memgraph_response_mode.invalid",
                provided=v,
                valid_modes=list(valid_modes),
                fallback="llm-best-effort"
            )
            return "llm-best-effort"
        return normalized
    
    # Tool Discovery configuration
    CATALOG_CACHE_TTL: int = Field(
        default=1800, description="TTL for tool catalog cache (seconds, default: 30 min)"
    )
    
    # Provider Health Scheduler configuration
    PROVIDER_HEALTH_REFRESH_INTERVAL: int = Field(
        default=3600, description="Interval for background provider health refresh (seconds, default: 1 hour)"
    )
    PROVIDER_HEALTH_TTL: int = Field(
        default=7200, description="TTL for provider health cache in Redis (seconds, default: 2 hours)"
    )
    SCHEDULER_ENABLED: bool = Field(
        default=True, description="Enable background provider health scheduler (default: enabled)"
    )

    # ---------------- Built-in LLM manifest ----------------
    # Database-based manifest system (removed file-based YAML approach)
    # Manifests are managed via /admin/models/manifests/builtins API
    # Model instances auto-created on manifest activation

    # ---------------- Internal Operations (UI Override) ----------------
    INTERNAL_UI_OVERRIDE_ALLOWED: bool = Field(
        default=True, description="Whether internal UI can override auto-start behavior (default: enabled)"
    )
    INTERNAL_UI_OVERRIDE_TTL_SECONDS: int = Field(
        default=600, description="TTL in seconds for UI override setting (default: 10 minutes; clamped 60-3600)"
    )
    INTERNAL_PREVIEW_CACHE_TTL_SECONDS: int = Field(
        default=90, description="TTL in seconds for preview-staged cache (default: 90s)"
    )
    INTERNAL_TOKEN_MAX_TTL_SECONDS: int = Field(
        default=3600, description="Maximum TTL for tokens on internal endpoints (default: 1 hour)"
    )
    FEATURE_MEMGRAPH_COUNTS: bool = Field(
        default=True, description="Enable Memgraph counts endpoint (returns 501 when disabled)"
    )
    INTERNAL_DB_UTILS_ENABLED: bool = Field(
        default=False, description="Enable DB job creation/population utilities (default: disabled for safety)"
    )
    BUILTIN_AUTO_START_MAX_CONCURRENT: int = Field(
        default=3, description="Maximum number of concurrent auto-started models"
    )
    BUILTIN_AUTO_START_MIN_FREE_GB: float = Field(
        default=2.0, description="Minimum free memory (GB) required to start another model; best-effort check"
    )
    # Optional comma-separated whitelist of builtin ids allowed to auto-start (empty = allow all)
    BUILTIN_AUTO_START_WHITELIST: str | None = Field(
        default=None, description="Comma-separated builtin ids allowed to auto-start; empty allows all"
    )
    # Short-lived Redis TTL (seconds) used for UI activation override. Increase if your UI->API latency may exceed this.
    BUILTIN_AUTO_START_OVERRIDE_TTL: int = Field(
        default=60, description="TTL (seconds) for the auto-start UI override key stored in Redis"
    )
    # Whether to allow the Streamlit UI to request an override of auto-start behavior.
    # If False (default), the UI checkbox will be allowed in the front-end but the backend
    # will ignore any UI-set override unless this is explicitly enabled by operators.
    BUILTIN_AUTO_START_ALLOW_UI_OVERRIDE: bool = Field(
        default=False, description="If true, allow the UI override to enable auto-start during activation"
    )

    # ---------------- Background jobs ----------------
    SCHEDULER_ENABLED: bool = Field(default=True)
    SCHEDULED_HEALTHCHECK_INTERVAL_SECONDS: int = Field(default=60)
    SCHEDULED_CLEANUP_INTERVAL_SECONDS: int = Field(default=3600)

    # ---------------- i18n & data generation ----------------
    DEFAULT_LOCALE: str = Field(default="en")
    FAKER_LOCALE: str = Field(default="en_US")

    # ---------------- Service limits / safety rails ----------------
    MAX_GRAPH_RESULT_NODES: int = Field(default=1000)
    MAX_GRAPH_RESULT_EDGES: int = Field(default=2000)
    MAX_QUERY_COST: int = Field(default=10_000)

    # ---------------- Data retention ----------------
    RETENTION_DAYS: int = Field(default=30)
    # Idempotency TTL seconds for POST replay windows (default 24h)
    IDEMPOTENCY_TTL_SECONDS: int = Field(default=24 * 3600)

    # ---------------- Backup ----------------
    BACKUP_DIR: str = Field(default="backups", description="Directory for database/application backups")
    BACKUP_RETENTION_DAYS: int = Field(default=14, description="Days to retain backups before purging")
    BACKUP_SCRIPT: str = Field(default="", description="Optional custom backup script path")

    # ---------------- Job Storage (Redis) ----------------
    # Job storage backend: 'memory' (in-process dict) or 'redis' (persistent)
    JOB_STORE_BACKEND: str = Field(
        default="memory",
        description="Job storage backend: 'memory' or 'redis'. Use 'redis' for production, 'memory' for testing.",
    )

    # PostgreSQL backend for jobs (feature flag)
    USE_POSTGRES_JOBS: bool = Field(
        default=False,
        description="Enable PostgreSQL backend for jobs API. When true, uses PostgreSQL + Redis for jobs instead of memory/Redis store. Requires running Alembic migrations first.",
    )

    # Job record retention in Redis (days) - auto-expire via TTL
    JOB_TTL_DAYS: int = Field(
        default=10, description="Job retention in Redis (days). Jobs auto-expire after this period."
    )
    # Deprecated: Use JOB_TTL_DAYS instead
    JOB_RETENTION_DAYS: int = Field(default=30, description="DEPRECATED: Use JOB_TTL_DAYS")

    # SSE event ring buffer size per job (capped LIST in Redis)
    SSE_RING_SIZE: int = Field(default=100, description="Max events stored per job for SSE Last-Event-ID resume")

    # Idempotency key TTL (hours) - how long to remember duplicate POST requests
    IDEMPOTENCY_TTL_HOURS: int = Field(default=24, description="Idempotency key expiry (hours)")

    # Allowed job types (comma-separated). Used by POST /jobs validation.
    ALLOWED_JOB_TYPES: str = Field(default="demo,test,long-running,agent.run", description="Comma-separated list of allowed job types")
    # Optional mapping of job type -> JSON Schema for payload validation
    JOB_PAYLOAD_SCHEMAS: dict | None = Field(
        default=None, description="Mapping of job type -> JSON Schema for payload validation"
    )
    # Heartbeat interval (seconds) for SSE job event streams
    JOB_SSE_HEARTBEAT_SECS: int = Field(
        default=15, description="Heartbeat (comment) interval seconds for /jobs/{id}/events SSE stream"
    )

    # ---------------- Health probe options ----------------
    # Whether to allow falling back to the low-level mg_health() function when
    # the MemgraphAdapter symbol is missing. Default False to preserve test
    # semantics where tests monkeypatch MemgraphAdapter to None and expect
    # adapter-missing/unknown responses.
    HEALTH_ALLOW_MG_HEALTH_FALLBACK: bool = Field(default=True)
    # Allow Redis ping failures to be considered non-fatal in tests/environments
    # where Redis is optional. Default False so readiness degrades by default
    # unless an operator explicitly opts into a fallback.
    HEALTH_ALLOW_REDIS_HEALTH_FALLBACK: bool = Field(default=True)

    # ---------------- db.populate defaults (also mirrored here for convenience) ----------------
    NUM_USERS: int = Field(default=200)
    NUM_INSTITUTIONS: int = Field(default=50)
    MAX_TASKS_PER_USER: int = Field(default=10)
    MAX_INPUT_FILES: int = Field(default=3)

    # pydantic-settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # Normalizers / validators
    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_loglevel(cls, v: str) -> str:
        v = (v or "INFO").upper()
        # Accept common aliases
        if v in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return v
        return "INFO"

    @field_validator("RATE_LIMIT_BACKEND", mode="before")
    @classmethod
    def normalize_rl_backend(cls, v: str) -> str:
        v = (v or "redis").lower()
        return v if v in {"memory", "redis"} else "redis"

    @field_validator("LLM_TOOL_PREFERENCES", mode="before")
    @classmethod
    def parse_tool_preferences(cls, v: Any, info: ValidationInfo) -> Any:  # type: ignore[override]
        # Accept JSON string or simple comma-separated k=v
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if s.startswith("{"):
                try:
                    return json.loads(s)
                except Exception:
                    return None
            out: dict = {}
            for part in s.split(","):
                if not part.strip():
                    continue
                if "=" in part:
                    k, val = part.split("=", 1)
                    out[k.strip()] = val.strip()
            return out or None
        return None

    @field_validator("LLM_AGENT_ROLES", mode="before")
    @classmethod
    def parse_agent_roles(cls, v: Any, info: ValidationInfo) -> Any:  # type: ignore[override]
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if s.startswith("{"):
                try:
                    return json.loads(s)
                except Exception:
                    return None
            # Simple comma-separated role=prompt pairs are rarely used for long prompts
            out: dict = {}
            for part in s.split(","):
                if not part.strip():
                    continue
                if "=" in part:
                    k, val = part.split("=", 1)
                    out[k.strip()] = val.strip()
            return out or None
        return None

    @field_validator("LLM_TOOL_ACL", mode="before")
    @classmethod
    def parse_tool_acl(cls, v: Any, info: ValidationInfo) -> Any:  # type: ignore[override]
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if s.startswith("{"):
                try:
                    return json.loads(s)
                except Exception:
                    return None
            out: dict = {}
            for part in s.split(","):
                if not part.strip():
                    continue
                if "=" in part:
                    k, val = part.split("=", 1)
                    out[k.strip()] = val.strip()
            return out or None
        return None

    @field_validator("OLLAMA_BASE_URL", mode="before")
    @classmethod
    def normalize_ollama_base(cls, v: Any) -> str | None:  # type: ignore[override]
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped.rstrip("/") if stripped else None
        return None

    @field_validator("OLLAMA_MODEL_MAP", mode="before")
    @classmethod
    def parse_ollama_model_map(cls, v: Any) -> dict | None:  # type: ignore[override]
        if v is None:
            return None
        if isinstance(v, dict):
            return {str(k): str(vv) for k, vv in v.items()}
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                data = json.loads(s)
                if isinstance(data, dict):
                    return {str(k): str(vv) for k, vv in data.items()}
            except Exception:
                return None
        return None

    @property
    def effective_ollama_model_map(self) -> dict[str, str]:
        # Only use the current DEFAULT_MODEL_NAME instead of hardcoded list
        # This allows flexibility for different environments with different models
        default_model = self.DEFAULT_MODEL_NAME or "phi3:mini"
        default_map: dict[str, str] = {
            "phi3-mini-q4": default_model,
        }
        try:
            custom = self.OLLAMA_MODEL_MAP or {}
            for key, value in custom.items():
                if value:
                    default_map[str(key)] = str(value)
        except Exception:
            pass
        return default_map

    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection URL from settings."""
        # Basic auth credentials with URL encoding
        from urllib.parse import quote_plus

        user = quote_plus(self.DB_USER)
        password = quote_plus(self.DB_PASSWORD)

        # Build base URL
        url = f"postgresql://{user}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        # Add SSL mode if not disable
        if self.DB_SSLMODE and self.DB_SSLMODE != "disable":
            url += f"?sslmode={self.DB_SSLMODE}"

        return url

    def resolve_ollama_base_url(self) -> str:
        if self.OLLAMA_BASE_URL:
            return self.OLLAMA_BASE_URL
        try:
            if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
                return "http://ollama:11434"
        except Exception:
            pass
        # Heuristic: Docker Compose typically sets this env var for service containers
        if os.getenv("DOCKER_COMPOSE") or os.getenv("COMPOSE_PROJECT_NAME"):
            return "http://ollama:11434"
        return "http://localhost:11434"

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normalize_env(cls, v: str) -> str:
        return (v or "dev").lower()

    @field_validator("INTERNAL_UI_OVERRIDE_TTL_SECONDS", mode="before")
    @classmethod
    def clamp_override_ttl(cls, v: Any) -> int:
        """Clamp override TTL to reasonable bounds (60-3600 seconds)."""
        try:
            val = int(v) if v is not None else 600
            return max(60, min(3600, val))
        except (ValueError, TypeError):
            return 600

    @field_validator("INTERNAL_PREVIEW_CACHE_TTL_SECONDS", mode="before")
    @classmethod
    def clamp_preview_cache_ttl(cls, v: Any) -> int:
        """Clamp preview cache TTL to reasonable bounds (30-300 seconds)."""
        try:
            val = int(v) if v is not None else 90
            return max(30, min(300, val))
        except (ValueError, TypeError):
            return 90

    @field_validator("INTERNAL_TOKEN_MAX_TTL_SECONDS", mode="before")
    @classmethod
    def clamp_token_max_ttl(cls, v: Any) -> int:
        """Clamp token max TTL to reasonable bounds.

        Production: 300-7200s (5min-2h) for safety.
        Development: Allows higher values via env var (e.g., 86400s for 24h tokens).
        """
        try:
            val = int(v) if v is not None else 3600
            # Allow explicit high values in development (e.g., docker-compose override)
            # but enforce reasonable bounds for production (max 2h)
            if val > 7200:
                # Only allow >2h if explicitly set (not default)
                return max(300, val)  # Trust explicit config in dev
            else:
                return max(300, min(7200, val))  # Normal production bounds
        except (ValueError, TypeError):
            return 3600

    @field_validator("JOB_PAYLOAD_SCHEMAS", mode="before")
    @classmethod
    def parse_job_payload_schemas(cls, v: Any) -> Any:  # type: ignore[override]
        if v is None or isinstance(v, dict):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            if s.startswith("{"):
                try:
                    return json.loads(s)
                except Exception:
                    return None
        return None


# Singleton settings instance
settings = Settings()

__all__ = ["Settings", "settings"]
