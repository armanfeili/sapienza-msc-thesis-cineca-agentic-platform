"""
Unit tests for compute configuration module.

Validates:
- Device-appropriate timeout defaults
- Environment variable overrides
- CPU extended timeout rules
- Configuration consistency
"""

import os
import pytest
from unittest.mock import patch

from src.config_modules.compute import ComputeConfig, get_compute_config, reset_compute_config


class TestComputeConfig:
    """Test compute configuration loading and defaults."""
    
    def setup_method(self):
        """Reset config before each test."""
        reset_compute_config()
    
    def teardown_method(self):
        """Reset config after each test."""
        reset_compute_config()
    
    def test_default_cpu_config(self):
        """Verify CPU device gets appropriate defaults."""
        with patch.dict(os.environ, {}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            assert config.device == "cpu"
            assert config.max_concurrent_llm_calls == 1
            assert config.step_timeout_seconds == 1200
            assert config.run_timeout_seconds == 1800
    
    def test_env_override_run_timeout(self):
        """Verify LLM_RUN_TIMEOUT_SECONDS environment variable is respected."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "600"}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            assert config.run_timeout_seconds == 600
            assert config.step_timeout_seconds == 600
    
    def test_cpu_step_timeout_clamped_to_run(self):
        """Verify CPU step timeout never exceeds the configured run timeout."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "600"}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            assert config.run_timeout_seconds == 600
            assert config.step_timeout_seconds == 600  # Clamped to run timeout
    
    def test_cpu_extended_timeout_explicit_step_override(self):
        """Verify explicit LLM_STEP_TIMEOUT_SECONDS overrides auto-increase logic."""
        with patch.dict(os.environ, {
            "LLM_RUN_TIMEOUT_SECONDS": "600",
            "LLM_STEP_TIMEOUT_SECONDS": "180",
        }, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            assert config.run_timeout_seconds == 600
            assert config.step_timeout_seconds == 180  # Explicit override honored
    
    def test_gpu_config(self):
        """Verify GPU (CUDA) device gets appropriate defaults."""
        with patch.dict(os.environ, {}, clear=False):
            config = ComputeConfig(device="cuda")
            config.apply_recommended_defaults()
            
            assert config.device == "cuda"
            assert config.max_concurrent_llm_calls == 4
            assert config.step_timeout_seconds == 30
            assert config.run_timeout_seconds == 120
    
    def test_mps_config(self):
        """Verify MPS (Apple Silicon) device gets appropriate defaults."""
        with patch.dict(os.environ, {}, clear=False):
            config = ComputeConfig(device="mps")
            config.apply_recommended_defaults()
            
            assert config.device == "mps"
            assert config.max_concurrent_llm_calls == 2
            assert config.run_timeout_seconds == 180
            assert config.step_timeout_seconds == 60
    
    def test_test_mode(self):
        """Verify test mode uses lightweight defaults."""
        with patch.dict(os.environ, {"LLM_TEST_MODE": "true"}, clear=False):
            config = ComputeConfig(device="cpu", test_mode=True)
            config.apply_recommended_defaults()
            
            assert config.test_mode is True
            assert config.max_concurrent_llm_calls == 1
            assert config.step_timeout_seconds == 60
            assert config.run_timeout_seconds == 120
    
    def test_global_singleton_config(self):
        """Verify get_compute_config returns singleton instance."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "600"}, clear=False):
            config1 = get_compute_config()
            config2 = get_compute_config()
            
            assert config1 is config2  # Same instance
            assert config1.run_timeout_seconds == 600
    
    def test_config_to_dict(self):
        """Verify configuration exports correctly to dict for logging."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "600"}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            config_dict = config.to_dict()
            
            assert config_dict["device"] == "cpu"
            assert config_dict["run_timeout_seconds"] == 600
            assert config_dict["step_timeout_seconds"] == 600  # Clamped to run timeout
            assert "recommended" in config_dict
    
    def test_orchestrator_uses_config_singleton(self):
        """
        Integration test: Verify orchestrator.py uses compute config correctly.
        
        This ensures RUN_TIMEOUT_SECONDS in orchestrator matches LLM_RUN_TIMEOUT_SECONDS env.
        """
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "600"}, clear=False):
            # Reset and reload config
            reset_compute_config()
            
            # Import orchestrator to trigger config load
            from src.services import orchestrator
            # Force reload to pick up new config
            import importlib
            importlib.reload(orchestrator)
            
            # Verify timeout matches environment
            assert orchestrator.RUN_TIMEOUT_SECONDS == 600, (
                f"RUN_TIMEOUT_SECONDS should be 600 when LLM_RUN_TIMEOUT_SECONDS=600, "
                f"but got {orchestrator.RUN_TIMEOUT_SECONDS}"
            )


class TestTimeoutConsistency:
    """Test timeout configuration consistency rules."""
    
    def test_step_timeout_not_greater_than_run_timeout(self):
        """Verify step timeout never exceeds run timeout (sanity check)."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "120"}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            # Step timeout should be reasonable relative to run timeout
            assert config.step_timeout_seconds <= config.run_timeout_seconds
    
    def test_cpu_short_run_timeout_normal_step_timeout(self):
        """Verify CPU with short run timeout uses normal step timeout."""
        with patch.dict(os.environ, {"LLM_RUN_TIMEOUT_SECONDS": "120"}, clear=False):
            config = ComputeConfig(device="cpu")
            config.apply_recommended_defaults()
            
            assert config.run_timeout_seconds == 120
            assert config.step_timeout_seconds == 120  # No auto-increase for short runs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
