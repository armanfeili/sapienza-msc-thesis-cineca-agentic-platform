"""
Health check infrastructure for the Cineca Agentic Platform.

This package provides a unified component-based health check system with:
- Component registry for all dependencies
- Standardized probe interface
- Policy-based readiness/startup evaluation
- Deprecation management for legacy endpoints
"""

from src.health.components import ComponentCheck, ComponentStatus, get_component_registry
from src.health.config import HealthConfig, get_health_config
from src.health.policy import (
    build_response_body,
    evaluate_readiness,
    evaluate_startup,
    get_all_checks,
)

__all__ = [
    "ComponentCheck",
    "ComponentStatus",
    "HealthConfig",
    "build_response_body",
    "evaluate_readiness",
    "evaluate_startup",
    "get_all_checks",
    "get_component_registry",
    "get_health_config",
]
