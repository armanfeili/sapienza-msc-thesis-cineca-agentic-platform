"""
Logging bootstrap for the Cineca Agentic Platform.

- Configures a unified logging pipeline for stdlib logging, FastAPI, and Uvicorn.
- Uses `structlog` with either pretty console logs (dev) or JSON logs (prod).
- Call `setup_logging(level="INFO")` once at startup (the app does this).

Environment knobs (optional):
- LOG_FORMAT=json|console   # default: console in dev, json if APP_ENV in {prod,production}
- APP_ENV=dev|stage|prod    # influences default format
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

class AccessPathFilter(logging.Filter):
    """Filter that drops records whose message contains suppressed path fragments."""

    def __init__(self, *paths: str) -> None:
        super().__init__(name="access-path-filter")
        if paths:
            self._paths = tuple(p.lower() for p in paths if p)
        else:
            self._paths = tuple()

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not self._paths:
            return True

        targets: list[str] = []
        try:
            message = record.getMessage()
            if message:
                targets.append(message.lower())
        except Exception:  # pragma: no cover - defensive fallback
            pass

        args = getattr(record, "args", None)
        if isinstance(args, tuple):
            for value in args:
                if isinstance(value, str):
                    targets.append(value.lower())
        elif isinstance(args, dict):
            for value in args.values():
                if isinstance(value, str):
                    targets.append(value.lower())

        if not targets:
            return True

        return not any(path in target for target in targets for path in self._paths)


def _coerce_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    if not level:
        return logging.INFO
    try:
        return getattr(logging, str(level).upper())
    except AttributeError:
        return logging.INFO


def _wants_json() -> bool:
    fmt = os.getenv("LOG_FORMAT", "").strip().lower()
    if fmt in {"json", "console"}:
        return fmt == "json"
    env = os.getenv("APP_ENV", "dev").strip().lower()
    return env in {"prod", "production"}


def setup_logging(level: str | int = "INFO") -> None:
    """
    Initialize structlog + stdlib logging with a single StreamHandler.

    This function is idempotent-ish: calling it again will replace handlers
    on the root/uvicorn/fastapi loggers with the current configuration.
    """
    log_level = _coerce_level(level)
    use_json = _wants_json()

    # Base processors used for both console and JSON
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    pre_chain = [
        structlog.contextvars.merge_contextvars,  # support contextvars if used
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
    ]

    if use_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer()  # nice human format

    # Configure structlog to hand off rendering to ProcessorFormatter
    structlog.configure(
        processors=[
            # Add/normalize event dict
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,  # hand off to stdlib formatter
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    # Build a ProcessorFormatter so stdlib handlers can use structlog processors
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=pre_chain,
    )

    # Create a single stream handler writing to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)

    # Root logger
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(log_level)

    # Align common framework loggers
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers[:] = [handler]
        lg.setLevel(log_level)
        lg.propagate = False

    # Drop high-frequency access logs while keeping other routes visible
    noise_paths = ["/metrics", "/health", "get /v1/agent-runs/", "options /v1/"]
    extra_noise = os.getenv("UVICORN_ACCESS_FILTER_PATHS")
    if extra_noise:
        noise_paths.extend(p.strip() for p in extra_noise.split(",") if p.strip())
    access_filter = AccessPathFilter(*noise_paths)
    logging.getLogger("uvicorn.access").addFilter(access_filter)

    # Reduce noise from common libraries (tune as needed)
    for noisy in ("asyncio", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(min(log_level, logging.WARNING))

    structlog.get_logger(__name__).info(
        "logging initialized",
        level=log_level,
        json=use_json,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Convenience accessor for a structlog logger.
    """
    return structlog.get_logger(name) if name else structlog.get_logger()
