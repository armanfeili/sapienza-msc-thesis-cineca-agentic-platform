#!/usr/bin/env bash
#
# Disaster Recovery Drill Automation
#
# Automates periodic DR drills to verify backup/restore procedures and measure RTO/RPO.
#
# Usage:
#   ./dr-drill.sh [--environment <staging|test>] [--type <postgres|redis|memgraph|full>] [--verify-only]

set -euo pipefail

# Configuration
DRILL_ENV="${DRILL_ENV:-staging}"
DRILL_TYPE="${DRILL_TYPE:-full}"
VERIFY_ONLY="${VERIFY_ONLY:-false}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DRILL_DIR="/tmp/dr-drill-${TIMESTAMP}"
REPORT_DIR="./ops/backup/drill-reports"

# Targets
RTO_TARGET_POSTGRES=3600  # 60 minutes
RTO_TARGET_REDIS=1800     # 30 minutes
RTO_TARGET_MEMGRAPH=2700  # 45 minutes
RTO_TARGET_FULL=14400     # 4 hours
RPO_TARGET=3600           # 1 hour

# Logging
LOG_FILE="${DRILL_DIR}/drill.log"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

success() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $*" | tee -a "$LOG_FILE"
}

fail() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ❌ $*" | tee -a "$LOG_FILE"
}

# Create directories
mkdir -p "$DRILL_DIR"
mkdir -p "$REPORT_DIR"

# Drill phases
declare -A PHASE_START_TIMES
declare -A PHASE_END_TIMES

start_phase() {
    local phase=$1
    PHASE_START_TIMES[$phase]=$(date +%s)
    log "=== PHASE: $phase ==="
}

end_phase() {
    local phase=$1
    PHASE_END_TIMES[$phase]=$(date +%s)
    local duration=$((${PHASE_END_TIMES[$phase]} - ${PHASE_START_TIMES[$phase]}))
    log "Phase '$phase' completed in ${duration}s"
}

# Backup verification
verify_backup_exists() {
    local backup_type=$1
    
    start_phase "verify_${backup_type}_backup"
    
    log "Checking for recent $backup_type backup..."
    
    # List backups from last 24 hours
    local recent_backups=$(find /var/backups/cineca-platform/ -name "${backup_type}_*.gz" -o -name "${backup_type}_*.tar.gz" -mtime -1 2>/dev/null | wc -l)
    
    if [ "$recent_backups" -gt 0 ]; then
        success "$backup_type backup found (recent)"
        end_phase "verify_${backup_type}_backup"
        return 0
    else
        fail "No recent $backup_type backup found!"
        end_phase "verify_${backup_type}_backup"
        return 1
    fi
}

# Postgres drill
drill_postgres() {
    start_phase "postgres_drill"
    
    # 1. Verify backup exists
    verify_backup_exists "postgres" || return 1
    
    # 2. Measure backup size
    local backup_file=$(find /var/backups/cineca-platform/ -name "postgres_*.sql.gz" | head -n1)
    local backup_size=$(du -h "$backup_file" | cut -f1)
    log "Postgres backup size: $backup_size"
    
    # 3. Test restore to temp database (non-destructive)
    local test_db="dr_drill_${TIMESTAMP}"
    
    log "Creating test database: $test_db"
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER:-postgres}" \
        -c "CREATE DATABASE $test_db;" 2>&1 | tee -a "$LOG_FILE"
    
    local restore_start=$(date +%s)
    
    log "Restoring backup to test database..."
    if gunzip -c "$backup_file" | PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
        -h "${POSTGRES_HOST:-localhost}" \
        -U "${POSTGRES_USER:-postgres}" \
        -d "$test_db" \
        2>&1 | tee -a "$LOG_FILE"; then
        
        local restore_end=$(date +%s)
        local restore_duration=$((restore_end - restore_start))
        
        success "Postgres restore completed in ${restore_duration}s"
        
        # Verify data
        local table_count=$(PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
            -h "${POSTGRES_HOST:-localhost}" \
            -U "${POSTGRES_USER:-postgres}" \
            -d "$test_db" \
            -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "0")
        
        log "Restored tables: $table_count"
        
        # Cleanup
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER:-postgres}" \
            -c "DROP DATABASE $test_db;" 2>&1 | tee -a "$LOG_FILE"
        
        # Check against RTO
        if [ $restore_duration -le $RTO_TARGET_POSTGRES ]; then
            success "Postgres RTO met: ${restore_duration}s <= ${RTO_TARGET_POSTGRES}s"
        else
            fail "Postgres RTO exceeded: ${restore_duration}s > ${RTO_TARGET_POSTGRES}s"
        fi
        
        end_phase "postgres_drill"
        return 0
    else
        fail "Postgres restore failed!"
        PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER:-postgres}" \
            -c "DROP DATABASE IF EXISTS $test_db;" 2>&1 | tee -a "$LOG_FILE"
        end_phase "postgres_drill"
        return 1
    fi
}

