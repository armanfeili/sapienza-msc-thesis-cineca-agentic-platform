# Integration Tests

Comprehensive integration tests for batch operations and export/import functionality.

## Quick Start

### Prerequisites

1. **Start Database Services:**

```bash
# From project root
docker compose up -d postgres redis

# Wait for PostgreSQL to be ready
docker compose exec -T postgres pg_isready -U cineca_user -d cineca_platform
```

2. **Run Tests:**

```bash
# Run all integration tests (DB_HOST automatically set to localhost)
pytest tests/integration/ -v

# Run specific suite
pytest tests/integration/test_batch_operations.py -v
pytest tests/integration/test_export_import.py -v

# Run specific test
pytest tests/integration/test_batch_operations.py::TestBatchOperations::test_batch_operations_authentication_required -v
```

### With Docker (Alternative)

```bash
# Run tests inside Docker container
docker compose up -d postgres redis app

# Run tests in container
docker compose exec app pytest tests/integration/ -v
```

## Test Suites

### test_batch_operations.py

**25 tests** covering:

- Batch operations endpoint
- Bulk model create/delete
- Bulk tool create
- Authentication & authorization
- Validation & error handling
- Idempotency

### test_export_import.py

**40+ tests** covering:

- Export configurations
- Export tenant data
- Import configurations
- Format handling (JSON, ZIP)
- Versioning
- Error scenarios

## Test Results

**Without Database:**

- 8/65 tests pass (authentication, validation)
- 57/65 tests require database connection

**With Database:**

- All tests should pass
- Full workflow testing enabled
- Database fixtures work correctly

## Common Test Commands

```bash
# Run with output
pytest tests/integration/test_batch_operations.py -v -s

# Run specific test
pytest tests/integration/test_batch_operations.py::TestBatchOperations::test_batch_operations_authentication_required -v

# Run with coverage
pytest tests/integration/ --cov=src.routers --cov-report=html

# Run only passing tests (no DB)
pytest tests/integration/ -k "authentication" -v
```

## Fixtures

### Authentication

- `admin_headers`: Admin token with admin:all, admin:write
- `read_only_headers`: Token with only admin:read
- `write_only_headers`: Token with only admin:write

### Database

- `test_tenant_id`: Creates test tenant, returns ID
- `test_provider_id`: Creates test provider, returns ID

## Database Setup

The tests require PostgreSQL to be running. Use docker-compose:

```bash
docker-compose up -d postgres
```

Or set up locally with:

```bash
createdb cineca_platform_test
export DATABASE_URL="postgresql://user:pass@localhost/cineca_platform_test"
```

## Test Structure

```
tests/integration/
├── README.md                      # This file
├── test_batch_operations.py       # Batch operations tests
└── test_export_import.py          # Export/import tests
```

## Coverage

Run with coverage report:

```bash
pytest tests/integration/ --cov=src.routers.batch --cov=src.routers.export_import --cov-report=term-missing
```

Expected coverage:

- Batch operations: >90%
- Export/import: >85%
- Validation helpers: >95%

## Troubleshooting

### Database Connection Error

**Error:**

```
OperationalError: could not translate host name "postgres"
```

**Solution:**

```bash
docker-compose up -d postgres
# Or update connection string in .env
```

### Fixture 404 Errors

**Error:**

```
assert 404 == 201
```

**Cause:** Database not running or tenant endpoint not available

**Solution:** Start database and ensure API is running

### Tests Timeout

**Cause:** Database slow or not responding

**Solution:**

```bash
docker-compose restart postgres
docker-compose logs postgres
```

## Next Steps

1. Run full test suite with database
2. Check coverage reports
3. Add more edge case tests
4. Integrate with CI/CD

For detailed test documentation, see: `docs/INTEGRATION_TESTS_SUMMARY.md`
