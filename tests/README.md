# Tests

This repository ships with a pragmatic test suite that balances unit correctness, integration fidelity, end-to-end behavior, performance guardrails, and security posture. The suite is built around `pytest` and is runnable locally, in Docker, and in CI.

> TL;DR
>
> * `pytest -q` runs everything fast.
> * `pytest -m "unit"` runs just the speedy unit tests.
> * `pytest -m "integration"` spins up lightweight fakes for Memgraph/Redis unless you opt into real services.
> * `pytest -m "e2e"` exercises the HTTP surface (health, readiness, MCP tool calls).
> * `pytest -m "performance"` and `pytest -m "security"` are opt-in and skipped by default in CI unless explicitly enabled.

---

## Quick start

```bash
# (Recommended) Create a virtualenv
python -m venv .venv && source .venv/bin/activate

# Install dev requirements
pip install -r requirements.txt
pip install -r requirements-dev.txt  # if present; else pyproject extras

# Run the full suite (auto-discovers tests/)
pytest -q

# Show test durations and slowest nodes
pytest -q --durations=10

# Only unit tests
pytest -q -m "unit"

# Only integration tests
pytest -q -m "integration"

# Only E2E tests (start app separately, or use docker-compose)
pytest -q -m "e2e"
```

If you prefer containers:

```bash
# Build and run the stack (app + memgraph + redis + prom/grafana)
docker compose up -d --build

# Run tests inside a throwaway container that shares the network
docker compose run --rm app pytest -q
```

---

## Project structure (tests/)

```
tests/
├── README.md                    # this file
├── conftest.py                  # global fixtures & markers
├── fixtures/
│   ├── __init__.py
│   ├── fake_memgraph.py         # minimal Memgraph adapter double
│   └── sample_data.py           # synthetic graph data used by ETL/archive tests
├── db/
│   ├── __init__.py
│   └── test_populate.py         # db/create_original_db.py smoke test
├── e2e/
│   ├── __init__.py
│   └── test_end_to_end_health.py
├── integration/
│   ├── __init__.py
│   ├── test_archive_round_trip.py
│   ├── test_db_adapter_memgraph_ok.py
│   ├── test_db_adapter_memgraph_unavailable.py
│   ├── test_mcp_system_health.py
│   ├── test_openapi_export.py
│   ├── test_ready.py
│   └── test_redis_rate_limit.py
├── performance/
│   ├── __init__.py
│   └── test_health_latency.py
├── security/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_authorization.py
│   ├── test_intent_output_guards.py
│   ├── test_rate_limit.py
│   └── test_validators.py
└── unit/
    ├── __init__.py
    ├── test_agent_policies_loader.py
    ├── test_archive_service.py
    ├── test_pii_scrubber.py
    └── test_services_health.py
```

---

## Conventions & markers

We use `pytest` markers to gate categories:

* `@pytest.mark.unit` — Pure Python logic; no external processes. Must run under 1s each.
* `@pytest.mark.integration` — Touch adapters/services with fakes or ephemeral resources.
* `@pytest.mark.e2e` — Hit the actual HTTP API (`/health`, `/ready`, `/status`, MCP tool routes).
* `@pytest.mark.performance` — Light latency budgets and regressions (skipped by default).
* `@pytest.mark.security` — AuthN/Z, rate limits, intent/output guards.

Select with `-m`:

```bash
pytest -m "unit or integration"
pytest -m "e2e and not performance"
```

To see all markers:

```bash
pytest --markers
```

---

## Environment variables for tests

Many tests pick sensible defaults but can be steered with ENV:

| Variable                      | Purpose                               | Default in tests       |
| ----------------------------- | ------------------------------------- | ---------------------- |
| `MG_HOST`, `MG_PORT`          | Memgraph host/port (if using real DB) | `memgraph:7687`        |
| `REDIS_URL`                   | Redis connection string               | `redis://redis:6379/0` |
| `APP_ENV`                     | App environment                       | `test`                 |
| `APP_VERSION`                 | App version string                    | `0.0.0-test`           |
| `SESSION_TTL_SECONDS`         | Default session TTL                   | `604800` (7d)          |
| `BACKUP_DIR`                  | Where archive snapshots are written   | `./backups` tmp        |
| `LLM_BASE_URL`, `LLM_API_KEY` | If running LLM-dependent code         | not required           |

Set with:

```bash
export APP_ENV=test
export REDIS_URL=redis://localhost:6379/0
```

---

## Fixtures

Global fixtures live in `tests/conftest.py`:

* **`app_client`** — a test client for the FastAPI app (httpx/ASGI), no network.
* **`memgraph_fake`** — a deterministic in-memory fake of the Memgraph adapter API defined in `tests/fixtures/fake_memgraph.py`.
* **`redis_fake` / `redis_pool`** — lightweight stub or real pool depending on `REDIS_URL`.
* **`tmp_backups_dir`** — temporary directory for archive snapshots, auto-cleaned.
* **`sample_nodes`, `sample_relationships`** — small node/edge sets for ETL.

You can override fixtures per test or compose them.

---

## How integration tests avoid flakiness

