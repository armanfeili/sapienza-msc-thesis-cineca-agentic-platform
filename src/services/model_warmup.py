"""
Model Warmup Service

Provides deterministic warmup workflow for LLM models with:
- Configurable timeout and retry logic
- Keep-alive support for Ollama
- Comprehensive metrics and logging
- Graceful failure handling

Usage:
    warmup = ModelWarmupService()
    result = await warmup.warmup_model(model_id="phi3:mini", provider_id="ollama")
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from src.config import settings

# Conditional imports
try:
    from src.metrics.prometheus import record_model_warmup
except ImportError:
    record_model_warmup = None  # type: ignore

logger = structlog.get_logger(__name__)


class ModelWarmupService:
    """
    Deterministic model warmup with timeout, retry, and observability.
    
    Features:
    - Timeout: settings.LLM_WARMUP_TIMEOUT (default: 300s / 5 minutes)
    - Retry: settings.LLM_WARMUP_RETRY_MAX (default: 3 attempts)
    - Retry Delay: settings.LLM_WARMUP_RETRY_DELAY (default: 10s)
    - Metrics: Records warmup duration and success/failure
    - Logging: Structured logs for all warmup events

    Note: This is intended to run once at application startup so the first user
    request does not pay the model load cost. Orchestrator runs do not invoke
    additional warmup beyond capturing first-call latency in metrics.
    """

    def __init__(self):
        self.timeout = getattr(settings, "LLM_WARMUP_TIMEOUT", 300)  # 5 minutes
        self.retry_max = getattr(settings, "LLM_WARMUP_RETRY_MAX", 3)
        self.retry_delay = getattr(settings, "LLM_WARMUP_RETRY_DELAY", 10)  # seconds

    async def warmup_model(
        self, model_id: str, provider_id: str | None, provider_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Warm up a model with deterministic timeout and retry.

        Args:
            model_id: Model identifier (e.g., "phi3:mini", "gpt-4o")
            provider_id: Provider identifier (e.g., "ollama", "openai"). May be None.
            provider_config: Optional provider configuration

        Returns:
            dict with:
            - success: bool
            - duration_ms: float
            - attempts: int
            - error: str | None

        Example:
            result = await warmup.warmup_model("phi3:mini", "ollama")
            if result["success"]:
                logger.info("Warmup succeeded", duration=result["duration_ms"])
        """
        start_time = time.time()
        last_error = None

        # Provider may not always be set (e.g., default resolver returns None); guard upstream usage
        provider_fallback = getattr(settings, "LLM_DEFAULT_PROVIDER", "unknown")
        normalized_provider_id = provider_id or provider_fallback
        if not isinstance(normalized_provider_id, str):
            normalized_provider_id = str(normalized_provider_id)
        if provider_id != normalized_provider_id:
            logger.debug(
                "model.warmup.provider_fallback",
                extra={"requested": provider_id, "fallback": normalized_provider_id, "model_id": model_id},
            )
        provider_id = normalized_provider_id

        logger.info(
            "model.warmup.started",
            extra={
                "model_id": model_id,
                "provider_id": provider_id,
                "timeout": self.timeout,
                "retry_max": self.retry_max,
            },
        )

        for attempt in range(1, self.retry_max + 1):
            try:
                logger.debug(
                    "model.warmup.attempt",
                    extra={"model_id": model_id, "attempt": attempt, "max_attempts": self.retry_max},
                )

                # Execute warmup with timeout
                warmup_result = await asyncio.wait_for(
                    self._execute_warmup(model_id, provider_id, provider_config), timeout=self.timeout
                )

                duration_ms = (time.time() - start_time) * 1000

                logger.info(
                    "model.warmup.succeeded",
                    extra={
                        "model_id": model_id,
                        "provider_id": provider_id,
                        "duration_ms": duration_ms,
                        "attempts": attempt,
                    },
                )

                # Record metrics
                if record_model_warmup:
                    try:
                        record_model_warmup(
                            model_name=model_id, provider=provider_id, status="success", duration_seconds=duration_ms / 1000
                        )
                    except Exception as metric_exc:
                        logger.warning(f"Failed to record warmup metric: {metric_exc}")

                return {
                    "success": True,
                    "duration_ms": duration_ms,
                    "attempts": attempt,
                    "error": None,
                    "result": warmup_result,
                }

            except asyncio.TimeoutError as exc:
                last_error = f"Warmup timeout after {self.timeout}s"
                duration_ms = (time.time() - start_time) * 1000

                logger.warning(
                    "model.warmup.timeout",
                    extra={
                        "model_id": model_id,
                        "provider_id": provider_id,
                        "attempt": attempt,
                        "timeout": self.timeout,
                        "duration_ms": duration_ms,
                    },
                )

                # Record timeout metric
                if record_model_warmup:
                    try:
                        record_model_warmup(
                            model_name=model_id, provider=provider_id, status="timeout", duration_seconds=duration_ms / 1000
                        )
                    except Exception:
                        pass

            except Exception as exc:
                last_error = str(exc)
                duration_ms = (time.time() - start_time) * 1000

                logger.warning(
                    "model.warmup.attempt_failed",
                    extra={
                        "model_id": model_id,
                        "provider_id": provider_id,
                        "attempt": attempt,
                        "error": last_error,
                        "duration_ms": duration_ms,
                    },
                    exc_info=True,
                )

            # Retry delay (except on last attempt)
            if attempt < self.retry_max:
                logger.debug(
                    "model.warmup.retry_delay",
                    extra={"model_id": model_id, "delay": self.retry_delay, "attempt": attempt},
                )
                await asyncio.sleep(self.retry_delay)

        # All attempts failed
        duration_ms = (time.time() - start_time) * 1000

        logger.error(
            "model.warmup.failed",
            extra={
                "model_id": model_id,
                "provider_id": provider_id,
                "attempts": self.retry_max,
                "error": last_error,
                "duration_ms": duration_ms,
            },
        )

        # Record failure metric
        if record_model_warmup:
            try:
                record_model_warmup(
                    model_name=model_id, provider=provider_id, status="error", duration_seconds=duration_ms / 1000
                )
            except Exception:
                pass

        return {
            "success": False,
            "duration_ms": duration_ms,
            "attempts": self.retry_max,
            "error": last_error,
            "result": None,
        }

    async def _execute_warmup(
        self, model_id: str, provider_id: str, provider_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Execute actual warmup call to provider.

        This is the core warmup logic that calls the LLM provider to ensure
        the model is loaded and ready for inference.

        Args:
            model_id: Model identifier
            provider_id: Provider identifier
            provider_config: Optional provider configuration

        Returns:
            dict with warmup result metadata

        Raises:
            Exception: If warmup fails (will be caught by retry logic)
        """
        # Get LLM adapter (lazy import to avoid circular dependencies)
        try:
            from src.adapters import llm as llm_adapter
        except ImportError:
            logger.warning("LLM adapter not available, skipping warmup execution")
            return {"skipped": True, "reason": "adapter_unavailable"}

        # Determine provider type
        is_ollama = provider_id.lower() in ("ollama", "ollama-local", "local")

        # Build warmup request
        warmup_kwargs: dict[str, Any] = {
            "prompt": "Hello",  # Minimal prompt
            "model": model_id,
            "temperature": 0.0,
            "max_tokens": 1,
            "metadata": {"purpose": "warmup", "provider": provider_id},
        }

        # NOTE: keep_alive is an Ollama-specific parameter that must be passed via options, not directly
        # The LLM adapter's complete() method doesn't accept keep_alive as a direct parameter
        # If we need to control this, it should be done via the ollama_options in model configuration
        
        # Execute warmup call (removed keep_alive parameter - not supported by complete())
        try:
            if hasattr(llm_adapter, "complete"):
                result = llm_adapter.complete(**warmup_kwargs)
            else:
                logger.warning("LLM adapter has no 'complete' method, skipping warmup execution")
                return {"skipped": True, "reason": "no_complete_method"}

            return {"completed": True, "response": result}

        except Exception as exc:
            logger.error(
                "model.warmup.execution_failed",
                extra={"model_id": model_id, "provider_id": provider_id, "error": str(exc)},
                exc_info=True,
            )
            raise


# Singleton instance
_warmup_service: ModelWarmupService | None = None


def get_warmup_service() -> ModelWarmupService:
    """Get or create singleton ModelWarmupService instance."""
    global _warmup_service
    if _warmup_service is None:
        _warmup_service = ModelWarmupService()
    return _warmup_service
