#!/bin/bash
#
# Pre-load Ollama models into memory to avoid cold start delays
# This ensures integration tests run quickly without 2-minute timeouts
#

set -e

echo "🔥 Warming up Ollama models..."
echo ""

# Models to pre-load (from database configuration)
MODELS=(
    "phi3:mini"
    "phi3:mini-instruct"
    "llama3.2:3b-instruct"
    "qwen2.5:3b-instruct"
    "mistral-7b-instruct-q4:latest"
)

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

echo "📍 Ollama URL: $OLLAMA_URL"
echo "📦 Models to warm: ${#MODELS[@]}"
echo ""

warm_model() {
    local model=$1
    echo -n "  ⏳ Warming $model... "
    
    # Send a minimal generate request to load the model
    # keep_alive ensures model stays in memory for 10 minutes
    response=$(curl -s -m 180 -X POST "$OLLAMA_URL/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$model\",\"prompt\":\"test\",\"stream\":false,\"keep_alive\":\"10m\"}" 2>&1)
    
    if echo "$response" | grep -q '"done":true'; then
        echo "✅ Ready"
        return 0
    else
        echo "❌ Failed"
        echo "     Response: $response"
        return 1
    fi
}

success_count=0
failed_count=0

for model in "${MODELS[@]}"; do
    if warm_model "$model"; then
        ((success_count++))
    else
        ((failed_count++))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Successfully warmed: $success_count/$((success_count + failed_count))"
echo "❌ Failed: $failed_count"

if [ $failed_count -gt 0 ]; then
    echo ""
    echo "⚠️  Some models failed to load. Tests may be slow or fail."
    echo "   Consider reducing the number of models or increasing Ollama resources."
    exit 1
fi

echo ""
echo "🎉 All models ready! Integration tests should run quickly now."
