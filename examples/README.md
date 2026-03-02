````markdown
# Examples — Cineca Agentic Platform

This directory contains minimal, copy-pasteable examples for calling the platform’s HTTP API and tools. Use them as smoke tests during local development or as templates for client integrations.

> These examples assume the API is running locally at `http://localhost:8000`.  
> If not, set `BASE_URL` (or replace the host/port inline).

---

## Contents

- `README.md` — you are here
- `auth.http` — login + whoami examples (VS Code/Insomnia/REST Client format)
- `curl.http` — basic cURL examples for agent, tools, and models
- `health_ready.http` — liveness/readiness checks
- `python_client.py` — tiny, dependency-free Python client
- `tools/`
  - `query_read.json` — parameterized graph read query (MCP graph.query)
  - `generate_cypher.json` — LLM-assisted Cypher generation (MCP graph.generate_cypher)
  - `system_health.json` — system health/metrics (MCP system.health)
- `data/`
  - `sample_nodes.csv` — optional CSV for bulk import demos
  - `sample_relationships.csv` — optional CSV for bulk import demos

> **Note**: Examples use the MCP (Model Context Protocol) tools structure.  
> See [MCP Tools Reference](../docs/mcp/TOOLS_REFERENCE.md) for complete API documentation.

---

## Quick start

### 1) Environment

```bash
export BASE_URL=${BASE_URL:-http://localhost:8000}
# Optional (if JWT is required for protected endpoints)
export API_TOKEN="REPLACE_WITH_YOUR_JWT"
````

If you don’t have a token yet, see **Authentication** below.

### 2) Health checks

```bash
curl -s "$BASE_URL/health/live" | jq .
curl -s "$BASE_URL/health/ready" | jq .
curl -s "$BASE_URL/health/info" | jq .
```

Expected: JSON with `status: "ok"` for live/ready.

---

## Authentication

The platform supports Bearer JWTs (and can be configured for API keys). Use `auth.http` to request a demo token, or call directly:

```bash
# Exchange credentials for a token (demo/dev flow)
curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}' | jq .
```

Export the token:

```bash
export API_TOKEN="$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}' | jq -r .access_token)"
```

Verify:

```bash
curl -s "$BASE_URL/auth/whoami" -H "Authorization: Bearer $API_TOKEN" | jq .
```

---

## Calling the Agent API

Free-form prompt to the platform’s agent:

```bash
curl -s -X POST "$BASE_URL/agent/run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d '{
    "input": "Summarize recent tasks and show the top 3 labels by volume.",
    "mode": "plan-execute",
    "stream": false
  }' | jq .
```

Streaming (SSE):

```bash
curl -N -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $API_TOKEN" \
  -X POST "$BASE_URL/agent/run?stream=1" \
  -H "Content-Type: application/json" \
  -d '{"input": "What are the 5 most connected labels?"}'
```

---

## Tools API

All MCP tools follow a consistent request/response pattern. See the [MCP Tools Reference](../docs/mcp/TOOLS_REFERENCE.md) for complete documentation.

### Basic Tool Invocation Pattern

```bash
curl -s -X POST "$BASE_URL/mcp/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d '{
    "name": "graph.query",
    "arguments": {
      "action": "execute",
      "cypher": "MATCH (n) RETURN count(n) AS total_nodes",
      "params": {}
    }
  }' | jq .
```

### Graph: Query (read)

```bash
curl -s -X POST "$BASE_URL/mcp/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d @tools/query_read.json | jq .
```

### Graph: Generate Cypher (LLM-assisted)

```bash
curl -s -X POST "$BASE_URL/mcp/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d @tools/generate_cypher.json | jq .
```

### System: Health snapshot

```bash
curl -s -X POST "$BASE_URL/mcp/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
  -d @tools/system_health.json | jq .
```

> **Documentation**: For all 18+ MCP tools, their actions, parameters, and examples, see:
> - [MCP Tools Reference](../docs/mcp/TOOLS_REFERENCE.md) - Complete tool catalog
> - [Secure NL→Cypher Quickstart](../docs/quickstarts/secure-nl-to-cypher.md) - Safe query generation
> - [Bulk Import Quickstart](../docs/quickstarts/bulk-import.md) - Efficient data loading

---

## Models API

List registered models:

```bash
curl -s "$BASE_URL/models" -H "Authorization: Bearer $API_TOKEN" | jq .
```

Test an LLM:

```bash
curl -s -X POST "$BASE_URL/models/test" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "input": "Say hello in 3 words."
  }' | jq .
```

---

## Python client (no dependencies)

`python_client.py` demonstrates tiny wrappers around a few endpoints.

```bash
python examples/python_client.py --base-url "$BASE_URL" --token "$API_TOKEN" health
python examples/python_client.py --base-url "$BASE_URL" --token "$API_TOKEN" whoami
python examples/python_client.py --base-url "$BASE_URL" --token "$API_TOKEN" agent \
  --input "List the top 3 labels by node count"
python examples/python_client.py --base-url "$BASE_URL" --token "$API_TOKEN" tool \
  --name graph.query --file examples/tools/query_read.json
```

---

## Using `.http` files (VS Code REST Client or Insomnia)

Open any of:

* `auth.http`
* `curl.http`
* `health_ready.http`

Replace the `@host` / `@token` variables at the top if needed, then click “Send Request”.

---

## Bulk data (optional)

If you enabled the ETL service, you can use the sample CSVs for quick imports:

* `examples/data/sample_nodes.csv`
* `examples/data/sample_relationships.csv`

Format:

```csv
# sample_nodes.csv
orig_id,label,props
u-1,User,{"user_id":"u-1","firstName":"Ada","lastName":"Lovelace"}
i-1,Institution,{"name":"Analytical Engine Institute"}
```

```csv
# sample_relationships.csv
start_id,rel_type,end_id
u-1,WORKS_AT,i-1
```

---

## Troubleshooting

* **401 Unauthorized**: Export a valid `API_TOKEN` (see Authentication).
* **Connection refused**: Ensure the API is running and `BASE_URL` is correct.
* **Graph errors**: Verify Memgraph is reachable and populated (see Phase 2 population scripts).
* **CORS** (browser): configure allowed origins in `src/config.py` or environment.

---

## License

This project’s examples are provided under the project’s main license. See the repository root for details.

```
```
