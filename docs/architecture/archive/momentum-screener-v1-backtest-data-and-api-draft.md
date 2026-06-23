# 强势筛选 V1 回测数据表与接口草案
## 1. 文档信息

- 文档名称：强势筛选 V1 回测数据表与接口草案
- 英文名称：Momentum Screener V1 Backtest Data and API Draft
- 所属系统：`daily_stock_analysis`
- 文档类型：数据表草案 / 接口草案 / 实施约束
- 当前状态：`draft v1.0`
- 最后更新：`2026-04-16`
- 关联文档：
  - [强势筛选 V1 回测与问题诊断框架](./momentum-screener-v1-backtest-and-diagnosis-framework.md)
  - [强势筛选 V1 回测数据口径与结果面板设计](./momentum-screener-v1-backtest-metrics-and-dashboard.md)
  - [强势筛选 V1 产品原则 + 总闸门规则](./momentum-screener-v1-product-principles-and-gate-rules.md)
  - [强势筛选字段级实现映射表](./momentum-screener-field-mapping.md)

## 2. 文档目标

这份文档要解决的是：

- 回测数据最终准备落成哪些表
- 各表之间如何关联
- 对前端结果页至少要开放哪些接口
- V1 先做到哪里，哪些暂时不做

一句话总结：

**V1 先把回测存储结构和接口骨架定清楚，再进入开发实现。**

## 3. 设计原则

V1 回测数据层和接口层先遵守 6 条原则：

1. 先围绕 `Standard` 官方生产引擎落地
2. 统一使用 V1 固定入口基线：
   - 全市场
   - `4 / 2亿 / 2% + Top30`
3. 数据结构优先支持“问题诊断”，不是优先支持复杂收益模拟
4. 优先保留版本字段，避免后续口径漂移
5. 先支持只读查询和回测结果查看，不做在线调参
6. 先做“显式跑一轮”的任务型回测，不做复杂实时增量回放系统

## 4. V1 回测对象范围

V1 第一版固定回测以下对象：

- 候选池 Top10
- 二次决策官方 Top3
- 主仓 / 次仓 / 观察仓
- 今日出手级别
- 市场环境强 / 中 / 弱

V1 暂不做：

- Aggressive 独立官方回测结论
- 多持仓模拟器
- 仓位曲线回测
- 自动调参回测
- 研究模式参数网格搜索

## 5. 数据表设计

V1 建议最少落 5 张表。

## 5.1 `momentum_backtest_run`

用途：

- 记录一次完整回测任务的元信息
- 对应前端“一个回测结果集”

主键：

- `run_id`

建议字段：

- `run_id`
- `name`
- `status`
  - `pending`
  - `running`
  - `completed`
  - `failed`
- `started_at`
- `finished_at`
- `date_from`
- `date_to`
- `engine_profile`
- `engine_version`
- `entry_baseline_version`
- `market_scope_version`
- `real_strength_label_version`
- `strategy_health_mode`
  - `cached_only`
  - `strict_final`
- `sample_trade_days`
- `notes`
- `created_by`

说明：

- 这张表回答“这轮回测到底是在什么规则版本上跑出来的”。
- `strategy_health_mode` 用于区分：
  - `cached_only`：生产兼容口径，优先读缓存，允许 `proxy / partial / final`
  - `strict_final`：严格研究口径，逐日强制等待 20/60 历史窗跑完；若当日拿不到可用历史样本，日级结果记为 `failed`，不再回退到 `proxy`

## 5.2 `momentum_backtest_daily_summary`

用途：

- 记录每个交易日的总闸门结论和日级摘要

主键建议：

- `id`

唯一键建议：

- `run_id + trade_date`

建议字段：

