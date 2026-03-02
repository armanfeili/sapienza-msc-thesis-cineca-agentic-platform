#!/usr/bin/env python3
"""
Initialize default model in database.

This script ensures that the configured default model (phi3:mini-instruct)
is registered in the database and marked as the default model.

Usage:
    python scripts/init_default_model.py
    
Environment variables:
    DEFAULT_MODEL_NAME: Model name to set as default (default: phi3:mini)
    OLLAMA_BASE_URL: Ollama API URL (default: http://ollama:11434/v1)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.postgres_control.repositories import model_instance_repo, provider_repo
import structlog

log = structlog.get_logger(__name__)


def init_default_model():
    """Initialize default model in database."""
    
    # Get configuration from environment
    default_model_name = os.getenv("DEFAULT_MODEL_NAME", "phi3:mini")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
    
    log.info("init_default_model.start", model=default_model_name, base_url=ollama_base_url)
    
    try:
        # Reuse existing healthy default if present to avoid redundant warmups
        try:
            existing_default = model_instance_repo.get_default(scope="global", tenant_id=None)
        except Exception as existing_err:
            existing_default = None
            log.warning("init_default_model.default_lookup_failed", error=str(existing_err))

        if existing_default:
            same_model = str(existing_default.provider_model_id) == default_model_name
            same_base = str(existing_default.base_url).rstrip("/") == ollama_base_url.rstrip("/")
            cached_health = provider_repo.get_provider_health(existing_default.provider_id)
            if same_model and same_base and cached_health and cached_health.get("ok") and cached_health.get("reachable"):
                log.info(
                    "init_default_model.reuse_existing_default",
                    model=default_model_name,
                    provider_id=existing_default.provider_id,
                    instance_name=existing_default.instance_name,
                )
                return {
                    "id": existing_default.instance_id or existing_default.provider_id,
                    "model_id": existing_default.provider_model_id,
                    "provider_id": existing_default.provider_id,
                    "instance_name": existing_default.instance_name,
                }

        # 1. Ensure Ollama provider exists
        log.info("init_default_model.check_provider")
        providers = provider_repo.list_providers()
        
        ollama_provider = None
        for provider in providers:
            if provider.get("base_url") == ollama_base_url:
                ollama_provider = provider
                break
        
        if not ollama_provider:
            log.info("init_default_model.create_provider", base_url=ollama_base_url)
            ollama_provider = provider_repo.create_provider(
                name="ollama-local",
                type="ollama",
                base_url=ollama_base_url,
                tenant_id=None,
                config={"timeout_secs": 180},
                actor="system:init"
            )
        
        provider_id = ollama_provider["id"]
        log.info("init_default_model.provider_ready", provider_id=provider_id)
        
        # 2. Check if model instance already exists
        log.info("init_default_model.check_instance", model=default_model_name)
        instances, _, _ = model_instance_repo.list_instances()
        
        target_instance = None
        for inst in instances:
            if inst.get("model_id") == default_model_name and inst.get("provider_id") == provider_id:
                target_instance = inst
                break
        
        # 3. Create model instance if it doesn't exist
        if not target_instance:
            log.info("init_default_model.create_instance", model=default_model_name)
            target_instance = model_instance_repo.create_instance(
                provider_id=provider_id,
                instance_name=default_model_name.replace(":", "-"),
                model_id=default_model_name,
                tenant_id=None,  # Global default
                parameters={
                    "temperature": 0.7,
                    "max_tokens": 2048,
                    "top_p": 0.9
                },
                owner_sub="system:init"
            )
            log.info("init_default_model.instance_created", instance_id=target_instance["id"])
        
        # 4. Set this instance as the global default
        instance_id = target_instance["id"]
        log.info("init_default_model.set_default", instance_id=instance_id)
        model_instance_repo.set_default(
            instance_id=instance_id,
            scope="global",
            tenant_id=None,
            owner_sub="system:init"
        )
        log.info("init_default_model.default_set", instance_id=instance_id)
        
        # 5. Warm up the model and refresh provider health
        log.info("init_default_model.warmup_start", model=default_model_name)
        try:
            import httpx
            import time
            
            # Give Ollama a moment to be fully ready
            time.sleep(2)
            
            # Warm up the model with a simple call
            warmup_url = f"{ollama_base_url}/chat/completions"
            warmup_payload = {
                "model": default_model_name,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10,
                "temperature": 0.1
            }
            
            async def warmup_model():
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(warmup_url, json=warmup_payload)
                    return response.status_code == 200
            
            import asyncio
            warmup_success = asyncio.run(warmup_model())
            
            if warmup_success:
                log.info("init_default_model.warmup_success", model=default_model_name)
                
                # Set provider health in Redis to mark it as healthy
                try:
                    health_data = {
                        "ok": True,
                        "reachable": True,
                        "status": 200,
                        "checked_at": int(time.time())
                    }
                    provider_repo.set_provider_health(provider_id, health_data)
                    log.info("init_default_model.health_set", provider_id=provider_id)
                except Exception as health_err:
                    log.warning("init_default_model.health_set_failed", error=str(health_err))
            else:
                log.warning("init_default_model.warmup_failed", model=default_model_name)
                
        except Exception as warmup_err:
            log.warning("init_default_model.warmup_error", error=str(warmup_err))
            # Non-fatal: continue even if warmup fails
        
        log.info(
            "init_default_model.complete",
            model=default_model_name,
            instance_id=target_instance["id"],
            instance_name=target_instance.get("instance_name")
        )
        
        return target_instance
        
    except Exception as e:
        log.error("init_default_model.failed", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    try:
        init_default_model()
        print("✅ Default model initialized successfully")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to initialize default model: {e}")
        sys.exit(1)
