#!/bin/bash
# Quick test script for verifying single default model setup

set -e

echo "🔍 Verifying Single Default Model Configuration"
echo "================================================"
echo ""

# 1. Check environment variables
echo "1️⃣ Checking environment variables..."
docker compose config | grep -E "DEFAULT_MODEL|LLM_FALLBACK|OLLAMA_MAX_LOADED" || echo "⚠️  Variables not found in config"
echo ""

# 2. Check database
echo "2️⃣ Checking database for default model..."
docker compose exec -T postgres psql -U cineca_user -d cineca_platform -c \
  "SELECT instance_name, model_id, is_default, enabled, loaded FROM model_instances WHERE is_default = true;" \
  || echo "⚠️  Database query failed"
echo ""

# 3. Check orchestrator logs
echo "3️⃣ Checking orchestrator initialization..."
docker compose logs app 2>&1 | grep "orchestrator.preferred_model.set" | tail -5 || echo "⚠️  No orchestrator logs found"
echo ""

# 4. Check Ollama models
echo "4️⃣ Checking Ollama loaded models..."
docker compose exec ollama ollama list || echo "⚠️  Ollama not accessible"
echo ""

# 5. Check RAM usage
echo "5️⃣ Checking Ollama RAM usage..."
docker stats ollama --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}" || echo "⚠️  Stats unavailable"
echo ""

echo "✅ Verification complete!"
echo ""
echo "Next steps:"
echo "  - Run E2E test: docker compose exec -e AUTH0_ADMIN_TOKEN app pytest tests/integration/test_agent_execution.py -v"
echo "  - Monitor logs: docker compose logs -f app"
echo "  - Check metrics: curl http://localhost:8000/health"
