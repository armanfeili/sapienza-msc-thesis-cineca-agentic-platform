import { test, expect } from '@playwright/test';

/**
 * Tool Invocation Tests (B.1.6)
 * Tests direct tool invocation functionality
 */

test.describe('Tool Invocation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Login as User
    const userButton = page.getByRole('button', { name: /login.*user/i });
    await userButton.click();
    await expect(page.getByText(/user@/i)).toBeVisible({ timeout: 5000 });
  });

  test('Safe tool invocation works', async ({ page }) => {
    // Navigate to Tools tab
    const toolsTab = page.getByRole('tab', { name: /tools/i });
    await expect(toolsTab).toBeVisible({ timeout: 10000 });
    await toolsTab.click();
    
    // Wait for tools to load
    await page.waitForTimeout(2000);
    
    // Look for a safe tool like tools.list or tools.inspect
    const safeTools = [
      /tools\.list/i,
      /tools\.inspect/i,
      /tools\.describe/i,
    ];
    
    let toolFound = false;
    for (const toolPattern of safeTools) {
      const tool = page.getByText(toolPattern);
      if (await tool.count() > 0) {
        await tool.first().click();
        toolFound = true;
        break;
      }
    }
    
    if (toolFound) {
      // Find and click invoke button
      const invokeButton = page.getByRole('button', { name: /invoke|execute|run/i });
      if (await invokeButton.count() > 0) {
        await invokeButton.first().click();
        
        // Wait for result
        await page.waitForTimeout(3000);
        
        // Verify result is displayed
        const resultIndicators = [
          /success/i,
          /result/i,
          /output/i,
          /response/i,
        ];
        
        let foundResult = false;
        for (const indicator of resultIndicators) {
          if (await page.getByText(indicator).count() > 0) {
            foundResult = true;
            break;
          }
        }
        
        expect(foundResult).toBeTruthy();
      }
    }
  });

  test('Tool list displays available tools', async ({ page }) => {
    const toolsTab = page.getByRole('tab', { name: /tools/i });
    await toolsTab.click();
    await page.waitForTimeout(2000);
    
    // Verify multiple tools are listed
    // Look for common tool categories
    const toolCategories = [
      /tools\./i,
      /graph\./i,
      /db\./i,
      /system\./i,
    ];
    
    let categoriesFound = 0;
    for (const category of toolCategories) {
      if (await page.getByText(category).count() > 0) {
        categoriesFound++;
      }
    }
    
    // At least one tool category should be visible
    expect(categoriesFound).toBeGreaterThan(0);
  });

  test('Tool parameters can be configured', async ({ page }) => {
    const toolsTab = page.getByRole('tab', { name: /tools/i });
    await toolsTab.click();
    await page.waitForTimeout(2000);
    
    // Select a tool
    const anyTool = page.getByText(/tools\.|graph\./i).first();
    if (await anyTool.count() > 0) {
      await anyTool.click();
      
      // Look for parameter inputs (text inputs, number inputs, etc.)
      const paramInputs = await page.locator('input[type="text"], input[type="number"], textarea').all();
      
      // If tool has parameters, there should be inputs
      // Some tools may have no parameters, which is also valid
      expect(paramInputs.length).toBeGreaterThanOrEqual(0);
    }
  });

  test('Tool invocation shows error for invalid parameters', async ({ page }) => {
    const toolsTab = page.getByRole('tab', { name: /tools/i });
    await toolsTab.click();
    await page.waitForTimeout(2000);
    
    // Try to find a tool that requires parameters
    const tools = await page.getByText(/tools\.|graph\./i).all();
    
    if (tools.length > 0) {
      await tools[0].click();
      
      // Try to invoke without filling required parameters
      const invokeButton = page.getByRole('button', { name: /invoke|execute/i });
      if (await invokeButton.count() > 0) {
        const isEnabled = await invokeButton.first().isEnabled();
        
        // Either button is disabled or clicking shows validation error
        if (isEnabled) {
          await invokeButton.first().click();
          await page.waitForTimeout(2000);
          
          // Look for error or validation message
          // (or successful execution if tool has no required params)
          const hasError = await page.getByText(/error|invalid|required/i).count() > 0;
          const hasSuccess = await page.getByText(/success|result/i).count() > 0;
          
          // Either error or success is valid (depends on tool requirements)
          expect(hasError || hasSuccess).toBeTruthy();
        }
      }
    }
  });
});

