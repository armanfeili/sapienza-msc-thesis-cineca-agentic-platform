#!/bin/sh
# Docker entrypoint script for Cineca Agentic Platform
# Runs database migrations before starting the application

set -e

echo "🔄 Running database migrations..."

# Wait for PostgreSQL to be ready
max_attempts=30
attempt=0

until pg_isready -h "${DB_HOST:-postgres}" -p "${DB_PORT:-5432}" -U "${DB_USER:-cineca_user}" > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -gt $max_attempts ]; then
        echo "❌ PostgreSQL not ready after ${max_attempts} attempts"
        exit 1
    fi
    echo "⏳ Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
    sleep 2
done

echo "✅ PostgreSQL is ready"

# Run Alembic migrations
echo "🔧 Applying database migrations..."
cd /app/db/postgres_control && alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully"
else
    echo "❌ Migration failed"
    exit 1
fi

# Return to app directory
cd /app

# Execute the main command (uvicorn)
echo "🚀 Starting application..."
exec "$@"
