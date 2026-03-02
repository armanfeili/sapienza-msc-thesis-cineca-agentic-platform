#!/usr/bin/env bash

#
# Automated PostgreSQL Database Backup Script
# 
# This script creates daily backups of the PostgreSQL database and maintains
# a retention policy to automatically clean up old backups.
#
# Usage: ./backup_database.sh
# Recommended: Run via cron daily
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"  # Keep backups for 7 days
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cineca_agentic_platform}"
POSTGRES_USER="${POSTGRES_USER:-cineca}"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

echo "========================================"
echo "PostgreSQL Backup Script"
echo "========================================"
echo "Database: $POSTGRES_DB"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Backup file: $BACKUP_FILE"
echo "Retention: $RETENTION_DAYS days"
echo "========================================"

# Perform backup using pg_dump
echo "Starting backup..."
if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean \
    --create \
    --if-exists \
    | gzip > "$BACKUP_FILE"; then
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ Backup completed successfully!"
    echo "   File: $BACKUP_FILE"
    echo "   Size: $BACKUP_SIZE"
else
    echo "❌ Backup failed!"
    exit 1
fi

# Clean up old backups
echo ""
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..."
DELETED_COUNT=0

while IFS= read -r old_backup; do
    echo "   Deleting: $old_backup"
    rm -f "$old_backup"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "$BACKUP_DIR" -name "backup_*.sql.gz" -type f -mtime +"$RETENTION_DAYS")

if [ "$DELETED_COUNT" -gt 0 ]; then
    echo "✅ Deleted $DELETED_COUNT old backup(s)"
else
    echo "ℹ️  No old backups to delete"
fi

# Show current backups
echo ""
echo "Current backups:"
ls -lh "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null || echo "No backups found"

echo ""
echo "========================================"
echo "Backup completed at $(date)"
echo "========================================"

# Optional: Upload to S3 or other cloud storage
# Uncomment and configure if needed
# if [ -n "${AWS_S3_BUCKET:-}" ]; then
#     echo "Uploading to S3..."
#     aws s3 cp "$BACKUP_FILE" "s3://${AWS_S3_BUCKET}/backups/postgres/"
#     echo "✅ Uploaded to S3"
# fi
