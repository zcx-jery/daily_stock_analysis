# 强势筛选（Momentum Screener）文档总览

## 项目定位

强势筛选是一个 **T 日收盘后，为 T+1 做准备的强势股筛选与二次决策系统**。它从全市场 A 股中选出当天最强势的候选股票，做主线识别和角色收口，输出 1-3 只次日该盯的票以及对应的执行建议。

## 文档导航

新开发者建议按以下顺序阅读，不要直接跳进架构目录。

### 第一步：功能概念（了解这个功能是什么）

| 文档 | 说明 |
|------|------|
| [使用说明书](../momentum-screener-user-guide.md) | 面向用户：参数怎么设、页面每个窗口在表达什么、每个字段是什么意思 |
| [执行逻辑说明](../momentum-screener-execution-logic.md) | 面向开发者/进阶用户：完整的数据流、评分链路、二次决策和盘中信号逻辑 |

### 第二步：产品定义（理解设计意图和约束）

> 以下文档位于 `docs/architecture/` 目录。

#### 核心 SPEC（产品原始约束 — 所有开发的真源）

| 文档 | 版本 | 说明 |
|------|------|------|
| [二次决策 SPEC](./momentum-screener-secondary-decision-spec.md) | draft v0.5 | 定义二次决策的职责边界、主线/角色/买点/总闸门的核心规则和禁止行为 |
| [时序质量评分 SPEC](./momentum-screener-temporal-quality-scoring-spec.md) | draft v0.1 | **新**：初次评分引入 K 线走势质量和题材时序动量两个维度，含精确公式和验收标准 |

#### 产品设计文档

| 文档 | 说明 |
|------|------|
| [V1 产品原则 + 总闸门规则](./momentum-screener-v1-product-principles-and-gate-rules.md) | 筛选入口规则、总闸门等级定义、进攻许可框架 |
| [V1.3 主线增强产品设计](./momentum-screener-v1-3-mainline-enhancement-product-design.md) | 6000 积分数据权限下的主线识别和情绪辅助方案 |
| [AI 点评增强 PRD](./momentum-screener-ai-commentary-prd.md) | AI 点评功能的完整产品需求 |
| [时序质量评分产品设计](./momentum-screener-temporal-quality-product-design.md) | **新**：两个新维度对用户可见行为的影响，与 V1.3 的关系 |

#### 评分规则文档

| 文档 | 说明 |
|------|------|
| [Standard 评分规则](./momentum-screener-v1-scoring-rules.md) | Standard 模式的六个维度评分细节（权重调整后以 SPEC 为准） |
| [Aggressive 评分规则](./momentum-screener-v1-aggressive-scoring-rules.md) | Aggressive 模式的评分维度，与 Standard 的差异 |
| [V1.3 评分升级方案](./momentum-screener-v1-3-profile-scoring-upgrade.md) | V1.3 对 Standard/Aggressive 评分公式的升级设计 |

### 第三步：技术实现（理解代码结构和架构决策）

| 文档 | 说明 |
|------|------|
| [二次决策技术开发文档](./momentum-screener-secondary-decision-technical-design.md) | 二次决策的数据流、缓存策略、模块拆分、API 契约 |
| [V1.3 主线增强技术开发文档](./momentum-screener-v1-3-mainline-enhancement-technical-design.md) | V1.3 的数据接入、题材强度/主线评分/情绪闸门的实现方案 |
| [AI 点评技术开发文档](./momentum-screener-ai-commentary-technical-design.md) | AI 点评的接口设计、prompt 管理、缓存策略 |

### 第四步：协作与交付

#### 开发任务清单

| 文档 | 说明 |
|------|------|
| [二次决策开发任务](./momentum-screener-secondary-decision-development-tasks.md) | 二次决策功能的拆分任务和验收点 |
| [V1.3 开发任务](./momentum-screener-v1-3-development-tasks.md) | V1.3 主线增强的实施顺序和阶段划分 |

#### 回测与验证

| 文档 | 说明 |
|------|------|
| [回测验收标准](./momentum-screener-backtest-acceptance-criteria.md) | 回测的通过标准、数据口径、异常判定规则 |
| [回测与诊断框架](./momentum-screener-v1-backtest-and-diagnosis-framework.md) | 回测整体框架、问题诊断方法 |
| [回测数据口径与面板](./momentum-screener-v1-backtest-metrics-and-dashboard.md) | 回测指标定义和结果面板设计 |

