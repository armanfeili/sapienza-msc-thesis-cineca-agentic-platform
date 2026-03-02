"""
LLM adapter (demo + optional OpenAI HTTP client)

This module provides a thin abstraction used by the API routers. It is deliberately
minimal and dependency-light. If no provider/API key is configured, it falls back
to a deterministic **demo echo** implementation so the app remains usable.

Exposed callables (imported lazily by routers):

- list_models() -> List[dict]
- get_default_model() -> str
- set_default_model(name: str) -> None
- load_model(name: str, **options) -> dict
- unload_model(name: str) -> dict
- complete(prompt: str, model: str | None, temperature: float, max_tokens: int, metadata: dict, user: dict|None) -> dict
- test(**kwargs) -> dict  (same as complete with a tiny default prompt)
"""

from __future__ import annotations

import json
import math
import os
from contextlib import suppress
from typing import Any

import httpx

from src.config import settings

# Logging (structlog if configured; stdlib otherwise)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ---------------- Module state ----------------
_PROVIDER: str = (settings.LLM_PROVIDER or "demo").lower()

# Module-level cache for verified models (prevents repeated /api/tags calls)
# Key: (base_url, model_id), Value: True if verified
_VERIFIED_MODELS: set[tuple[str, str]] = set()

# Default model - initialized lazily to avoid async call at import time
_DEFAULT_MODEL: str | None = None

def _get_default_model_sync() -> str:
    """Get default model synchronously (lazy initialization, no async DMR call at import)."""
    global _DEFAULT_MODEL
    
    # Return cached value if already resolved
    if _DEFAULT_MODEL is not None:
        return _DEFAULT_MODEL
    
    # Fallback to settings directly (no async DMR call)
    # DMR should be used by callers that can handle async properly
    _DEFAULT_MODEL = settings.DEFAULT_MODEL_NAME or ("gpt-4o-mini" if _PROVIDER == "openai" else "demo-echo")
    return _DEFAULT_MODEL

_OPENAI_API_KEY: str | None = settings.OPENAI_API_KEY

# Hardcoded defaults for safety; adjust as needed.
_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


# ---------------- Public API ----------------
def list_models() -> list[dict[str, Any]]:
    """
    Return a list of models known to this adapter (best effort).
    We do not call remote "list models" APIs to avoid extra latency/permissions.
    """
    default_model = _get_default_model_sync()
    
    if _PROVIDER == "openai":
        # Minimal curated set; you can customize for your org/tenancy.
        candidates = [
            {"name": "gpt-4o-mini", "context_window": 128000},
            {"name": "gpt-4o", "context_window": 128000},
            {"name": "gpt-4.1-mini", "context_window": 128000},
        ]
        for c in candidates:
            c.update(
                provider="openai",
                modalities=["text"],
                enabled=bool(_OPENAI_API_KEY),
                loaded=None,
                description="OpenAI model (static catalog)",
                default=(c["name"] == default_model),
            )
        # Ensure default (from env) is present
        if default_model not in {m["name"] for m in candidates}:
            candidates.append(
                {
                    "name": default_model,
                    "context_window": None,
                    "provider": "openai",
                    "modalities": ["text"],
                    "enabled": bool(_OPENAI_API_KEY),
                    "loaded": None,
                    "description": "Custom/default model from settings",
                    "default": True,
                }
            )
        return candidates

    # DEMO
    return [
        {
            "name": default_model,
            "provider": "demo",
            "context_window": 4096,
            "modalities": ["text"],
            "enabled": True,
            "loaded": True,
            "description": "Deterministic echo model (no external calls)",
            "default": True,
        }
    ]


def get_default_model() -> str:
    """Return the currently configured default model name."""
    return _get_default_model_sync()


def set_default_model(name: str) -> None:
    global _DEFAULT_MODEL
    _DEFAULT_MODEL = name


def load_model(name: str, **options: Any) -> dict[str, Any]:
    """
    For remote providers this may warm caches or perform validation.
    Here we just validate configuration and return a status object.
    """
    if _PROVIDER == "openai":
        if not _OPENAI_API_KEY:
            return {"ok": False, "message": "OPENAI_API_KEY not set"}
        # Optionally: perform a cheap validation request (skipped by default).
        return {"ok": True, "message": f"openai model '{name}' ready"}
    # DEMO
    return {"ok": True, "message": f"demo model '{name}' ready"}


