# End-to-End Testing Guide

## Overview

This guide covers comprehensive end-to-end (E2E) testing for the Cineca Agentic Platform. E2E tests validate complete user workflows from the UI through to the backend services and databases.

**Current E2E Test Coverage**: 8 test suites covering all major user workflows

---

## Table of Contents

1. [Test Architecture](#test-architecture)
2. [Test Suites](#test-suites)
3. [Setup & Prerequisites](#setup--prerequisites)
4. [Running Tests](#running-tests)
5. [Writing E2E Tests](#writing-e2e-tests)
6. [CI/CD Integration](#cicd-integration)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)

---

## Test Architecture

### Technology Stack

- **Framework**: Playwright (TypeScript)
- **Target**: Streamlit UI + FastAPI Backend
- **Browsers**: Chromium (default), Firefox, WebKit (optional)
- **Reporting**: HTML, JUnit XML, List

### Test Layers

```
┌─────────────────────────────────────┐
│   Playwright E2E Tests              │
├─────────────────────────────────────┤
│   Streamlit UI (Port 8501)          │
├─────────────────────────────────────┤
│   FastAPI Backend (Port 8000)       │
├─────────────────────────────────────┤
│   Services (PostgreSQL, Redis, etc) │
└─────────────────────────────────────┘
```

### Test Structure

```
tests/e2e/
├── playwright/
│   ├── auth.spec.ts                 # Authentication flows
│   ├── health-dashboard.spec.ts     # Health monitoring
│   ├── agent-run.spec.ts            # Agent execution
│   ├── cypher-query.spec.ts         # Graph queries
│   ├── tool-invocation.spec.ts      # Tool usage
│   ├── session-management.spec.ts   # Session lifecycle
│   ├── admin-operations.spec.ts     # Admin features
│   └── README.md                    # Test documentation
└── test_end_to_end_health.py        # Python E2E health check
```

---

## Test Suites

### 1. Authentication Tests (`auth.spec.ts`)

**Coverage**: User authentication, role-based access, token management

**Test Scenarios**:
- ✅ Admin login with client credentials
- ✅ Token badge display with scopes
- ✅ User login with password grant
- ✅ Logout and session cleanup
- ✅ Expired token handling
- ✅ Invalid credentials rejection

**Critical Flows**:
```typescript
test('admin login displays all scopes', async ({ page }) => {
  // Navigate to auth page
  // Enter admin credentials
  // Verify token badge shows all scopes
  // Check admin-specific UI elements visible
});
```

**Success Criteria**:
- Login completes within 5 seconds
- Token scopes displayed correctly
- Unauthorized access prevented

---

### 2. Health Dashboard Tests (`health-dashboard.spec.ts`)

**Coverage**: System health monitoring, component status, latency tracking

**Test Scenarios**:
- ✅ Display all health components (database, cache, graph DB)
- ✅ Show component status (healthy, degraded, down)
- ✅ Display latency metrics
- ✅ Refresh functionality
- ✅ Component detail expansion
- ✅ Error state handling

**Critical Flows**:
```typescript
test('health dashboard shows all components', async ({ page }) => {
  // Navigate to dashboard
  // Wait for health checks to complete
  // Verify all components visible
  // Check status indicators accurate
  // Test refresh button
});
```

**Success Criteria**:
- All components load within 10 seconds
- Status updates reflect real state
- Refresh updates data correctly

---

### 3. Agent Run Tests (`agent-run.spec.ts`)

**Coverage**: Agent execution, timeline display, error handling

**Test Scenarios**:
- ✅ Create and execute agent run
- ✅ Display execution timeline
- ✅ Show step-by-step progress
- ✅ Handle execution errors gracefully
- ✅ Display final results
- ✅ Cancel running agents

**Critical Flows**:
```typescript
test('agent execution shows timeline', async ({ page }) => {
  // Navigate to Agents tab
  // Create new agent session
  // Execute agent with valid parameters
  // Watch timeline populate
  // Verify results displayed
});
```

**Success Criteria**:
- Agent starts within 3 seconds
- Timeline updates in real-time
- Results displayed correctly
- Errors shown with actionable messages

---

### 4. Cypher Query Tests (`cypher-query.spec.ts`)

**Coverage**: Natural language to Cypher conversion, query execution, data export

**Test Scenarios**:
- ✅ Convert NL query to Cypher
- ✅ Execute Cypher query
- ✅ Display query results in table
- ✅ Export results to CSV
- ✅ Direct Cypher execution
- ✅ Query error handling

**Critical Flows**:
```typescript
test('natural language to cypher conversion', async ({ page }) => {
  // Navigate to Explore tab
  // Enter natural language query
  // Wait for Cypher generation
  // Verify Cypher syntax correct
  // Execute query
  // Check results displayed
});
```

**Success Criteria**:
- NL to Cypher conversion within 5 seconds
- Query execution successful
- Results formatted correctly
- CSV export downloads successfully

---

### 5. Tool Invocation Tests (`tool-invocation.spec.ts`)

**Coverage**: Tool discovery, parameter configuration, safe execution

**Test Scenarios**:
- ✅ List available tools
- ✅ Display tool documentation
- ✅ Configure tool parameters
- ✅ Execute tool safely
- ✅ Handle invalid parameters
- ✅ Display tool results

**Critical Flows**:
```typescript
test('tool invocation with valid parameters', async ({ page }) => {
  // Navigate to Tools tab
  // Select a tool
  // Configure parameters
  // Execute tool
  // Verify results displayed
  // Check no side effects occurred
});
```

**Success Criteria**:
- Tools listed with descriptions
- Parameter validation works
- Execution completes without errors
- Results shown clearly

---

### 6. Session Management Tests (`session-management.spec.ts`)

**Coverage**: Session lifecycle, step addition, session cancellation

**Test Scenarios**:
- ✅ Create new session
- ✅ View existing sessions
- ✅ Add steps to session
- ✅ Execute session steps
- ✅ Cancel active session
- ✅ Session state persistence

**Critical Flows**:
```typescript
test('complete session lifecycle', async ({ page }) => {
  // Create session
  // Add multiple steps
  // Execute session
  // Monitor progress
  // Verify completion
  // Check session persisted
});
```

**Success Criteria**:
- Session creation instant (<1s)
- Steps execute in order
- Cancel works immediately
- Session state saved correctly

---

### 7. Admin Operations Tests (`admin-operations.spec.ts`)

**Coverage**: Tenant management, model configuration, provider setup, job monitoring

**Test Scenarios**:
- ✅ Create/delete tenants with confirmation
- ✅ Configure LLM providers
- ✅ Set up models
- ✅ Monitor jobs
- ✅ Admin panel access control
- ✅ Bulk operations

**Critical Flows**:
```typescript
test('tenant deletion with confirmation', async ({ page }) => {
  // Navigate to Admin panel
  // Create test tenant
  // Attempt deletion
  // Confirm in modal
  // Verify tenant removed
  // Check cascade deletion
});
```

**Success Criteria**:
- Admin features require admin scope
- Confirmation modals prevent accidents
- Cascade deletions work correctly
- Audit logs created

---

## Setup & Prerequisites

### 1. Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Playwright browsers
npx playwright install chromium

# Optional: Install all browsers for full testing
npx playwright install
```

### 2. Configure Environment

Create `.env` file with test-specific settings:

```bash
# API endpoint
API_BASE_URL=http://localhost:8000

# UI endpoint
UI_BASE_URL=http://localhost:8501

# Auth0 test credentials
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-test-client-id
AUTH0_CLIENT_SECRET=your-test-secret

# Test user credentials
TEST_ADMIN_EMAIL=admin@test.com
TEST_ADMIN_PASSWORD=SecurePassword123!
TEST_USER_EMAIL=user@test.com
TEST_USER_PASSWORD=SecurePassword123!
```

### 3. Start Services

E2E tests require all services running:

```bash
# Start all services
docker compose up -d

# Wait for services to be ready (30-60 seconds)
sleep 30

# Verify services are healthy
curl -f http://localhost:8000/v1/health/ready
curl -f http://localhost:8501

# Check individual services
docker compose ps
```

### 4. Seed Test Data (Optional)

```bash
# Run database migrations
docker compose exec app alembic upgrade head

# Populate test data
docker compose exec app python db/populate.py
```

---

## Running Tests

### Local Development

```bash
# Run all E2E tests (headless)
npm run test:e2e

# Run with UI mode (interactive, recommended for development)
npm run test:e2e:ui

# Run with headed browsers (see what's happening)
npm run test:e2e:headed

# Debug mode (pauses on failures)
npm run test:e2e:debug
```

### Specific Test Files

```bash
# Run single test file
npx playwright test auth.spec.ts

# Run specific test by name
npx playwright test --grep "admin login"

# Run tests in folder
npx playwright test tests/e2e/playwright/

# Run tests with tag
npx playwright test --grep @smoke
```

### Advanced Options

```bash
# Run on specific browser
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit

# Run all browsers (full test)
FULL_E2E=1 npx playwright test

# Parallel execution (faster, use with caution)
npx playwright test --workers=4

# Update snapshots
npx playwright test --update-snapshots

# Show browser while running
npx playwright test --headed

# Generate test code
npx playwright codegen http://localhost:8501
```

### Viewing Results

```bash
# Open HTML report
npx playwright show-report

# View trace for debugging
npx playwright show-trace test-results/.../trace.zip

# View screenshots
open test-results/screenshots/

# View videos
open test-results/videos/
```

---

## Writing E2E Tests

### Test Template

```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to page
    await page.goto('/');
    
    // Wait for page to be ready
    await page.waitForLoadState('networkidle');
  });

  test('should do something', async ({ page }) => {
    // Arrange: Set up test data
    const testData = { name: 'Test' };
    
    // Act: Perform actions
    await page.getByRole('button', { name: /submit/i }).click();
    
    // Assert: Verify results
    await expect(page.getByText('Success')).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    // Clean up test data if needed
  });
});
```

### Locator Best Practices

**Priority Order**:

1. **Role-based** (most resilient):
```typescript
await page.getByRole('button', { name: /login/i });
await page.getByRole('textbox', { name: /email/i });
await page.getByRole('heading', { name: /dashboard/i });
```

2. **Text-based** (good for content):
```typescript
await page.getByText(/welcome/i);
await page.getByLabel('Email address');
```

3. **Test IDs** (explicit, but requires code changes):
```typescript
await page.getByTestId('submit-button');
```

**Avoid**:
- CSS selectors (fragile): `.st-button > div > button`
- XPath (hard to maintain): `//div[@class='button']//button`

### Assertions

Use Playwright's auto-waiting assertions:

```typescript
// Good - waits up to timeout
await expect(page.getByText('Success')).toBeVisible();
await expect(page.getByRole('button')).toBeEnabled();
await expect(page).toHaveTitle(/Dashboard/);

// Avoid - manual waiting
await page.waitForTimeout(5000);  // ❌ Fixed timeout
const text = await page.textContent('.message');  // ❌ No auto-waiting
expect(text).toBe('Success');  // ❌ Flaky
```

### Handling Streamlit-Specific Issues

**Dynamic Rendering**:
```typescript
// Wait for Streamlit to finish rendering
await page.waitForLoadState('networkidle');

// Wait for specific element
await page.waitForSelector('[data-testid="stApp"]');
```

**State Updates**:
```typescript
// Streamlit may recreate elements on state change
// Use flexible selectors
await page.getByRole('button', { name: /submit/i }).click();

// Wait for state update to complete
await page.waitForResponse(/\/api\/.*$/);
await page.waitForLoadState('networkidle');
```

**Iframes** (if using embedded content):
```typescript
const frame = page.frameLocator('iframe[title="My Frame"]');
await frame.getByRole('button').click();
```

---

## CI/CD Integration

### GitHub Actions Workflow

E2E tests run automatically on:
- Pull requests to `main`
- Pushes to `main`
- Manual workflow dispatch

**Configuration** (`.github/workflows/e2e.yml`):

```yaml
name: E2E Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium
      
      - name: Start services
        run: |
          docker compose up -d
          sleep 30
      
      - name: Run E2E tests
        run: npm run test:e2e
        env:
          CI: true
      
      - name: Upload artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-artifacts
          path: test-results/
          retention-days: 7
      
      - name: Publish test results
        if: always()
        uses: EnricoMi/publish-unit-test-result-action@v2
        with:
          files: test-results/junit.xml
```

### CI-Specific Configuration

In `playwright.config.ts`:

```typescript
export default defineConfig({
  // Retry failed tests on CI
  retries: process.env.CI ? 2 : 0,
  
  // Run tests serially on CI (avoid flakiness)
  workers: process.env.CI ? 1 : undefined,
  
  // Fail build if test.only found
  forbidOnly: !!process.env.CI,
  
  // Collect artifacts on failure
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
});
```

---

## Troubleshooting

### Common Issues

#### 1. Tests Timeout

**Symptoms**: Tests fail with "Test timeout of 120000ms exceeded"

**Solutions**:
```bash
# Check if services are running
docker compose ps

# Check service logs
docker compose logs -f app
docker compose logs -f ui

# Increase timeout in playwright.config.ts
timeout: 180 * 1000  # 3 minutes

# Or for specific test
test('slow test', async ({ page }) => {
  test.setTimeout(180000);
  // ... test code
});
```

#### 2. Element Not Found

**Symptoms**: "locator.click: Target closed" or "Element not found"

**Solutions**:
```typescript
// Use flexible locators
await page.getByRole('button', { name: /submit/i });

// Wait for element to be ready
await page.getByRole('button').waitFor({ state: 'visible' });

// Check if element is in iframe
const frame = page.frameLocator('iframe');
await frame.getByRole('button').click();

// Generate correct selector
// Run: npx playwright codegen http://localhost:8501
```

#### 3. Flaky Tests

**Symptoms**: Tests pass sometimes, fail other times

**Solutions**:
```typescript
// Use auto-waiting assertions
await expect(page.getByText('Success')).toBeVisible();

// Wait for network to settle
await page.waitForLoadState('networkidle');

// Wait for specific API call
await page.waitForResponse(/\/api\/agents/);

// Avoid fixed timeouts
// ❌ await page.waitForTimeout(5000);
// ✅ await expect(element).toBeVisible();
```

#### 4. Service Connection Errors

**Symptoms**: "Failed to fetch", "Connection refused"

**Solutions**:
```bash
# Restart services
docker compose restart

# Check ports are not in use
lsof -i :8000
lsof -i :8501

# Verify service health
curl -v http://localhost:8000/v1/health/ready
curl -v http://localhost:8501

# Check Docker network
docker network ls
docker network inspect cineca-agentic-platform_default
```

#### 5. Streamlit-Specific Issues

**Symptoms**: Elements appear but can't interact with them

**Solutions**:
```typescript
// Wait for Streamlit to finish rendering
await page.waitForSelector('[data-testid="stApp"]');
await page.waitForLoadState('networkidle');

// Use role-based selectors (more reliable)
await page.getByRole('button', { name: /submit/i });

// Handle Streamlit's dynamic re-rendering
await page.waitForResponse(/\/stream/);
```

---

## Best Practices

### 1. Test Independence

```typescript
// ✅ Good: Each test is independent
test('test 1', async ({ page }) => {
  await createTestData();  // Set up own data
  // Test logic
  await cleanupTestData();  // Clean up
});

// ❌ Bad: Tests depend on each other
test('test 1', async ({ page }) => {
  await createData();  // Creates data for test 2
});

test('test 2', async ({ page }) => {
  // Assumes data from test 1 exists
});
```

### 2. Page Object Model (Optional)

For complex UIs, use Page Object Model:

```typescript
// pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}
  
  async login(email: string, password: string) {
    await this.page.getByLabel('Email').fill(email);
    await this.page.getByLabel('Password').fill(password);
    await this.page.getByRole('button', { name: /login/i }).click();
  }
  
  async expectLoginSuccess() {
    await expect(this.page.getByText(/dashboard/i)).toBeVisible();
  }
}

// In test file
test('admin login', async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.login('admin@test.com', 'password');
  await loginPage.expectLoginSuccess();
});
```

### 3. Fixtures for Reusable Setup

```typescript
// fixtures/auth.ts
export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    // Auto-login before each test
    await page.goto('/auth');
    await page.getByLabel('Email').fill('admin@test.com');
    await page.getByLabel('Password').fill('password');
    await page.getByRole('button', { name: /login/i }).click();
    await expect(page).toHaveURL(/dashboard/);
    
    await use(page);
    
    // Cleanup if needed
  },
});

// In test file
import { test } from './fixtures/auth';

test('admin can see users', async ({ authenticatedPage }) => {
  // Already logged in!
  await authenticatedPage.goto('/users');
  // ...
});
```

### 4. Parallel Execution Safety

```typescript
// Use unique test data to avoid conflicts
test('parallel safe', async ({ page }) => {
  const uniqueId = Date.now();
  const testUser = `user-${uniqueId}@test.com`;
  
  // Create unique test data
  await createUser(testUser);
  
  // Test logic
  
  // Cleanup unique data
  await deleteUser(testUser);
});
```

### 5. Screenshot & Trace on Failure

```typescript
test('important flow', async ({ page }) => {
  // Test will auto-capture on failure
  // But you can also manually capture
  
  await page.screenshot({ path: 'step-1.png' });
  
  // Critical operation
  await doSomethingImportant();
  
  await page.screenshot({ path: 'step-2.png' });
});
```

---

## Metrics & Reporting

### Test Execution Metrics

Track these metrics over time:

```
Total Tests:      8 test files, ~50 test cases
Pass Rate:        >95%
Average Runtime:  ~5 minutes (all tests)
Flakiness:        <2%
```

### Coverage Metrics

E2E tests cover:

- ✅ 100% of critical user workflows
- ✅ 90% of UI components
- ✅ 85% of API endpoints (via UI interaction)
- ✅ All authentication flows
- ✅ All admin operations

### CI/CD Metrics

```
Build Success Rate:   >98%
Average CI Runtime:   ~8 minutes
Artifact Size:        ~50MB (on failure)
Retry Rate:           <5%
```

---

## Maintenance

### Regular Tasks

**Weekly**:
- Review failed tests and fix flaky tests
- Update selectors if UI changed
- Check for new Playwright version

**Monthly**:
- Review test coverage and add tests for new features
- Optimize slow tests
- Clean up obsolete tests

**Quarterly**:
- Full test audit and refactoring
- Update dependencies
- Review and update this documentation

### Updating Tests

When UI changes:

1. Run tests to identify failures
2. Use Playwright inspector to find new selectors:
   ```bash
   npx playwright codegen http://localhost:8501
   ```
3. Update test files with new locators
4. Verify tests pass locally
5. Commit and push

---

## Resources

### Documentation

- [Playwright Docs](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Streamlit Testing Guide](https://docs.streamlit.io/develop/concepts/app-testing)

### Tools

- [Playwright Test Generator](https://playwright.dev/docs/codegen): `npx playwright codegen`
- [Playwright Inspector](https://playwright.dev/docs/debug): `npx playwright test --debug`
- [Trace Viewer](https://playwright.dev/docs/trace-viewer): `npx playwright show-trace`

### Support

- Create issue in GitHub repository
- Check troubleshooting section above
- Review Playwright documentation

---

**Last Updated**: November 2, 2025  
**Version**: 1.0.0  
**Maintained By**: Platform Team
