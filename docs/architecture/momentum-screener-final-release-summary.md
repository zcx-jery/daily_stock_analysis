# Momentum Screener Final Release Summary

## Title

Momentum Screener: next-day strong-stock screening with standard and aggressive profiles

## Short Summary

This release adds a usable Momentum Screener workflow to `daily_stock_analysis`, including a new backend API, a new `/screener` frontend page, dual scoring profiles, export/copy flows, system-configurable defaults, Shenwan Level-1 sector mapping, and real-data release validation.

## Included in This Release

- New API: `POST /api/v1/stocks/screener/momentum`
- New page: `/screener`
- Two profiles:
  - `standard`
  - `aggressive`
- Ranking and score breakdown
- Copy/export:
  - copy current result set
  - export Markdown
  - export CSV
  - copy single-stock detail
  - export single-stock Markdown
- System-configurable screener defaults
- Shenwan Level-1 sector mapping with cache TTL and health diagnostics
- Real Tushare release check script
- Playwright smoke coverage for the main screener flow

## Main User Value

- Filter all stocks that rose above a threshold today
- Score them for next-day continuation probability
- Switch between balanced and aggressive trading styles
- Export ranked candidates in directly usable formats

## Validation

Verified on `2026-04-11`:

- Backend tests passed
- Frontend tests passed
- Production build passed
- Real Tushare checks passed for `standard` and `aggressive`
- Playwright smoke passed for `/screener`

## Real Runtime Snapshot

Trading date validated: `2026-04-09`

- `standard` top result: `002281.SZ 光迅科技`
- `aggressive` top result: `603507.SH 振江股份`

## New Configuration Keys

- `MOMENTUM_SCREENER_DEFAULT_PROFILE`
- `MOMENTUM_SCREENER_DEFAULT_TOP_N`
- `MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT`
- `MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI`
- `MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER`
- `MOMENTUM_SECTOR_CACHE_TTL_SECONDS`

## Commits

- `aeee050` docs: add momentum screener product and launch documentation
- `da354a7` feat: add momentum screener backend api and scoring engine
- `51455aa` feat: add momentum screener frontend page and smoke tests
- `2259267` refactor: optimize web bundle and support momentum screener smoke

## Known Non-Blocking Items

- Some backend tests still emit Pydantic v2 deprecation warnings
- Vite startup may still print a PostCSS warning that does not block runtime

## Recommended Rollout

- Release as internal beta
- Observe for `3-5` trading days
- Watch:
  - empty-result cases
  - sector fallback frequency
  - differences between `standard` and `aggressive`
  - runtime stability under real Tushare latency

## Related Docs

- [Commit Scope](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-commit-scope.md)
- [PR Summary](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pr-summary.md)
- [Launch Readiness](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-launch-readiness.md)
- [Release Notes](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-release-notes.md)
