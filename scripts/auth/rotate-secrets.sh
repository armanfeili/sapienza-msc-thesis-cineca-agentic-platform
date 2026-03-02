#!/bin/bash
set -euo pipefail

# Secrets Rotation Automation Script
# Usage: ./scripts/rotate-secrets.sh [secret-type] [--dry-run]
# Example: ./scripts/rotate-secrets.sh postgres
# Example: ./scripts/rotate-secrets.sh all --dry-run

SECRET_TYPE="${1:-}"
DRY_RUN="${2:-}"
BACKUP_DIR="/var/backups/secrets/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="logs/secrets-rotation.log"
ROTATION_RECORD="logs/rotation-history.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function: Log messages
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    
    case "$level" in
        INFO)
            echo -e "${BLUE}[INFO]${NC} [$timestamp] $message" | tee -a "$LOG_FILE"
            ;;
        SUCCESS)
            echo -e "${GREEN}[SUCCESS]${NC} [$timestamp] $message" | tee -a "$LOG_FILE"
            ;;
        WARNING)
            echo -e "${YELLOW}[WARNING]${NC} [$timestamp] $message" | tee -a "$LOG_FILE"
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} [$timestamp] $message" | tee -a "$LOG_FILE"
            ;;
    esac
}

# Function: Show usage
show_usage() {
    cat << EOF
Secrets Rotation Script

Usage: $0 <secret-type> [--dry-run]

Secret Types:
  postgres    - Rotate PostgreSQL password
  redis       - Rotate Redis password
  all         - Rotate all supported secrets

Options:
  --dry-run   - Show what would be done without making changes

Examples:
  $0 postgres
  $0 all --dry-run
  $0 redis

EOF
}

# Function: Check prerequisites
check_prerequisites() {
    log INFO "Checking prerequisites..."
    
    # Check if running from project root
    if [[ ! -f "docker-compose.yml" ]]; then
        log ERROR "Must run from project root directory"
        exit 1
    fi
    
    # Check if .env exists
    if [[ ! -f ".env" ]]; then
        log ERROR ".env file not found"
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info &>/dev/null; then
        log ERROR "Docker is not running"
        exit 1
    fi
    
    # Check if services are up
    if ! docker compose ps | grep -q "Up"; then
        log WARNING "Some services may not be running"
    fi
    
    log SUCCESS "Prerequisites check passed"
}

# Function: Backup current secrets
backup_secrets() {
    log INFO "Creating backup in $BACKUP_DIR"
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would create backup directory: $BACKUP_DIR"
        log INFO "[DRY RUN] Would backup: .env, docker-compose.yml"
        return 0
    fi
    
    mkdir -p "$BACKUP_DIR"
    cp .env "$BACKUP_DIR/.env"
    cp docker-compose.yml "$BACKUP_DIR/docker-compose.yml"
    
    # Create backup manifest
    cat > "$BACKUP_DIR/manifest.json" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_type": "secrets_rotation",
  "secret_type": "$SECRET_TYPE",
  "files": [".env", "docker-compose.yml"]
}
EOF
    
    log SUCCESS "Backup completed: $BACKUP_DIR"
}

# Function: Generate strong password
generate_password() {
    local length="${1:-32}"
    openssl rand -base64 48 | tr -d "=+/" | cut -c1-"$length"
}

# Function: Update .env file
update_env() {
    local key="$1"
    local value="$2"
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would update .env: $key=***"
        return 0
    fi
    
    # Use temporary file for atomic update
    local temp_file=$(mktemp)
    
    if grep -q "^${key}=" .env; then
        # Update existing key
        sed "s|^${key}=.*|${key}=${value}|" .env > "$temp_file"
    else
        # Add new key
        cp .env "$temp_file"
        echo "${key}=${value}" >> "$temp_file"
    fi
    
    mv "$temp_file" .env
    log INFO "Updated .env: $key"
}