# Redis drill
drill_redis() {
    start_phase "redis_drill"
    
    # 1. Verify backup exists
    verify_backup_exists "redis" || return 1
    
    # 2. Test backup integrity
    local backup_file=$(find /var/backups/cineca-platform/ -name "redis_*.rdb.gz" | head -n1)
    
    log "Testing Redis backup integrity..."
    if gunzip -t "$backup_file" 2>&1 | tee -a "$LOG_FILE"; then
        success "Redis backup integrity OK"
    else
        fail "Redis backup corrupted!"
        end_phase "redis_drill"
        return 1
    fi
    
    # 3. Measure restore time (simulated - don't actually stop Redis)
    local restore_start=$(date +%s)
    
    # Decompress to temp file to simulate restore
    gunzip -c "$backup_file" > "${DRILL_DIR}/test.rdb"
    
    local restore_end=$(date +%s)
    local restore_duration=$((restore_end - restore_start))
    
    success "Redis restore simulated in ${restore_duration}s"
    
    # Check RTO
    if [ $restore_duration -le $RTO_TARGET_REDIS ]; then
        success "Redis RTO met: ${restore_duration}s <= ${RTO_TARGET_REDIS}s"
    else
        fail "Redis RTO exceeded: ${restore_duration}s > ${RTO_TARGET_REDIS}s"
    fi
    
    end_phase "redis_drill"
    return 0
}

# Memgraph drill
drill_memgraph() {
    start_phase "memgraph_drill"
    
    # 1. Verify backup exists
    verify_backup_exists "memgraph" || return 1
    
    # 2. Test backup integrity
    local backup_file=$(find /var/backups/cineca-platform/ -name "memgraph_*.tar.gz" | head -n1)
    
    log "Testing Memgraph backup integrity..."
    if tar -tzf "$backup_file" >/dev/null 2>&1; then
        success "Memgraph backup integrity OK"
    else
        fail "Memgraph backup corrupted!"
        end_phase "memgraph_drill"
        return 1
    fi
    
    # 3. Measure restore time (simulated)
    local restore_start=$(date +%s)
    
    tar -xzf "$backup_file" -C "$DRILL_DIR" 2>&1 | tee -a "$LOG_FILE"
    
    local restore_end=$(date +%s)
    local restore_duration=$((restore_end - restore_start))
    
    success "Memgraph restore simulated in ${restore_duration}s"
    
    # Check RTO
    if [ $restore_duration -le $RTO_TARGET_MEMGRAPH ]; then
        success "Memgraph RTO met: ${restore_duration}s <= ${RTO_TARGET_MEMGRAPH}s"
    else
        fail "Memgraph RTO exceeded: ${restore_duration}s > ${RTO_TARGET_MEMGRAPH}s"
    fi
    
    end_phase "memgraph_drill"
    return 0
}

