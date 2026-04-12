# Momentum Screener Pressure Test Template

## Purpose

This document defines how to execute and record pressure and endurance tests for Momentum Screener without overwhelming the Tushare upstream dependency.

## Important Principle

Do not run high-concurrency stress directly against the real Tushare-backed path.

Pressure testing must be split into:

1. Local service capacity test with mocked or fixed data
2. Low-concurrency endurance test with real Tushare data
3. Multi-user frontend interaction test

## Test Matrix

| Layer | Goal | Upstream Mode | Concurrency | Duration |
|---|---|---:|---:|---:|
| Service-only | Test API/runtime stability | Mocked or fixed data | 1, 5, 10, 20 | 5-10 min each |
| Real-data endurance | Test real Tushare stability | Real data | 1-2 | 30-60 min |
| Frontend usage | Test user-side behavior | Real backend | 5-10 users | 15-30 min |

## Layer 1: Service-Only Pressure Test

### Goal

Measure server behavior without third-party network variability.

### Method

- Replace data fetch with fake/fixed data
- Hit `POST /api/v1/stocks/screener/momentum`
- Run with:
  - `profile=standard`
  - `profile=aggressive`

### Recommended Concurrency Steps

- `1`
- `5`
- `10`
- `20`

### Metrics to Record

- total requests
- success count
- error count
- average latency
- P95 latency
- P99 latency
- container restart count
- memory trend
- CPU trend

### Pass Criteria

- error rate `< 1%`
- no container restart
- no continuous memory growth
- no API-wide unresponsiveness

## Layer 2: Real-Data Endurance Test

### Goal

Measure production-like stability under real Tushare latency.

### Method

- Use real environment and real token
- Alternate between:
  - `standard`
  - `aggressive`
- Keep concurrency low to avoid upstream abuse

### Recommended Settings

- concurrency: `1-2`
- interval between requests: `10-30s`
- duration: `30-60 min`

### Metrics to Record

- request count
- success rate
- timeout count
- fallback count
- average latency
- P95 latency
- empty result count
- HTTP `500` count

### Pass Criteria

- error rate `< 5%`
- no long consecutive failure streak
- no repeated unrecovered `500`
- fallback can recover the request path when sector context load fails

## Layer 3: Frontend Multi-User Test

### Goal

Verify that normal interactive use remains stable when several users operate the page at the same time.

### User Actions

- open `/screener`
- switch profile
- execute screening
- sort results
- open detail drawer
- export Markdown
- export CSV

### Recommended Scale

- `5-10` concurrent users
- `15-30 min`

### Metrics to Record

- page load failures
- request failures
- export failures
- visible UI freeze
- browser console errors

### Pass Criteria

- no widespread page failure
- export remains usable
- no repeated frontend crash

## Recording Table

| Test ID | Layer | Profile | Concurrency | Duration | Requests | Success | Errors | Avg Latency | P95 | P99 | Fallback Count | Empty Results | Notes |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| PT-001 | Service-only | standard | 1 | 5 min |  |  |  |  |  |  |  |  |  |
| PT-002 | Service-only | standard | 5 | 5 min |  |  |  |  |  |  |  |  |  |
| PT-003 | Service-only | aggressive | 5 | 5 min |  |  |  |  |  |  |  |  |  |
| PT-004 | Service-only | standard | 10 | 10 min |  |  |  |  |  |  |  |  |  |
| PT-005 | Real-data | standard | 1 | 30 min |  |  |  |  |  |  |  |  |  |
| PT-006 | Real-data | aggressive | 1 | 30 min |  |  |  |  |  |  |  |  |  |
| PT-007 | Frontend | mixed | 5 users | 15 min |  |  |  |  |  |  |  |  |  |

## Final Evaluation

### Functional Stability

- [ ] Pass
- [ ] Conditional Pass
- [ ] Fail

### Performance

- [ ] Pass
- [ ] Conditional Pass
- [ ] Fail

### Release Decision

- [ ] Ready for internal beta
- [ ] Need more observation
- [ ] Block release

## Conclusion Template

Example:

- Functional stability: Pass
- Performance: Conditional Pass
- Main issue: real-data latency fluctuates during sector enrichment
- Release decision: ready for internal beta, not ready for formal production release
