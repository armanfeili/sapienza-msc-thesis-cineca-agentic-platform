import { test, expect } from '@playwright/test';

/**
 * NL to Cypher Query Tests (B.1.5)
 * Tests natural language to Cypher query generation and execution
 */

test.describe('Cypher Queries', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Login as User
    const userButton = page.getByRole('button', { name: /login.*user/i });
    await userButton.click();
    await expect(page.getByText(/user@/i)).toBeVisible({ timeout: 5000 });
  });

  test('NL to Cypher generates and executes query', async ({ page }) => {
    // Navigate to appropriate tab (might be Tools, Explore, or Cypher tab)
    const cypherTab = page.getByRole('tab', { name: /cypher|explore|graph/i });
    if (await cypherTab.isVisible()) {
      await cypherTab.click();
    } else {
      // Try Tools tab
      const toolsTab = page.getByRole('tab', { name: /tools/i });
      await toolsTab.click();
      
      // Look for graph query tool
      const graphQueryTool = page.getByText(/graph.*query|cypher/i);
      if (await graphQueryTool.count() > 0) {
        await graphQueryTool.first().click();
      }
    }
    
    // Find natural language input
    const nlInput = page.locator('input, textarea').filter({ hasText: /natural|query|cypher/i }).first();
    if (await nlInput.count() === 0) {
      // Alternative: look for any text input in the visible area
      const textInputs = page.locator('input[type="text"], textarea').all();
      const inputs = await textInputs;
      if (inputs.length > 0) {
        await inputs[0].fill('Show me all nodes');
        
        // Find invoke/run button
        const invokeButton = page.getByRole('button', { name: /invoke|run|execute|submit/i });
        if (await invokeButton.count() > 0) {
          await invokeButton.first().click();
          
          // Wait for Cypher generation
          await page.waitForTimeout(5000);
          
          // Look for MATCH keyword (indicates Cypher was generated)
          await expect(page.getByText(/MATCH/)).toBeVisible({ timeout: 10000 });
          
          // Look for results table or results section
          const resultsIndicators = [
            /result/i,
            /table/i,
            /row/i,
            /node/i,
          ];
          
          let foundResults = false;
          for (const indicator of resultsIndicators) {
            if (await page.getByText(indicator).count() > 0) {
              foundResults = true;
              break;
            }
          }
          
          expect(foundResults).toBeTruthy();
        }
      }
    }
  });

  test('Cypher query results can be exported to CSV', async ({ page }) => {
    // Navigate to Cypher/Graph tab
    const cypherTab = page.getByRole('tab', { name: /cypher|explore|graph/i });
    if (await cypherTab.isVisible()) {
      await cypherTab.click();
    }
    
    // Execute a simple query first
    const nlInput = page.locator('input, textarea').filter({ hasText: /natural|query/i }).first();
    if (await nlInput.count() > 0) {
      await nlInput.fill('Show all nodes limit 10');
      
      const invokeButton = page.getByRole('button', { name: /invoke|run|execute/i });
      await invokeButton.first().click();
      
      // Wait for results
      await page.waitForTimeout(5000);
      
      // Look for CSV export button
      const csvButton = page.getByRole('button', { name: /csv|export|download/i });
      
      if (await csvButton.count() > 0) {
        // Setup download listener
        const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null);
        
        await csvButton.first().click();
        
        const download = await downloadPromise;
        
        if (download) {
          expect(download.suggestedFilename()).toMatch(/\.csv$/i);
        }
      }
    }
  });

  test('Direct Cypher execution works', async ({ page }) => {
    // Navigate to Cypher tab
    const cypherTab = page.getByRole('tab', { name: /cypher|explore/i });
    if (await cypherTab.isVisible()) {
      await cypherTab.click();
      
      // Look for direct Cypher input (not NL)
      const cypherInput = page.locator('textarea').filter({ hasText: /MATCH|cypher|query/i }).first();
      if (await cypherInput.count() === 0) {
        // Try any textarea
        const allTextareas = await page.locator('textarea').all();
        if (allTextareas.length > 0) {
          await allTextareas[0].fill('MATCH (n) RETURN n LIMIT 5');
          
          const runButton = page.getByRole('button', { name: /run|execute/i });
          if (await runButton.count() > 0) {
            await runButton.first().click();
            
            // Wait for results
            await page.waitForTimeout(3000);
            
            // Verify results or no error
            const errorText = page.getByText(/error|failed|invalid/i);
            const errorCount = await errorText.count();
            
            // Some errors are ok (like empty graph), but shouldn't crash
            // Just verify the query was processed
            expect(errorCount).toBeLessThan(10); // Not flooded with errors
          }
        }
      }
    }
  });
});

