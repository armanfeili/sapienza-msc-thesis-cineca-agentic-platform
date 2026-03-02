# Configuration Guide

This document describes how to configure the **Agentic Platform**, covering environment variables, YAML/JSON configs, and service-specific settings.

---

## 1. Overview

The platform’s configuration is designed to be:

- **Declarative**: Controlled by `.env` files, YAML configs, and JSON tool definitions.
- **Environment-Aware**: Supports different values for `development`, `staging`, and `production`.
- **Secure by Default**: Sensitive values stored in `.env` or secret managers, never hard-coded.

---

## 2. Environment Variables (`.env`)

The `.env.example` file in the project root lists all required variables. Key settings include:

| Variable                | Description                                                                      | Default               |
| ----------------------- | -------------------------------------------------------------------------------- | --------------------- |
| `ENV`                   | Runtime environment (`development`, `staging`, `production`)                    | `development`         |
| `API_HOST`              | API bind address                                                                 | `0.0.0.0`             |
| `API_PORT`              | API port                                                                         | `8000`                |
| `API_LOG_LEVEL`         | Logging verbosity (`debug`, `info`, `warning`, `error`)                          | `info`                |
| `MG_HOST`               | Memgraph host                                                                    | `memgraph`            |
| `MG_PORT`               | Memgraph Bolt port                                                               | `7687`                |
| `MG_USER`               | Memgraph username (if auth enabled)                                             | *(empty)*             |
| `MG_PASSWORD`           | Memgraph password (if auth enabled)                                             | *(empty)*             |
| `REDIS_HOST`            | Redis host                                                                       | `redis`               |
| `REDIS_PORT`            | Redis port                                                                       | `6379`                |
| `REDIS_DB`              | Redis database index                                                             | `0`                   |
| `PROMETHEUS_PORT`       | Prometheus metrics endpoint port                                                 | `9090`                |
| `ENABLE_RATE_LIMIT`     | Enable rate limiting (`true`/`false`)                                            | `true`                |
| `RATE_LIMIT_REQUESTS`   | Max requests per window                                                          | `100`                 |
| `RATE_LIMIT_WINDOW_SEC` | Rate limit window in seconds                                                     | `60`                  |
| `OPENAI_API_KEY`        | API key for OpenAI (if using LLMs)                                               | *(required)*          |
| `LLM_MODEL`             | Default model for NL-to-Cypher conversion                                        | `gpt-4`               |
| `OLLAMA_BASE_URL`       | Override base URL for the Ollama runtime (auto-detected when unset)              | `http://ollama:11434` |
| `OLLAMA_TIMEOUT_SECS`   | Timeout in seconds for Ollama HTTP calls                                         | `60`                  |
| `OLLAMA_MODEL_MAP`      | JSON mapping of logical model ids to Ollama tags                                 | built-in defaults     |
| `SECURITY_ROLE_CONFIG`  | Path to agent role configuration YAML                                            | `src/agent/roles.yaml`|
| `SECURITY_RETRY_CONFIG` | Path to retry policy YAML                                                         | `src/agent/retry.yaml`|

> **Note:** Do **not** commit `.env` files with secrets to version control.

---

## 3. Agent Role Configuration (`src/agent/roles.yaml`)

Defines which MCP tools each role can access.

```yaml
roles:
  admin:
    tools: ["*"]
  analyst:
    tools:
      - query_read
      - search_semantic
  readonly:
    tools:
      - query_read
```

---

## 4. Retry Policy (`src/agent/retry.yaml`)

Controls how the orchestrator retries failed MCP tool calls.

```yaml
retry:
  max_attempts: 3
  backoff_strategy: exponential
  initial_delay_ms: 200
  max_delay_ms: 2000
```

---

## 5. MCP Tool Definitions (`examples/tools/*.json`)

Each tool is defined as a JSON file specifying:

- **`name`**: Tool identifier.
- **`arguments`**: Expected parameters.
- **`description`**: What the tool does.
- **`cypher_template`**: Cypher query template.

