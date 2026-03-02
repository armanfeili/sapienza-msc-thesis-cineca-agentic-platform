#!/bin/bash

echo "=== COMPREHENSIVE MODEL TEST RESULTS ==="
echo ""

models=("llama-3.2-3b" "qwen-2.5-3b" "phi3-mini" "mistral-7b")

for model in "${models[@]}"; do
  echo "Testing $model..."
  
  result=$(curl -s -X POST "http://localhost:8000/v1/admin/models/instances/$model/tests" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-ID: dev" \
    -d '{"prompt": "What is the capital of Italy?"}')
  
  # Extract fields using jq
  output=$(echo "$result" | jq -r '.output // "ERROR"')
  latency=$(echo "$result" | jq -r '.latency_ms // 0')
  tokens=$(echo "$result" | jq -r '.usage.total_tokens // 0')
  has_stop=$(echo "$result" | jq -r 'if .parameters.stop then "✅" else "❌" end')
  
  # Calculate seconds
  latency_sec=$(echo "scale=1; $latency / 1000" | bc)
  
  # Check for newlines in output
  no_trailing_newline="✅"
  if [[ "$output" =~ $'\n'$ ]]; then
    no_trailing_newline="❌"
  fi
  
  # Check for single sentence (no internal newlines)
  single_sentence="✅"
  if [[ "$output" =~ $'\n' ]]; then
    single_sentence="❌"
  fi
  
  echo "  Output: $output"
  echo "  Latency: ${latency_sec}s"
  echo "  Tokens: $tokens"
  echo "  Has Stop Tokens: $has_stop"
  echo "  Single Sentence: $single_sentence"
  echo "  No Trailing Newline: $no_trailing_newline"
  echo ""
done

echo "=== TEST COMPLETE ==="
