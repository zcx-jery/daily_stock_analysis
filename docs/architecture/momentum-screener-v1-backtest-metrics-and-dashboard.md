# 强势筛选 V1 回测数据口径与结果面板设计
## 1. 文档信息

- 文档名称：强势筛选 V1 回测数据口径与结果面板设计
- 英文名称：Momentum Screener V1 Backtest Metrics and Dashboard Design
- 所属系统：`daily_stock_analysis`
- 文档类型：数据口径文档 / 指标定义文档 / 结果面板设计
- 当前状态：`draft v1.0`
- 最后更新：`2026-04-26`
- 关联文档：
  - [强势筛选 V1 回测验收标准](./momentum-screener-backtest-acceptance-criteria.md)
  - [强势筛选 V1 回测与问题诊断框架](./momentum-screener-v1-backtest-and-diagnosis-framework.md)
  - [强势筛选 V1 产品原则 + 总闸门规则](./momentum-screener-v1-product-principles-and-gate-rules.md)
  - [强势筛选二次决策 SPEC](./momentum-screener-secondary-decision-spec.md)
  - [强势筛选字段级实现映射表](./momentum-screener-field-mapping.md)

## 2. 文档目标

这份文档解决的是“回测框架已经定了，但具体要记哪些数据、怎么算指标、页面怎么展示”这三个落地问题。

目标是统一三件事：

1. 回测数据的记录口径
2. 回测指标的计算口径
3. 回测结果页 / 诊断页的展示口径

一句话总结：

**V1 先把回测的数据字典、指标字典和面板结构定死，再做开发实现。**

## 3. 数据记录粒度

V1 回测建议按 4 个粒度记账：

### 3.1 交易日级

每个交易日只保留一条总记录，用于描述这一天系统给出的总体结论。

建议字段：

- `trade_date`
- `engine_profile`
- `engine_version`
- `entry_baseline_version`
- `market_scope_version`
- `market_regime`
- `market_environment_level`
- `opportunity_quality_level`
- `historical_validity_level`
- `action_level`
- `recommendation_cap`
- `checklist_mode`
- `buy_signal_permission`

### 3.2 候选池级

记录当天所有进入候选池的股票，以及它们在完整排序集中的位置。

建议字段：

- `trade_date`
- `ts_code`
- `market_type`
- `theme_name`
- `in_candidate_pool`
- `full_rank_position`
- `in_top10`
- `in_top3`
- `rank_score`
- `continuation_score`
- `extension_score`
- `risk_score`
- `leader_level`

### 3.3 二次决策级

记录官方组合如何收口，以及每只票为什么被选中或被落下。

建议字段：

- `trade_date`
- `ts_code`
- `decision_selected`
- `portfolio_slot`
  - `main`
  - `secondary`
  - `watch`
- `portfolio_priority`
- `role_type`
- `decision_reason`
- `elimination_reason`
- `buy_point_status`
- `suggested_action`
- `entry_range_low`
- `entry_range_high`
- `trigger_condition`
- `invalidation_level`

### 3.4 结果验证级

记录 `T+1 / T+2` 的真实结果，用于回填回测表现。

V1.4 起，回测主胜率采用“短线延续合格”口径，而不是简单使用 `T+2` 收盘是否高于买点：

- `T+1 方向确认`：`T+1 收盘价 > T+1 开盘价`
- `T+2 卖出窗口`：`T+2 最高价 > T+1 收盘价`
- `短线延续合格`：以上两个条件同时满足

这个口径验证的是“`T` 日选出的强势股，在 `T+1` 买入后，`T+2` 是否给过继续冲高/卖出的窗口”。利润窗口和回撤继续保留，但只作为收益幅度与风险参考，不再单独定义核心胜率。

建议字段：

- `trade_date`
- `ts_code`
- `t1_open`
- `t1_high`
- `t1_low`
- `t1_close`
- `t2_open`
- `t2_high`
- `t2_low`
- `t2_close`
- `t1_red`
- `t1_direction_pass`
- `t2_continuation_pass`
- `weak_continuity_pass`
- `tradable_success_pass`
- `settlement_pass`
- `t1_profit_window`
- `t2_profit_window`
- `max_drawdown_t1`
- `max_drawdown_t2`
- `buy_triggered`
- `trigger_timestamp_bucket`
  - `pre_open`
  - `first_30m`
  - `first_60m`
  - `not_triggered`
- `triggered_price`
- `overextended_before_trigger`

## 4. 页面回测对象定义

为了保证产品和技术统一，V1 页面级回测对象固定为三类：

### 4.1 `candidate_top10`

当日完整排序集 Top10，用来衡量广义强势股样本。

