#!/bin/bash
# Cleanup unused Ollama models to reduce storage and improve startup time

set -e

echo "🧹 Cleaning up unused Ollama models"
echo "===================================="
echo ""

# Models to keep (only the default model)
KEEP_MODEL="${DEFAULT_MODEL_NAME:-phi3:mini-instruct}"

echo "✅ Keeping model: $KEEP_MODEL"
echo ""

# List all models
echo "📋 Current models in Ollama:"
docker compose exec ollama ollama list
echo ""

# Confirm before deletion
read -p "⚠️  This will DELETE all models EXCEPT '$KEEP_MODEL'. Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🗑️  Removing unused models..."

# Get list of models and remove all except the one we want to keep
docker compose exec ollama ollama list | tail -n +2 | while read -r line; do
    model_name=$(echo "$line" | awk '{print $1}')
    
    if [ "$model_name" != "$KEEP_MODEL" ] && [ -n "$model_name" ]; then
        echo "  Removing: $model_name"
        docker compose exec ollama ollama rm "$model_name" || echo "    ⚠️  Failed to remove $model_name"
    else
        echo "  Keeping: $model_name"
    fi
done

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📊 Remaining models:"
docker compose exec ollama ollama list
echo ""

# Show storage savings
echo "💾 Storage usage:"
docker system df -v | grep ollama || echo "Ollama volume info not available"