- `id`
- `run_id`
- `trade_date`
- `market_regime`
- `market_environment_level`
- `opportunity_quality_level`
- `historical_validity_level`
- `action_level`
- `recommendation_cap`
- `checklist_mode`
- `buy_signal_permission`
- `candidate_count`
- `full_rank_count`
- `selected_count`
- `main_stock_code`
- `secondary_stock_code`
- `watch_stock_code`
- `benchmark_top3_profit_window_t1`
- `official_top3_profit_window_t1`
- `missed_opportunity_flag`
- `do_not_trade_correct_flag`
- `summary_score`

说明：

- 这张表是日级回放页和区间聚合页的核心来源。

## 5.3 `momentum_backtest_candidate_record`

用途：

- 记录某日进入候选池和完整排序集的股票样本

主键建议：

- `id`

唯一键建议：

- `run_id + trade_date + ts_code`

建议字段：

- `id`
- `run_id`
- `trade_date`
- `ts_code`
- `stock_name`
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
- `candidate_reasons_json`
- `risk_tags_json`

说明：

- 这张表用于回答：
  - 哪些票进了池
  - 排第几
  - 为什么被认为强

## 5.4 `momentum_backtest_decision_record`

用途：

- 记录二次决策如何从完整排序集收口成官方组合

主键建议：

- `id`

唯一键建议：

- `run_id + trade_date + ts_code`

建议字段：

- `id`
- `run_id`
- `trade_date`
- `ts_code`
- `decision_selected`
- `portfolio_slot`
  - `main`
  - `secondary`
  - `watch`
  - `none`
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
- `overextended_limit_pct`

说明：

- 这张表是问题归因里“排序问题 / 执行问题”的核心依据。

## 5.5 `momentum_backtest_outcome_record`

用途：

- 记录 T+1 / T+2 的真实结果和回填验证结果

主键建议：

- `id`

唯一键建议：

- `run_id + trade_date + ts_code`

建议字段：

- `id`
- `run_id`
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
- `t1_profit_window`
- `t2_profit_window`
- `max_drawdown_t1`
- `max_drawdown_t2`
- `buy_triggered`
- `trigger_timestamp_bucket`
- `triggered_price`
- `overextended_before_trigger`
- `real_strength_label`
- `real_strength_reason`

说明：

- 这张表用于把“系统判断”与“真实结果”接起来。

## 6. 表之间的关系

V1 关系建议如下：

- `momentum_backtest_run`
  - 1 对多
  - `momentum_backtest_daily_summary`
- `momentum_backtest_daily_summary`
  - 1 对多
  - `momentum_backtest_candidate_record`
- `momentum_backtest_daily_summary`
  - 1 对多
  - `momentum_backtest_decision_record`
- `momentum_backtest_decision_record`
  - 1 对 1 或 1 对多
  - `momentum_backtest_outcome_record`

其中真正统一串联全部结果的主键组合是：

- `run_id`
- `trade_date`
- `ts_code`

## 7. V1 推荐的数据写入时机

为了避免回测和生产逻辑打架，V1 建议分两段写入。

### 7.1 第一段：决策日写入

在回放 `T 日` 时写入：

- `run`
- `daily_summary`
- `candidate_record`
- `decision_record`

### 7.2 第二段：结果回填

等 `T+1 / T+2` 数据可用后，再补写：

- `outcome_record`
- `daily_summary` 中的结果摘要字段

这样做的好处是：

- 先冻结当时的系统结论
- 再补真实结果
- 更符合真实验证链路

## 8. 接口设计总览

V1 接口建议拆成 5 类：

1. 启动回测
2. 查询回测任务
3. 查询区间摘要
4. 查询日级明细
5. 查询问题诊断结果

## 9. 启动回测接口

建议接口：

- `POST /api/v1/stocks/screener/momentum/backtests`

用途：

- 创建并启动一轮回测任务

建议请求字段：

- `name`
- `date_from`
- `date_to`
- `engine_profile`
- `engine_version`
- `entry_baseline_version`
- `market_scope_version`
- `real_strength_label_version`
- `strict_strategy_health`
  - `false`：默认生产兼容口径
  - `true`：严格 20/60 回测口径