### 4.2 `decision_top3`

二次决策最终输出的 1-3 只官方组合，用来衡量系统最终答案。

### 4.3 `slot_view`

按 `主仓 / 次仓 / 观察仓` 单独切开，用来衡量组合排序质量。

这样后面所有报表都围绕这三类对象展开，不再出现“有时看候选池、有时看全部结果、有时看页面 TopN”的口径漂移。

## 5. 指标计算口径

## 5.1 候选池层指标

### `candidate_coverage_rate`

定义：

- 全市场次日真正强势股中，被候选池覆盖的比例

口径：

- 分子：进入候选池且次日满足“真实强势判定”的股票数
- 分母：次日满足“真实强势判定”的股票总数

### `leader_in_pool_rate`

定义：

- 次日主线龙头进入候选池的比例

### `top10_hit_rate`

定义：

- 次日真正强势股进入完整排序集 Top10 的比例

## 5.2 排序层指标

### `top3_vs_top10_alpha`

定义：

- 官方 Top3 相对 Top10 平均表现的超额

公式：

- `Top3 平均利润窗口 - Top10 平均利润窗口`

### `slot_win_rate_main`

定义：

- 主仓在 T+1 / T+2 窗口中的胜率

### `slot_win_rate_secondary`

定义：

- 次仓在 T+1 / T+2 窗口中的胜率

### `slot_win_rate_watch`

定义：

- 观察仓在 T+1 / T+2 窗口中的胜率

V1 期望关系：

- `主仓 >= 次仓 >= 观察仓`

如果这个关系长期不成立，说明排序层有问题。

## 5.3 执行层指标

### `buy_trigger_rate`

定义：

- 系统给出的买点条件最终被触发的比例

公式：

- `触发样本数 / 给出明确买点样本数`

### `buy_signal_win_rate_t1`

定义：

- 触发后在 T+1 窗口中拿到正利润窗口的比例

### `buy_signal_win_rate_t2`

定义：

- 触发后满足“可交易合格”的比例：T+1 非一字不可买、`T+1 open >= T0 close * 0.99`、`T+1 close > T+1 open`，且 `(T+2 high + T+2 close) / 2 >= T+1 close * 1.02`

### `weak_continuity_rate`

定义：

- 辅助观察方向惯性的比例：`T+1 收盘价 > T+1 开盘价`，且 `T+2 最高价 > T+1 收盘价`

### `tradable_success_rate`

定义：

- V1.3 主验收比例：T+1 非一字不可买、未深低开、T+1 收阳，并且 T+2 滑点调整退出价给出至少 `2%` 利润缓冲

### `profit_window_t1`

定义：

- 触发后 T+1 内可取得的最大正收益窗口

### `profit_window_t2`

定义：

- 触发后 T+2 内可取得的最大正收益窗口

### `max_drawdown_after_trigger`

定义：

- 从触发点开始，到窗口结束期间的最大回撤

## 5.4 总闸门层指标

### `do_not_trade_precision`

定义：

- 系统判定“今日不做”时，市场确实不适合出手的比例

### `missed_opportunity_rate`

定义：

- 系统判定“仅观察 / 今日不做”，但当天实际存在高质量强势机会的比例

这是 V1 当前最关键的风险指标之一。

### `allowed_trade_precision`

定义：

- 系统判定“可做”时，次日盘中真的存在可执行机会的比例

## 5.5 环境适配层指标

### `win_rate_bull_regime`

定义：

- 强市分桶内官方组合胜率

### `win_rate_neutral_regime`

定义：

- 中性市分桶内官方组合胜率

### `win_rate_bear_regime`

定义：

- 弱市分桶内官方组合胜率

### `missed_rate_bull_regime`

定义：

- 强市下系统错杀机会的比例

### `false_positive_rate_bear_regime`

定义：

- 弱市下系统误放行机会的比例

## 6. “真实强势判定”统一口径

为了避免候选池层和结果层口径冲突，V1 需要先有一个统一的“真实强势判定”。

V1.4 起统一为两段式短线延续口径：

- `T+1` 收盘价必须大于 `T+1` 开盘价，证明第二天资金仍有推进意愿。
- `T+2` 最高价必须大于 `T+1` 收盘价，证明后天至少给过卖出/兑现窗口。

这不是完整交易收益模型，而是“方向是否选对”的主评价标准；`T+2 利润窗口`、`T+2 最大回撤`、`买点触发率` 继续作为执行质量与风险控制指标。

后续如果升级，也必须版本化，例如：

- `real_strength_label_v1`
- `real_strength_label_v2`

## 7. 结果面板总体结构

V1 回测结果页建议固定成 6 个区块。

