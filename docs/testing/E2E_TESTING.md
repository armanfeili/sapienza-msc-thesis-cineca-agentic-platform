# E2E Testing Guide

Complete guide for running and maintaining end-to-end tests for the Cineca Agentic Platform.

## Quick Start

### Prerequisites

1. **Node.js 20+** installed
2. **Docker and Docker Compose** installed
3. **Services running** (API + UI)

### Installation

```bash
# From project root
npm install
npm run playwright:install
```

### Run Tests

```bash
# Start services
docker compose up -d

# Wait for services to be ready
sleep 30

# Run all E2E tests
npm run test:e2e

# Run with UI (interactive mode)
npm run test:e2e:ui

# Run specific test file
npx playwright test auth.spec.ts
```

## Test Structure

```
tests/e2e/playwright/
├── auth.spec.ts              # Authentication tests
├── health-dashboard.spec.ts  # Health dashboard tests
├── agent-run.spec.ts         # Agent execution tests
├── cypher-query.spec.ts      # Cypher query tests
├── tool-invocation.spec.ts   # Tool invocation tests
├── session-management.spec.ts # Session management tests
├── admin-operations.spec.ts  # Admin operations tests
└── README.md                 # Detailed test documentation
```

## Test Coverage

### ✅ B.1.2: Authentication (`auth.spec.ts`)
- Admin login with token badge display
- User login with appropriate scopes
- Logout functionality clears tokens

### ✅ B.1.3: Health Dashboard (`health-dashboard.spec.ts`)
- Display all health components (9 components)
- Show status (ok/degraded/error) and latency
- Refresh functionality
- Component details (Redis, Postgres, Memgraph, Ollama)

### ✅ B.1.4: Agent Runs (`agent-run.spec.ts`)
- **Real agent execution** (verifies NO demo mode)
- Timeline step display
- Error handling for invalid inputs
- Verification of real LLM responses

### ✅ B.1.5: Cypher Queries (`cypher-query.spec.ts`)
- Natural language to Cypher conversion
- Query execution against Memgraph
- CSV export functionality
- Direct Cypher execution

### ✅ B.1.6: Tool Invocation (`tool-invocation.spec.ts`)
- Safe tool execution (tools.list, tools.inspect)
- Tool listing and discovery
- Parameter configuration
- Error handling for invalid parameters

### ✅ B.1.7: Session Management (`session-management.spec.ts`)
- Session creation
- View existing sessions
- Add steps to sessions
- Cancel sessions with confirmation

### ✅ B.1.8: Admin Operations (`admin-operations.spec.ts`)
- Tenant deletion with confirmation modal
- Admin panel accessibility
- Model management operations
- Provider configuration access
- Jobs management interface

## CI Integration

E2E tests run automatically in CI via `.github/workflows/e2e.yml`:

### Trigger Events
- Pull requests to `main` or `develop`
- Pushes to `main` or `develop`
- Manual workflow dispatch

### CI Steps
1. Checkout code
2. Install Node.js dependencies
3. Install Playwright browsers
4. Start Docker Compose services
5. Wait for services to be healthy
6. Run Playwright tests (Chromium)
7. Upload artifacts on failure:
   - Screenshots
   - Videos
   - Traces
   - HTML report
   - JUnit XML

### Artifacts Retention
- Playwright report: 30 days
- Screenshots/videos/traces: 14 days

## Test Configuration

### playwright.config.ts

```typescript
{
  testDir: './tests/e2e/playwright',
  timeout: 120 * 1000,  // 2 minutes (for slow agent runs)
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  
  use: {
    baseURL: 'http://localhost:8501',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15 * 1000,
    navigationTimeout: 30 * 1000,
  }
}
```

### Environment Variables

- `UI_BASE_URL`: Base URL for UI (default: `http://localhost:8501`)
- `API_BASE_URL`: Base URL for API (default: `http://localhost:8000`)
- `FULL_E2E`: Set to `1` to run on all browsers (Firefox, WebKit)
- `CI`: Automatically set in CI environments

## Debugging Tests

### Run in Debug Mode

```bash
npm run test:e2e:debug
```

This opens Playwright Inspector where you can:
- Step through tests line by line
- See element locators
- View console logs
- Inspect DOM state

### View Test Traces

When a test fails, a trace file is generated:

```bash
npx playwright show-trace test-results/.../trace.zip
```

Trace viewer shows:
- Full timeline of actions
- Screenshots at each step
- Network requests
- Console logs
- DOM snapshots

### Run Tests in Headed Mode

See the browser as tests run:

```bash
npm run test:e2e:headed
```

### Generate Selectors

Use Playwright codegen to generate selectors:

```bash
npx playwright codegen http://localhost:8501
```

## Writing Tests

### Best Practices

