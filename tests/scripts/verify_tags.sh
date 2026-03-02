#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         OpenAPI Tags Verification                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Expected order
EXPECTED=(
    "meta"
    "health"
    "auth"
    "admin-tenants"
    "models-providers"
    "models-manifests-builtins"
    "models-instances"
    "tools"
    "jobs"
    "agents"
    "admin-processes"
    "internal-ops"
    "internal-db"
)

echo "Expected Order:"
for i in "${!EXPECTED[@]}"; do
    printf "%2d. %s\n" $((i+1)) "${EXPECTED[$i]}"
done

echo ""
echo "Actual Order from OpenAPI:"

ACTUAL=$(curl -s 'http://localhost:8000/openapi.json' | python3 -c "
import json, sys
spec = json.load(sys.stdin)
tags = [t.get('name') for t in spec.get('tags', [])]
for i, tag in enumerate(tags, 1):
    print(f'{i:2}. {tag}')
")

echo "$ACTUAL"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verify order matches
MATCH=true
for i in "${!EXPECTED[@]}"; do
    ACTUAL_TAG=$(echo "$ACTUAL" | sed -n "$((i+1))p" | awk '{print $2}')
    EXPECTED_TAG="${EXPECTED[$i]}"
    if [ "$ACTUAL_TAG" = "$EXPECTED_TAG" ]; then
        echo "✅ Position $((i+1)): $EXPECTED_TAG"
    else
        echo "❌ Position $((i+1)): Expected '$EXPECTED_TAG', got '$ACTUAL_TAG'"
        MATCH=false
    fi
done

echo ""
if [ "$MATCH" = true ]; then
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ ALL TAGS CORRECTLY ORDERED AND NAMED                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
else
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  ❌ TAG ORDER MISMATCH DETECTED                               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
fi
