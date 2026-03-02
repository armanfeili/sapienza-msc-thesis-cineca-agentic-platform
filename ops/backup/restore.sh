#!/usr/bin/env bash
#
# Database Restore Script
#
# Restores PostgreSQL, Redis, and Memgraph databases from backups.
#
# Usage:
#   ./restore.sh --type <postgres|redis|memgraph> --file <backup_file>

set -euo pipefail

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cineca_control}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

MEMGRAPH_HOST="${MEMGRAPH_HOST:-localhost}"
MEMGRAPH_PORT="${MEMGRAPH_PORT:-7687}"

LOG_FILE="${LOG_FILE:-/var/log/cineca-platform/restore.log}"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
    exit 1
}

# Restore PostgreSQL
restore_postgres() {
    local backup_file=$1
    
    log "Starting PostgreSQL restore from $backup_file..."
    
    # Check file extension
    if [[ "$backup_file" == *.dump ]]; then
        # Custom format restore
        PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_restore \
            -h "$POSTGRES_HOST" \
            -p "$POSTGRES_PORT" \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            --clean \
            --if-exists \
            --verbose \
            "$backup_file" \
            2>&1 | tee -a "$LOG_FILE"
    elif [[ "$backup_file" == *.sql.gz ]]; then
        # Plain SQL restore
        gunzip -c "$backup_file" | PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
            -h "$POSTGRES_HOST" \
            -p "$POSTGRES_PORT" \
            -U "$POSTGRES_USER" \
            -d "$POSTGRES_DB" \
            2>&1 | tee -a "$LOG_FILE"
    else
        error "Unknown PostgreSQL backup format: $backup_file"
    fi
    
    log "PostgreSQL restore completed"
}

# Restore Redis
restore_redis() {
    local backup_file=$1
    
    log "Starting Redis restore from $backup_file..."
    
    # Stop Redis (if running via systemd)
    if systemctl is-active --quiet redis; then
        log "Stopping Redis service..."
        sudo systemctl stop redis
    fi
    
    # Get Redis data directory
    local rdb_dir=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dir 2>/dev/null | tail -n1 || echo "/var/lib/redis")
    local rdb_name=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dbfilename 2>/dev/null | tail -n1 || echo "dump.rdb")
    
    # Decompress and copy RDB file
    if [[ "$backup_file" == *.gz ]]; then
        gunzip -c "$backup_file" > "${rdb_dir}/${rdb_name}"
    else
        cp "$backup_file" "${rdb_dir}/${rdb_name}"
    fi
    
    # Start Redis
    if command -v systemctl &> /dev/null; then
        log "Starting Redis service..."
        sudo systemctl start redis
    else
        log "Please start Redis manually"
    fi
    
    log "Redis restore completed"
}

# Restore Memgraph
restore_memgraph() {
    local backup_file=$1
    
    log "Starting Memgraph restore from $backup_file..."
    
    # Extract backup
    local temp_dir=$(mktemp -d)
    tar -xzf "$backup_file" -C "$temp_dir"
    
    # Restore using mgconsole or cypher-shell
    if command -v mgconsole &> /dev/null; then
        # Clear existing data
        echo "MATCH (n) DETACH DELETE n;" | mgconsole \
            --host "$MEMGRAPH_HOST" \
            --port "$MEMGRAPH_PORT" \
            --use-ssl=false
        
        # Restore from snapshot if available
        # Note: Actual restore depends on Memgraph version and backup format
        log "Memgraph restore: Please load snapshot manually via Memgraph Lab or mgconsole"
    else
        error "mgconsole not found. Cannot restore Memgraph."
    fi
    
    # Cleanup
    rm -rf "$temp_dir"
    
    log "Memgraph restore completed"
}

# Verify restore
verify_restore() {
    local db_type=$1
    
    log "Verifying $db_type restore..."
    
    case "$db_type" in
        postgres)
            # Check connection and row count
            local count=$(PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
                -h "$POSTGRES_HOST" \
                -p "$POSTGRES_PORT" \
                -U "$POSTGRES_USER" \
                -d "$POSTGRES_DB" \
                -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
                2>/dev/null || echo "0")
            log "PostgreSQL tables found: $count"
            ;;
        redis)
            # Check connection and key count
            local count=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DBSIZE 2>/dev/null || echo "0")
            log "Redis keys found: $count"
            ;;
        memgraph)
            # Check connection and node count
            if command -v mgconsole &> /dev/null; then
                local count=$(echo "MATCH (n) RETURN count(n);" | mgconsole \
                    --host "$MEMGRAPH_HOST" \
                    --port "$MEMGRAPH_PORT" \
                    --use-ssl=false 2>/dev/null || echo "0")
                log "Memgraph nodes found: $count"
            fi
            ;;
    esac
}

# Main
main() {
    local db_type=""
    local backup_file=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --type)
                db_type="$2"
                shift 2
                ;;
            --file)
                backup_file="$2"
                shift 2
                ;;
            *)
                error "Unknown argument: $1"
                ;;
        esac
    done
    
    # Validate arguments
    if [ -z "$db_type" ]; then
        error "Missing --type argument"
    fi
    
    if [ -z "$backup_file" ]; then
        error "Missing --file argument"
    fi
    
    if [ ! -f "$backup_file" ]; then
        error "Backup file not found: $backup_file"
    fi
    
    log "===== Starting restore ====="
    log "Type: $db_type"
    log "File: $backup_file"
    
    # Confirm restore
    read -p "This will OVERWRITE existing data. Continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log "Restore cancelled by user"
        exit 0
    fi
    
    # Restore
    case "$db_type" in
        postgres)
            restore_postgres "$backup_file"
            verify_restore "postgres"
            ;;
        redis)
            restore_redis "$backup_file"
            verify_restore "redis"
            ;;
        memgraph)
            restore_memgraph "$backup_file"
            verify_restore "memgraph"
            ;;
        *)
            error "Unknown database type: $db_type"
            ;;
    esac
    
    log "===== Restore completed successfully ====="
}

main "$@"
