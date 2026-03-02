"""
Compute configuration for LLM execution.

Provides device-aware defaults for timeouts, concurrency, and model selection.

This module is consumed by src/services/orchestrator.py to set:
- STEP_TIMEOUT_SECONDS: Individual LLM call / tool execution timeout
- RUN_TIMEOUT_SECONDS: Overall orchestration run timeout
- MAX_CONCURRENT_LLM_CALLS: Number of parallel LLM requests

TUNING GUIDELINES:
- CPU environments: Use higher timeouts (1200s step, 1800s run), lower concurrency (1)
    * phi3:mini on CPU can take several minutes per call; allow 20–30 minute runs
- GPU environments: Use lower timeouts (30s step, 120s run), higher concurrency (4)
- MPS (Apple Silicon): Moderate timeouts (60s step, 180s run), moderate concurrency (2)

Environment variables:
- LLM_DEVICE: "cpu" | "cuda" | "mps" | "auto"
- LLM_STEP_TIMEOUT_SECONDS: Override step timeout
- LLM_RUN_TIMEOUT_SECONDS: Override run timeout
- LLM_MAX_CONCURRENT_CALLS: Override concurrency limit
- LLM_TEST_MODE: Enable test mode with reduced timeouts
"""

from __future__ import annotations

import os
from contextlib import suppress
from typing import Literal

from pydantic_settings import BaseSettings


DeviceType = Literal["cpu", "cuda", "mps", "auto"]


class ComputeConfig(BaseSettings):
    """
    Configuration for compute resources and LLM execution.
    
    Provides device-appropriate defaults for timeouts, concurrency limits,
    and model selection. Can be overridden via environment variables.
    """
    
    # Device configuration
    device: DeviceType = "cpu"
    """
    Compute device to use for LLM inference.
    - cpu: CPU-only execution
    - cuda: NVIDIA GPU execution
    - mps: Apple Silicon GPU execution
    - auto: Automatic detection
    """
    
    # Concurrency limits
    max_concurrent_llm_calls: int = 1
    """Maximum number of concurrent LLM calls (varies by device)"""
    
