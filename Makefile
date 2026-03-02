# ------------------------------
# Cineca Agentic Platform Makefile
# ------------------------------

SHELL := /usr/bin/env bash -o pipefail
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

PROJECT_NAME ?= cineca-agentic-platform
APP_HOST ?= 0.0.0.0
APP_PORT ?= 8000
PY := $(shell command -v python3 >/dev/null 2>&1 && echo python3 || echo python)
PIP := $(PY) -m pip
UVICORN := uvicorn src.app:app --host $(APP_HOST) --port $(APP_PORT)
DC := docker compose

TIMESTAMP := $(shell date +"%Y%m%d_%H%M%S")
BACKUP_DIR ?= backups

# ------------- Help -------------
.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<TARGET>\033[0m\n\nTargets:\n"} \
	/^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0,5) } ' $(MAKEFILE_LIST)

##@ Environment & Setup
.PHONY: env
env: ## Create .env from example if missing
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; else echo ".env already exists"; fi

.PHONY: install
install: ## Install Python dependencies into current environment
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

.PHONY: pre-commit-install
pre-commit-install: ## Install and enable pre-commit hooks
	$(PIP) install pre-commit
	pre-commit install
	pre-commit run -a || true

##@ Dev Server
.PHONY: dev
dev: ## Run FastAPI with auto-reload (local dev)
	$(UVICORN) --reload

.PHONY: ready
ready: ## Probe /health and /ready endpoints locally
	curl -fsS "http://localhost:$(APP_PORT)/health" -o /dev/null && echo "✓ /health OK"
	curl -fsS "http://localhost:$(APP_PORT)/ready"  -o /dev/null && echo "✓ /ready  OK"

##@ Docker Compose
.PHONY: up
up: ## Start all services (compose up -d)
	$(DC) up -d

.PHONY: up-cpu
up-cpu: ## Start services with CPU profile (lightweight models, longer timeouts)
	$(DC) --env-file .env.cpu up -d --build

.PHONY: up-gpu
up-gpu: ## Start services with GPU profile (standard models, GPU support)
	$(DC) --env-file .env.gpu -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

.PHONY: up-observability
up-observability: ## Start only Prometheus & Grafana services
	$(DC) up -d prometheus grafana

.PHONY: up-redis
up-redis: ## Start only Redis service
	$(DC) up -d redis

.PHONY: down
down: ## Stop services (compose down)
	$(DC) down

.PHONY: clean
clean: ## Stop & remove volumes and orphans
	$(DC) down -v --remove-orphans

.PHONY: restart
restart: ## Restart the app service
	$(DC) restart app || $(DC) restart

.PHONY: logs
logs: ## Tail all service logs (or set S=<service>)
	@if [ -n "$(S)" ]; then $(DC) logs -f --tail=200 $(S); else $(DC) logs -f --tail=200; fi

.PHONY: ps
ps: ## Show compose process status
	$(DC) ps

##@ Linting / Formatting / Types
.PHONY: fmt
fmt: ## Auto-format code (black + ruff)
	black .
	ruff format .

.PHONY: lint
lint: ## Lint with ruff (with fixes)
	ruff . --fix
	ruff format --check .

.PHONY: typecheck
typecheck: ## Static type-check with mypy
	mypy --config-file pyproject.toml

##@ Testing & Security
.PHONY: test
test: ## Run tests (quick)
	pytest -q

.PHONY: test-all
test-all: ## Run full test suite (incl. e2e and performance)
	pytest -q -m "e2e or performance or integration or security or not e2e"

.PHONY: test-ollama
test-ollama: ## Run Ollama-focused unit and contract checks
	pytest -q tests/unit/test_models_ollama.py tests/unit/test_model_management_instance.py tests/test_openapi_contract.py

.PHONY: test-memgraph-nl
test-memgraph-nl: ## Run Memgraph NL→Cypher integration tests with full pipeline (fetch tokens, restart app, run tests)
	@echo "🚀 Running Memgraph NL→Cypher Integration Tests"
	@echo "=================================================="
	@echo "1. Fetching fresh Auth0 tokens..."
	@bash ./fetch_auth0_tokens.sh --save-to-env || (echo "❌ Token fetch failed. Ensure AUTH0_* vars are configured." && exit 1)
	@echo "✅ Tokens refreshed"
	@echo ""
	@echo "2. Restarting app container to pick up new tokens..."
	@$(DC) restart app
	@echo "✅ App restarted"
	@echo ""
	@echo "3. Running Memgraph NL prompt tests (first prompt only)..."
	@$(DC) exec -T app pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py \
		-m memgraph_nl --nl-prompts=1 --nl-prompts-role=admin -v
	@echo ""
	@echo "📂 Test output files:"
	@echo "  - JSON logs: tests/logs/memgraph_nl/"
	@$(DC) exec -T app ls -lh tests/logs/memgraph_nl/ | tail -n 5
	@echo ""
	@echo "  - Text output: tests/integration/output/"
	@$(DC) exec -T app ls -lh tests/integration/output/ | tail -n 5
	@echo ""
	@echo "✅ Memgraph NL tests complete!"

.PHONY: test-memgraph-nl-smoke
test-memgraph-nl-smoke: ## Run smoke test (first 3 prompts) for Memgraph NL→Cypher
	@bash ./fetch_auth0_tokens.sh --save-to-env || exit 1
	@$(DC) restart app
	@$(DC) exec -T app pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py \
		-m memgraph_nl --nl-prompts=1:3 -v

.PHONY: security
security: ## Run security linters/scanners (bandit + pip-audit)
	bandit -c pyproject.toml -r src
	pip-audit --progress-spinner=off || true

.PHONY: check
check: lint typecheck test security ## Run lint, types, tests, and security checks

##@ OpenAPI & Docs
.PHONY: openapi
openapi: ## Export OpenAPI to docs/api/openapi.json
	mkdir -p docs/api
	if [ -f "scripts/openapi/export_openapi.py" ]; then \
		$(PY) scripts/openapi/export_openapi.py ; \
	else \
		echo "scripts/openapi/export_openapi.py not found; skipping"; \
	fi

.PHONY: openapi-docker
openapi-docker: ## Export OpenAPI inside a disposable Python container (writes api/openapi.json and api/openapi_v2.json)
	docker run --rm -v "$$PWD":/app -w /app python:3.11-slim \
		bash -lc "pip install -r requirements.txt >/dev/null 2>&1 || true; PYTHONPATH=. python scripts/openapi/export_openapi.py"

.PHONY: test-ci
test-ci: ## Run integration tests via the docker test-runner image (use host.docker.internal on macOS)
	docker run --rm \
		-e ENABLE_ADMIN_ROUTES=1 \
		-e ADMIN_TOKEN=ci-secret \
		-e BASE_URL=$${BASE_URL:-http://host.docker.internal:8000} \
		--network host \
		cineca/test-runner:latest pytest -q

##@ Database (Memgraph)
.PHONY: seed
seed: ## Seed original DB from db/create_original_db.py
	$(PY) db/create_original_db.py

.PHONY: populate
populate: ## Populate demo data from db/populate.py
	$(PY) db/populate.py

.PHONY: backup
backup: ## Backup DB via script to backups/ (requires script & running DB)
	mkdir -p $(BACKUP_DIR)
	if [ -f "src/scripts/backup_db.sh" ]; then \
		bash src/scripts/backup_db.sh "$(BACKUP_DIR)/backup_$(TIMESTAMP).tar.gz"; \
	else \
		echo "backup_db.sh not found; skipping"; \
	fi

.PHONY: restore
restore: ## Restore DB from BACKUP=<file> (requires script)
	@if [ -z "$(BACKUP)" ]; then echo "Usage: make restore BACKUP=backups/backup_xxx.tar.gz"; exit 1; fi
	if [ -f "src/scripts/restore_db.sh" ]; then \
		bash src/scripts/restore_db.sh "$(BACKUP)"; \
	else \
		echo "restore_db.sh not found; skipping"; \
	fi

##@ Database (PostgreSQL)
.PHONY: db-migrate
db-migrate: ## Run Alembic migrations (upgrade to head)
	cd db/postgres_control && alembic upgrade head

.PHONY: db-migrate-down
db-migrate-down: ## Rollback last migration
	cd db/postgres_control && alembic downgrade -1

.PHONY: db-reset
db-reset: ## Drop all tables, re-run migrations (DESTRUCTIVE - prompts for confirmation)
	@echo "⚠️  WARNING: This will destroy ALL data in the database!"
	@read -p "Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	cd db/postgres_control && alembic downgrade base
	cd db/postgres_control && alembic upgrade head
	@echo "✅ Database reset complete"

.PHONY: db-seed
db-seed: ## Seed demo tenants into PostgreSQL
	$(PY) db/postgres_control/seed_tenants.py

.PHONY: db-revision
db-revision: ## Create new Alembic migration (usage: make db-revision MSG="add field")
	@if [ -z "$(MSG)" ]; then echo "Usage: make db-revision MSG='migration description'"; exit 1; fi
	cd db/postgres_control && alembic revision --autogenerate -m "$(MSG)"

.PHONY: db-shell
db-shell: ## Open psql shell to database
	$(DC) exec postgres psql -U $(shell grep DB_USER .env | cut -d= -f2) -d $(shell grep DB_NAME .env | cut -d= -f2)

.PHONY: db-logs
db-logs: ## Show PostgreSQL logs
	$(DC) logs -f postgres

##@ Misc
.PHONY: ci
ci: check openapi ## Aggregate target for CI runs

##@ Models
.PHONY: bootstrap-models
bootstrap-models: ## Download artifacts listed in builtins manifest to TARGET_DIR (operator host)
	@echo "Run this on the model-serving host or where you want artifacts mounted."
	@if [ -z "$(TARGET_DIR)" ]; then echo "Usage: make bootstrap-models TARGET_DIR=/opt/models"; exit 1; fi
	@bash ops/builtins/bootstrap_model.sh ops/builtins/manifest.yaml $(TARGET_DIR)

.PHONY: ollama-models
ollama-models: ## Create Ollama models inside container from Modelfiles
	$(DC) exec -T ollama bash -lc 'bash /models/create_ollama_models.sh'

.PHONY: llm-smoke-test
llm-smoke-test: ## Verify LLM configuration via internal smoke test endpoint (DB-driven model config)
	@set -euo pipefail; \
	BASE_URL=$${BASE_URL:-http://localhost:8000}; \
	TOKEN=$${AUTH0_MACHINE_TOKEN:-$$(grep '^AUTH0_MACHINE_TOKEN=' .env 2>/dev/null | cut -d= -f2 | tr -d ' "')}; \
	if [ -z "$$TOKEN" ]; then \
		echo "❌ AUTH0_MACHINE_TOKEN not found in env or .env file"; \
		echo "   Run: bash ./fetch_auth0_tokens.sh --save-to-env"; \
		exit 1; \
	fi; \
	echo "🔍 Testing LLM configuration at $$BASE_URL/v1/internal/ops/llm-smoke-test"; \
	RESPONSE=$$(curl -fsS -X POST "$$BASE_URL/v1/internal/ops/llm-smoke-test" \
		-H "Authorization: Bearer $$TOKEN" \
		-H "Content-Type: application/json" 2>&1) || { \
		echo "❌ Request failed:"; \
		echo "$$RESPONSE"; \
		exit 1; \
	}; \
	echo "$$RESPONSE" | jq -e '.status == "success"' >/dev/null || { \
		echo "❌ Smoke test returned non-success status:"; \
		echo "$$RESPONSE" | jq .; \
		exit 1; \
	}; \
	echo "✅ LLM smoke test passed!"; \
	echo ""; \
	echo "Configuration:"; \
	echo "$$RESPONSE" | jq '{status, config_source, instance_name, provider_model_id, base_url: .api_base, device, latency_ms}'


.PHONY: runtime-smoke
runtime-smoke: ## Register provider, create instances, run /tests for each
	set -euo pipefail
	: $${ADMIN_TOKEN?"ADMIN_TOKEN env var required"}
	BASE_URL=$${BASE_URL:-http://localhost:8000}
	# Register provider (idempotent)
	curl -fsS -X POST "$$BASE_URL/v1/admin/models/providers/register" -H 'Content-Type: application/json' -H "Authorization: Bearer $$ADMIN_TOKEN" -d '{"name":"local-llamacpp","type":"openai_compatible","config":{"base_url":"http://ollama:11434/v1"}}' >/dev/null || true
	# Create instances (idempotent attempts) with explicit instance_id:model_id pairs
	for PAIR in \
	  llama32-3b:llama32-3b-q4 \
	  qwen25-3b:qwen25-3b-q4 \
	  mistral-7b:mistral-7b-instruct-q4 \
	  phi3-mini:phi3-mini-q4; do \
	  IID=$${PAIR%%:*}; MID=$${PAIR##*:}; \
	  curl -fsS -X POST "$$BASE_URL/v1/admin/models/instances" -H 'Content-Type: application/json' -H "Authorization: Bearer $$ADMIN_TOKEN" \
	    -d "{\"provider_id\":\"local-llamacpp\",\"instance_name\":\"$${IID}\",\"model_id\":\"$${MID}\"}" >/dev/null || true; \
	done
	# Run tests against the same instance IDs
	for IID in llama32-3b qwen25-3b mistral-7b phi3-mini; do \
	  echo "-- Testing $$IID"; \
	  curl -fsS -X POST "$$BASE_URL/v1/admin/models/instances/$$IID/tests" -H 'Content-Type: application/json' -H "Authorization: Bearer $$ADMIN_TOKEN" -d '{"prompt":"ping","max_tokens":8}' | jq .model,.usage.total_tokens; \
	done

.PHONY: doctor
doctor: ## Print useful env info
	@echo "Python: $$($(PY) --version 2>&1 || true)"
	@echo "Pip:    $$($(PIP) --version 2>&1 || true)"
	@echo "Ruff:   $$(ruff --version 2>&1 || true)"
	@echo "Black:  $$(black --version 2>&1 || true)"
	@echo "Mypy:   $$(mypy --version 2>&1 || true)"
	@echo "Bandit: $$(bandit --version 2>&1 || true)"
	@echo "Audit:  $$(pip-audit --version 2>&1 || true)"
	@echo "DC:     $$(docker compose version 2>&1 || true)"