def unload_model(name: str) -> dict[str, Any]:
    # Nothing to unload in this simple adapter; return a status object.
    return {"ok": True, "message": f"model '{name}' unloaded (noop)"}


def complete(
    *,
    prompt: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 256,
    timeout_seconds: float | None = None,
    num_predict: int | None = None,
    top_k: int | None = None,
    metadata: dict[str, Any] | None = None,
    user: dict[str, Any] | None = None,
    ollama_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Produce a completion. Returns a dict compatible with the routers:

    {
      "text": "...",
      "output": "...",
      "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
      "model": "name"
    }
    """
    model = model or _get_default_model_sync()
    base_ollama_options = dict(ollama_options or {})

    # Respect explicit timeout override for downstream callers (e.g., orchestrator budgets)
    if timeout_seconds is None:
        with suppress(ValueError):
            # Default to 1200s (20 minutes) to match step_timeout for CPU inference
            timeout_seconds = float(os.getenv("LLM_CLIENT_TIMEOUT_SECONDS", "1200"))

    if _PROVIDER == "openai" and _OPENAI_API_KEY:
        return _complete_openai(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata or {},
            user=user or {},
        )

    # DEMO fallback (deterministic echo)
    text = f"(demo) {prompt}"
    usage = _estimate_usage(prompt, text)
    return {"text": text, "output": text, "usage": usage, "model": model, "provider": "demo"}


def test(
    *,
    prompt: str = "ping",
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 64,
    metadata: dict[str, Any] | None = None,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return complete(
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata=metadata,
        user=user,
    )


# ---------------- Providers ----------------
def _complete_openai(
    *,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    metadata: dict[str, Any],
    user: dict[str, Any],
) -> dict[str, Any]:
    """
    Minimal OpenAI Chat Completions call using httpx.

    Environment:
      - OPENAI_API_KEY in settings
      - Optional OPENAI_BASE_URL (defaults to https://api.openai.com/v1)
    """
    url = f"{_OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        # You may add top_p, frequency_penalty, presence_penalty if you need.
    }

    try:
        # Increased timeout to 1800s (30 minutes) to handle cold model loading and long inference in Ollama
        with httpx.Client(timeout=1800.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        detail = f"{e.response.status_code} {e.response.text}"
        logger.warning("openai error: %s", detail)
        return {
            "text": "",
            "output": "",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "model": model,
            "provider": "openai",
            "error": detail,
        }
    except Exception as e:  # pragma: no cover - network/env specific
        logger.warning("openai request failed: %s", e)
        return {
            "text": "",
            "output": "",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "model": model,
            "provider": "openai",
            "error": str(e),
        }

    # Normalize response
    text = ""
    with suppress(Exception):
        text = (data["choices"][0]["message"]["content"] or "").strip()

    usage = {
        "prompt_tokens": int(data.get("usage", {}).get("prompt_tokens") or 0),
        "completion_tokens": int(data.get("usage", {}).get("completion_tokens") or 0),
        "total_tokens": int(data.get("usage", {}).get("total_tokens") or 0),
    }
    # If the API didn't return usage (rare), do a naive estimate
    if usage["total_tokens"] == 0:
        usage = _estimate_usage(prompt, text)

    return {
        "text": text,
        "output": text,
        "usage": usage,
        "model": model,
        "provider": "openai",
        "raw": data,  # keep raw for debugging (remove in prod if sensitive)
    }


# ---------------- Utilities ----------------
def _estimate_usage(prompt: str, completion: str) -> dict[str, int]:
    """
    Very naive token estimate: ~4 chars/token heuristic.
    This is sufficient for demo metrics without pulling a tokenizer.
    """

    def est(s: str) -> int:
        n = max(1, len(s))
        return math.ceil(n / 4)

    p = est(prompt)
    c = est(completion)
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}


class LLMClient:
    """Lightweight LLM client wrapper used by Orchestrator.from_env().

    If a base_url is provided, this client will POST to {base_url}/complete
    with JSON {prompt, model, temperature, max_tokens, metadata, user} and
    expect a JSON response. Otherwise it falls back to the local adapter
    `complete` function (demo echo).
    
    For Ollama providers, verifies model exists before first use to prevent
    auto-pull behavior that can cause long timeouts.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else None
        self._model_verified = False  # Track if we've verified model exists
        
    async def _verify_model_exists(self) -> bool:
        """Verify that the model exists in Ollama to prevent auto-pull.
        
        Uses module-level cache to avoid repeated /api/tags calls for the same (base_url, model).
        Only checks once per (base_url, model) combination across all client instances.
        Returns True if verified or not an Ollama provider.
        Raises ValueError if model doesn't exist.
        """
        # Check instance-level flag first (fast path for same client)
        if self._model_verified:
            return True
        
        if not self.base_url or not self.model:
            self._model_verified = True
            return True
            
        # Only check for Ollama providers
        # Detection: hostname contains "ollama" OR port 11434 (default Ollama port)
        is_ollama = "ollama" in self.base_url.lower() or ":11434" in self.base_url
        
        if not is_ollama:
            self._model_verified = True
            return True
        
        # Check module-level cache (shared across all LLMClient instances)
        cache_key = (self.base_url, self.model)
        if cache_key in _VERIFIED_MODELS:
            self._model_verified = True
            logger.debug("llm.model_verified_cached", model=self.model, base_url=self.base_url)
            return True
            
        try:
            # Check Ollama /api/tags endpoint to list available models
            tags_url = self.base_url.replace("/v1", "") + "/api/tags"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(tags_url)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception as exc:
                    logger.warning(
                        "llm.model_verification_failed",
                        model=self.model,
                        error=str(exc),
                        message="Proceeding without verification (non-JSON response)",
                    )
                    self._model_verified = True
                    return True
                models = data.get("models", [])
                
                # Check if our model is in the list
                model_names = [m.get("name", "") for m in models]
                
                if self.model not in model_names:
                    logger.error(
                        "llm.model_not_found",
                        model=self.model,
                        available_models=model_names[:5],  # Log first 5 for debugging
                        base_url=self.base_url,
                    )
                    raise ValueError(
                        f"Model '{self.model}' not found in Ollama. "
                        f"Available models: {', '.join(model_names[:3])}. "
                        f"Please ensure the model is pulled before use."
                    )
                
                # Model verified - add to cache
                _VERIFIED_MODELS.add(cache_key)
                logger.info("llm.model_verified", model=self.model, base_url=self.base_url)
                self._model_verified = True
                return True
                
        except httpx.HTTPError as exc:
            # If we can't verify (network error, endpoint unavailable), log warning but continue
            # This prevents breaking non-Ollama providers
            logger.warning(
                "llm.model_verification_failed",
                model=self.model,
                error=str(exc),
                message="Proceeding without verification"
            )
            self._model_verified = True  # Don't check again
            return True
        except ValueError:
            # Re-raise model not found errors
            raise

    async def complete(self, prompt: str, timeout_seconds: float | None = None, **kwargs: Any) -> str:
        import time
        
        model = kwargs.get("model") or self.model
        if not model:
            raise ValueError("LLMClient.complete called without a model; configure self.model or pass model=...")
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 256)
        metadata = kwargs.get("metadata", {})
        user = kwargs.get("user")
        is_ollama = bool(self.base_url and ("ollama" in self.base_url.lower() or ":11434" in self.base_url))
        # Normalize ollama options from kwargs
        base_ollama_options: dict[str, Any] = {}
        extra_opts = kwargs.pop("ollama_options", None)
        if isinstance(extra_opts, dict):
            base_ollama_options.update(extra_opts)
        kw_num_predict = kwargs.pop("num_predict", None)
        kw_top_k = kwargs.pop("top_k", None)
        if is_ollama:
            # Caller-provided overrides take precedence, then env, then defaults
            with suppress(ValueError):
                if kw_num_predict is not None:
                    base_ollama_options["num_predict"] = int(kw_num_predict)
            if "num_predict" not in base_ollama_options:
                with suppress(ValueError):
                    num_predict_env = os.getenv("OLLAMA_NUM_PREDICT")
                    if num_predict_env:
                        base_ollama_options["num_predict"] = int(num_predict_env)
            with suppress(ValueError):
                if kw_top_k is not None:
                    base_ollama_options["top_k"] = int(kw_top_k)
            if "top_k" not in base_ollama_options:
                with suppress(ValueError):
                    top_k_env = os.getenv("OLLAMA_TOP_K")
                    if top_k_env:
                        base_ollama_options["top_k"] = int(top_k_env)
        ollama_options = base_ollama_options
        with suppress(ValueError):
            env_max_tokens = os.getenv("LLM_CLIENT_MAX_TOKENS")
            if env_max_tokens:
                max_tokens = int(env_max_tokens)
        if timeout_seconds is None:
            with suppress(ValueError):
                # Default to 1200s (20 minutes) to match step_timeout for CPU inference
                timeout_seconds = float(os.getenv("LLM_CLIENT_TIMEOUT_SECONDS", "1200"))
        
        # Extract run_id from metadata for tracing
        run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
        
        # Determine prompt type (planner vs tool execution)
        prompt_type = metadata.get("prompt_type", "execution") if isinstance(metadata, dict) else "execution"
        
        # Verify model exists before first use (prevents Ollama auto-pull timeouts)
        try:
            await self._verify_model_exists()
        except ValueError as exc:
            logger.error(
                "llm.request.error",
                model=model,
                prompt_type=prompt_type,
                error_type="ModelNotFound",
                error_message=str(exc),
                run_id=run_id,
            )
            raise
        
        # Log LLM request start
        start_time = time.time()
        logger.debug(
            "llm.request.start",
            model=model,
            prompt_type=prompt_type,
            prompt_length=len(prompt),
            run_id=run_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if self.base_url:
            # Use OpenAI-compatible chat completions endpoint
            # If base_url already ends with /v1, just append /chat/completions
            # Otherwise, append /v1/chat/completions
            if self.base_url.endswith("/v1"):
                url = f"{self.base_url}/chat/completions"
            else:
                url = f"{self.base_url}/v1/chat/completions"
            try:
                # Timeout: 1200s per LLM call for CPU inference (phi3:mini needs time on CPU)
                # Matches STEP_TIMEOUT_SECONDS to allow completion within step budget
                # Use explicit httpx.Timeout to set all components (connect, read, write, pool)
                # Allow per-call timeout override (defaults to env or 1200s for CPU runs)
                default_timeout = float(os.getenv("LLM_CLIENT_TIMEOUT_SECONDS", "1200"))
                effective_timeout = float(timeout_seconds or default_timeout)
                timeout_config = httpx.Timeout(
                    connect=30.0,    # Connection establishment
                    read=effective_timeout,      # Reading response (main inference time)
                    write=30.0,      # Writing request
                    pool=10.0        # Getting connection from pool
                )
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": float(temperature),
                        "max_tokens": int(max_tokens),
                    }
                    if is_ollama and ollama_options:
                        payload["options"] = ollama_options
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    # Extract completion text and usage
                    text = (data["choices"][0]["message"]["content"] or "").strip()
                    usage = data.get("usage", {})
                    tokens_input = usage.get("prompt_tokens", 0)
                    tokens_output = usage.get("completion_tokens", 0)
                    
                    # Log success
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    logger.debug(
                        "llm.request.success",
                        model=model,
                        prompt_type=prompt_type,
                        elapsed_ms=elapsed_ms,
                        tokens_input=tokens_input,
                        tokens_output=tokens_output,
                        run_id=run_id,
                    )
                    
                    return text
                    
            except httpx.HTTPStatusError as exc:  # pragma: no cover - HTTP errors
                elapsed_ms = int((time.time() - start_time) * 1000)
                http_status = exc.response.status_code
                error_body = exc.response.text[:500]  # Truncate error message
                
                logger.error(
                    "llm.request.error",
                    model=model,
                    prompt_type=prompt_type,
                    elapsed_ms=elapsed_ms,
                    http_status=http_status,
                    error_message=error_body,
                    error_type="HTTPStatusError",
                    run_id=run_id,
                    url=url,
                )
                raise
            except httpx.TimeoutException as exc:  # pragma: no cover - Timeout errors
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "llm.request.error",
                    model=model,
                    prompt_type=prompt_type,
                    elapsed_ms=elapsed_ms,
                    timeout_read_seconds=effective_timeout,  # Log actual configured timeout
                    error_type="TimeoutException",
                    error_message=str(exc),
                    run_id=run_id,
                    url=url,
                )
                raise
            except Exception as exc:  # pragma: no cover - Other errors
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "llm.request.error",
                    model=model,
                    prompt_type=prompt_type,
                    elapsed_ms=elapsed_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    run_id=run_id,
                    url=url,
                )
                raise

            # Extract response from OpenAI-compatible format
            if isinstance(data, dict):
                # OpenAI format: data.choices[0].message.content
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    if content:
                        return str(content)

                # Fallback: check for text/output fields
                if "text" in data:
                    return str(data.get("text") or "")
                if "output" in data:
                    return str(data.get("output") or "")
                # Otherwise return the JSON string
                return json.dumps(data, ensure_ascii=False)
            return str(data)

        # Fallback to local adapter complete (sync) wrapped for async
        result = complete(
            prompt=prompt, model=model, temperature=temperature, max_tokens=max_tokens, metadata=metadata, user=user
        )
        if isinstance(result, dict):
            return str(result.get("text") or result.get("output") or json.dumps(result, ensure_ascii=False))
        return str(result)