# Full DR drill
drill_full() {
    local overall_start=$(date +%s)
    
    log "===== FULL DISASTER RECOVERY DRILL ====="
    
    # Run all drills
    local postgres_result=0
    local redis_result=0
    local memgraph_result=0
    
    drill_postgres || postgres_result=$?
    drill_redis || redis_result=$?
    drill_memgraph || memgraph_result=$?
    
    local overall_end=$(date +%s)
    local total_duration=$((overall_end - overall_start))
    
    log "===== DRILL SUMMARY ====="
    log "Total duration: ${total_duration}s"
    log "Postgres: $([ $postgres_result -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
    log "Redis: $([ $redis_result -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
    log "Memgraph: $([ $memgraph_result -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
    
    # Check overall RTO
    if [ $total_duration -le $RTO_TARGET_FULL ]; then
        success "Overall RTO met: ${total_duration}s <= ${RTO_TARGET_FULL}s"
    else
        fail "Overall RTO exceeded: ${total_duration}s > ${RTO_TARGET_FULL}s"
    fi
    
    # Return failure if any drill failed
    if [ $postgres_result -ne 0 ] || [ $redis_result -ne 0 ] || [ $memgraph_result -ne 0 ]; then
        return 1
    fi
    
    return 0
}

# Generate report
generate_report() {
    local report_file="${REPORT_DIR}/dr-drill-${TIMESTAMP}.md"
    
    log "Generating report: $report_file"
    
    cat > "$report_file" <<EOF
# DR Drill Report

**Date**: $(date +'%Y-%m-%d %H:%M:%S')
**Environment**: $DRILL_ENV
**Type**: $DRILL_TYPE
**Verify Only**: $VERIFY_ONLY

## Phases

EOF
    
    for phase in "${!PHASE_START_TIMES[@]}"; do
        local duration=$((${PHASE_END_TIMES[$phase]:-0} - ${PHASE_START_TIMES[$phase]:-0}))
        echo "- **$phase**: ${duration}s" >> "$report_file"
    done
    
    cat >> "$report_file" <<EOF

## RTO/RPO Targets

| Database | RTO Target | RPO Target |
|----------|------------|------------|
| Postgres | ${RTO_TARGET_POSTGRES}s (60 min) | ${RPO_TARGET}s (1 hour) |
| Redis    | ${RTO_TARGET_REDIS}s (30 min) | ${RPO_TARGET}s (1 hour) |
| Memgraph | ${RTO_TARGET_MEMGRAPH}s (45 min) | ${RPO_TARGET}s (1 hour) |
| Full     | ${RTO_TARGET_FULL}s (4 hours) | ${RPO_TARGET}s (1 hour) |

## Log

\`\`\`
$(cat "$LOG_FILE")
\`\`\`

## Next Steps

- Review any failed phases
- Update runbook if procedures changed
- Schedule remediation for RTO/RPO violations
- Notify team of drill results

EOF
    
    success "Report generated: $report_file"
    
    # Print report summary
    echo ""
    echo "===== DR DRILL REPORT ====="
    cat "$report_file"
}

# Main
main() {
    log "===== DR DRILL STARTED ====="
    log "Environment: $DRILL_ENV"
    log "Type: $DRILL_TYPE"
    log "Verify Only: $VERIFY_ONLY"
    
    # Pre-flight checks
    start_phase "preflight"
    
    if [ "$DRILL_ENV" != "staging" ] && [ "$DRILL_ENV" != "test" ]; then
        error "DR drill only allowed in staging/test environments!"
        exit 1
    fi
    
    log "Environment check passed"
    end_phase "preflight"
    
    # Run drill
    local drill_result=0
    
    case "$DRILL_TYPE" in
        postgres)
            drill_postgres || drill_result=$?
            ;;
        redis)
            drill_redis || drill_result=$?
            ;;
        memgraph)
            drill_memgraph || drill_result=$?
            ;;
        full)
            drill_full || drill_result=$?
            ;;
        *)
            error "Unknown drill type: $DRILL_TYPE"
            exit 1
            ;;
    esac
    
    # Generate report
    generate_report
    
    # Cleanup
    rm -rf "$DRILL_DIR"
    
    if [ $drill_result -eq 0 ]; then
        success "===== DR DRILL PASSED ====="
        exit 0
    else
        fail "===== DR DRILL FAILED ====="
        exit 1
    fi
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --environment)
            DRILL_ENV="$2"
            shift 2
            ;;
        --type)
            DRILL_TYPE="$2"
            shift 2
            ;;
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        *)
            error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

main
