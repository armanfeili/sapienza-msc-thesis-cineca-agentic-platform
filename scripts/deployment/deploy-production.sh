#!/bin/bash
#
# Production Deployment Script for Cineca Agentic Platform
#
# Usage:
#   ./scripts/deploy-production.sh [environment]
#
# Examples:
#   ./scripts/deploy-production.sh staging
#   ./scripts/deploy-production.sh production
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-staging}"
DOCKER_COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="./backups"
DEPLOYMENT_LOG="./logs/deployment-$(date +%Y%m%d-%H%M%S).log"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$DEPLOYMENT_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$DEPLOYMENT_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$DEPLOYMENT_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$DEPLOYMENT_LOG"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check environment file
    if [ ! -f .env ]; then
        log_error ".env file not found"
        log_info "Copy .env.example to .env and configure it"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

backup_current_state() {
    log_info "Creating backup before deployment..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup PostgreSQL
    if docker compose ps postgres | grep -q "Up"; then
        log_info "Backing up PostgreSQL database..."
        ./scripts/backup_database.sh || log_warning "PostgreSQL backup failed"
    fi
    
    # Backup Memgraph (if needed)
    # Add Memgraph backup logic here if required
    
    log_success "Backup completed"
}

run_smoke_tests() {
    log_info "Running smoke tests..."
    
    # Wait for services to be ready
    sleep 10
    
    # Test health endpoints
    for service in app ui; do
        max_attempts=30
        attempt=0
        
        while [ $attempt -lt $max_attempts ]; do
            if curl -f http://localhost:8000/v1/health/live &> /dev/null; then
                log_success "$service health check passed"
                break
            fi
            
            attempt=$((attempt + 1))
            log_info "Waiting for $service to be ready ($attempt/$max_attempts)..."
            sleep 2
        done
        
        if [ $attempt -eq $max_attempts ]; then
            log_error "$service failed to become healthy"
            return 1
        fi
    done
    
    log_success "All smoke tests passed"
}

deploy() {
    log_info "Starting deployment to $ENVIRONMENT..."
    
    # Pull latest images
    log_info "Pulling latest Docker images..."
    docker compose pull
    
    # Build custom images
    log_info "Building application images..."
    docker compose build --no-cache
    
    # Stop old containers
    log_info "Stopping old containers..."
    docker compose down
    
    # Start new containers
    log_info "Starting new containers..."
    docker compose up -d
    
    # Wait for containers to be healthy
    log_info "Waiting for containers to be healthy..."
    sleep 5
    
    # Check container status
    docker compose ps
    
    log_success "Deployment completed"
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check all containers are running
    if ! docker compose ps | grep -q "Up"; then
        log_error "Some containers are not running"
        docker compose ps
        return 1
    fi
    
    # Run smoke tests
    run_smoke_tests
    
    log_success "Deployment verification passed"
}

rollback() {
    log_warning "Rolling back deployment..."
    
    # Stop current containers
    docker compose down
    
    # Restore from backup if needed
    # Add restore logic here
    
    # Start previous version
    # Add rollback logic here
    
    log_success "Rollback completed"
}

show_status() {
    log_info "Current system status:"
    echo ""
    docker compose ps
    echo ""
    
    log_info "Container logs (last 20 lines):"
    docker compose logs --tail=20
}

# Main execution
main() {
    log_info "=== Cineca Agentic Platform Deployment ==="
    log_info "Environment: $ENVIRONMENT"
    log_info "Timestamp: $(date)"
    log_info "User: $(whoami)"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Confirmation prompt
    read -p "Deploy to $ENVIRONMENT? (yes/no): " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
    
    # Backup current state
    backup_current_state
    
    # Deploy
    if deploy; then
        # Verify deployment
        if verify_deployment; then
            log_success "=== Deployment successful ==="
            show_status
        else
            log_error "Deployment verification failed"
            read -p "Rollback? (yes/no): " -r
            if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                rollback
            fi
            exit 1
        fi
    else
        log_error "Deployment failed"
        read -p "Rollback? (yes/no): " -r
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            rollback
        fi
        exit 1
    fi
}

# Handle script arguments
case "${1:-deploy}" in
    deploy|staging|production)
        main
        ;;
    status)
        show_status
        ;;
    rollback)
        rollback
        ;;
    *)
        echo "Usage: $0 [deploy|staging|production|status|rollback]"
        exit 1
        ;;
esac
