# Rate Limiting Test Fix Summary

## Problem
The integration test `test_rate_limit_per_resource` was failing with an assertion error:
```
AssertionError: Rate limit mismatch: expected 100 (from config), got 10000 (from API header).
Ensure RATE_LIMIT_MODE env var matches test expectations.
```

## Root Cause
The system has two separate processes with different `RATE_LIMIT_MODE` settings:

1. **Docker API Server** (`cineca-agentic-platform-app`): Running with `RATE_LIMIT_MODE=test`
   - This is configured in `docker-compose.override.yml` and `docker-compose.override.dev.yml`
   - In "test" mode, the rate limit for `steps:create` is 10000/minute

2. **Test Process** (pytest): Not explicitly setting `RATE_LIMIT_MODE`
   - The db modules would default to "prod" mode
   - In "prod" mode, the rate limit for `steps:create` is 100/minute

The test:
- Makes an HTTP request to the API server and gets `X-RateLimit-Limit: 10000` (test mode)
- Imports `get_rate_limit_config` from the test process (defaulting to prod mode) and gets 100
- Asserts they should match → fails!

## Solution
Configure both the Docker API server and the test process to use the same `RATE_LIMIT_MODE`.
Since they're both in a development/test environment, we set both to "test" mode:

### Changes Made

1. **Created root-level `/conftest.py`**
   - Runs before test collection begins
   - Sets `RATE_LIMIT_MODE=test` in the environment
   - Ensures db modules import with the correct mode

2. **Updated `/tests/conftest.py`**
   - Also sets `RATE_LIMIT_MODE=test` as a backup
   - Documents that this must match the API server's setting

### Result
All 3 rate limiting tests now pass:
- ✅ `test_rate_limit_headers_present`
- ✅ `test_rate_limit_enforced_on_sessions`
- ✅ `test_rate_limit_per_resource`

## Key Insights
- `RATE_LIMIT_MODE` is read at module import time (not at function call time)
- Environment variables must be set BEFORE pytest collects and imports test modules
- When testing against a running Docker API server, the test process and server must agree on the mode
- The docker-compose files define different modes for different contexts:
  - `docker-compose.override.dev.yml`: `RATE_LIMIT_MODE=test` (for development)
  - `docker-compose.override.yml`: `RATE_LIMIT_MODE=test` (for override)
  - `docker-compose.yml`: `RATE_LIMIT_MODE=${RATE_LIMIT_MODE:-prod}` (prod by default)
