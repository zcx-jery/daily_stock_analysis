# Momentum Screener Final Release Summary

## V1.3 Production Readiness Contract

V1.3 的发布目标不再只是“扫描今日强势股”，而是形成可审计的短线决策链路。最终架构按以下层级收口：

```text
Gate Rules
-> Raw Scoring
-> Risk Stacking (R1-R5)
-> Mainline Privilege
-> AI Audit
```

- `Gate Rules`：先判断市场环境、机会质量和 20 日进攻许可，决定今日可做 / 谨慎 / 仅观察 / 不做。
- `Raw Scoring`：使用原始强势排序与 V1.3 画像字段形成候选池，保留 Raw Momentum Top3 作为不可篡改基准。
- `Risk Stacking (R1-R5)`：对高位、封板、背离、主线不足和量能竭尽做组合风险审计，R5 保持一票否决。
- `Mainline Privilege`：当 `Mainline_Intensity > 1.2x` 时，允许主线中军 / 龙头在充分换手后完成封板确认，避免用秒板标准误杀板块共振机会。
- `AI Audit`：AI 只做逻辑审计和执行守卫解释，不覆盖数值闸门，也不替代回测标签。

Golden Alpha Rule：

```text
60-day Selection Efficiency = Official Top3 Tradable Success Rate - Raw Momentum Top3 Tradable Success Rate
Production-ready only if Selection Efficiency > 0
```

也就是说，Official Top3 只有在 60 日窗口内持续跑赢 Raw Momentum Top3，才说明二次决策、画像过滤、Risk Stack 和主线优先权真实创造了 Alpha；若 Official 低于 Raw，则必须继续调参或降级为观察工具，不得标记为实盘参考摘要。

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
