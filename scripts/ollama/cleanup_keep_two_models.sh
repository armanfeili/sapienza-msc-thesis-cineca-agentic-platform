#!/bin/bash
# Remove unused Ollama models, keeping only phi3:mini-instruct and mistral-7b-instruct-q4

set -e

echo "🧹 Cleaning up Ollama models"
echo "============================"
echo ""
echo "✅ Keeping:"
echo "  - phi3:mini-instruct (2.4 GB) - Default model"
echo "  - mistral-7b-instruct-q4:latest (4.4 GB) - Backup model"
echo ""
echo "🗑️  Will remove all other models"
echo ""

# List current models
echo "📋 Current models:"
docker compose exec ollama ollama list
echo ""

# Confirm
read -p "⚠️  Continue with cleanup? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🗑️  Removing models..."

# Models to keep
KEEP_MODELS=("phi3:mini-instruct" "mistral-7b-instruct-q4:latest")

# Get all models and remove those not in keep list
docker compose exec ollama ollama list | tail -n +2 | while read -r line; do
    model_name=$(echo "$line" | awk '{print $1}')
    
    # Skip empty lines
    if [ -z "$model_name" ]; then
        continue
    fi
    
    # Check if model should be kept
    should_keep=false
    for keep_model in "${KEEP_MODELS[@]}"; do
        if [ "$model_name" = "$keep_model" ]; then
            should_keep=true
            break
        fi
    done
    
    if [ "$should_keep" = true ]; then
        echo "  ✅ Keeping: $model_name"
    else
        echo "  🗑️  Removing: $model_name"
        docker compose exec ollama ollama rm "$model_name" 2>&1 | grep -v "error" || true
    fi
done

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "📊 Remaining models:"
docker compose exec ollama ollama list
echo ""

# Show storage info
echo "💾 Storage usage:"
docker exec ollama du -sh /root/.ollama 2>/dev/null || echo "Unable to check storage"
