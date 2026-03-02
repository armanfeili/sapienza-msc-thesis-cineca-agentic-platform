-- PostgreSQL initialization script for Cineca Agentic Platform
-- This script runs once when the container is first created

-- Ensure the database and user exist (handled by POSTGRES_DB, POSTGRES_USER env vars)
-- Grant necessary privileges
GRANT ALL PRIVILEGES ON DATABASE cineca_platform TO cineca_user;

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Note: Actual schema (tables) will be created by Alembic migrations
