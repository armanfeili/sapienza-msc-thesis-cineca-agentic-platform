# Playwright E2E Tests

End-to-end tests for the Cineca Agentic Platform UI using Playwright.

## Test Coverage

### B.1.2: Authentication (`auth.spec.ts`)
- Admin login and token badge display
- User login with appropriate scopes
- Logout functionality

### B.1.3: Health Dashboard (`health-dashboard.spec.ts`)
- Display all health components
- Show status and latency
- Refresh functionality
- Component details

### B.1.4: Agent Runs (`agent-run.spec.ts`)
- Real agent execution (no demo mode)
- Timeline step display
- Error handling

### B.1.5: Cypher Queries (`cypher-query.spec.ts`)
- Natural language to Cypher conversion
- Query execution
- CSV export
- Direct Cypher execution

### B.1.6: Tool Invocation (`tool-invocation.spec.ts`)
- Safe tool execution
- Tool listing
- Parameter configuration
- Error handling for invalid parameters

### B.1.7: Session Management (`session-management.spec.ts`)
- Session creation
- View existing sessions
- Add steps to sessions
- Cancel sessions

### B.1.8: Admin Operations (`admin-operations.spec.ts`)
- Tenant deletion with confirmation
- Admin panel access
- Model management
- Provider configuration
- Jobs management

## Prerequisites

### Install Dependencies

```bash
# Install Node.js dependencies (from project root)
npm install

# Install Playwright browsers
npm run playwright:install
```

### Start Services

E2E tests require the full platform to be running:

```bash
# From project root
docker compose up -d

# Wait for services to be ready
sleep 30

# Verify services are running
curl http://localhost:8000/v1/health/ready
curl http://localhost:8501
```

## Running Tests

### All Tests

```bash
# Run all E2E tests (headless)
npm run test:e2e

# Run with UI mode (interactive)
npm run test:e2e:ui

# Run with headed browsers (see what's happening)
npm run test:e2e:headed

# Debug mode
npm run test:e2e:debug
```

### Specific Test Files

```bash
npx playwright test auth.spec.ts
npx playwright test health-dashboard.spec.ts
npx playwright test agent-run.spec.ts
```

### Run on Different Browsers

```bash
# Chromium only (default)
npx playwright test --project=chromium

# All browsers (Firefox, WebKit)
FULL_E2E=1 npx playwright test
```

## Configuration

### Environment Variables

- `UI_BASE_URL`: Base URL for the UI (default: `http://localhost:8501`)
- `FULL_E2E`: Set to `1` to run tests on all browsers (Firefox, WebKit)
- `CI`: Automatically set in CI environments

### Test Configuration

See `playwright.config.ts` in the project root for:
- Timeout settings
- Reporter configuration
- Artifact collection (screenshots, videos, traces)

## Test Artifacts

When tests fail, Playwright automatically captures:

- **Screenshots**: Captured on test failure
- **Videos**: Recorded for failed tests
- **Traces**: Full execution trace for debugging

Artifacts are saved to `test-results/` directory.

### Viewing Artifacts

```bash
# Open HTML report
npx playwright show-report test-results/playwright-report

# View trace files
npx playwright show-trace test-results/.../trace.zip
```

## CI Integration

E2E tests are integrated into the CI pipeline via `.github/workflows/e2e.yml`.

On CI:
- Tests run in headless mode
- Retries are enabled (2 retries on failure)
- All artifacts are uploaded on failure
- JUnit XML report is generated for test result tracking

## Test Writing Guidelines

### Locator Strategies

Prefer in order:
1. **Role-based**: `page.getByRole('button', { name: /login/i })`
2. **Text-based**: `page.getByText(/admin@/i)`
3. **Test IDs**: `page.getByTestId('submit-button')` (if added)

Avoid:
- CSS selectors (brittle)
- XPath (hard to maintain)

### Timeouts

- Default action timeout: 15 seconds
- Default navigation timeout: 30 seconds
- Test timeout: 120 seconds (for slow agent runs)

### Assertions

Use Playwright's auto-waiting assertions:

```typescript
// Good - waits automatically
await expect(page.getByText('Success')).toBeVisible();

// Avoid - manual waiting
await page.waitForTimeout(5000);
const element = page.getByText('Success');
expect(await element.isVisible()).toBeTruthy();
```

### Flakiness Prevention

1. **Wait for network idle**: `await page.waitForLoadState('networkidle')`
2. **Use auto-waiting**: Playwright waits for elements automatically
3. **Avoid fixed timeouts**: Use `waitForTimeout` sparingly
4. **Check visibility**: Use `toBeVisible()` instead of counting elements

## Troubleshooting

### Tests Timeout

- Increase timeout in `playwright.config.ts`
- Check if services are running: `docker compose ps`
- Check service logs: `docker compose logs -f`

### Element Not Found

- Check if element is inside iframe: `page.frameLocator('iframe')`
- Verify element selector with: `npx playwright codegen http://localhost:8501`
- Run in headed mode to see what's happening

### Streamlit-Specific Issues

Streamlit uses dynamic rendering:
- Wait for `networkidle` before interacting
- Elements may be in nested divs - use flexible selectors
- Some elements are recreated on state change

### Service Issues

If tests fail with connection errors:

```bash
# Restart services
docker compose restart

# Check service health
curl -v http://localhost:8501
curl -v http://localhost:8000/v1/health/ready

# Check logs for errors
docker compose logs app | grep -i error
docker compose logs ui | grep -i error
```

## Maintenance

### Updating Tests

When UI changes:
1. Run `npx playwright codegen http://localhost:8501` to generate new selectors
2. Update test files with new locators
3. Run tests to verify: `npm run test:e2e`

### Adding New Tests

1. Create new `.spec.ts` file in `tests/e2e/playwright/`
2. Follow existing test structure
3. Add test documentation to this README
4. Run locally before committing

## References

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Test Assertions](https://playwright.dev/docs/test-assertions)
- [Locators Guide](https://playwright.dev/docs/locators)