# Function: Record rotation
record_rotation() {
    local secret_name="$1"
    local status="$2"
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would record rotation: $secret_name - $status"
        return 0
    fi
    
    # Create rotation record directory if it doesn't exist
    mkdir -p "$(dirname "$ROTATION_RECORD")"
    
    # Initialize file if it doesn't exist
    if [[ ! -f "$ROTATION_RECORD" ]]; then
        echo "[]" > "$ROTATION_RECORD"
    fi
    
    # Add rotation record
    local record=$(cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "secret": "$secret_name",
  "status": "$status",
  "user": "${USER:-unknown}",
  "dry_run": $([ "$DRY_RUN" == "--dry-run" ] && echo "true" || echo "false")
}
EOF
)
    
    # Append to rotation history using jq if available, otherwise simple append
    if command -v jq &>/dev/null; then
        local temp_file=$(mktemp)
        jq ". += [$record]" "$ROTATION_RECORD" > "$temp_file"
        mv "$temp_file" "$ROTATION_RECORD"
    else
        # Fallback: simple append (not valid JSON array, but keeps history)
        echo "$record" >> "$ROTATION_RECORD"
    fi
}

# Function: Rotate PostgreSQL password
rotate_postgres() {
    log INFO "========================================="
    log INFO "Starting PostgreSQL password rotation"
    log INFO "========================================="
    
    NEW_PG_PASSWORD=$(generate_password 32)
    NEW_USER="cineca_app_$(date +%Y%m%d)"
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would create new PostgreSQL user: $NEW_USER"
        log INFO "[DRY RUN] Would grant all privileges"
        log INFO "[DRY RUN] Would update DATABASE_URL in .env"
        record_rotation "postgresql" "dry_run"
        return 0
    fi
    
    # Check if PostgreSQL container is running
    if ! docker compose ps postgres | grep -q "Up"; then
        log ERROR "PostgreSQL container is not running"
        record_rotation "postgresql" "failed"
        return 1
    fi
    
    # Create new user with same privileges
    log INFO "Creating new PostgreSQL user: $NEW_USER"
    
    docker compose exec -T postgres psql -U postgres <<EOF || {
        log ERROR "Failed to create PostgreSQL user"
        record_rotation "postgresql" "failed"
        return 1
    }
CREATE USER ${NEW_USER} WITH PASSWORD '${NEW_PG_PASSWORD}';
GRANT ALL PRIVILEGES ON DATABASE cineca_platform TO ${NEW_USER};
-- Grant privileges on existing tables
\c cineca_platform
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${NEW_USER};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${NEW_USER};
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO ${NEW_USER};
-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO ${NEW_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO ${NEW_USER};
EOF
    
    # Update DATABASE_URL in .env
    DATABASE_URL="postgresql://${NEW_USER}:${NEW_PG_PASSWORD}@postgres:5432/cineca_platform"
    update_env "DATABASE_URL" "$DATABASE_URL"
    
    log SUCCESS "PostgreSQL password rotated successfully"
    log INFO "New user: $NEW_USER"
    log WARNING "Old user will be removed in 48 hours (manual step required)"
    
    record_rotation "postgresql" "success"
}

# Function: Rotate Redis password
rotate_redis() {
    log INFO "========================================="
    log INFO "Starting Redis password rotation"
    log INFO "========================================="
    
    NEW_REDIS_PASSWORD=$(generate_password 24)
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would update REDIS_PASSWORD in .env"
        log INFO "[DRY RUN] Would update REDIS_URL in .env"
        log INFO "[DRY RUN] Would restart Redis container"
        record_rotation "redis" "dry_run"
        return 0
    fi
    
    # Update .env
    update_env "REDIS_PASSWORD" "$NEW_REDIS_PASSWORD"
    update_env "REDIS_URL" "redis://:${NEW_REDIS_PASSWORD}@redis:6379/0"
    
    log WARNING "Redis password rotation will invalidate all active sessions"
    log INFO "Users will need to re-authenticate"
    
    log SUCCESS "Redis password rotated successfully"
    record_rotation "redis" "success"
}

# Function: Restart services
restart_services() {
    local service="${1:-app ui}"
    
    log INFO "========================================="
    log INFO "Restarting services: $service"
    log INFO "========================================="
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would restart services: $service"
        return 0
    fi
    
    for svc in $service; do
        log INFO "Restarting $svc..."
        docker compose up -d --no-deps --force-recreate "$svc"
        sleep 3
        
        # Check if service is healthy
        if docker compose ps "$svc" | grep -q "Up"; then
            log SUCCESS "$svc restarted successfully"
        else
            log ERROR "$svc failed to restart"
            return 1
        fi
    done
}

# Function: Verify rotation
verify_rotation() {
    log INFO "========================================="
    log INFO "Verifying rotation"
    log INFO "========================================="
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would verify service health"
        return 0
    fi
    
    # Check health endpoint
    log INFO "Checking health endpoints..."
    
    sleep 5  # Wait for services to stabilize
    
    # Check if app container is responding
    if docker compose exec -T app curl -f http://localhost:8000/v1/health/live &>/dev/null; then
        log SUCCESS "Health check passed"
    else
        log WARNING "Health check failed - manual verification required"
    fi
    
    # Check logs for errors
    log INFO "Checking recent logs for errors..."
    if docker compose logs --tail=50 app 2>&1 | grep -iE "error|exception|failed" | grep -v "test"; then
        log WARNING "Found errors in logs - please review"
    else
        log SUCCESS "No recent errors found in logs"
    fi
}

# Function: Send notification
notify() {
    local message="$1"
    
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        log INFO "[DRY RUN] Would send notification: $message"
        return 0
    fi
    
    # Log notification (can be extended to send to Slack, email, etc.)
    log INFO "NOTIFICATION: $message"
    
    # Example: Send to Slack (uncomment and configure)
    # if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    #     curl -X POST -H 'Content-type: application/json' \
    #       --data "{\"text\":\"🔐 Secrets Rotation: $message\"}" \
    #       "$SLACK_WEBHOOK_URL"
    # fi
}

# Main execution
main() {
    # Create log directory if it doesn't exist
    mkdir -p logs
    
    log INFO "======================================================"
    log INFO "Secrets Rotation Script"
    log INFO "======================================================"
    log INFO "Date: $(date)"
    log INFO "User: ${USER:-unknown}"
    log INFO "Secret Type: ${SECRET_TYPE:-not specified}"
    log INFO "Mode: $([ "$DRY_RUN" == "--dry-run" ] && echo "DRY RUN" || echo "LIVE")"
    log INFO "======================================================"
    
    # Validate arguments
    if [[ -z "$SECRET_TYPE" ]]; then
        log ERROR "No secret type specified"
        show_usage
        exit 1
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Create backup
    backup_secrets
    
    # Perform rotation based on type
    case "$SECRET_TYPE" in
        postgres|database|postgresql)
            rotate_postgres
            restart_services "app"
            ;;
        redis)
            rotate_redis
            restart_services "redis app ui"
            ;;
        all)
            rotate_postgres
            rotate_redis
            restart_services "redis app ui"
            ;;
        *)
            log ERROR "Unknown secret type: $SECRET_TYPE"
            show_usage
            exit 1
            ;;
    esac
    
    # Verify rotation
    verify_rotation
    
    # Send notification
    if [[ "$DRY_RUN" != "--dry-run" ]]; then
        notify "Secrets rotation completed successfully for: $SECRET_TYPE"
    fi
    
    log SUCCESS "======================================================"
    log SUCCESS "Secrets Rotation Completed"
    log SUCCESS "======================================================"
    log INFO "Backup location: $BACKUP_DIR"
    log INFO "Log file: $LOG_FILE"
    log INFO "Rotation history: $ROTATION_RECORD"
    log WARNING "Please verify all services are functioning correctly"
    log WARNING "Review the deployment checklist for post-rotation steps"
}

# Run main function
main "$@"
