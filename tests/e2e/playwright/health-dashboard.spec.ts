import { test, expect } from '@playwright/test';

/**
 * Health Dashboard Tests (B.1.3)
 * Tests the health dashboard displays all components correctly
 */

test.describe('Health Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('Health dashboard shows all components', async ({ page }) => {
    // Navigate to Dashboard tab
    const dashboardTab = page.getByRole('tab', { name: /dashboard/i });
    await expect(dashboardTab).toBeVisible({ timeout: 10000 });
    await dashboardTab.click();
    
    // Wait for health components to load
    await page.waitForTimeout(2000);
    
    // Check for key health component indicators
    // Looking for common health status terms
    const healthIndicators = [
      /postgres/i,
      /redis/i,
      /memgraph/i,
      /ollama/i,
      /ok|healthy|degraded|error/i,
    ];
    
    for (const indicator of healthIndicators) {
      const elements = page.getByText(indicator);
      const count = await elements.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test('Health components show status and latency', async ({ page }) => {
    const dashboardTab = page.getByRole('tab', { name: /dashboard/i });
    await dashboardTab.click();
    await page.waitForTimeout(2000);
    
    // Look for status indicators (ok, error, degraded)
    const statusPattern = /status.*:.*ok|error|degraded/i;
    await expect(page.getByText(statusPattern).first()).toBeVisible({ timeout: 10000 });
    
    // Look for latency information (should show ms)
    const latencyPattern = /\d+\s*ms/i;
    await expect(page.getByText(latencyPattern).first()).toBeVisible({ timeout: 10000 });
  });

  test('Health dashboard can be refreshed', async ({ page }) => {
    const dashboardTab = page.getByRole('tab', { name: /dashboard/i });
    await dashboardTab.click();
    await page.waitForTimeout(2000);
    
    // Look for refresh button
    const refreshButton = page.getByRole('button', { name: /refresh|reload/i });
    if (await refreshButton.isVisible()) {
      await refreshButton.click();
      
      // Wait for refresh to complete
      await page.waitForTimeout(1000);
      
      // Verify health data is still displayed
      await expect(page.getByText(/ok|healthy|degraded|error/i).first()).toBeVisible();
    }
  });

  test('Health dashboard displays component details', async ({ page }) => {
    const dashboardTab = page.getByRole('tab', { name: /dashboard/i });
    await dashboardTab.click();
    await page.waitForTimeout(2000);
    
    // Expected components based on the system architecture
    const expectedComponents = [
      'Redis',
      'Postgres',
      'Memgraph',
      'Ollama',
    ];
    
    // Check if at least 3 of the expected components are visible
    let visibleCount = 0;
    for (const component of expectedComponents) {
      const elements = page.getByText(new RegExp(component, 'i'));
      if (await elements.count() > 0) {
        visibleCount++;
      }
    }
    
    expect(visibleCount).toBeGreaterThanOrEqual(3);
  });
});

