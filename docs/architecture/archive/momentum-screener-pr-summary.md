# Momentum Screener PR Summary

## Summary

This change introduces the first usable release of Momentum Screener, a next-day strong-stock screening capability built on Tushare-based post-close scoring.

The feature adds:

- a new backend API: `/api/v1/stocks/screener/momentum`
- a new frontend page: `/screener`
- two selectable scoring profiles:
  - `standard`
  - `aggressive`
- export and copy workflows for ranked results
- configurable system defaults
- Shenwan Level-1 sector mapping with runtime cache and diagnostics

## Why

The existing system had single-stock analysis and backtest capabilities, but it did not provide a dedicated workflow for:

- filtering all stocks that rose above a threshold today
- scoring them for next-day continuation
- switching between a balanced and aggressive strategy style
- producing directly usable ranked output for traders

Momentum Screener fills that gap.

## Main Changes

### Backend

- Added `MomentumScreenerService`
- Added screener request/response schema
- Added `POST /api/v1/stocks/screener/momentum`
- Added support for:
  - `standard` profile
  - `aggressive` profile
- Added sector mapping based on Shenwan Level-1 industry data
- Added sector cache with:
  - shared process-level cache
  - TTL
  - health diagnostics
  - runtime-configurable TTL
- Added real-data release check script

### Frontend

- Added `/screener` page
- Added profile switch between `standard` and `aggressive`
- Added result ranking and sorting controls
- Added score breakdown drawer
- Added:
  - copy current result set
  - export Markdown
  - export CSV
  - copy single-stock detail
  - export single-stock Markdown
- Added system-default restore flow
- Added support for aggressive-only fields:
  - `buyability_score`
  - `opportunity_tag`
  - `entry_range_low`
  - `entry_range_high`

### Product and Docs

- Added product plan
- Added PRD
- Added scoring rule docs for both profiles
- Added field mapping, commit scope, launch readiness, beta notes, and release notes

### Supporting Engineering Work

- Refactored screener service creation to dependency injection
- Added smoke backend wrapper for Playwright
- Improved web bundle by route-level lazy loading and selective manual chunking
- Removed a Windows console logging issue in Tushare startup logs

## Validation

Verified on `2026-04-11`.

### Backend

- `python -m pytest tests/test_momentum_screener_service.py -q`
- `python -m pytest tests/test_momentum_screener_api.py -q`
- `python -m pytest tests/test_system_config_api.py -q`

### Frontend

- `npm test -- --run src/pages/__tests__/MomentumScreenerPage.test.tsx src/pages/__tests__/SettingsPage.test.tsx src/hooks/__tests__/useSystemConfig.test.tsx src/pages/__tests__/HomePage.test.tsx src/components/report/__tests__/ReportMarkdown.test.tsx src/components/layout/__tests__/SidebarNav.test.tsx`
- `npm run build`

### Real Runtime Checks

- `python scripts/run_momentum_screener_release_check.py --profile standard --top-n 1`
- `python scripts/run_momentum_screener_release_check.py --profile aggressive --top-n 3`
- `npx playwright test e2e/momentum-screener.spec.ts --project=chromium`

## Real-Data Snapshot

Verified with real Tushare data on trading date `2026-04-09`:

- `standard` top result: `002281.SZ 光迅科技`
- `aggressive` top result: `603507.SH 振江股份`

## Configuration Notes

New runtime defaults are now configurable from system settings:

- `MOMENTUM_SCREENER_DEFAULT_PROFILE`
- `MOMENTUM_SCREENER_DEFAULT_TOP_N`
- `MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT`
- `MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI`
- `MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER`
- `MOMENTUM_SECTOR_CACHE_TTL_SECONDS`

## Known Non-Blocking Issues

- Some backend tests still emit Pydantic v2 deprecation warnings
- Vite startup may print a PostCSS warning that does not block runtime

## Rollout Recommendation

- Release as internal beta first
- Observe for `3-5` trading days
- Focus on:
  - empty result cases
  - sector fallback frequency
  - differences between `standard` and `aggressive`
  - runtime stability under real Tushare latency
