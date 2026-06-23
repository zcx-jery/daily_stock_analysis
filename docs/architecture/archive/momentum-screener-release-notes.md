# Momentum Screener Release Notes

## Scope

This release introduces the first usable version of Momentum Screener for next-day strong-stock selection.

## What Is Included

- New backend API: `/api/v1/stocks/screener/momentum`
- New frontend page: `/screener`
- Two selectable scoring profiles:
  - `standard`
  - `aggressive`
- Result ranking, sorting, copy, Markdown export, CSV export, and single-stock detail export
- Configurable system defaults for screener parameters
- Shenwan Level-1 sector mapping with cache, TTL, and health diagnostics

## User-Facing Capabilities

- Filter stocks by:
  - profile
  - top N
  - minimum change percent
  - minimum amount
  - minimum turnover
- Review:
  - rank score
  - continuation score
  - extension score
  - risk score
  - buyability score for `aggressive`
- Inspect:
  - score breakdown
  - themes
  - leader level
  - top reasons
  - risk tags
  - opportunity tag and entry range for `aggressive`

## Validation Status

Verified on `2026-04-11`:

- Backend unit and API tests passed
- Frontend page tests passed
- Frontend production build passed
- Real Tushare release checks passed for:
  - `standard`
  - `aggressive`
- Playwright smoke passed for `/screener`

## Runtime Notes

- `TUSHARE_TOKEN` is required for real-data execution
- `DSA_WEB_SMOKE_PASSWORD` is only required when `ADMIN_AUTH_ENABLED=true`
- Screener defaults can be managed in `/settings`

## Known Non-Blocking Issues

- Some backend test runs still emit Pydantic v2 deprecation warnings
- Vite startup may still print a PostCSS warning that does not block build or runtime

## Rollout Recommendation

- Release as internal beta first
- Observe for `3-5` trading days
- Focus on:
  - result stability
  - sector mapping fallback rate
  - empty-result cases
  - perceived difference between `standard` and `aggressive`
