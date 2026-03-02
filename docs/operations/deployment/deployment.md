````markdown
# Deployment Guide

This guide provides instructions for deploying the **Agentic Platform** in different environments: local development, staging, and production.

---

## 1. Prerequisites

Before deploying, ensure you have:

- **Docker** (≥ 20.10) and **Docker Compose** (v2+)
- **Git** (for pulling the repo)
- Access to environment variables and secrets (see `.env.example`)
- Optional: **Prometheus** and **Grafana** for observability

---

## 2. Clone the Repository

```bash
git clone https://github.com/your-org/agentic-platform.git
cd agentic-platform
````

---

## 3. Environment Configuration

Copy the sample environment file and adjust values:

```bash
cp .env.example .env
```

Edit `.env` to set:

* API host and port
* Memgraph/Redis connection details
* API keys for LLM providers (e.g., OpenAI)
* Role and retry policy file paths

Example:

```
ENV=production
API_HOST=0.0.0.0
API_PORT=8000
MG_HOST=memgraph
MG_PORT=7687
REDIS_HOST=redis
REDIS_PORT=6379
OPENAI_API_KEY=sk-xxxxxxxx
SECURITY_ROLE_CONFIG=src/agent/roles.yaml
SECURITY_RETRY_CONFIG=src/agent/retry.yaml
```

---

## 4. Local Development Deployment

Run the stack in development mode:

```bash
docker compose up --build
```

Access:

* API: [http://localhost:8000](http://localhost:8000)
* Memgraph Lab: [http://localhost:3000](http://localhost:3000)
* Prometheus (if enabled): [http://localhost:9090](http://localhost:9090)
* Grafana (if enabled): [http://localhost:3001](http://localhost:3001)

---

## 5. Staging / Production Deployment

### 5.1 Production Docker Compose

In production, use optimized settings:

* `ENV=production`
* Enable rate limiting and security policies
* Attach to external databases if needed
* Mount persistent storage volumes

Example `docker-compose.override.yml`:

```yaml
version: "3.9"

services:
  api:
    environment:
      ENV: production
      API_LOG_LEVEL: info
    restart: unless-stopped

  memgraph:
    volumes:
      - memgraph_data:/var/lib/memgraph
    restart: unless-stopped

  redis:
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  memgraph_data:
  redis_data:
```

Deploy:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

---

## 6. Kubernetes Deployment (Optional)

For Kubernetes environments, create manifests or use Helm:

```bash
kubectl create secret generic agentic-env --from-env-file=.env

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Example `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentic-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agentic
  template:
    metadata:
      labels:
        app: agentic
    spec:
      containers:
        - name: api
          image: your-org/agentic-platform:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: agentic-env
```

---

## 7. Database Migration & Seeding

To seed the database:

```bash
docker compose run --rm db-populate
```

This will:

* Create schema in Memgraph
* Populate sample nodes/relationships from `examples/data/`

---

## 8. Observability Setup

### Prometheus

Prometheus is defined in `docker-compose.yml`.
Check scrape targets in `observability/prometheus.yml`.

### Grafana

Import dashboards from:

* `docs/observability/mcp-tools-dashboard.json`
* `docs/observability/grafana-dashboard.json`
* `docs/observability/db-memgraph-dashboard.json`

---

## 9. Health Checks

Verify API health:

```bash
curl http://localhost:8000/health
```

Example successful response:

```json
{
  "status": "ok",
  "services": {
    "memgraph": "up",
    "redis": "up"
  }
}
```

---

## 10. Rolling Updates

For zero-downtime updates in production:

```bash
docker compose pull
docker compose up -d
```

Or in Kubernetes:

```bash
kubectl rollout restart deployment/agentic-platform
```

---

## 11. Backup & Restore

See `docs/runbooks/backup-restore.md` for full procedure.

---

## 12. Troubleshooting

| Issue                        | Likely Cause                     | Resolution                                      |
| ---------------------------- | -------------------------------- | ----------------------------------------------- |
| API not reachable            | Container crash or port conflict | Check logs: `docker compose logs api`           |
| Memgraph connection error    | Wrong `MG_HOST` or `MG_PORT`     | Update `.env`, restart stack                    |
| Prometheus shows no metrics  | Wrong scrape target              | Update `prometheus.yml`, restart Prometheus     |
| Slow responses in production | Low resource limits              | Increase CPU/memory in Docker/K8s configuration |

---

**Next Steps:**
Once deployed, follow the [Configuration Guide](configuration.md) to fine-tune your platform.

```
```
