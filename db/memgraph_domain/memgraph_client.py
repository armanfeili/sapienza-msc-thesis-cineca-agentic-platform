from dotenv import load_dotenv
from gqlalchemy import Memgraph

from .config import settings

# Load environment variables from .env (in project root or current dir)
load_dotenv()

# Get Memgraph connection details from environment variables, with sensible defaults
MG_HOST = settings.MG_HOST
MG_PORT = settings.MG_PORT
MG_USER = settings.MG_USER
MG_PASSWORD = settings.MG_PASSWORD


def get_memgraph():
    """
    Returns a Memgraph client instance using environment variables.
    Usage:
        mg = get_memgraph()
        mg.execute("MATCH (n) RETURN n LIMIT 5")
    """
    # If username/password are set, use them (future-proofing for auth)
    if MG_USER and MG_PASSWORD:
        return Memgraph(host=MG_HOST, port=MG_PORT, username=MG_USER, password=MG_PASSWORD)
    else:
        return Memgraph(host=MG_HOST, port=MG_PORT)


# Optional: Quick test if run directly (for debugging)
if __name__ == "__main__":
    mg = get_memgraph()
    print(f"Connected to Memgraph at {MG_HOST}:{MG_PORT}")
    try:
        result = mg.execute_and_fetch("MATCH (n) RETURN n LIMIT 5")
        for record in result:
            print(record)
        print("Sample query succeeded!")
    except Exception as e:
        print(f"Failed to query Memgraph: {e}")
