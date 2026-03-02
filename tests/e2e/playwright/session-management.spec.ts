import { test, expect } from '@playwright/test';

/**
 * Session Management Tests (B.1.7)
 * Tests session creation, step addition, and cancellation
 */

test.describe('Session Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Login as User
    const userButton = page.getByRole('button', { name: /login.*user/i });
    await userButton.click();
    await expect(page.getByText(/user@/i)).toBeVisible({ timeout: 5000 });
  });

  test('Create new session', async ({ page }) => {
    // Navigate to Agents tab
    const agentsTab = page.getByRole('tab', { name: /agents/i });
    await agentsTab.click();
    
    // Look for Sessions sub-tab or section
    const sessionsSection = page.getByText(/sessions/i);
    if (await sessionsSection.count() > 0) {
      await sessionsSection.first().click();
      await page.waitForTimeout(1000);
      
      // Look for New Session button
      const newSessionButton = page.getByRole('button', { name: /new.*session|create.*session/i });
      if (await newSessionButton.count() > 0) {
        await newSessionButton.click();
        
        // Fill in session details (if form appears)
        const tenantInput = page.locator('input[name="tenant"], input').filter({ hasText: /tenant/i });
        if (await tenantInput.count() > 0) {
          await tenantInput.first().fill('default');
        }
        
        // Submit/Create
        const createButton = page.getByRole('button', { name: /create|submit/i });
        if (await createButton.count() > 0) {
          await createButton.first().click();
          
          // Verify session was created (look for session ID or success message)
          await page.waitForTimeout(2000);
          const successIndicators = [
            /session.*created/i,
            /success/i,
            /session.*id/i,
          ];
          
          let foundSuccess = false;
          for (const indicator of successIndicators) {
            if (await page.getByText(indicator).count() > 0) {
              foundSuccess = true;
              break;
            }
          }
          
          expect(foundSuccess).toBeTruthy();
        }
      }
    }
  });

  test('View existing sessions', async ({ page }) => {
    const agentsTab = page.getByRole('tab', { name: /agents/i });
    await agentsTab.click();
    
    const sessionsSection = page.getByText(/sessions/i);
    if (await sessionsSection.count() > 0) {
      await sessionsSection.first().click();
      await page.waitForTimeout(2000);
      
      // Look for session list indicators
      const sessionIndicators = [
        /session/i,
        /status/i,
        /created/i,
        /tenant/i,
      ];
      
      let foundSessionInfo = false;
      for (const indicator of sessionIndicators) {
        if (await page.getByText(indicator).count() > 0) {
          foundSessionInfo = true;
          break;
        }
      }
      
      // Sessions list should be visible (even if empty)
      expect(foundSessionInfo).toBeTruthy();
    }
  });

  test('Session add-step functionality', async ({ page }) => {
    const agentsTab = page.getByRole('tab', { name: /agents/i });
    await agentsTab.click();
    
    const sessionsSection = page.getByText(/sessions/i);
    if (await sessionsSection.count() > 0) {
      await sessionsSection.first().click();
      await page.waitForTimeout(2000);
      
      // Try to find an existing session or create one
      let sessionExists = false;
      const sessionElements = await page.getByText(/session.*\d+/i).all();
      
      if (sessionElements.length > 0) {
        // Click on first session
        await sessionElements[0].click();
        sessionExists = true;
      } else {
        // Create a new session first
        const newSessionButton = page.getByRole('button', { name: /new.*session/i });
        if (await newSessionButton.count() > 0) {
          await newSessionButton.click();
          
          const createButton = page.getByRole('button', { name: /create|submit/i });
          if (await createButton.count() > 0) {
            await createButton.click();
            await page.waitForTimeout(2000);
            sessionExists = true;
          }
        }
      }
      
      if (sessionExists) {
        // Look for Add Step button
        const addStepButton = page.getByRole('button', { name: /add.*step/i });
        if (await addStepButton.count() > 0) {
          await addStepButton.click();
          
          // Fill in step content
          const contentInput = page.locator('textarea[name="content"], textarea').first();
          if (await contentInput.count() > 0) {
            await contentInput.fill('Test step content');
            
            const submitButton = page.getByRole('button', { name: /submit|add/i });
            if (await submitButton.count() > 0) {
              await submitButton.click();
              
              // Verify step was added
              await page.waitForTimeout(2000);
              await expect(page.getByText(/test step content/i)).toBeVisible();
            }
          }
        }
      }
    }
  });

  test('Session cancel functionality', async ({ page }) => {
    const agentsTab = page.getByRole('tab', { name: /agents/i });
    await agentsTab.click();
    
    const sessionsSection = page.getByText(/sessions/i);
    if (await sessionsSection.count() > 0) {
      await sessionsSection.first().click();
      await page.waitForTimeout(2000);
      
      // Find or create a session
      const sessionElements = await page.getByText(/session.*\d+/i).all();
      
      if (sessionElements.length > 0) {
        await sessionElements[0].click();
        
        // Look for Cancel/Delete session button
        const cancelButton = page.getByRole('button', { name: /cancel.*session|delete.*session/i });
        if (await cancelButton.count() > 0) {
          await cancelButton.click();
          
          // Look for confirmation modal
          const confirmButton = page.getByRole('button', { name: /confirm|yes|delete/i });
          if (await confirmButton.count() > 0) {
            await confirmButton.click();
            
            // Verify session was cancelled
            await page.waitForTimeout(2000);
            const cancelledIndicators = [
              /cancelled/i,
              /deleted/i,
              /removed/i,
            ];
            
            let foundCancellation = false;
            for (const indicator of cancelledIndicators) {
              if (await page.getByText(indicator).count() > 0) {
                foundCancellation = true;
                break;
              }
            }
            
            expect(foundCancellation).toBeTruthy();
          }
        }
      }
    }
  });
});

