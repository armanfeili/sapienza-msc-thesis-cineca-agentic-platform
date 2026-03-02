#!/usr/bin/env bash

#
# PostgreSQL Database Restore Script
#
# This script restores a PostgreSQL database from a backup file.
#
# Usage: ./restore_database.sh <backup_file>
# Example: ./restore_database.sh /backups/postgres/backup_cineca_agentic_platform_20250102_120000.sql.gz
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# Check if backup file is provided
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh /backups/postgres/backup_*.sql.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cineca_agentic_platform}"
POSTGRES_USER="${POSTGRES_USER:-cineca}"

echo "========================================"
echo "PostgreSQL Restore Script"
echo "========================================"
echo "Database: $POSTGRES_DB"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Backup file: $BACKUP_FILE"
echo "========================================"

# Warning
echo ""
echo "⚠️  WARNING: This will REPLACE all data in the database!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

# Perform restore
echo ""
echo "Starting restore..."
if zcat "$BACKUP_FILE" | PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    --quiet; then
    
    echo "✅ Restore completed successfully!"
else
    echo "❌ Restore failed!"
    exit 1
fi

echo ""
echo "========================================"
echo "Restore completed at $(date)"
echo "========================================"
