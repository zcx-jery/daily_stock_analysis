# Momentum Screener Functional Test Report 2026-04-11

## Environment

- Target server: `163.7.12.193`
- Public entry:
  - `http://163.7.12.193/`
  - `http://163.7.12.193/screener`
  - `http://163.7.12.193/api/health`
- Deployed branch: `feat/momentum-screener-internal-beta`
- Verified backend commit: `462fff6`

## Test Scope

This round executed the automated and scriptable parts of:

- pre-check
- core API validation
- public page shell validation
- empty-result handling
- sector mapping fallback validation through real runtime behavior

Full manual UI actions such as browser-side copy/export button interaction were not re-executed on the deployed server in this round. Those flows remain covered by local frontend tests and earlier local Playwright smoke.

## Results

### Pre-Check

| Check | URL | Result | Status | Time |
|---|---|---|---:|---:|
| health | `/api/health` | Pass | `200` | `0.23s` |
| home | `/` | Pass | `200` | `0.21s` |
| screener | `/screener` | Pass | `200` | `0.20s` |
| auth status | `/api/v1/auth/status` | Pass | `200` | `0.32s` |

### Core API Validation

| Case | Result | Status | Time | Candidate Count | Top Result |
|---|---|---:|---:|---:|---|
| `standard` | Pass | `200` | `87.09s` | `47` | `002281.SZ 光迅科技` |
| `aggressive` | Pass | `200` | `93.82s` | `47` | `603507.SH 振江股份` |
| `strict-empty` | Pass | `200` | `13.37s` | `0` | `None` |

### Key Assertions

- `standard` returned:
  - `trade_date=2026-04-09`
  - non-empty ranked results
  - expected standard score fields
- `aggressive` returned:
  - `trade_date=2026-04-09`
  - non-empty ranked results
  - `buyability_score` present
- strict filter parameters returned an empty result set instead of `500`

### Public Page Shell Validation

| Check | Result | Status | Time |
|---|---|---:|---:|
| `/` serves frontend shell | Pass | `200` | `0.26s` |
| `/screener` serves frontend shell | Pass | `200` | `0.18s` |

## Runtime Issue Found and Fixed During Test

Initial deployed runtime failed on the first real screener request because Shenwan sector-context loading hit a Tushare timeout and the error propagated as HTTP `500`.

Fix applied:

- when sector-context loading fails, Momentum Screener now falls back to `stock_basic.industry`
- the request still returns results instead of failing the whole API

Fix commit:

- `462fff6` `fix: fallback when momentum sector context loading times out`

## Functional Verdict

### Internal Beta Acceptance

- Pre-check: Pass
- Core API: Pass
- Empty-result handling: Pass
- Public page entry: Pass
- Fallback resilience: Pass

### Final Decision

- **Status: Conditional Pass**

Reason:

- the deployable core flow is working and suitable for internal beta
- however, not every UI interaction item in the functional checklist was re-run against the deployed public server in this round
- real-data latency remains high enough that formal production release should wait for more observation

## Recommended Next Functional Step

- Run one manual browser walkthrough on the deployed `/screener` page covering:
  - sort switch
  - detail drawer
  - copy result
  - export Markdown
  - export CSV