建议响应字段：

- `run_id`
- `status`
- `date_from`
- `date_to`
- `engine_profile`
- `engine_version`
- `strategy_health_mode`
- `strategy_health_mode_label`

V1 原则：

- 只允许跑固定生产基线
- 不开放自定义最小涨幅 / 成交额 / 换手率
- 严格 20/60 回测模式只切换“历史窗验证口径”，不改变候选池、排序、二次决策主链路

## 10. 回测任务详情接口

建议接口：

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}`

用途：

- 查看这轮回测的元信息和运行状态

建议响应字段：

- `run_id`
- `name`
- `status`
- `started_at`
- `finished_at`
- `sample_trade_days`
- `engine_profile`
- `engine_version`
- `entry_baseline_version`
- `market_scope_version`
- `real_strength_label_version`
- `strategy_health_mode`
- `strategy_health_mode_label`

## 11. 区间摘要接口

建议接口：

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/summary`

用途：

- 驱动顶部概览区和整体摘要卡片

建议响应分段：

### `summary`

- 总样本数
- 强 / 中 / 弱市样本数
- 官方组合胜率
- 劝退准确率
- 错杀率
- `strategy_health_validation_status_breakdown`
  - `final`
  - `failed`
  - 兼容口径下允许出现 `proxy / partial`
- `attack_permission_breakdown`
- `theme_confidence_breakdown`

### `benchmark_comparison`

- 官方 Top3 vs Top10
- 官方 Top3 vs 龙头基准
- 官方 Top3 vs 原始排序基准
- 官方 Top3 vs 空仓

### `layer_diagnostics`

- 候选池层
- 排序层
- 执行层
- 总闸门层
- 环境适配层

### 严格 20/60 模式补充约束

- `strict_final` 只用于研究和诊断，不面向默认页面主链路。
- 在该模式下，每个交易日都必须：
  1. 只使用该日之前的历史交易日样本
  2. 强制把 20 日 / 60 日窗口计算推进到 `final` 或 `failed`
  3. 禁止把 `failed` 日静默回退成 `proxy`
- 因此前端或报告在解读严格模式结果时，应把 `strategy_health_validation_status_breakdown` 视为一等指标：
  - `final` 越多，说明该区间内 20/60 逻辑被真实验证的覆盖度越高
  - `failed` 越多，说明该区间前段或数据链路仍存在样本缺口，不能把这部分日子和 `final` 混为一谈

## 12. 日级列表接口

建议接口：

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/daily`

用途：

- 驱动“日级回放区”

建议支持筛选参数：

- `date_from`
- `date_to`
- `market_regime`
- `action_level`
- `portfolio_slot`
- `theme_name`
- `page`
- `page_size`

建议每条记录返回：

- `trade_date`
- `market_regime`
- `action_level`
- `main_stock`
- `secondary_stock`
- `watch_stock`
- `selected_count`
- `official_top3_profit_window_t1`
- `missed_opportunity_flag`
- `do_not_trade_correct_flag`

## 13. 单日详情接口

建议接口：

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/daily/{trade_date}`

用途：

- 驱动单日详情页

建议响应结构：

### `daily_context`

- 市场环境结论
- 机会质量结论
- 历史有效性结论
- 今日出手级别

### `candidate_top10`

- 当日完整排序集 Top10
- 每只候选保留 `decision_diagnostics`，用于追溯二次决策为什么选/没选它
- `decision_diagnostics` 当前至少包含：规则底座分、解释修正分、`extension_signal_score`、`forward_alpha_score`、最终组合优先级、是否入选与入选槽位

### `decision_top3`

- 官方组合和每只票的理由

### `slot_view`

- 主仓 / 次仓 / 观察仓

### `outcomes`

- T+1 / T+2 验证结果

### `diagnosis`

- 这一天主要错在入口 / 排序 / 执行 / 总闸门 / 环境哪一层

## 14. 问题诊断接口

