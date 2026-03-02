# Ollama Integration (Local Runtime)

This guide shows how to bring up Ollama, create portable models, register the provider, create instances, set the default, and run a quick test.

## Prerequisites

- Docker and docker compose
- Admin token available as `ADMIN_TOKEN`

## Start the stack

```bash
docker compose up -d --build --remove-orphans
```

## Configure runtime overrides (optional)

The API auto-detects Ollama providers, but you can fine-tune behaviour with environment variables before starting `uvicorn` (or the container):

```bash
export OLLAMA_BASE_URL="http://localhost:11434"          # Use a remote host instead of the docker service name
export OLLAMA_TIMEOUT_SECS=120                           # Increase request timeout for larger models
export OLLAMA_MODEL_MAP='{"llama32-3b-q4":"llama3.2:3b-instruct","phi3-mini-q4":"phi3:mini-instruct","qwen25-3b-q4":"qwen2.5:3b-instruct","mistral-7b-instruct-q4":"mistral:7b-instruct"}'
```

After tweaking these overrides, restart the API process (or `docker compose restart api`) so the new settings are loaded.

When the API itself runs in Docker alongside the `ollama` service, point to the service name instead:

```bash
export OLLAMA_BASE_URL="http://ollama:11434"
```

`OLLAMA_MODEL_MAP` accepts JSON or comma-separated pairs (`llama32-3b-q4=llama3.2:3b-instruct,phi3-mini-q4=phi3:mini`). The router logs each rewrite as `model.*.ollama_model_mapped` so you can confirm which upstream tag was used.

### Docker-to-host bridging

When you run the API container but keep Ollama on the host, Compose already maps `host.docker.internal` to the host gateway (see `docker-compose.yml`). Set:

```bash
export OLLAMA_BASE_URL="http://host.docker.internal:11434"
```

This also works on Linux now that the compose file injects the gateway mapping. You can still point to a remote host by replacing the hostname.

## Live validation checklist

Follow this quick sequence whenever you need to exercise `/v1/models/completions` end-to-end after changing timeouts, mapping, or Ollama inventory:

1. **Set environment variables** (host run shown; adjust `OLLAMA_BASE_URL` if you are inside Docker):

  ```bash
  export OLLAMA_BASE_URL="http://localhost:11434"
  export OLLAMA_TIMEOUT_SECS="60"
  export OLLAMA_MODEL_MAP='{"llama32-3b-q4":"llama3.2:3b-instruct","phi3-mini-q4":"phi3:mini-instruct","qwen25-3b-q4":"qwen2.5:3b-instruct","mistral-7b-instruct-q4":"mistral:7b-instruct"}'
  ```

  Restart `uvicorn` or the running container after exporting these values so FastAPI reloads the configuration.

  For Docker deployments simply overwrite the base URL:

  ```bash
  export OLLAMA_BASE_URL="http://ollama:11434"
  ```

1. **Ensure the target model exists and is warm**:

  ```bash
  ollama create llama3.2:3b-instruct -f /models/Llama-3.2-3B.Modelfile
  ollama create mistral:7b-instruct -f /models/Mistral-7B.Modelfile
  ollama create phi3:mini-instruct -f /models/Phi-3-Mini.Modelfile
  ollama create qwen2.5:3b-instruct -f /models/Qwen2.5-3B.Modelfile
  curl -s "${OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" | jq
  curl -s "${OLLAMA_BASE_URL:-http://localhost:11434}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"llama3.2:3b-instruct","messages":[{"role":"user","content":"Say pong."}],"max_tokens":8}'
  ```

  The warm-up call prevents the first token penalty during API testing.

1. **Exercise the API using Swagger or curl**. In Swagger’s “Edit Value” box (or in a manual request), paste:

  ```json
  {
    "model": "llama32-3b-q4",
    "prompt": "Say \"pong\".",
    "max_tokens": 8,
    "temperature": 0,
    "metadata": { "source": "swagger-test" }
  }
  ```

  Replace `model` with your instance id when different. Because of the mapping, the API forwards the call to `llama3.2:3b-instruct`.

1. **Troubleshoot if the call fails**:

- Responses now follow the Problem+JSON format. A missing tag yields:

  ```json
  {
    "type": "about:blank",
    "title": "upstream request failed",
    "status": 424,
    "detail": "Provider returned client error",
    "traceId": "...",
    "extensions": {
      "correlation_id": "...",
      "provider_status": 404,
      "event_id": "evt_xxx"
    }
  }
  ```

- Check API logs for `ollama.probe.*`, `model.instance.test.error`, or `provider request failed` lines.
- Confirm network reachability: `docker compose ps | grep ollama` or `curl "$OLLAMA_BASE_URL/api/tags"`.
- Increase the timeout: `export OLLAMA_TIMEOUT_SECS=120`.
- Try a different mapped model such as `qwen2.5:3b-instruct` or `mistral:7b-instruct`.

## Create models inside Ollama

The repo mounts `./ops/ollama/models` as `/models` in the `ollama` container.
Use the Modelfiles in `./ops/ollama/models` (mounted as `/models` inside the container) to register the CPU-friendly aliases:

```bash
docker compose exec -T ollama bash -lc '
  ollama create llama3.2:3b-instruct -f /models/Llama-3.2-3B.Modelfile
  ollama create mistral:7b-instruct -f /models/Mistral-7B.Modelfile
  ollama create phi3:mini-instruct -f /models/Phi-3-Mini.Modelfile
  ollama create qwen2.5:3b-instruct -f /models/Qwen2.5-3B.Modelfile
'
```

## Register provider (OpenAI-compatible)

```bash
curl -sS -X POST http://localhost:8000/v1/admin/models/providers/register \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name":"local-llamacpp","type":"openai_compatible","config":{"base_url":"http://ollama:11434/v1"}}'
```

## Create a model instance

```bash
curl -sS -X POST http://localhost:8000/v1/admin/models/instances \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"provider_id":"local-llamacpp","instance_name":"llama32-3b","model_id":"llama32-3b-q4"}'
```

## Test the instance

```bash
curl -sS -X POST http://localhost:8000/v1/admin/models/instances/llama32-3b/tests \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"prompt":"Echo: test","max_tokens":16}'
```

## Set default

```bash
curl -sS -X PATCH http://localhost:8000/v1/admin/models/defaults \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"chat":{"name":"llama32-3b"}}'
```

## Notes

- Instance listing shows `provider` as the provider id and includes `loaded/enabled` flags.
- Provider listing includes a cached `health` object (reachable/status).
- `/metrics` exposes a histogram `model_instance_test_latency_ms`; dashboards are provisioned under Grafana.
- Registry is Redis-backed and is hydrated at startup.
- On API startup a lightweight probe hits `OLLAMA_BASE_URL/api/tags` using the shared provider helpers. Logs now include the provider id (`ollama.probe.success`/`missing_models`) so you can confirm which registration was probed. Missing tags still surface as warnings with the expected IDs so you can `ollama pull` or adjust your map.