```json
{
  "name": "crud_create_node",
  "arguments": {
    "label": "string",
    "properties": "object"
  },
  "description": "Creates a new node in the graph",
  "cypher_template": "CREATE (n:${label} $properties) RETURN n"
}
```

---

## 6. Observability Configuration

### 6.1 Prometheus

Prometheus is configured in `docker-compose.yml`:

```yaml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml
```

**Scrape Config Example (`observability/prometheus.yml`):**

```yaml
scrape_configs:
  - job_name: "agentic-platform"
    static_configs:
      - targets: ["api:8000"]
```

### 6.2 Grafana

Grafana dashboards (`docs/observability/*.json`) can be imported directly.

---

## 7. Security & Compliance

Security settings are defined across:

- `.env` (for enabling/disabling features)
- `docs/compliance/` (policies)
- `src/security/` (audit logging, PII scrubbing)

**Example `.env` setting:**

```bash
ENABLE_PII_SCRUBBING=true
```

---

## 8. Local vs Production Differences

| Setting       | Local Dev            | Production                               |
| ------------- | -------------------- | ---------------------------------------- |
| Logging       | Debug-level, console | Info/error level, file/ELK sink          |
| DB Auth       | Disabled by default  | Enabled, credentials from secret manager |
| Rate Limiting | Optional             | Mandatory                                |
| SSL/TLS       | Disabled             | Enabled via reverse proxy or API server  |
| Observability | Minimal              | Full Prometheus + Grafana stack          |

---

## 9. Applying Configuration Changes

1. Update `.env` and any YAML/JSON configs.
2. Restart the service:

   ```bash
   docker compose down && docker compose up -d
   ```
3. Verify:

   - API health: `curl http://localhost:8000/health`
   - Metrics: `curl http://localhost:8000/metrics`

---

## 10. Troubleshooting

| Symptom                         | Possible Cause                           | Fix                                    |
| ------------------------------- | ---------------------------------------- | -------------------------------------- |
| API not starting                | Missing `.env` variable                  | Check `.env.example` and update `.env` |
| Memgraph connection error       | Wrong `MG_HOST` or `MG_PORT`             | Update `.env` with correct values      |
| Rate limit triggers too often   | `RATE_LIMIT_REQUESTS` too low            | Increase limit in `.env`               |
| Prometheus not scraping metrics | Wrong target address in `prometheus.yml` | Update scrape configs                  |

---

## 11. Ollama provider overrides

When the API detects an Ollama-backed provider (id, name, or URL containing `ollama`), it applies the following settings automatically:

| Variable              | Purpose                                                                   | Default behaviour when unset                                |
| --------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `OLLAMA_BASE_URL`     | Force the upstream Ollama endpoint. Useful when the API runs outside Docker. | Resolves to `http://ollama:11434` in containers, `http://localhost:11434` otherwise. Compose also maps `host.docker.internal` to the host gateway so `http://host.docker.internal:11434` works cross-platform. |
| `OLLAMA_TIMEOUT_SECS` | Timeout in seconds for Ollama HTTP requests (connect/read/write).         | `60`                                                         |
| `OLLAMA_MODEL_MAP`    | JSON or comma-separated `logical=tag` map that rewrites model ids.        | Merges a curated default map with any overrides you provide. |

Mapped models are logged (`model.*.ollama_model_mapped`) so you can verify which upstream tag was used for a given request. During startup the service also probes `{{ OLLAMA_BASE_URL }}/api/tags`; missing tags trigger a warning (`ollama.probe.missing_models`) with both the missing identifiers and the tags detected on the server.

When running Ollama outside of Docker, set `OLLAMA_BASE_URL=http://localhost:11434` (or your remote host) before starting the API. To pin a slower model to a shorter timeout, override `OLLAMA_TIMEOUT_SECS` per deployment.

The default `docker-compose.yml` injects `OLLAMA_BASE_URL=http://ollama:11434`, sets `OLLAMA_TIMEOUT_SECS=60`, and adds `extra_hosts: host.docker.internal:host-gateway` for host bridging. Adjust these in an override file or environment as needed.

---
