import { expect, test, type Page } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;

async function login(page: Page) {
  test.skip(!smokePassword, 'Set DSA_WEB_SMOKE_PASSWORD to run authenticated smoke tests.');

  const homeLink = page.getByRole('link', { name: '首页' });
  const homeWorkspaceMarker = page.getByRole('button', { name: '分析', exact: true });

  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  const canUseHomeDirectly =
    page.url().endsWith('/') ||
    await homeLink.isVisible({ timeout: 3_000 }).catch(() => false) ||
    await homeWorkspaceMarker.isVisible({ timeout: 3_000 }).catch(() => false);

  if (canUseHomeDirectly) {
    return;
  }

  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  const passwordInput = page.locator('#password');
  const submitButton = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
  const loginVisible = await passwordInput.isVisible({ timeout: 2_000 }).catch(() => false);

  if (!loginVisible) {
    const isAlreadyAuthenticated =
      page.url().endsWith('/') ||
      await homeLink.isVisible({ timeout: 2_000 }).catch(() => false) ||
      await homeWorkspaceMarker.isVisible({ timeout: 2_000 }).catch(() => false);

    if (isAlreadyAuthenticated) {
      await page.waitForLoadState('domcontentloaded');
      return;
    }
  }

  await expect(passwordInput).toBeVisible({ timeout: 10_000 });
  await passwordInput.fill(smokePassword!);
  await expect(submitButton).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 15_000 },
    ),
    submitButton.click(),
  ]);

  await page.waitForURL('/', { timeout: 15_000 });
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1000);
}

test.describe('web smoke', () => {
  test('login page renders password form', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');

    const passwordVisible = await page.locator('#password').isVisible({ timeout: 2_000 }).catch(() => false);

    if (passwordVisible) {
      await expect(page.getByText('DAILY STOCK').first()).toBeVisible();
      await expect(page.getByText('Analysis Engine')).toBeVisible();
      await expect(page.locator('#password')).toBeVisible();
      await expect(page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ })).toBeVisible();
      return;
    }

    await expect(page.getByRole('link', { name: '首页' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '分析', exact: true })).toBeVisible({ timeout: 10_000 });
  });

  test('home page shows analysis entry and history panel after login', async ({ page }) => {
    await login(page);

    const stockInput = page.getByPlaceholder(/600519/);
    await expect(stockInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '首页' })).toBeVisible();
    await expect(page.getByRole('link', { name: '问股' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '历史分析' })).toBeVisible();

    await stockInput.fill('600519');
    await expect(page.getByRole('button', { name: '分析', exact: true })).toBeVisible();
  });

  test('chat page allows entering a question and starts a request', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '问股' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('chat-session-list-scroll')).toBeVisible();
    await expect(page.getByTestId('chat-message-scroll')).toBeVisible();

    const input = page.getByPlaceholder(/分析 600519/);
    await expect(input).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('策略', { exact: true })).toBeVisible();

    const prompt = '请简要分析 600519';
    await input.fill(prompt);
    await page.getByRole('button', { name: '发送' }).click();

    await expect(page.locator('p').filter({ hasText: prompt }).last()).toBeVisible({ timeout: 5_000 });
  });

  test('chat page uses accessible labels instead of native title attributes for key actions', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '问股' }).click();
    await page.waitForLoadState('domcontentloaded');

    const sendButton = page.getByRole('button', { name: '发送' });
    const composer = page.getByPlaceholder(/分析 600519/);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(sendButton).toBeVisible({ timeout: 10_000 });
    await expect(composer).toBeVisible({ timeout: 10_000 });

    await expect(sendButton).not.toHaveAttribute('title', /.+/);
    await expect(composer).not.toHaveAttribute('title', /.+/);
  });

  test('mobile shell opens navigation drawer after login', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    const menuButton = page.getByRole('button', { name: /打开导航菜单/i });
    await expect(menuButton).toBeVisible({ timeout: 5_000 });
    await menuButton.click();

    const navDrawer = page.getByRole('dialog', { name: /导航菜单/i });
    await expect(navDrawer).toBeVisible({ timeout: 5_000 });
    await expect(navDrawer.getByRole('link', { name: '回测' })).toBeVisible({ timeout: 5_000 });
  });

  test('settings page renders title and save actions after login', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '设置' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '重置' })).toBeVisible();
    await expect(page.getByRole('button', { name: /保存配置/ })).toBeVisible();
  });

  test('backtest page defaults to V1 momentum mode and can still switch to classic controls', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '回测' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByRole('button', { name: /V1 .*回测/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: /传统回测/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: /创建回测/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/还没有 V1 回测结果/i)).toBeVisible({ timeout: 10_000 });

    await page.getByRole('button', { name: /传统回测/i }).click();
    await expect(page.getByPlaceholder(/stock code/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: /filter/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /run backtest/i })).toBeVisible();
  });
});
