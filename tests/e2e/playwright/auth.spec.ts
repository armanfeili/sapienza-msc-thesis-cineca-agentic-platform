import { test, expect } from '@playwright/test';

/**
 * Authentication Flow Tests (B.1.2)
 * Tests login functionality and token badge display
 */

test.describe('Authentication', () => {
  test('Admin login succeeds and displays token badge', async ({ page }) => {
    await page.goto('/');
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Find and click the Admin login button
    // Streamlit buttons might be in different locations, so we'll search flexibly
    const adminButton = page.getByRole('button', { name: /login.*admin/i });
    await expect(adminButton).toBeVisible({ timeout: 10000 });
    await adminButton.click();
    
    // Wait for token to be set (there should be a visible token badge)
    // Look for text containing "admin@" which indicates admin identity
    await expect(page.getByText(/admin@/i)).toBeVisible({ timeout: 5000 });
    
    // Navigate to Auth tab to verify scopes
    const authTab = page.getByRole('tab', { name: /auth/i });
    if (await authTab.isVisible()) {
      await authTab.click();
      
      // Verify admin:all scope is present
      await expect(page.getByText(/admin:all/i)).toBeVisible({ timeout: 5000 });
    }
  });

  test('User login succeeds and displays appropriate scopes', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Click the User login button
    const userButton = page.getByRole('button', { name: /login.*user/i });
    await expect(userButton).toBeVisible({ timeout: 10000 });
    await userButton.click();
    
    // Wait for token to be set
    await expect(page.getByText(/user@/i)).toBeVisible({ timeout: 5000 });
    
    // Navigate to Auth tab to verify user scopes (not admin)
    const authTab = page.getByRole('tab', { name: /auth/i });
    if (await authTab.isVisible()) {
      await authTab.click();
      
      // Verify user:me scope is present
      await expect(page.getByText(/user:me/i)).toBeVisible({ timeout: 5000 });
      
      // Verify admin:all scope is NOT present
      await expect(page.getByText(/admin:all/i)).not.toBeVisible();
    }
  });

  test('Logout clears token and identity', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Login first
    const adminButton = page.getByRole('button', { name: /login.*admin/i });
    await adminButton.click();
    await expect(page.getByText(/admin@/i)).toBeVisible({ timeout: 5000 });
    
    // Find and click logout button
    const logoutButton = page.getByRole('button', { name: /logout/i });
    if (await logoutButton.isVisible()) {
      await logoutButton.click();
      
      // Verify token badge is cleared
      await expect(page.getByText(/admin@/i)).not.toBeVisible();
    }
  });
});