# Timeout configuration
    step_timeout_seconds: int = 1200
    """Timeout for individual step execution (LLM calls, tool execution)"""

    run_timeout_seconds: int = 1800
    """Timeout for entire orchestration run - allows CPU-based LLM inference to complete"""
    
    # Model selection
    plan_model_name: str | None = None
    """Model to use for TODO planning (lightweight preferred for CPU)"""
    
    execute_model_name: str | None = None
    """Model to use for step execution (can be more powerful)"""
    
    # Warmup configuration
    warmup_models: list[str] = []
    """List of models to warm up at startup"""
    
    # Test mode
    test_mode: bool = False
    """Use lightweight models and reduced timeouts for testing"""
    
    # Memgraph NL test mode (separate from general test mode)
    memgraph_nl_test_mode: bool = False
    """Use reduced timeouts specifically for Memgraph NL integration tests"""
    
    model_config = {
        "env_prefix": "LLM_",
        "env_file": ".env",
        "extra": "ignore"
    }
    
    @property
    def recommended_step_timeout(self) -> int:
        """
        Get device-appropriate step timeout.
        
        Returns:
            Recommended timeout in seconds based on device type
        """
        # Memgraph NL test mode: aggressive timeout reduction
        if self.memgraph_nl_test_mode:
            return 90  # 90s per LLM call for simple NL→Cypher queries
        
        if self.test_mode:
            return 60
        
        timeouts = {
            "cuda": 30,
            "mps": 60,
            "cpu": 1200,  # Increased for CPU phi3:mini inference (can take 15-20+ minutes)
            "auto": 60,
        }
        return timeouts.get(self.device, 1200)
    
    @property
    def recommended_run_timeout(self) -> int:
        """
        Get device-appropriate run timeout.
        
        Returns:
            Recommended timeout in seconds based on device type
        """
        # Memgraph NL test mode: aggressive timeout reduction
        if self.memgraph_nl_test_mode:
            return 180  # 3 minutes total for NL→Cypher test runs
        
        if self.test_mode:
            return 120
        
        timeouts = {
            "cuda": 120,
            "mps": 180,
            "cpu": 1800,  # Increased for CPU phi3:mini (allows multi-step runs >20 minutes)
            "auto": 180,
        }
        return timeouts.get(self.device, 1800)
    
    @property
    def recommended_concurrency(self) -> int:
        """
        Get device-appropriate concurrency limit.
        
        Returns:
            Recommended number of concurrent LLM calls
        """
        if self.test_mode:
            return 1
        
        limits = {
            "cuda": 4,
            "mps": 2,
            "cpu": 1,
            "auto": 2,
        }
        return limits.get(self.device, 1)
    
    def apply_recommended_defaults(self) -> None:
        """
        Apply device-appropriate defaults if not explicitly set.
        
        This should be called during initialization to ensure
        timeouts and concurrency match the device capabilities.
        
        IMPORTANT: Step timeout is clamped to the run timeout so individual steps
        never exceed the total orchestration budget.
        
        MEMGRAPH_NL_TEST_MODE: When enabled, use reduced timeouts (90s step, 180s run)
        optimized for simple NL→Cypher queries in integration tests.
        """
        fields_set = set(getattr(self, "model_fields_set", set()))

        # Apply recommended run timeout first so step clamping can reference it
        if "run_timeout_seconds" not in fields_set:
            self.run_timeout_seconds = self.recommended_run_timeout

        if "step_timeout_seconds" not in fields_set:
            recommended_step = self.recommended_step_timeout
            self.step_timeout_seconds = min(recommended_step, self.run_timeout_seconds)
        
        if "max_concurrent_llm_calls" not in fields_set:
            self.max_concurrent_llm_calls = self.recommended_concurrency
    
    def to_dict(self) -> dict:
        """Export configuration as dict for logging/debugging."""
        return {
            "device": self.device,
            "max_concurrent_llm_calls": self.max_concurrent_llm_calls,
            "step_timeout_seconds": self.step_timeout_seconds,
            "run_timeout_seconds": self.run_timeout_seconds,
            "plan_model_name": self.plan_model_name,
            "execute_model_name": self.execute_model_name,
            "warmup_models": self.warmup_models,
            "test_mode": self.test_mode,
            "memgraph_nl_test_mode": self.memgraph_nl_test_mode,
            "recommended": {
                "step_timeout": self.recommended_step_timeout,
                "run_timeout": self.recommended_run_timeout,
                "concurrency": self.recommended_concurrency,
            }
        }


# Global singleton instance
_compute_config: ComputeConfig | None = None


def get_compute_config() -> ComputeConfig:
    """
    Get or create the global compute configuration instance.
    
    Returns:
        ComputeConfig singleton instance
    """
    global _compute_config
    if _compute_config is None:
        # Respect explicit timeout env vars even when test modes are enabled.
        # Pydantic marks fields as "unset" when defaults are used, so we pull
        # env values first to ensure they are treated as explicit overrides
        # (e.g., LLM_STEP_TIMEOUT_SECONDS=1200, LLM_RUN_TIMEOUT_SECONDS=1800).
        env_step = os.getenv("LLM_STEP_TIMEOUT_SECONDS")
        env_run = os.getenv("LLM_RUN_TIMEOUT_SECONDS")
        init_kwargs = {}
        if env_step:
            with suppress(Exception):
                init_kwargs["step_timeout_seconds"] = int(env_step)
        if env_run:
            with suppress(Exception):
                init_kwargs["run_timeout_seconds"] = int(env_run)

        _compute_config = ComputeConfig(**init_kwargs)
        _compute_config.apply_recommended_defaults()
    return _compute_config


def reset_compute_config() -> None:
    """Reset the global compute configuration (mainly for testing)."""
    global _compute_config
    _compute_config = None


# Convenience export
compute_config = get_compute_config()
