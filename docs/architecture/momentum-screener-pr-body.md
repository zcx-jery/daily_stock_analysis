# Momentum Screener PR Body

## Suggested PR Title

`feat: add momentum screener with standard and aggressive profiles`

## PR Body

```md
## PR Type

- [x] feat
- [x] refactor
- [x] docs
- [x] test

## Background And Problem

当前系统已经具备单股分析、历史记录和回测能力，但缺少“从全市场今日强势股中筛出明日高概率延续标的”的独立工作流。

这导致两个问题：

1. 无法直接按“今日涨幅阈值 -> 次日延续评分 -> TopX 排名”完成短线筛选
2. 无法在平衡型与进攻型交易风格之间切换

本 PR 新增 Momentum Screener，补齐这一块能力。

## Scope Of Change

本 PR 主要包含：

- 后端新增 `MomentumScreenerService`
- 新增接口 `POST /api/v1/stocks/screener/momentum`
- 新增 `standard` / `aggressive` 双画像评分
- 新增 `/screener` 页面
- 新增复制、Markdown 导出、CSV 导出、单票明细导出
- 接入申万一级行业映射、缓存 TTL、健康检查诊断
- 接入系统配置默认值
- 增加真实 Tushare 发布检查脚本
- 增加 Playwright smoke
- 补齐产品、规则、发布相关文档

## Issue Link

No linked issue.

动机：

- 为短线次日筛选提供独立产品能力
- 形成可内测上线的完整前后端链路

验收标准：

- `/api/v1/stocks/screener/momentum` 可返回真实结果
- `/screener` 页面可完成筛选、排序、查看、复制、导出
- `standard` 与 `aggressive` 可切换
- 真实 Tushare 校验通过
- Playwright smoke 通过

## Verification Commands And Results

```bash
python -m pytest tests/test_momentum_screener_service.py -q
python -m pytest tests/test_momentum_screener_api.py -q
python -m pytest tests/test_system_config_api.py -q

npm test -- --run src/pages/__tests__/MomentumScreenerPage.test.tsx src/pages/__tests__/SettingsPage.test.tsx src/hooks/__tests__/useSystemConfig.test.tsx src/pages/__tests__/HomePage.test.tsx src/components/report/__tests__/ReportMarkdown.test.tsx src/components/layout/__tests__/SidebarNav.test.tsx
npm run build

python scripts/run_momentum_screener_release_check.py --profile standard --top-n 1
python scripts/run_momentum_screener_release_check.py --profile aggressive --top-n 3

npx playwright test e2e/momentum-screener.spec.ts --project=chromium
```

关键输出/结论：

- 后端测试通过
- 前端页面测试通过
- 前端构建通过
- 真实 Tushare 发布检查通过
- `/screener` Playwright smoke 通过
- 实盘校验日 `2026-04-09`
  - `standard` Top1: `002281.SZ 光迅科技`
  - `aggressive` Top1: `603507.SH 振江股份`

## Compatibility And Risk

兼容性影响：

- 新增接口和新页面，不破坏现有接口契约
- `/settings` 增加了 Momentum Screener 默认参数

潜在风险：

- 真实 Tushare 延迟可能导致筛选耗时波动
- 申万行业映射在部分股票上可能 fallback 到旧行业口径
- `aggressive` 画像本身风险高于 `standard`

## Rollback Plan

如果上线后需要回滚：

1. 回退这组 Momentum Screener 相关 commit
2. 或仅从前端导航隐藏 `/screener`，并停止暴露 `POST /api/v1/stocks/screener/momentum`
3. 如需保守处理，可先保留后端实现，仅移除页面入口

## EXTRACT_PROMPT Change (if applicable)

Not applicable.

## Checklist

- [x] 本 PR 有明确动机和业务价值
- [x] 已提供可复现的验证命令与结果
- [x] 已评估兼容性与风险
- [x] 已提供回滚方案
- [x] 已同步更新相关文档与 `docs/CHANGELOG.md`
```

## Related Docs

- [PR Summary](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pr-summary.md)
- [Final Release Summary](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-final-release-summary.md)
- [Launch Readiness](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-launch-readiness.md)
