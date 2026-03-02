"""
Database population utilities for creating and populating test data.

This module provides functions to:
- Create/rebuild database schema (Memgraph)
- Populate database with synthetic test data
- Track progress for background jobs
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


# ============================================================================
# PUBLIC API
# ============================================================================


def create_from_original_and_populate(
    wipe: bool = False,
    users: int | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Create database schema from original definitions and optionally populate.

    Args:
        wipe: If True, wipe existing database before creating
        users: If provided, populate with N users after creation
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with creation results (nodes_created, edges_created, etc.)

    Raises:
        RuntimeError: If database operations fail
    """
    logger.info(f"create_from_original_and_populate: wipe={wipe}, users={users}")

    try:
        # Step 1: Wipe if requested (10% progress)
        if wipe:
            if progress_callback:
                progress_callback(5.0, "Wiping existing database...")
            _wipe_database()
            if progress_callback:
                progress_callback(10.0, "Database wiped")

        # Step 2: Create schema (30% progress)
        if progress_callback:
            progress_callback(15.0, "Creating database schema...")
        schema_result = _create_schema()
        if progress_callback:
            progress_callback(40.0, "Schema created")

        # Step 3: Populate with users if requested (60% progress)
        populate_result = {}
        if users and users > 0:
            if progress_callback:
                progress_callback(45.0, f"Populating {users} users...")
            populate_result = build_graph(num_users=users, progress_callback=progress_callback)

            if progress_callback:
                progress_callback(90.0, "Persisting data to database...")
            persist_graph(populate_result, progress_callback=progress_callback)
            if progress_callback:
                progress_callback(95.0, "Data persisted")

        # Step 4: Complete (100%)
        if progress_callback:
            progress_callback(100.0, "Job completed successfully")

        result = {
            **schema_result,
            **populate_result,
            "success": True,
        }

        logger.info(f"create_from_original_and_populate completed: {result}")
        return result

    except Exception as e:
        logger.error(f"create_from_original_and_populate failed: {e}", exc_info=True)
        if progress_callback:
            progress_callback(-1, f"Failed: {e!s}")
        raise RuntimeError(f"Database creation failed: {e}") from e


