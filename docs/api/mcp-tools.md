````markdown
# MCP Tools Documentation

This document describes the **Machine Composable Protocol (MCP) Tools** available in the Agentic Platform.  
MCP tools are modular, declarative API operations that can be invoked by:
- The **Agent Orchestrator** internally
- External services (LangChain, LlamaIndex, etc.)
- Direct HTTP clients via the API

Each tool is defined by a JSON specification in `examples/tools/*.json` containing:
- `name` — Unique identifier
- `description` — Human-readable description
- `arguments` — Expected input parameters
- `output` — JSON schema of the expected output

---

## 1. Available MCP Tools

| Tool Name            | Path                              | Description |
|----------------------|-----------------------------------|-------------|
| `generate_cypher`    | `/mcp/tools/generate_cypher`      | Translates natural language to Cypher queries |
| `crud_create_node`   | `/mcp/tools/crud_create_node`     | Creates a node in the Memgraph database |
| `query_read`         | `/mcp/tools/query_read`           | Executes a Cypher read query |
| `schema_discover`    | `/mcp/tools/schema_discover`      | Retrieves graph schema (labels, relationships, properties) |
| `search_semantic`    | `/mcp/tools/search_semantic`      | Performs semantic search across stored graph data |
| `system_health`      | `/mcp/tools/system_health`        | Checks health of the MCP runtime and dependencies |

---

## 2. Common Invocation Pattern

All MCP tool endpoints:
- Use `POST` (except `system_health`, which can be `GET`)
- Accept JSON request bodies
- Return JSON responses

**Example request (generate_cypher):**
```http
POST /mcp/tools/generate_cypher
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "input": "Find all products sold in the last 7 days"
}
````

**Example response:**

```json
{
  "status": "success",
  "data": {
    "cypher": "MATCH (p:Product)-[s:SOLD]->(o:Order) WHERE o.date >= date() - duration({days:7}) RETURN p"
  }
}
```

---

## 3. Tool Specifications

### 3.1 `generate_cypher`

**Purpose:**
Convert a natural language question or command into an executable Cypher query, leveraging the underlying schema.

**Arguments:**

| Name    | Type   | Required | Description                 |
| ------- | ------ | -------- | --------------------------- |
| `input` | string | Yes      | Natural language query text |

**Output:**

```json
{
  "cypher": "<generated_cypher_query>"
}
```

---

### 3.2 `crud_create_node`

**Purpose:**
Create a labeled node with properties in Memgraph.

**Arguments:**

| Name         | Type   | Required | Description                        |
| ------------ | ------ | -------- | ---------------------------------- |
| `label`      | string | Yes      | Node label (e.g., "Person")        |
| `properties` | object | Yes      | Key-value pairs of node properties |

**Output:**

```json
{
  "node_id": "<internal_memgraph_id>",
  "label": "Person",
  "properties": { "name": "Alice", "age": 30 }
}
```

---

### 3.3 `query_read`

**Purpose:**
Execute a Cypher read query and return the results.

**Arguments:**

| Name     | Type   | Required | Description         |
| -------- | ------ | -------- | ------------------- |
| `cypher` | string | Yes      | Cypher query string |

**Output:**

```json
{
  "records": [
    { "name": "Alice", "age": 30 },
    { "name": "Bob", "age": 25 }
  ]
}
```

---

### 3.4 `schema_discover`

**Purpose:**
Retrieve metadata about labels, relationships, and property keys in the graph database.

**Arguments:** *(none)*

**Output:**

```json
{
  "labels": ["Person", "Order", "Product"],
  "relationships": ["PURCHASED", "SOLD", "FRIEND_OF"],
  "properties": ["name", "age", "date", "price"]
}
```

---

### 3.5 `search_semantic`

**Purpose:**
Perform a semantic similarity search on nodes, based on embedded vector representations.

**Arguments:**

| Name    | Type   | Required | Description               |
| ------- | ------ | -------- | ------------------------- |
| `query` | string | Yes      | Search phrase             |
| `limit` | int    | No       | Max results (default: 10) |

**Output:**

```json
{
  "results": [
    { "node_id": 123, "label": "Product", "score": 0.92, "properties": { "name": "Laptop" } },
    { "node_id": 456, "label": "Product", "score": 0.88, "properties": { "name": "Notebook" } }
  ]
}
```

---

### 3.6 `system_health`

**Purpose:**
Check if the MCP service and its dependencies (Memgraph, Redis, embedding model, etc.) are operational.

**Arguments:** *(none)*

**Output:**

```json
{
  "status": "healthy",
  "components": {
    "memgraph": "ok",
    "redis": "ok",
    "embedding_service": "ok"
  }
}
```

---

## 4. JSON Spec Files

Each tool is also defined in a static JSON spec file inside `examples/tools/`, e.g.:

**`examples/tools/generate_cypher.json`**

```json
{
  "name": "generate_cypher",
  "description": "Convert natural language to a Cypher query for Memgraph.",
  "arguments": {
    "input": {
      "type": "string",
      "description": "Natural language query text."
    }
  }
}
```

These can be loaded dynamically by the Orchestrator to expose tools without hardcoding their definitions.

---

## 5. Error Handling

All tools return a standardized error format on failure:

```json
{
  "status": "error",
  "message": "Description of error",
  "code": "ERROR_CODE"
}
```

Possible `code` values include:

* `INVALID_INPUT`
* `QUERY_EXECUTION_ERROR`
* `TOOL_NOT_FOUND`
* `INTERNAL_ERROR`

### 5.1 Tool invocation semantics and status codes

Tools may be invoked synchronously or asynchronously depending on the tool implementation. The API presents a uniform HTTP interface:


* Synchronous tools: the endpoint performs the requested work and returns a 200 response containing the `data` payload on success. If the tool encounters a recoverable or invalid input error it returns a 4xx status (typically 400 or 422) with the standardized error payload shown above. If the tool fails due to an internal server error, a 500 status is returned with `code: INTERNAL_ERROR`.

* Asynchronous tools: some tools may accept a request and immediately return a 202 Accepted with a small job descriptor containing a job id and status. Clients can poll a job status endpoint (`/v1/admin/jobs/{job_id}`) to retrieve completion status and result. Asynchronous tools will also use the standardized error payloads for failures.

When invoking tools from orchestrators or other internal components, prefer the synchronous variant for short-running operations and the asynchronous pattern for long-running tasks. All error responses adhere to the `status/message/code` shape to simplify client-side handling.

---

## 6. Security Considerations

* Input validation is enforced at the API layer and within each tool.
* Rate limits can be applied per tool.
* RBAC (Role-Based Access Control) can restrict access to specific tools.
* Sensitive queries (e.g., schema modifications) require elevated permissions.

---

**Next Steps:**
For endpoint details and HTTP examples, see [`README.md`](README.md) in this folder and the JSON tool specs in `examples/tools/`.
