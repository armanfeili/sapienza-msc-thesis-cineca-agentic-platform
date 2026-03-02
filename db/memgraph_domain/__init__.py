"""
db package — Memgraph helpers and configuration.

Convenience re-exports so callers can simply do:

    from db import settings, get_memgraph

    mg = get_memgraph()
    mg.execute("MATCH (n) RETURN n LIMIT 5")

Files:
- config.py           -> pydantic Settings (MG_HOST, MG_PORT, …)
- memgraph_client.py  -> get_memgraph() factory for gqlalchemy.Memgraph
- create_original_db.py / populate.py -> dataset loaders (CLI entry scripts)
"""

from .config import settings
from .memgraph_client import get_memgraph

__all__ = ["get_memgraph", "settings"]
