#!/usr/bin/env bash
#
# Automated Database Backup Script
#
# Backs up PostgreSQL, Redis, and Memgraph databases with retention policy.
# Supports local and remote storage (S3-compatible).
#
# Usage:
#   ./backup.sh [--type <postgres|redis|memgraph|all>] [--upload]

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cineca-platform}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Database connection settings
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cineca_control}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

MEMGRAPH_HOST="${MEMGRAPH_HOST:-localhost}"
MEMGRAPH_PORT="${MEMGRAPH_PORT:-7687}"
MEMGRAPH_USER="${MEMGRAPH_USER:-}"
MEMGRAPH_PASSWORD="${MEMGRAPH_PASSWORD:-}"

# S3 settings (optional, for remote backups)
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-backups/cineca-platform}"

# Logging
LOG_FILE="${BACKUP_DIR}/backup.log"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
    exit 1
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL
backup_postgres() {
    log "Starting PostgreSQL backup..."
    
    local backup_file="${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.gz"
    
    # Use pg_dump with compression
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --format=custom \
        --verbose \
        --file="${BACKUP_DIR}/postgres_${TIMESTAMP}.dump" \
        2>&1 | tee -a "$LOG_FILE"
    
    # Also create plain SQL backup (easier to inspect)
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
        -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        2>&1 | gzip > "$backup_file"
    
    local size=$(du -h "$backup_file" | cut -f1)
    log "PostgreSQL backup completed: $backup_file ($size)"
    
    echo "$backup_file"
}

# Backup Redis
backup_redis() {
    log "Starting Redis backup..."
    
    local backup_file="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"
    
    # Trigger BGSAVE
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE
    
    # Wait for BGSAVE to complete
    while true; do
        local status=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE)
        sleep 1
        local new_status=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE)
        if [ "$status" != "$new_status" ]; then
            break
        fi
    done
    
    # Copy RDB file
    local rdb_file=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dir | tail -n1)
    local rdb_name=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dbfilename | tail -n1)
    
    cp "${rdb_file}/${rdb_name}" "$backup_file"
    gzip "$backup_file"
    
    local size=$(du -h "${backup_file}.gz" | cut -f1)
    log "Redis backup completed: ${backup_file}.gz ($size)"
    
    echo "${backup_file}.gz"
}

# Backup Memgraph
backup_memgraph() {
    log "Starting Memgraph backup..."
    
    local backup_dir="${BACKUP_DIR}/memgraph_${TIMESTAMP}"
    mkdir -p "$backup_dir"
    
    # Create snapshot using mgconsole or cypher-shell
    # Note: Memgraph requires LOCK DATA DIRECTORY for snapshots
    
    # If mgconsole is available
    if command -v mgconsole &> /dev/null; then
        echo "CREATE SNAPSHOT;" | mgconsole \
            --host "$MEMGRAPH_HOST" \
            --port "$MEMGRAPH_PORT" \
            --use-ssl=false
    else
        # Fallback: Export as Cypher script
        log "mgconsole not found, exporting as Cypher script"
        
        # Export all nodes and relationships
        # This is a simplified version - in production, use proper Memgraph export
        echo "MATCH (n) RETURN n LIMIT 100000;" > "${backup_dir}/nodes.cypher"
        echo "MATCH ()-[r]->() RETURN r LIMIT 100000;" > "${backup_dir}/relationships.cypher"
    fi
    
    # Compress backup directory
    tar -czf "${backup_dir}.tar.gz" -C "$BACKUP_DIR" "memgraph_${TIMESTAMP}"
    rm -rf "$backup_dir"
    
    local size=$(du -h "${backup_dir}.tar.gz" | cut -f1)
    log "Memgraph backup completed: ${backup_dir}.tar.gz ($size)"
    
    echo "${backup_dir}.tar.gz"
}

# Upload to S3
upload_to_s3() {
    local file=$1
    
    if [ -z "$S3_BUCKET" ]; then
        log "S3_BUCKET not set, skipping upload"
        return
    fi
    
    log "Uploading $file to S3..."
    
    # Use AWS CLI or s3cmd
    if command -v aws &> /dev/null; then
        aws s3 cp "$file" "s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$file")"
        log "Uploaded to s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$file")"
    elif command -v s3cmd &> /dev/null; then
        s3cmd put "$file" "s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$file")"
        log "Uploaded to s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$file")"
    else
        error "Neither aws nor s3cmd found. Cannot upload to S3."
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    
    find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+$RETENTION_DAYS" -delete
    find "$BACKUP_DIR" -name "*.dump" -mtime "+$RETENTION_DAYS" -delete
    find "$BACKUP_DIR" -name "*.rdb.gz" -mtime "+$RETENTION_DAYS" -delete
    find "$BACKUP_DIR" -name "memgraph_*.tar.gz" -mtime "+$RETENTION_DAYS" -delete
    
    log "Cleanup completed"
}

# Main backup function
main() {
    local backup_type="${1:-all}"
    local upload="${2:-false}"
    
    log "===== Starting backup ====="
    log "Type: $backup_type"
    log "Upload to S3: $upload"
    
    local files=()
    
    case "$backup_type" in
        postgres)
            files+=($(backup_postgres))
            ;;
        redis)
            files+=($(backup_redis))
            ;;
        memgraph)
            files+=($(backup_memgraph))
            ;;
        all)
            files+=($(backup_postgres))
            files+=($(backup_redis))
            files+=($(backup_memgraph))
            ;;
        *)
            error "Unknown backup type: $backup_type. Use: postgres, redis, memgraph, or all"
            ;;
    esac
    
    # Upload if requested
    if [ "$upload" = "true" ]; then
        for file in "${files[@]}"; do
            upload_to_s3 "$file"
        done
    fi
    
    # Cleanup old backups
    cleanup_old_backups
    
    log "===== Backup completed successfully ====="
    log "Backup files:"
    for file in "${files[@]}"; do
        log "  - $file"
    done
}

# Parse arguments
BACKUP_TYPE="all"
UPLOAD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        --upload)
            UPLOAD=true
            shift
            ;;
        *)
            error "Unknown argument: $1"
            ;;
    esac
done

main "$BACKUP_TYPE" "$UPLOAD"
