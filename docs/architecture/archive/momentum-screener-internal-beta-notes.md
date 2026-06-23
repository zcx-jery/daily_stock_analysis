# Momentum Screener Internal Beta Notes

## Scope
This note records the current internal beta scope for Momentum Screener, including:

- feature scope
- suggested commit scope
- verification status
- rollout notes for testers

## Feature Summary
Momentum Screener is now available as a first usable beta inside the existing stock analysis system.

Current scope:

- backend API:
  - `POST /api/v1/stocks/screener/momentum`
- frontend page:
  - `/screener`
- profiles:
  - `standard`
  - `aggressive`
- outputs:
  - `rank_score`
  - `continuation_score`
  - `extension_score`
  - `risk_score`
  - `buyability_score` for `aggressive`
- user actions:
  - sort results
  - copy results
  - export Markdown
  - export CSV
  - copy single-stock detail
  - export single-stock Markdown

## Suggested Commit Scope
The current implementation can be treated as one feature line, but for PR review it is cleaner to think about it in four groups.

### 1. Product Docs
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
- `docs/architecture/README.md`

### 2. Backend API and Service
- `src/services/momentum_screener_service.py`
- `api/deps.py`
- `api/v1/endpoints/stocks.py`
- `api/v1/schemas/stocks.py`
- `api/app.py`
- `api/v1/endpoints/health.py`
- `api/v1/schemas/common.py`
- `src/config.py`
- `src/core/config_registry.py`
- `scripts/run_momentum_screener_release_check.py`
- `.env.example`
- `data_provider/tushare_fetcher.py`

### 3. Frontend Page and UX
- `apps/dsa-web/src/pages/MomentumScreenerPage.tsx`
- `apps/dsa-web/src/api/momentumScreener.ts`
- `apps/dsa-web/src/types/momentumScreener.ts`
- `apps/dsa-web/src/App.tsx`
- `apps/dsa-web/src/components/layout/SidebarNav.tsx`
- `apps/dsa-web/vite.config.ts`
- `apps/dsa-web/playwright.config.ts`
- `apps/dsa-web/e2e/momentum-screener.spec.ts`
- `apps/dsa-web/scripts/run_smoke_backend.py`

### 4. Supporting Engineering Changes
These are related but broader than only Momentum Screener:

- `apps/dsa-web/src/pages/HomePage.tsx`
- `apps/dsa-web/src/pages/PortfolioPage.tsx`
- `apps/dsa-web/src/pages/ChatPage.tsx`
- `apps/dsa-web/src/pages/MarketReportsPage.tsx`
- `apps/dsa-web/src/components/report/ReportMarkdown.tsx`
- `apps/dsa-web/src/components/markdown/*`
- `apps/dsa-web/src/components/portfolio/*`
- `patch/eastmoney_patch.py`

## Verification Status
Verified on `2026-04-11`.

Passed:

- backend tests:
  - `tests/test_momentum_screener_service.py`
  - `tests/test_momentum_screener_api.py`
  - `tests/test_system_config_api.py`
- frontend tests:
  - `src/pages/__tests__/MomentumScreenerPage.test.tsx`
  - `src/pages/__tests__/SettingsPage.test.tsx`
  - `src/hooks/__tests__/useSystemConfig.test.tsx`
  - `src/pages/__tests__/HomePage.test.tsx`
  - `src/components/report/__tests__/ReportMarkdown.test.tsx`
  - `src/components/layout/__tests__/SidebarNav.test.tsx`
- frontend build:
  - `npm run build`
- real-data release check:
  - `standard`: passed
  - `aggressive`: passed
- Playwright smoke:
  - `apps/dsa-web/e2e/momentum-screener.spec.ts`: passed

## Latest Real Validation Snapshot
- trade date: `2026-04-09`
- standard top result:
  - `002281.SZ 光迅科技`
- aggressive top result:
  - `603507.SH 振江股份`

## Runtime Defaults
- `MOMENTUM_SCREENER_DEFAULT_PROFILE=standard`
- `MOMENTUM_SCREENER_DEFAULT_TOP_N=10`
- `MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT=7`
- `MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI=3`
- `MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER=3`
- `MOMENTUM_SECTOR_CACHE_TTL_SECONDS=21600`

## Tester Notes
- The page automatically runs a screening once it loads.
- The page prefers local saved state over system defaults.
- `aggressive` is intentionally more momentum-heavy and can rank higher-risk names above `standard`.
- Current board theme mapping uses Shenwan level-1 first, with `industry` fallback kept for resilience.

## Non-Blocking Technical Debt
- Pydantic v2 deprecation warnings still appear in backend test output.
- Vite startup still prints one PostCSS plugin warning, but build and runtime are normal.

## Rollout Recommendation
1. Start internal beta.
2. Observe for 3 to 5 trading days.
3. Compare `standard` and `aggressive` result quality.
4. Collect false-positive and false-negative cases.
5. Only then decide whether to adjust default thresholds or default profile.