### 7.1 顶部概览区

显示全局摘要卡片：

- 回测区间
- 使用版本
- 总样本数
- 强 / 中 / 弱市样本数
- 官方组合胜率
- 劝退准确率
- 错杀率

目标：

让用户 10 秒内知道这套系统整体是“偏有用、偏保守、还是明显失真”。

### 7.2 比较基准区

并排展示：

- 官方 Top3
- Top10 平均
- 主线龙头基准
- 原始排序基准
- 空仓基准

目标：

明确回答：

**二次决策到底有没有比更简单的做法更强。**

### 7.3 分层诊断区

按 5 层展示：

- 候选池
- 排序
- 买点
- 总闸门
- 环境适配

每层展示：

- 核心指标
- 当前评分
- 主要问题提示

目标：

一眼看出问题主要集中在哪一层。

### 7.4 市场分桶区

按：

- 强市
- 中性市
- 弱市

分别展示：

- 胜率
- 利润窗口
- 回撤
- 错杀率
- 劝退准确率

目标：

看系统是否只在某类市场失真。

### 7.5 日级回放区

按交易日列表展示：

- 当天总闸门结论
- 主仓 / 次仓 / 观察仓
- 次日实际表现
- 是否发生错杀或误放行

支持点击下钻到单日详情。

### 7.6 问题清单区

自动聚合最近回测中的高频问题，例如：

- 主仓经常不优于次仓
- 仅观察天数过多
- 强市下错杀明显偏高
- 买点触发率长期偏低

目标：

把回测结果从“报数”变成“可行动的问题清单”。

## 8. 单日详情页结构

V1 建议单日详情页固定展示 5 块：

1. 当日市场环境结论
2. 候选池与完整排序集 Top10
3. 二次决策官方组合
4. 买点与盘中收口
5. T+1 / T+2 验证结果

详情页的目的不是做复杂图表，而是让用户能追问：

- 这一天为什么系统这么判断
- 最后到底是哪里对了，哪里错了

## 9. 结果面板筛选器

V1 结果页建议先保留这些筛选器：

- 回测区间
- `engine_profile`
- `engine_version`
- 市场分桶
- 主题 / 主线
- 槽位
  - 主仓
  - 次仓
  - 观察仓
- 总闸门级别

这样后面可以快速回答：

- 强市里主仓到底准不准
- 弱市里系统是否真的敢劝退
- 哪条主线最容易被错判

## 10. 面板显示原则

V1 结果页必须遵守 4 条显示原则：

### 10.1 先结论后细节

先展示摘要和问题，再展示日级明细。

### 10.2 先对比再解释

每个核心指标都应尽量配对比基准，而不是单独报一个数字。

### 10.3 先问题定位再谈优化

页面优先回答“错在哪”，而不是直接给“怎么调”。

### 10.4 版本与口径必须显式可见

页面顶部必须显式展示：

- 候选池入口版本
- 市场范围版本
- 引擎版本
- 真实强势判定版本

避免后续口径漂移后，回看老结果时无法解释。

## 11. 最低可行接口输出建议

为了支撑结果页，V1 接口至少应输出 4 段：

### 11.1 `summary`

- 区间级汇总指标
- 必须同时给出 `tradable_success_rate` / `settlement_pass_rate`、`weak_continuity_rate` 以及拆分项：
  - `t1_direction_pass_rate`
  - `t2_continuation_pass_rate`
- 候选池 Top10 与官方 Top3 都要输出上述拆分，避免只看到最终合格率而无法判断瓶颈在可买性、T+1 方向、T+2 延续还是 2% 滑点退出缓冲。

### 11.2 `benchmark_comparison`

- 与 Top10 / Top3 / 龙头 / 空仓等基准的对比
- 基准项同样输出 `settlement_pass_rate_pct`、`t1_direction_pass_rate_pct`、`t2_continuation_pass_rate_pct`。

### 11.3 `layer_diagnostics`

- 五层诊断指标

### 11.4 `daily_records`

- 日级回放数据

如果只做第一页，优先做前三段；`daily_records` 可分页加载。

## 12. 面板对后续进化的作用

这套结果页不只是给人看，还要为后续“受控进化”提供证据。

它至少要支持三件事：

1. 发现系统最常出错的层
2. 对比 champion 与 challenger
3. 判断新版本到底是局部提升还是整体提升

一句话：

**没有统一的结果面板，系统就算做了回测，也很难真正进入可持续进化。**

## 13. 一句话版结论

如果只记这份文档的一句话，可以直接记：

**V1 回测页面不是收益展示页，而是“统一数据口径 + 统一指标口径 + 分层问题诊断”的决策验证面板。**