建议接口：

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/issues`

用途：

- 给页面“问题清单区”提供结构化问题结果

建议响应结构：

- `top_issues`
  - 问题标题
  - 问题层级
  - 影响范围
  - 证据指标
  - 建议优先级
- `regime_issues`
  - 强市问题
  - 中性市问题
  - 弱市问题
- `slot_issues`
  - 主仓问题
  - 次仓问题
  - 观察仓问题

V1 先不做自动修正规则，只做结构化问题输出。

## 15. 数据与接口的最小约束

V1 落地时建议加 5 条约束：

1. 所有回测接口必须返回版本字段
2. 所有日级接口必须带 `trade_date`
3. 所有个股级接口必须带 `ts_code`
4. 所有结果页指标都必须可追溯到日级记录
5. 所有“问题清单”都必须有对应证据指标，不能只给解释文案

## 16. V1 非目标

这份草案当前明确不覆盖：

- 参数实验接口
- 自定义候选池入口回测
- 自动进化控制接口
- 复杂仓位模拟接口
- 多账户或多用户权限模型

这些内容后续如需要，必须作为 V1.5 / V2 单独扩展。

## 17. 一句话版结论

如果只记这份文档的一句话，可以直接记：

**V1 回测系统要先落一套“run 级 + 日级 + 候选池级 + 决策级 + 结果级”的统一数据结构，并围绕摘要、日级回放、单日详情和问题清单四类接口提供查询能力。**

## 18. 任务中心新增字段与接口（2026-04-17 补充）

为支持串行队列、刷新进度、取消/删除和服务重启恢复，`momentum_backtest_runs` 需新增以下字段：

- `current_trade_date`
- `current_stage_key`
- `current_stage_label`
- `heartbeat_at`
- `started_at`
- `finished_at`
- `cancel_requested`

这些字段用于页面直接判断：

- 当前任务是否在排队还是在执行
- 当前卡在哪个交易日、哪个阶段
- 最近一次心跳是否仍在推进
- 是否已经收到取消请求

## 19. 任务列表接口升级

原 `GET /api/v1/stocks/screener/momentum/backtests` 从“扁平最近列表”升级为三段式任务中心响应：

- `current_running`
- `queued`
- `history`
- `refreshed_at`

其中：

- `queued.items` 按 FIFO 顺序返回
- `history.items` 默认只返回最近 `20` 条
- `history.total` 仍返回完整历史总数

## 20. 创建任务接口升级

`POST /api/v1/stocks/screener/momentum/backtests`

响应从单个 `run` 扩展为：

- `created_new`
- `message`
- `run`

这样前端可以明确区分：

- 本次是新建任务
- 还是复用了同参旧任务

### 20.1 启动脚本

仓库内提供了一个轻量启动脚本：

- [start_momentum_backtest_task.py](D:/AI_Project/_remote_edit/daily_stock_analysis/scripts/start_momentum_backtest_task.py)

用途：

- 直接向后端 `POST /api/v1/stocks/screener/momentum/backtests`
- 适合从本地命令行快速发起一条新的 V1 回测任务
- 只负责启动，不负责轮询监控

示例：

```bash
python scripts/start_momentum_backtest_task.py \
  --base-url http://163.7.12.193 \
  --start-trade-date 2026-01-19 \
  --end-trade-date 2026-04-21 \
  --strict-strategy-health
```

## 21. 新增任务操作接口

### 21.1 取消任务

- `POST /api/v1/stocks/screener/momentum/backtests/{run_id}/cancel`

约束：

- 仅 `running` 状态可取消
- 取消后保留已完成部分结果
- 最终状态写为 `cancelled`

### 21.2 删除任务

- `DELETE /api/v1/stocks/screener/momentum/backtests/{run_id}`

约束：

- `running` 状态不可直接删除，必须先取消
- `queued / completed / failed / cancelled` 允许删除
- 删除为硬删除，级联清理 run 关联冻结结果
