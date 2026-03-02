"""
PostgreSQL database engine and session management.

Provides SQLAlchemy engine with connection pooling, session factory,
and dependency injection for FastAPI endpoints.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from src.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy declarative base for ORM models
Base = declarative_base()


def create_db_engine() -> Engine:
    """
    Create SQLAlchemy engine with connection pooling.

    Returns:
        Configured Engine instance
    """
    engine_config = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "pool_recycle": settings.DB_POOL_RECYCLE,
    }

    # Use QueuePool for production, NullPool for testing
    if settings.APP_ENV == "test":
        engine_config["poolclass"] = NullPool
        logger.info("Using NullPool for testing")
    else:
        engine_config["poolclass"] = QueuePool
        engine_config["pool_size"] = settings.DB_POOL_SIZE
        engine_config["max_overflow"] = settings.DB_POOL_SIZE * 2
        engine_config["pool_timeout"] = settings.DB_POOL_TIMEOUT
        logger.info(f"Using QueuePool with size={settings.DB_POOL_SIZE}")

    # Add statement timeout for safety
    connect_args = {"options": "-c statement_timeout=30000"}  # 30 seconds
    if settings.DB_SSLMODE and settings.DB_SSLMODE != "disable":
        connect_args["sslmode"] = settings.DB_SSLMODE

    engine_config["connect_args"] = connect_args

    engine = create_engine(settings.database_url, **engine_config)

    # Register event listeners for logging slow queries
    @event.listens_for(engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
        conn.info.setdefault("query_start_time", []).append(__import__("time").time())

    @event.listens_for(engine, "after_cursor_execute")
    def receive_after_cursor_execute(conn, cursor, statement, params, context, executemany):
        total = __import__("time").time() - conn.info["query_start_time"].pop()
        # Log slow queries (>200ms)
        if total > 0.2:
            # Redact params for security
            logger.warning(f"Slow query detected ({total:.3f}s): {statement[:200]}...")

    logger.info(f"Database engine created: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    return engine


# Global engine instance (created on first import)
engine: Engine = create_db_engine()

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Prevent lazy loading issues
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.

    Usage:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions (non-FastAPI code).

    Usage:
        with get_db_context() as db:
            items = db.query(Item).all()

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> tuple[bool, str | None]:
    """
    Check if database is reachable and healthy.

    Returns:
        Tuple of (is_healthy, error_message)
        - (True, None) if database is healthy
        - (False, error_message) if database check failed
    """
    try:
        with get_db_context() as db:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return (True, None)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return (False, str(e))


__all__ = [
    "Base",
    "SessionLocal",
    "check_db_health",
    "engine",
    "get_db",
    "get_db_context",
]
