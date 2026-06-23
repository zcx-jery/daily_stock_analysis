# Momentum Screener Launch Readiness

## Status
- Current release target: internal beta
- Backend real-data validation: passed
- Frontend Playwright smoke: passed
- Recommended rollout: internal beta first, then wider rollout after 3 to 5 trading days

## Production Defaults
| Config Key | Default |
| --- | --- |
| `MOMENTUM_SCREENER_DEFAULT_PROFILE` | `standard` |
| `MOMENTUM_SCREENER_DEFAULT_TOP_N` | `10` |
| `MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT` | `7` |
| `MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI` | `3` |
| `MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER` | `3` |
| `MOMENTUM_SECTOR_CACHE_TTL_SECONDS` | `21600` |

## Real Data Validation
### Backend real-data check
```bash
python scripts/run_momentum_screener_release_check.py --profile standard --top-n 5
python scripts/run_momentum_screener_release_check.py --profile aggressive --top-n 5
```

Requirements:
- `TUSHARE_TOKEN` is set

Optional:
```bash
python scripts/run_momentum_screener_release_check.py --profile aggressive --trade-date 2026-04-10
```

### Frontend smoke
```bash
cd apps/dsa-web
npx playwright test e2e/momentum-screener.spec.ts --project=chromium
```

Requirements:
- `TUSHARE_TOKEN` is set

Auth note:
- `DSA_WEB_SMOKE_PASSWORD` is only required when `ADMIN_AUTH_ENABLED=true`
- In the current default repo state, auth is disabled, so smoke can run without it

### Latest verified result
- Verification date: `2026-04-11`
- Real backend check:
  - `standard`: passed
  - `aggressive`: passed
- Playwright smoke:
  - `apps/dsa-web/e2e/momentum-screener.spec.ts`: passed

## Regression Commands
### Backend
```bash
python -m pytest tests/test_momentum_screener_service.py -q
python -m pytest tests/test_momentum_screener_api.py -q
python -m pytest tests/test_system_config_api.py -q
```

### Frontend
```bash
cd apps/dsa-web
npm test -- --run src/pages/__tests__/MomentumScreenerPage.test.tsx
npm test -- --run src/pages/__tests__/SettingsPage.test.tsx
npm test -- --run src/hooks/__tests__/useSystemConfig.test.tsx
npm test -- --run src/pages/__tests__/HomePage.test.tsx
npm test -- --run src/components/report/__tests__/ReportMarkdown.test.tsx
npm test -- --run src/components/layout/__tests__/SidebarNav.test.tsx
npm run build
```

## Pre-Release Checklist
- System config page shows and saves all Momentum Screener defaults
- `/screener` loads system defaults when no local state is present
- `standard` and `aggressive` both return usable results
- Copy/export actions work
- Health endpoints expose `momentum_sector_cache` diagnostics
- Shenwan level-1 mapping works, with `industry` fallback still available

## Known Risks
- Strategy logic is validated against a real Tushare run, but still needs observation across live trading days
- `DSA_WEB_SMOKE_PASSWORD` is only needed when admin auth is enabled
- Strategy logic is ready for beta, but still needs observation across live trading days

## Rollout Order
1. Set `TUSHARE_TOKEN`
2. Run backend real-data check
3. Run frontend smoke
4. Start internal beta
5. Observe 3 to 5 trading days
6. Expand usage
