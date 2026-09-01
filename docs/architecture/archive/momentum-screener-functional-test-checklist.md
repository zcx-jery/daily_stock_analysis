# Momentum Screener Functional Test Checklist

## Purpose

This checklist is used to validate the functional completeness of Momentum Screener before and during internal beta rollout.

## Test Environment

- Target URL:
  - `http://163.7.12.193/`
  - `http://163.7.12.193/screener`
  - `http://163.7.12.193/api/health`
- Build branch:
  - `feat/momentum-screener-internal-beta`
- Required backend dependency:
  - valid `TUSHARE_TOKEN`

## Pre-Check

- [ ] `GET /api/health` returns `200`
- [ ] `/screener` opens normally
- [ ] No frontend white screen
- [ ] No backend `500` during initial page load
- [ ] System config contains Momentum Screener default keys

## Core API Validation

### Standard Profile

Request parameters:

- `profile=standard`
- `top_n=10`
- `min_change_pct=7`
- `min_amount_yi=3`
- `min_turnover=3`

Checklist:

- [ ] API returns `200`
- [ ] `candidate_count > 0`
- [ ] `results` is not empty
- [ ] `trade_date` is present
- [ ] Result items contain:
  - [ ] `ts_code`
  - [ ] `name`
  - [ ] `pct_chg`
  - [ ] `rank_score`
  - [ ] `continuation_score`
  - [ ] `extension_score`
  - [ ] `risk_score`
  - [ ] `themes`
  - [ ] `leader_level`
- [ ] Results are sorted by `rank_score` descending

### Aggressive Profile

Request parameters:

- `profile=aggressive`
- `top_n=10`
- `min_change_pct=7`
- `min_amount_yi=3`
- `min_turnover=3`

Checklist:

- [ ] API returns `200`
- [ ] `candidate_count > 0`
- [ ] `results` is not empty
- [ ] Result items contain all standard fields
- [ ] Result items additionally contain:
  - [ ] `buyability_score`
  - [ ] `opportunity_tag`
  - [ ] `entry_range_low`
  - [ ] `entry_range_high`

## Frontend Workflow Validation

### Basic Page Flow

- [ ] `/screener` page loads
- [ ] Default parameters are populated
- [ ] `standard` profile can run successfully
- [ ] `aggressive` profile can run successfully

### Interaction

- [ ] Profile switch triggers re-screening
- [ ] Sorting switch updates result order
- [ ] Clicking a result row opens detail drawer
- [ ] Drawer shows score breakdown correctly
- [ ] `aggressive` drawer shows:
  - [ ] `可买分`
  - [ ] `机会标签`
  - [ ] `建议区间`

### Export and Copy

- [ ] `复制结果` works
- [ ] `导出 Markdown` works
- [ ] `导出 CSV` works
- [ ] Single-row `复制明细` works
- [ ] Single-row `导出 Markdown` works

## System Defaults Validation

### Config Chain

- [ ] `/settings` shows Momentum Screener default fields
- [ ] Updating defaults in `/settings` can be saved
- [ ] Clearing local persisted state causes `/screener` to load from system defaults
- [ ] Local persisted state takes precedence over system defaults
- [ ] `恢复系统默认` resets the form and triggers screening

## Fallback and Error Handling

### Empty Result Case

- [ ] Very strict filter parameters return an empty list instead of `500`
- [ ] Page shows a clear empty-state message

### Sector Mapping Fallback

- [ ] Sector mapping timeout does not break the request
- [ ] Results still return using fallback industry classification

### Data and UI Resilience

- [ ] Invalid local persisted parameters do not crash the page
- [ ] Export actions do not crash when result set is empty
- [ ] No unhandled frontend exception is observed in browser console

## Acceptance Criteria

### Internal Beta Pass

- [ ] Both profiles work end-to-end
- [ ] No blocking bug in sorting, detail, copy, or export
- [ ] No recurring `500` during normal use
- [ ] Fallback path works when sector enrichment fails
- [ ] Core API failure rate during manual regression is below `5%`

### Decision

- [ ] Pass
- [ ] Conditional Pass
- [ ] Fail

## Tester Notes

Write down:

- observed latency
- result quality feedback
- difference between `standard` and `aggressive`
- any empty-result or timeout case
