````markdown
# Getting Started

This guide will walk you through setting up the **Agentic Platform** for local development and basic testing.  
By the end of this guide, you will have the system running locally with sample data and example tools.

---

## 1. Prerequisites

Before starting, ensure you have the following installed:

- **[Docker](https://docs.docker.com/get-docker/)** (v20+)
- **[Docker Compose](https://docs.docker.com/compose/install/)** (v2+)
- **[Python](https://www.python.org/downloads/)** (3.10+)
- **[pip](https://pip.pypa.io/en/stable/)** and **[virtualenv](https://virtualenv.pypa.io/en/latest/)** (optional but recommended)
- **Make** (optional, for running convenience commands)
- **Git** (to clone the repository)

---

## 2. Clone the Repository

```bash
git clone https://github.com/your-org/agentic-platform.git
cd agentic-platform
````

---

## 3. Set Up Environment Variables

1. Copy the example `.env` file:

   ```bash
   cp .env.example .env
   ```
2. Edit `.env` to match your local environment (database credentials, API keys, etc.).

---

## 4. Start the Platform (Docker Compose)

The platform includes:

* **Memgraph** graph database
* **Optional Redis** (for caching, rate-limiting)
* **Prometheus & Grafana** (for observability, if enabled)
* Application services (from `src/`)

Run:

```bash
docker compose up -d
```

Check that services are running:

```bash
docker compose ps
```

---

## 5. Populate the Database with Sample Data

We provide example CSV files and scripts under `examples/data/`.

To load them:

```bash
docker compose exec db-populate python populate.py
```

Or run via Makefile:

```bash
make populate-db
```

---

## 6. Verify the Setup

You can check Memgraph UI at [http://localhost:3000](http://localhost:3000) (Memgraph Lab).

To verify API health:

```bash
curl http://localhost:8000/health/ready
```

Expected response:

```json
{"status": "ready"}
```

---

## 7. Run the Example Clients

We provide example clients in the `examples/` folder:

* **HTTP requests**: `examples/curl.http`
* **Python client**: `examples/python_client.py`
* **Tool JSON payloads**: `examples/tools/*.json`

Example (run from repo root):

```bash
python examples/python_client.py
```

---

## 8. Development Workflow

If you want to run services locally (instead of inside Docker):

1. Create a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:

   ```bash
   uvicorn src.main:app --reload
   ```

---

## 9. Observability (Optional)

If you enabled Prometheus & Grafana in `docker-compose.yml`:

* Prometheus: [http://localhost:9090](http://localhost:9090)
* Grafana: [http://localhost:3001](http://localhost:3001)
  (Default credentials: `admin` / `admin` — change after first login.)

Load dashboards from `docs/observability/*.json`.

---

## 10. Next Steps

* Read the [Architecture](architecture.md) document to understand the system's components.
* Explore [MCP Tool Documentation](api/mcp-tools.md) for supported tools and how to use them.
* Follow [Deployment](deployment.md) for staging/production deployment.

---

**Support:** If you encounter issues, open a GitHub issue or contact the maintainers.

---

## Authentication and Authorization (OIDC)

The platform validates Bearer JWTs against your OIDC provider (e.g., Auth0). Configure these environment variables in your shell before starting, or in your Docker environment:

```bash
export OIDC_ISSUER=https://cineca.eu.auth0.com
export OIDC_AUDIENCE=api://cineca-agentic-platform
export OIDC_JWKS_URL=https://cineca.eu.auth0.com/.well-known/jwks.json
export SAFE_TOOLS=system.health,system.status,system.metrics,graph.schema,graph.search
```

With Auth0:

* Enable API RBAC and "Add Permissions in the Access Token".
* Admin role should yield `admin:all` (or `tools:invoke:all`), User role should have `tools:invoke:basic` and `user:me`.

Quick smoke tests (replace `<TOKEN>`):

```bash
curl -s http://localhost:8000/v1/auth/me \
   -H "Authorization: Bearer <TOKEN>" | jq

curl -s http://localhost:8000/v1/tools \
   -H "Authorization: Bearer <TOKEN>" | jq

curl -s -X POST http://localhost:8000/v1/tools/system.health/invocations \
   -H "Authorization: Bearer <TOKEN>" \
   -H "Content-Type: application/json" \
   -d '{}'

curl -s -o /dev/null -w "%{http_code}\n" \
   -X POST http://localhost:8000/v1/tools/<non_safe_tool>/invocations \
   -H "Authorization: Bearer <TOKEN>" \
   -H "Content-Type: application/json" \
   -d '{}'

curl -s -o /dev/null -w "%{http_code}\n" \
   http://localhost:8000/v1/admin/models/instances \
   -H "Authorization: Bearer <TOKEN>"
```

To allow standard users to run more tools, adjust the allow-list and restart:

```bash
export SAFE_TOOLS=system.health,translate,search
```