1. **Use role-based locators** (most stable)
   ```typescript
   page.getByRole('button', { name: /login/i })
   ```

2. **Use text locators** (Streamlit-friendly)
   ```typescript
   page.getByText(/admin@/i)
   ```

3. **Avoid CSS selectors** (brittle)
   ```typescript
   // ❌ Avoid
   page.locator('.stButton > button')
   
   // ✅ Better
   page.getByRole('button', { name: /submit/i })
   ```

4. **Wait for network idle** (Streamlit rerenders)
   ```typescript
   await page.waitForLoadState('networkidle');
   ```

5. **Use auto-waiting assertions**
   ```typescript
   // ✅ Good - waits automatically
   await expect(page.getByText('Success')).toBeVisible();
   
   // ❌ Avoid - manual waiting
   await page.waitForTimeout(5000);
   ```

### Example Test

```typescript
test('User can submit agent run', async ({ page }) => {
  // Setup
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  // Login
  const userButton = page.getByRole('button', { name: /login.*user/i });
  await userButton.click();
  await expect(page.getByText(/user@/i)).toBeVisible();
  
  // Navigate to Agents tab
  const agentsTab = page.getByRole('tab', { name: /agents/i });
  await agentsTab.click();
  
  // Submit prompt
  const promptInput = page.locator('textarea').first();
  await promptInput.fill('List available tools');
  
  const runButton = page.getByRole('button', { name: /run/i });
  await runButton.click();
  
  // Verify execution (not demo mode)
  await expect(page.getByText(/\(demo\)/i)).not.toBeVisible();
});
```

## Troubleshooting

### Tests Timeout

**Symptom**: Tests fail with timeout error

**Solutions**:
- Increase timeout in config: `timeout: 180 * 1000`
- Check services are running: `docker compose ps`
- Check service logs: `docker compose logs -f`
- Verify health: `curl http://localhost:8501`

### Element Not Found

**Symptom**: "Locator.click: Target closed"

**Solutions**:
- Wait for network idle before interacting
- Use more flexible selectors (text over CSS)
- Check if element is in iframe
- Run in headed mode to see what's happening

### Flaky Tests

**Symptom**: Tests pass/fail inconsistently

**Solutions**:
- Add `waitForLoadState('networkidle')` after navigation
- Use `toBeVisible()` instead of counting elements
- Avoid fixed `waitForTimeout` delays
- Increase action timeout for slow operations

### Service Health Issues

**Symptom**: Tests fail with connection errors

**Solutions**:
```bash
# Restart services
docker compose restart

# Check health endpoints
curl -v http://localhost:8501
curl -v http://localhost:8000/v1/health/ready

# Check for errors in logs
docker compose logs app | grep -i error
docker compose logs ui | grep -i error
```

## Maintenance

### Updating Tests

When UI changes:
1. Run tests locally to identify failures
2. Use codegen to find new selectors: `npx playwright codegen http://localhost:8501`
3. Update test files with new locators
4. Run tests to verify: `npm run test:e2e`
5. Commit changes

### Adding New Tests

1. Create new `.spec.ts` file in `tests/e2e/playwright/`
2. Follow existing test structure
3. Add test documentation to this guide
4. Run locally to verify
5. Ensure CI passes

### Test Data Management

Tests should:
- **Create** their own test data (sessions, tenants)
- **Clean up** after themselves (delete test data)
- **Use unique identifiers** (e.g., `test-tenant-e2e-${Date.now()}`)
- **Be idempotent** (can run multiple times)

## Performance Considerations

### Test Execution Time

Average execution times:
- Authentication: 5-10 seconds
- Health Dashboard: 5-10 seconds
- Agent Run: 60-120 seconds (real LLM inference)
- Cypher Query: 10-20 seconds
- Tool Invocation: 10-15 seconds
- Session Management: 15-20 seconds
- Admin Operations: 15-25 seconds

**Total suite**: ~3-5 minutes

### Optimization Tips

1. **Run in parallel** (on different workers)
   ```typescript
   workers: 4  // Run 4 tests in parallel
   ```

2. **Skip slow tests in development**
   ```typescript
   test.skip('slow test', async ({ page }) => {
     // ...
   });
   ```

3. **Use test fixtures** for common setup
   ```typescript
   test.beforeEach(async ({ page }) => {
     // Common setup
   });
   ```

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Test Assertions](https://playwright.dev/docs/test-assertions)
- [Locators Guide](https://playwright.dev/docs/locators)
- [Debugging Guide](https://playwright.dev/docs/debug)

## Support

For questions or issues:
- Check this documentation first
- Review test results and artifacts in GitHub Actions
- Open an issue with:
  - Test file and line number
  - Error message and stack trace
  - Screenshots/traces from failure
  - Steps to reproduce

