# Momentum Screener Pressure Test Report 2026-04-11

## Environment

- Target server: `163.7.12.193`
- Public API entry: `http://163.7.12.193/api/v1/stocks/screener/momentum`
- Health endpoint: `http://163.7.12.193/api/health`
- Deployed branch: `feat/momentum-screener-internal-beta`
- Backend commit during run: `462fff6`

## Test Type

This was a **low-concurrency real-data endurance baseline**, not a formal high-concurrency production stress test.

It intentionally followed the pressure-test template constraint:

- do not overload real Tushare-backed requests
- use low concurrency
- validate stability first

## Test Plan Executed

### Sequential Endurance Baseline

- total requests: `6`
- profiles:
  - `standard`
  - `aggressive`
  - alternating
- pause between requests: `5s`

### Small Concurrent Probe

- total requests: `2`
- concurrency: `2`
- profiles:
  - `standard`
  - `aggressive`

## Results

### Sequential Endurance Baseline

| Round | Profile | Result | Status | Time | Candidate Count | Top Result |
|---|---|---|---:|---:|---:|---|
| 1 | `standard` | Pass | `200` | `72.81s` | `47` | `002281.SZ` |
| 2 | `aggressive` | Pass | `200` | `91.30s` | `47` | `603507.SH` |
| 3 | `standard` | Pass | `200` | `78.47s` | `47` | `002281.SZ` |
| 4 | `aggressive` | Pass | `200` | `87.56s` | `47` | `603507.SH` |
| 5 | `standard` | Pass | `200` | `68.30s` | `47` | `002281.SZ` |
| 6 | `aggressive` | Pass | `200` | `80.54s` | `47` | `603507.SH` |

Summary:

- total: `6`
- success: `6`
- errors: `0`
- success rate: `100%`
- average latency: `79.83s`
- max latency: `91.30s`

### Small Concurrent Probe

| Profile | Result | Status | Time | Candidate Count | Top Result |
|---|---|---:|---:|---:|---|
| `standard` | Pass | `200` | `76.46s` | `47` | `002281.SZ` |
| `aggressive` | Pass | `200` | `96.95s` | `47` | `603507.SH` |

Summary:

- total: `2`
- success: `2`
- errors: `0`
- success rate: `100%`
- average latency: `86.70s`
- max latency: `96.95s`

## Health Check After Test

Final health response remained `ok`.

Observed cache diagnostics:

- `hit=17`
- `miss=1`
- `expired=0`
- `size=1`
- `ttl_seconds=21600`

This indicates sector-context caching worked as expected after warm-up.

## Pressure Verdict

### Stability

- **Pass for internal beta**

Reason:

- no request failure in the executed baseline
- no repeated `500`
- service remained healthy after the run
- repeated calls benefited from sector-context cache reuse

### Performance

- **Conditional Pass**

Reason:

- latency is stable but still high
- real-data requests are currently closer to internal-beta tolerance than to formal production expectations

Observed latency range:

- roughly `68s` to `97s`

## Release Decision

- **Ready for internal beta**
- **Not yet recommended for formal production-grade release**

## Main Follow-Up Recommendation

- continue observation for `3-5` trading days
- record:
  - average latency
  - P95 latency
  - empty-result frequency
  - fallback frequency
  - any repeated upstream timeout pattern