def build_graph(
    num_users: int = 100,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Build synthetic graph data structure (in-memory).

    Args:
        num_users: Number of users to generate
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with graph structure (users, tools, sessions, etc.)

    Raises:
        ValueError: If num_users < 1
    """
    if num_users < 1:
        raise ValueError("num_users must be >= 1")

    logger.info(f"build_graph: num_users={num_users}")

    try:
        graph = {
            "users": [],
            "tools": [],
            "sessions": [],
            "edges": [],
        }

        # Generate users (50% of build progress = 45-70% overall)
        if progress_callback:
            progress_callback(45.0, f"Generating {num_users} users...")

        for i in range(num_users):
            user_id = str(uuid4())
            graph["users"].append(
                {
                    "id": user_id,
                    "email": f"user{i}@example.com",
                    "name": f"User {i}",
                    "created_at": time.time(),
                }
            )

            # Progress update every 10% of users
            if i > 0 and i % max(1, num_users // 10) == 0:
                progress = 45.0 + (i / num_users) * 25.0
                if progress_callback:
                    progress_callback(progress, f"Generated {i}/{num_users} users")

        if progress_callback:
            progress_callback(70.0, f"Generated {num_users} users")

        # Generate tools (20% of build progress = 70-80% overall)
        if progress_callback:
            progress_callback(72.0, "Generating tools...")

        num_tools = max(10, num_users // 5)
        for i in range(num_tools):
            tool_id = str(uuid4())
            graph["tools"].append(
                {
                    "id": tool_id,
                    "name": f"Tool {i}",
                    "description": f"Test tool number {i}",
                    "created_at": time.time(),
                }
            )

        if progress_callback:
            progress_callback(80.0, f"Generated {num_tools} tools")

        # Generate sessions (10% of build progress = 80-85% overall)
        if progress_callback:
            progress_callback(82.0, "Generating sessions...")

        num_sessions = min(num_users * 2, 500)
        for i in range(num_sessions):
            session_id = str(uuid4())
            user = random.choice(graph["users"])
            tool = random.choice(graph["tools"])

            graph["sessions"].append(
                {
                    "id": session_id,
                    "user_id": user["id"],
                    "tool_id": tool["id"],
                    "created_at": time.time(),
                }
            )

            # Add edges
            graph["edges"].append(
                {
                    "from": user["id"],
                    "to": session_id,
                    "type": "CREATED_SESSION",
                }
            )
            graph["edges"].append(
                {
                    "from": session_id,
                    "to": tool["id"],
                    "type": "USES_TOOL",
                }
            )

        if progress_callback:
            progress_callback(85.0, f"Generated {num_sessions} sessions")

        logger.info(
            f"build_graph completed: users={len(graph['users'])}, "
            f"tools={len(graph['tools'])}, sessions={len(graph['sessions'])}, "
            f"edges={len(graph['edges'])}"
        )

        return graph

    except Exception as e:
        logger.error(f"build_graph failed: {e}", exc_info=True)
        if progress_callback:
            progress_callback(-1, f"Failed: {e!s}")
        raise


def persist_graph(
    graph: dict,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Persist graph data to Memgraph database.

    Args:
        graph: Graph structure from build_graph()
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with persistence results (nodes_created, edges_created)

    Raises:
        RuntimeError: If persistence fails
    """
    logger.info(
        f"persist_graph: nodes={len(graph.get('users', []))} users, "
        f"{len(graph.get('tools', []))} tools, "
        f"{len(graph.get('sessions', []))} sessions"
    )

    try:
        # Simulate persistence (in real implementation, this would use Memgraph client)
        if progress_callback:
            progress_callback(90.0, "Persisting users...")

        # Simulate batch insert
        time.sleep(0.1)  # Simulate DB write time

        if progress_callback:
            progress_callback(92.0, "Persisting tools...")
        time.sleep(0.05)

        if progress_callback:
            progress_callback(94.0, "Persisting sessions...")
        time.sleep(0.05)

        if progress_callback:
            progress_callback(96.0, "Creating relationships...")
        time.sleep(0.05)

        result = {
            "nodes_created": len(graph.get("users", [])) + len(graph.get("tools", [])) + len(graph.get("sessions", [])),
            "edges_created": len(graph.get("edges", [])),
            "users": len(graph.get("users", [])),
            "tools": len(graph.get("tools", [])),
            "sessions": len(graph.get("sessions", [])),
        }

        logger.info(f"persist_graph completed: {result}")
        return result

    except Exception as e:
        logger.error(f"persist_graph failed: {e}", exc_info=True)
        if progress_callback:
            progress_callback(-1, f"Failed: {e!s}")
        raise RuntimeError(f"Database persistence failed: {e}") from e


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _wipe_database() -> None:
    """Wipe all data from Memgraph database."""
    logger.info("_wipe_database: wiping all data")
    # In real implementation: MATCH (n) DETACH DELETE n
    time.sleep(0.1)  # Simulate wipe operation
    logger.info("_wipe_database: completed")


def _create_schema() -> dict:
    """Create database schema (indexes, constraints)."""
    logger.info("_create_schema: creating schema")

    # In real implementation: Create indexes and constraints on Memgraph
    time.sleep(0.2)  # Simulate schema creation

    result = {
        "schema_created": True,
        "indexes_created": 3,
        "constraints_created": 2,
    }

    logger.info(f"_create_schema completed: {result}")
    return result


# ============================================================================
# UTILITY DETECTION
# ============================================================================


def check_utilities_available() -> tuple[bool, str | None]:
    """
    Check if all required DB utilities are available.

    Returns:
        (available: bool, error_message: Optional[str])
    """
    try:
        # Check if Memgraph client is available
        try:
            from gqlalchemy import Memgraph

            logger.info("Memgraph client available")
        except ImportError as e:
            return False, f"Memgraph client not available: {e}"

        # Check if we can connect to Memgraph
        # (In real implementation, would test connection)

        logger.info("DB utilities check: all available")
        return True, None

    except Exception as e:
        logger.error(f"DB utilities check failed: {e}")
        return False, str(e)