---

## 历史文档（仅保留用于追溯，不用于当前开发）

以下文档是在开发过程中生成的产物，已经被后续的 SPEC 或正式文档覆盖。**新开发者不需要读**，只在需要查历史决策原因时参考。

| 文档 | 被什么取代 |
|------|------|
| `momentum-screener-prd.md` | 二次决策 PRD + AI 点评 PRD |
| `momentum-screener-product-plan.md` | V1 产品原则 + 二次决策 SPEC |
| `momentum-screener-development-tasks.md` | 二次决策开发任务 + V1.3 开发任务 |
| `momentum-screener-secondary-score-rules.md` | V1 评分规则 + V1.3 评分升级方案 |
| `momentum-screener-v1-development-refactor-checklist.md` | V1.3 开发任务 |
| `momentum-screener-v1-backtest-development-tasks.md` | 回测验收标准 |
| `momentum-screener-v1-backtest-data-and-api-draft.md` | 回测数据口径与面板 |
| `momentum-screener-rule-profiles-comparison.md` | Aggressive 评分规则 |
| `momentum-screener-aggressive-secondary-score-rules.md` | Aggressive 评分规则 |
| `momentum-screener-new-gate-rules-draft.md` | 二次决策 SPEC（总闸门规则已并入） |
| `momentum-screener-field-mapping.md` | 字段定义已分散到各 SPEC |
| `momentum-screener-watchlist-summary-mvp-prd.md` | AI 点评 PRD |
| `momentum-screener-watchlist-summary-ai-review.md` | AI 点评 PRD |
| `momentum-screener-watchlist-summary-feishu-submission.md` | AI 点评 PRD |
| `momentum-screener-commit-scope.md` | PR 提交模板（仓库已有 `.github/PULL_REQUEST_TEMPLATE.md`） |

## 一次性报告（归档，不更新）

以下是在特定时间点生成的分析报告，仅作为历史记录保留。

| 文档 | 日期 | 说明 |
|------|------|------|
| `momentum-screener-functional-test-checklist.md` | 2026-04-11 | Beta 版本功能测试清单 |
| `momentum-screener-functional-test-report-2026-04-11.md` | 2026-04-11 | Beta 版本测试报告 |
| `momentum-screener-pressure-test-template.md` | 2026-04-11 | 压力测试模板 |
| `momentum-screener-pressure-test-report-2026-04-11.md` | 2026-04-11 | 压力测试报告 |
| `momentum-screener-internal-beta-notes.md` | 2026-04-11 | 内测说明 |
| `momentum-screener-launch-readiness.md` | 2026-04-11 | 上线检查清单 |
| `momentum-screener-pr-summary.md` | 2026-04-11 | PR 总结 |
| `momentum-screener-pr-body.md` | 2026-04-11 | PR 正文 |
| `momentum-screener-release-notes.md` | 2026-04-11 | 发版说明 |
| `momentum-screener-final-release-summary.md` | 2026-05-07 | V1.3 最终发版总结 |
| `momentum-main-slot-ranking-diagnosis-20260421.md` | 2026-04-21 | 主仓排序 P0 诊断 |
| `momentum-backtest-task-heartbeat-note.md` | 2026-04-22 | 回测任务心跳机制说明 |
| `momentum-backtest-60d-report-20260421.md` | 2026-04-21 | 60 交易日回测报告 |
| `momentum-strategy-health-strict-backtest-report-20260424.md` | 2026-04-24 | 20/60 窗口合理性诊断报告 |
| `momentum_bt_core60_focus_details_20260417.json` | 2026-04-17 | 回测原始数据 |
| `momentum_bt_core60_overview_20260417.json` | 2026-04-17 | 回测概览数据 |

## 建议的归档操作

以下文件可以移出 `docs/architecture/` 以减少噪音（建议移到 `docs/architecture/archive/` 或删除）：

1. 历史文档（16 个）：已被后续文档取代，新开发者不应阅读
2. 一次性报告（16 个）：仅作为历史归档，不参与当前开发

归档后 `architecture/` 下保留 ~20 个活跃文档（SPEC、产品设计、技术设计、评分规则、开发任务、回测标准）。