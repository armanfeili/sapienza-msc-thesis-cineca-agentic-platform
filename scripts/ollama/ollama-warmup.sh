#!/usr/bin/env bash
#
# Ollama Model Warmup Script
# ==========================
# Pre-loads the default model to avoid ~11 minute cold start on first LLM call.
# This script is designed to be run as part of the Ollama container's entrypoint.
#
# Expected impact:
#   - Before: First LLM call takes 11m 42s (cold model load)
#   - After: First LLM call takes <2 min (model already loaded)
#
# Usage:
#   1. Add to docker-compose.yml as entrypoint override
#   2. Or call manually: docker exec ollama /scripts/ollama-warmup.sh

set -euo pipefail

# Default model to preload (can be overridden via OLLAMA_DEFAULT_MODEL env var)
DEFAULT_MODEL="${OLLAMA_DEFAULT_MODEL:-phi3:mini-instruct}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Check if Ollama is available
if ! command -v ollama &> /dev/null; then
    log_error "Ollama command not found. Skipping warmup."
    exit 1
fi

# Wait for Ollama service to be ready (max 60 seconds)
log_info "Waiting for Ollama service to be ready..."
MAX_WAIT=60
WAITED=0
while ! ollama list &> /dev/null; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        log_error "Ollama service not ready after ${MAX_WAIT}s. Skipping warmup."
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo -n "."
done
echo ""
log_info "Ollama service is ready."

# Check if model is already loaded/pulled
log_info "Checking if model ${DEFAULT_MODEL} exists..."
if ollama list | grep -q "${DEFAULT_MODEL}"; then
    log_info "Model ${DEFAULT_MODEL} already exists."
else
    log_warn "Model ${DEFAULT_MODEL} not found. It will be pulled on first use."
    # Note: We don't pull here to avoid long delays during startup.
    # The model will be auto-pulled on first ollama run command.
fi

# Check available memory before warmup
log_info "Warming up model ${DEFAULT_MODEL}..."
if command -v free &> /dev/null; then
    AVAILABLE_MEM=$(free -m | awk '/^Mem:/{print $7}')
    if [ "$AVAILABLE_MEM" -lt 2048 ]; then
        log_warn "Low memory detected (${AVAILABLE_MEM}MB available). Warmup may fail or cause issues."
        log_warn "Consider increasing Docker memory limits in docker-compose.yml."
    fi
fi

# Run a simple inference to load the model into memory
# This ensures subsequent calls are fast
log_info "Running warmup inference (this may take 30-120 seconds)..."
START_TIME=$(date +%s)

if ollama run "${DEFAULT_MODEL}" "Hello" > /dev/null 2>&1; then
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    log_info "✅ Model warmup completed successfully in ${ELAPSED}s."
    log_info "   First LLM call should now be fast (<2 min instead of ~11 min)."
else
    log_error "❌ Model warmup failed. First LLM call may be slow."
    exit 1
fi

# Optional: List loaded models to confirm
log_info "Currently loaded models:"
ollama list

log_info "Warmup complete. Ollama is ready for fast inference."