* **Memgraph**: By default, adapter tests use `fake_memgraph.py` (pure Python).
  To run against a real Memgraph instance (e.g., from `docker compose`):

  ```bash
  export MG_HOST=localhost
  export MG_PORT=7687
  pytest -q -m "integration" --run-real-memgraph
  ```

  The `--run-real-memgraph` option is read in `conftest.py` and switches fixtures.

* **Redis**: If `REDIS_URL` is reachable, tests create ephemeral namespaces (unique prefixes). Otherwise, an in-memory stub is used.

* **Files**: Archive tests write to `tmp_path` via the `tmp_backups_dir` fixture and never touch your repo.

---

## Running E2E tests

You have two options:

1. **Run the app in-process** (ASGI app imported in test fixtures). This is the default for fast E2E checks that hit `/health`, `/ready`, `/status`, minimal MCP tool flows.

2. **Run against a live server**:

```bash
docker compose up -d --build
export BASE_URL=http://localhost:8000
pytest -q -m "e2e" --live
```

`--live` toggles the client to issue real HTTP requests to `BASE_URL`.

---

## Performance micro-benchmarks

Performance tests are intentionally modest (e.g., health probe budget). They:

* assert a max latency budget for `/health` and probe subcalls;
* are skipped by default to avoid flakiness on CI shared runners.

Enable explicitly:

```bash
pytest -q -m "performance" --runslow
```

Tune thresholds with `PERF_HEALTH_P99_MS` (e.g., `<= 50ms` default).

---

## Security tests

Security tests validate:

* **Authentication**: Missing/bad tokens are rejected with 401.
* **Authorization**: Disallowed roles/tenants receive 403; allowed can proceed.
* **Intent filtering**: Malicious prompts are flagged at the input guard.
* **Output guard**: Potentially unsafe content is detected/redacted.
* **Rate limiting**: 429 on exceeding configured quotas.

These tests are deterministic and use the in-process app with fake policies from `src/agent_policies`.

Run:

```bash
pytest -q -m "security"
```

---

## Coverage

If you want coverage locally:

```bash
pip install coverage
coverage run -m pytest -q
coverage html
open htmlcov/index.html
```

In CI we typically run:

```bash
pytest --maxfail=1 --disable-warnings -q \
  --cov=src --cov-report=term-missing:skip-covered
```

---

## Common commands

```bash
# Re-run only failed tests
pytest -q --lf

# Stop on first failure
pytest -q -x

# Verbose output for a single test module
pytest -vv tests/unit/test_archive_service.py::test_snapshot_round_trip

# Show print/log output (by default pytest captures)
pytest -s -k "snapshot"
```

---

## Writing new tests

1. Prefer **unit tests** for pure logic (e.g., PII scrubbing, policy loading).
2. Use **fakes** for adapters (Memgraph/Redis) unless you are testing the adapter itself.
3. Keep **integration** tests hermetic by relying on temp dirs and per-test namespaces.
4. When writing **E2E** tests:

   * Use the app fixture or explicitly opt into `--live`;
   * Assert both the response envelope and the semantic payload;
   * Avoid asserting volatile fields (`time`, `latency_ms`) unless tolerant.

### Example unit test skeleton

```python
import pytest
from src.security.pii_scrubber import scrub

@pytest.mark.unit
def test_scrub_basic_email():
    text = "Email me at jane.doe@example.com"
    cleaned, findings = scrub(text)
    assert "example.com" not in cleaned
    assert any(f["type"] == "EMAIL" for f in findings)
```

### Example integration test skeleton (archive round trip)

```python
import json
import pytest
from src.services.archive import ArchiveService

@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_round_trip(tmp_backups_dir, memgraph_fake):
    svc = ArchiveService(etl=memgraph_fake.etl, base_dir=tmp_backups_dir, gzip_snapshots=True)
    snap = await svc.snapshot_graph()
    assert snap.ok and snap.data["file"].endswith(".json.gz")
    res = await svc.restore_graph(snap.data["file"])
    assert res.ok
```

---

## Linting & type checks (pre-commit)

Run the same quality gates as CI:

```bash
pip install pre-commit
pre-commit run --all-files
```

Typically includes `ruff`, `black`, `mypy` (if configured), and basic yaml/json checks.

---

## CI tips

* Parallelize: `pytest -n auto` (requires `pytest-xdist`).
* Split jobs by marker: unit → integration → e2e to surface regressions early.
* Cache `.pytest_cache` and `.venv`/pip to speed up.
* Artifacts: upload `htmlcov/`, and on failure, attach logs (e.g., app stdout).

---

## Troubleshooting

* **“Cannot connect to Memgraph/Redis”**
  You likely switched to real services but they’re not up. Start `docker compose up -d` or remove `--run-real-memgraph`.

* **Flaky performance test**
  Ensure your machine isn’t under heavy load, or run without the `performance` marker.

* **Port conflicts on e2e `--live`**
  Change `BASE_URL` or stop existing containers: `docker compose down -v`.

* **Windows path issues**
  Prefer WSL2 or set environment variables in PowerShell with `$Env:VAR="value"`.

---

## Philosophy

* Tests should be **fast, isolated, and meaningful**.
* Prefer **behavioral assertions** over implementation specifics.
* Keep the **happy path covered**, and **assert on failures** (errors, 4xx, 5xx).
* When in doubt, write a failing test that expresses the desired behavior, then fix the code.

Happy testing! 🧪🛡️