# ---------------- Lightweight process-based adapter ----------------
import socket
import subprocess
import time

# In-memory process table: model name -> {proc, port, artifact}
_PROCESS_TABLE: dict = {}


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class LLMAdapter:
    """A minimal adapter that can start/stop local `llama-server` processes.

    This is intentionally small and best-effort:
    - Exposes info(), configure(), available_models(), load_model(), unload_model(), health().
    - load_model spawns `llama-server -m <artifact> --host 127.0.0.1 --port <port>` and records the process.
    - If `llama-server` is not present or the spawn fails, a helpful error is returned.

    NOTE: This adapter is suitable for development and testing. In production you should
    run model servers via an operator/Kubernetes Job and point manifests at reachable endpoints.
    """

    def __init__(
        self, model: str | None = None, temperature: float | None = None, max_tokens: int | None = None
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def info(self) -> dict:
        return {
            "provider": "local-llama",
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def configure(self, **cfg) -> None:
        if "model" in cfg:
            self.model = cfg.get("model")
        if "temperature" in cfg:
            self.temperature = float(cfg.get("temperature"))
        if "max_tokens" in cfg:
            self.max_tokens = int(cfg.get("max_tokens"))

    def available_models(self) -> list:
        # Best-effort: defer to settings if present
        try:
            from src.config import settings

            val = getattr(settings, "LLM_AVAILABLE_MODELS", None)
            if isinstance(val, (list, tuple)) and val:
                return [str(m) for m in val]
        except Exception:
            pass
        return [self.model] if self.model else []

    def load_model(
        self, name: str, artifact: str | None = None, port: int | None = None, extra_args: list | None = None
    ) -> dict:
        """Start a local llama-server process for the given artifact.

        Returns: {ok: bool, message/port/pid}
        """
        if not artifact:
            return {"ok": False, "message": "artifact path required to load model"}
        if name in _PROCESS_TABLE:
            return {"ok": False, "message": "model already loaded"}

        # find a free port if not provided
        try:
            port = int(port) if port else _find_free_port()
        except Exception:
            port = 8080

        cmd = ["llama-server", "-m", artifact, "--host", "127.0.0.1", "--port", str(port)]
        if extra_args:
            cmd += extra_args

        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            return {"ok": False, "message": "llama-server executable not found in PATH"}
        except Exception as exc:
            return {"ok": False, "message": f"failed to start process: {exc}"}

        # Wait briefly to let server bind (best-effort)
        t0 = time.time()
        ready = False
        while time.time() - t0 < 5:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    ready = True
                    break
            except Exception:
                time.sleep(0.2)

        _PROCESS_TABLE[name] = {"proc": p, "port": port, "artifact": artifact, "started_at": time.time()}

        return {"ok": True, "pid": p.pid, "port": port, "ready": ready}

    def unload_model(self, name: str) -> dict:
        entry = _PROCESS_TABLE.get(name)
        if not entry:
            return {"ok": False, "message": "model not loaded"}
        p = entry.get("proc")
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            with suppress(Exception):
                p.kill()
        _PROCESS_TABLE.pop(name, None)
        return {"ok": True}

    def health(self) -> dict:
        out = {}
        for name, entry in list(_PROCESS_TABLE.items()):
            p = entry.get("proc")
            alive = p.poll() is None
            out[name] = {"alive": alive, "pid": getattr(p, "pid", None), "port": entry.get("port")}
        return {"ok": True, "processes": out}
