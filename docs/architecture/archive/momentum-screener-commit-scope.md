# Momentum Screener Commit Scope

## Purpose

This document defines the recommended git commit scope for the Momentum Screener feature line, so the current worktree can be split into reviewable batches instead of one oversized feature commit.

## Recommendation

Split the current work into `4` commits.

## Commit 1: Product Docs and Release Materials

Scope:

- `docs/CHANGELOG.md`
- `docs/architecture/README.md`
- `docs/architecture/momentum-screener-product-plan.md`
- `docs/architecture/momentum-screener-prd.md`
- `docs/architecture/momentum-screener-v1-scoring-rules.md`
- `docs/architecture/momentum-screener-secondary-score-rules.md`
- `docs/architecture/momentum-screener-v1-aggressive-scoring-rules.md`
- `docs/architecture/momentum-screener-aggressive-secondary-score-rules.md`
- `docs/architecture/momentum-screener-rule-profiles-comparison.md`
- `docs/architecture/momentum-screener-field-mapping.md`
- `docs/architecture/momentum-screener-development-tasks.md`
- `docs/architecture/momentum-screener-launch-readiness.md`
- `docs/architecture/momentum-screener-internal-beta-notes.md`
- `docs/architecture/momentum-screener-release-notes.md`

Suggested commit message:

`docs: add momentum screener product and launch documentation`

## Commit 2: Backend API, Scoring Engine, Config, and Tests

Scope:

- `.env.example`
- `api/app.py`
- `api/deps.py`
- `api/v1/endpoints/health.py`
- `api/v1/endpoints/stocks.py`
- `api/v1/schemas/common.py`
- `api/v1/schemas/stocks.py`
- `data_provider/tushare_fetcher.py`
- `src/config.py`
- `src/core/config_registry.py`
- `src/services/momentum_screener_service.py`
- `scripts/run_momentum_screener_release_check.py`
- `tests/test_momentum_screener_api.py`
- `tests/test_momentum_screener_service.py`
- `tests/test_system_config_api.py`

Suggested commit message:

`feat: add momentum screener backend api and scoring engine`

## Commit 3: Frontend Page, UX, Exports, and Smoke Coverage

Scope:

- `apps/dsa-web/src/api/momentumScreener.ts`
- `apps/dsa-web/src/pages/MomentumScreenerPage.tsx`
- `apps/dsa-web/src/pages/__tests__/MomentumScreenerPage.test.tsx`
- `apps/dsa-web/src/types/momentumScreener.ts`
- `apps/dsa-web/e2e/momentum-screener.spec.ts`
- `apps/dsa-web/scripts/run_smoke_backend.py`

Suggested commit message:

`feat: add momentum screener frontend page and smoke tests`

## Commit 4: Supporting Frontend Refactor and Build Optimization

Scope:

- `apps/dsa-web/playwright.config.ts`
- `apps/dsa-web/src/App.tsx`
- `apps/dsa-web/src/components/layout/SidebarNav.tsx`
- `apps/dsa-web/src/components/markdown/MarkdownContent.tsx`
- `apps/dsa-web/src/components/portfolio/PortfolioConcentrationChart.tsx`
- `apps/dsa-web/src/components/report/ReportMarkdown.tsx`
- `apps/dsa-web/src/hooks/__tests__/useSystemConfig.test.tsx`
- `apps/dsa-web/src/pages/ChatPage.tsx`
- `apps/dsa-web/src/pages/HomePage.tsx`
- `apps/dsa-web/src/pages/MarketReportsPage.tsx`
- `apps/dsa-web/src/pages/PortfolioPage.tsx`
- `apps/dsa-web/src/pages/__tests__/HomePage.test.tsx`
- `apps/dsa-web/src/pages/__tests__/SettingsPage.test.tsx`
- `apps/dsa-web/vite.config.ts`
- `patch/eastmoney_patch.py`

Suggested commit message:

`refactor: optimize web bundle and support momentum screener smoke`

## Notes on Scope

- Commit `4` contains supporting work that is not the screener page itself, but it was introduced to make the new feature testable and keep the web bundle healthy after adding `/screener`.
- `patch/eastmoney_patch.py` is included because the smoke backend path needs startup to succeed even when optional browser-agent dependencies are missing.
- `data_provider/tushare_fetcher.py` belongs in backend commit scope because it fixed a real runtime issue discovered during screener release validation.

## Suggested Staging Commands

### Commit 1

```powershell
git add docs/CHANGELOG.md `
  docs/architecture/README.md `
  docs/architecture/momentum-screener-product-plan.md `
  docs/architecture/momentum-screener-prd.md `
  docs/architecture/momentum-screener-v1-scoring-rules.md `
  docs/architecture/momentum-screener-secondary-score-rules.md `
  docs/architecture/momentum-screener-v1-aggressive-scoring-rules.md `
  docs/architecture/momentum-screener-aggressive-secondary-score-rules.md `
  docs/architecture/momentum-screener-rule-profiles-comparison.md `
  docs/architecture/momentum-screener-field-mapping.md `
  docs/architecture/momentum-screener-development-tasks.md `
  docs/architecture/momentum-screener-launch-readiness.md `
  docs/architecture/momentum-screener-internal-beta-notes.md `
  docs/architecture/momentum-screener-release-notes.md `
  docs/architecture/momentum-screener-commit-scope.md
```

### Commit 2

```powershell
git add .env.example `
  api/app.py `
  api/deps.py `
  api/v1/endpoints/health.py `
  api/v1/endpoints/stocks.py `
  api/v1/schemas/common.py `
  api/v1/schemas/stocks.py `
  data_provider/tushare_fetcher.py `
  src/config.py `
  src/core/config_registry.py `
  src/services/momentum_screener_service.py `
  scripts/run_momentum_screener_release_check.py `
  tests/test_momentum_screener_api.py `
  tests/test_momentum_screener_service.py `
  tests/test_system_config_api.py
```

### Commit 3

```powershell
git add apps/dsa-web/src/api/momentumScreener.ts `
  apps/dsa-web/src/pages/MomentumScreenerPage.tsx `
  apps/dsa-web/src/pages/__tests__/MomentumScreenerPage.test.tsx `
  apps/dsa-web/src/types/momentumScreener.ts `
  apps/dsa-web/e2e/momentum-screener.spec.ts `
  apps/dsa-web/scripts/run_smoke_backend.py
```

### Commit 4

```powershell
git add apps/dsa-web/playwright.config.ts `
  apps/dsa-web/src/App.tsx `
  apps/dsa-web/src/components/layout/SidebarNav.tsx `
  apps/dsa-web/src/components/markdown/MarkdownContent.tsx `
  apps/dsa-web/src/components/portfolio/PortfolioConcentrationChart.tsx `
  apps/dsa-web/src/components/report/ReportMarkdown.tsx `
  apps/dsa-web/src/hooks/__tests__/useSystemConfig.test.tsx `
  apps/dsa-web/src/pages/ChatPage.tsx `
  apps/dsa-web/src/pages/HomePage.tsx `
  apps/dsa-web/src/pages/MarketReportsPage.tsx `
  apps/dsa-web/src/pages/PortfolioPage.tsx `
  apps/dsa-web/src/pages/__tests__/HomePage.test.tsx `
  apps/dsa-web/src/pages/__tests__/SettingsPage.test.tsx `
  apps/dsa-web/vite.config.ts `
  patch/eastmoney_patch.py
```

## Current Decision

If the goal is fastest delivery rather than the cleanest git history, commits `3` and `4` can be merged into one frontend commit. Commits `1` and `2` should stay separate.
