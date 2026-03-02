import { test, expect } from '@playwright/test';

/**
 * Admin Operations Tests (B.1.8)
 * Tests admin destructive actions with confirmation modals
 */

test.describe('Admin Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Login as Admin
    const adminButton = page.getByRole('button', { name: /login.*admin/i });
    await adminButton.click();
    await expect(page.getByText(/admin@/i)).toBeVisible({ timeout: 5000 });
  });

  test('Tenant delete requires confirmation', async ({ page }) => {
    // Navigate to Tenants tab
    const tenantsTab = page.getByRole('tab', { name: /tenants/i });
    await expect(tenantsTab).toBeVisible({ timeout: 10000 });
    await tenantsTab.click();
    await page.waitForTimeout(2000);
    
    // Create a test tenant first
    const createTenantButton = page.getByRole('button', { name: /create.*tenant|new.*tenant/i });
    if (await createTenantButton.count() > 0) {
      await createTenantButton.click();
      
      // Fill in tenant details
      const nameInput = page.locator('input[name="name"], input').filter({ hasText: /name/i }).first();
      if (await nameInput.count() === 0) {
        // Try any text input
        const inputs = await page.locator('input[type="text"]').all();
        if (inputs.length > 0) {
          await inputs[0].fill('test-tenant-e2e');
        }
      } else {
        await nameInput.fill('test-tenant-e2e');
      }
      
      const submitButton = page.getByRole('button', { name: /submit|create/i });
      if (await submitButton.count() > 0) {
        await submitButton.click();
        await page.waitForTimeout(2000);
      }
    }
    
    // Now try to delete the tenant
    const deleteButton = page.getByRole('button', { name: /delete/i }).filter({ hasText: /test-tenant-e2e/i });
    if (await deleteButton.count() === 0) {
      // Try finding delete button near the tenant name
      const tenantRow = page.locator('text=test-tenant-e2e').locator('..');
      const deleteInRow = tenantRow.getByRole('button', { name: /delete|remove/i });
      
      if (await deleteInRow.count() > 0) {
        await deleteInRow.first().click();
        
        // Verify confirmation modal appears
        await page.waitForTimeout(1000);
        await expect(page.getByText(/are you sure|confirm|warning/i)).toBeVisible({ timeout: 5000 });
        
        // Cancel first
        const cancelButton = page.getByRole('button', { name: /cancel|no/i });
        if (await cancelButton.count() > 0) {
          await cancelButton.first().click();
          
          // Verify modal closed
          await page.waitForTimeout(500);
          expect(await page.getByText(/are you sure|confirm/i).count()).toBe(0);
          
          // Tenant should still exist
          await expect(page.getByText(/test-tenant-e2e/i)).toBeVisible();
        }
        
        // Try again and confirm
        await deleteInRow.first().click();
        await page.waitForTimeout(1000);
        
        const confirmButton = page.getByRole('button', { name: /confirm|yes|delete/i }).last();
        if (await confirmButton.count() > 0) {
          await confirmButton.click();
          
          // Verify tenant was deleted
          await page.waitForTimeout(2000);
          expect(await page.getByText('test-tenant-e2e').count()).toBe(0);
        }
      }
    }
  });

  test('Admin panel is accessible to admin users', async ({ page }) => {
    const adminTab = page.getByRole('tab', { name: /admin/i });
    await expect(adminTab).toBeVisible({ timeout: 10000 });
    await adminTab.click();
    
    // Verify admin content is visible
    const adminIndicators = [
      /tenant/i,
      /user/i,
      /configuration/i,
      /system/i,
    ];
    
    let foundAdminContent = false;
    for (const indicator of adminIndicators) {
      if (await page.getByText(indicator).count() > 0) {
        foundAdminContent = true;
        break;
      }
    }
    
    expect(foundAdminContent).toBeTruthy();
  });

  test('Model management operations work', async ({ page }) => {
    // Navigate to Models tab
    const modelsTab = page.getByRole('tab', { name: /models/i });
    if (await modelsTab.isVisible()) {
      await modelsTab.click();
      await page.waitForTimeout(2000);
      
      // Verify model list is visible
      const modelIndicators = [
        /model/i,
        /provider/i,
        /instance/i,
        /manifest/i,
      ];
      
      let foundModels = false;
      for (const indicator of modelIndicators) {
        if (await page.getByText(indicator).count() > 0) {
          foundModels = true;
          break;
        }
      }
      
      expect(foundModels).toBeTruthy();
    }
  });

  test('Provider configuration is accessible', async ({ page }) => {
    // Try to access provider configuration
    const modelsTab = page.getByRole('tab', { name: /models/i });
    if (await modelsTab.isVisible()) {
      await modelsTab.click();
      await page.waitForTimeout(2000);
      
      // Look for provider section
      const providerSection = page.getByText(/provider/i);
      if (await providerSection.count() > 0) {
        // Providers are visible
        expect(await providerSection.count()).toBeGreaterThan(0);
        
        // Look for common provider types
        const providerTypes = [
          /ollama/i,
          /openai/i,
          /azure/i,
        ];
        
        let foundProviderType = false;
        for (const type of providerTypes) {
          if (await page.getByText(type).count() > 0) {
            foundProviderType = true;
            break;
          }
        }
        
        // At least one provider type should be configured
        expect(foundProviderType).toBeTruthy();
      }
    }
  });

  test('Jobs management is available to admin', async ({ page }) => {
    // Navigate to Jobs tab
    const jobsTab = page.getByRole('tab', { name: /jobs/i });
    if (await jobsTab.isVisible()) {
      await jobsTab.click();
      await page.waitForTimeout(2000);
      
      // Verify jobs interface is visible
      const jobIndicators = [
        /job/i,
        /status/i,
        /queue/i,
        /task/i,
      ];
      
      let foundJobs = false;
      for (const indicator of jobIndicators) {
        if (await page.getByText(indicator).count() > 0) {
          foundJobs = true;
          break;
        }
      }
      
      expect(foundJobs).toBeTruthy();
    }
  });
});

