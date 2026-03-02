#!/usr/bin/env bash
# Entrypoint script for Cineca Agentic Platform Docker container
# Runs database migrations before starting the application

set -e

echo "🚀 Starting Cineca Agentic Platform..."

# Run database migrations if PostgreSQL is available
if [ -n "$DB_HOST" ]; then
    echo "📦 Running database migrations..."
    cd /app/db/postgres_control && alembic upgrade head || {
        echo "⚠️  Migration failed, but continuing..."
    }
    cd /app
    
    # Initialize default model in database (in background to not block startup)
    echo "🤖 Initializing default model (${DEFAULT_MODEL_NAME:-phi3:mini-instruct}) in background..."
    python scripts/ollama/init_default_model.py > /proc/1/fd/1 2>&1 &
fi

# Execute the main command (CMD from Dockerfile)
exec "$@"
