import { test, expect } from '@playwright/test';

test.describe('PaisaClarity Full Browser End-to-End Suite', () => {
  test.setTimeout(60000);

  const timestamp = Date.now();
  const testUser = {
    name: `E2E Browser User ${timestamp}`,
    email: `browser_user_${timestamp}@example.com`,
    password: 'Password123!@#',
  };

  test('Complete 12-flow realistic browser journey', async ({ page }) => {
    // Flow 1: Signup & Login
    await page.goto('/signup');
    await expect(page).toHaveTitle(/Paisa\s*Clarity/i);

    await page.fill('input[type="text"]', testUser.name);
    await page.fill('input[type="email"]', testUser.email);
    await page.fill('input[type="password"]', testUser.password);
    await page.click('button[type="submit"]');

    // Wait for redirect to login or dashboard
    await page.waitForTimeout(1000);
    if (page.url().includes('/login')) {
      await page.fill('input[type="email"]', testUser.email);
      await page.fill('input[type="password"]', testUser.password);
      await page.click('button[type="submit"]');
    }

    // Flow 2: Dashboard Loading
    await expect(page).toHaveURL(/.*(\/dashboard|\/)/);
    await expect(page.locator('text=Dashboard').first()).toBeVisible({ timeout: 10000 });

    // Flow 3: Navigate to Accounts & Create Account
    await page.goto('/accounts');
    await expect(page.locator('text=Financial Accounts').first()).toBeVisible({ timeout: 10000 });

    const addAccountBtn = page.locator('button:has-text("Add Account")').first();
    if (await addAccountBtn.isVisible()) {
      await addAccountBtn.click();
      await page.waitForSelector('input[placeholder*="HDFC Salary"]', { timeout: 5000 });
      await page.fill('input[placeholder*="HDFC Salary"]', 'HDFC Primary Savings');
      await page.fill('input[type="number"]', '25000.00');
      await page.click('button:has-text("Create Account")');
      await page.waitForTimeout(1000);
      await expect(page.locator('text=HDFC Primary Savings').first()).toBeVisible({ timeout: 10000 });
    }

    // Flow 4: Navigate to Transactions
    await page.goto('/transactions');
    await expect(page.locator('text=Transactions').first()).toBeVisible({ timeout: 10000 });

    // Flow 5: Navigate to Budgets
    await page.goto('/budgets');
    await expect(page.locator('text=Budget').first()).toBeVisible({ timeout: 10000 });

    // Flow 6: Navigate to Savings Goals
    await page.goto('/savings-goals');
    await expect(page.locator('text=Savings').first()).toBeVisible({ timeout: 10000 });

    // Flow 7: Navigate to Recurring Payments / Subscriptions
    await page.goto('/recurring');
    await expect(page.locator('text=Recurring').first()).toBeVisible({ timeout: 10000 });

    // Flow 8: Navigate to Alerts
    await page.goto('/alerts');
    await expect(page.locator('text=Alert').first()).toBeVisible({ timeout: 10000 });

    // Flow 9: Navigate to Financial Reports & Export Actions
    await page.goto('/reports');
    await expect(page.locator('text=Financial Reports').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Export CSV")').first()).toBeVisible();
    await expect(page.locator('button:has-text("Download PDF")').first()).toBeVisible();

    // Flow 10: Navigate to AI Copilot
    await page.goto('/copilot');
    await expect(page.locator('text=Copilot').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Spending Summary').first()).toBeVisible({ timeout: 10000 });

    // Flow 11: Navigate to Investments
    await page.goto('/investments');
    await expect(page.locator('text=Investment').first()).toBeVisible({ timeout: 10000 });

    // Flow 12: Protected Route Rejection on Logout
    await page.evaluate(() => localStorage.clear());
    await page.goto('/dashboard');
    await page.waitForURL(/.*login/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  });
});
