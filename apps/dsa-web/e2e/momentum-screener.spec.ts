import { expect, test, type Page } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;
const tushareToken = process.env.TUSHARE_TOKEN;

async function login(page: Page) {
  test.skip(!tushareToken, 'Set TUSHARE_TOKEN to run momentum screener smoke tests.');

  const authStatusResponse = await page.request.get('/api/v1/auth/status');
  const authStatus = (await authStatusResponse.json()) as {
    authEnabled?: boolean;
  };
  const authEnabled = Boolean(authStatus.authEnabled);

  if (!authEnabled) {
    return;
  }

  test.skip(
    !smokePassword,
    'Set DSA_WEB_SMOKE_PASSWORD to run momentum screener smoke tests when auth is enabled.',
  );

  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  const passwordInput = page.locator('#password');
  const submitButton = page.getByRole('button', { name: /登录|授权进入工作台/ });
  const homeLink = page.getByRole('link', { name: '首页' });

  const isAlreadyAuthenticated =
    page.url().endsWith('/') ||
    (await homeLink.isVisible({ timeout: 2_000 }).catch(() => false));

  if (isAlreadyAuthenticated) {
    await page.waitForLoadState('domcontentloaded');
    return;
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
}

test.describe('momentum screener smoke', () => {
  test('runs standard and aggressive screener flow against real backend', async ({ page }) => {
    test.setTimeout(360_000);

    await login(page);

    const setPageState = async (profile: 'standard' | 'aggressive') => {
      await page.addInitScript((nextProfile) => {
        window.localStorage.setItem(
          'dsa.momentum-screener.page-state',
          JSON.stringify({
            form: {
              profile: nextProfile,
              topN: '3',
              minChangePct: '9',
              minAmountYi: '3',
              minTurnover: '3',
              tradeDate: '',
            },
            sortBy: 'rank_score',
          }),
        );
      }, profile);
    };

    await setPageState('standard');
    await page.goto('/screener');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.getByRole('heading', { name: '强势筛选' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByLabel('评分画像')).toBeVisible();

    await expect(page.getByRole('button', { name: '复制结果' })).toBeEnabled({ timeout: 180_000 });
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Standard').first()).toBeVisible({ timeout: 10_000 });

    await setPageState('aggressive');
    await page.goto('/screener');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.getByRole('button', { name: '复制结果' })).toBeEnabled({ timeout: 180_000 });
    await expect(page.getByText('Aggressive').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('dialog').getByText('可买分')).toBeVisible({ timeout: 10_000 });
  });
});
