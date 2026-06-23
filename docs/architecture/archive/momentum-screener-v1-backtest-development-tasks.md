# 强势筛选 V1 回测开发任务清单
## 1. 文档信息

- 文档名称：强势筛选 V1 回测开发任务清单
- 英文名称：Momentum Screener V1 Backtest Development Tasks
- 所属系统：`daily_stock_analysis`
- 文档类型：开发任务清单 / 实施顺序清单
- 当前状态：`draft v1.0`
- 最后更新：`2026-04-16`
- 关联文档：
  - [强势筛选 V1 回测与问题诊断框架](./momentum-screener-v1-backtest-and-diagnosis-framework.md)
  - [强势筛选 V1 回测数据口径与结果面板设计](./momentum-screener-v1-backtest-metrics-and-dashboard.md)
  - [强势筛选 V1 回测数据表与接口草案](./momentum-screener-v1-backtest-data-and-api-draft.md)

## 2. 文档目标

这份清单把 V1 回测系统拆成可以直接进入研发排期的实施顺序。

重点回答 4 件事：

1. 先做哪些后端能力
2. 哪些数据表先落
3. 哪些接口先开放
4. 前端结果页按什么顺序推进

一句话总结：

**这份清单的目标不是继续讨论回测逻辑，而是把回测系统真正拆成开发任务。**

## 3. V1 回测系统总目标

V1 回测系统要做到：

1. 能对固定生产基线做交易日逐日回放
2. 能冻结候选池、二次决策和总闸门结论
3. 能回填 `T+1 / T+2` 真实结果
4. 能计算分层指标
5. 能输出问题诊断结果
6. 能在页面上展示摘要、分层诊断、市场分桶和日级明细

## 4. 实施原则

V1 回测开发优先遵守 6 条原则：

1. 先做后端记账和聚合，再做前端展示
2. 先支持 `Standard` 官方生产链路
3. 先做“手动触发一轮回测”，不先做复杂调度
4. 先支持摘要和诊断，再做漂亮图表
5. 先保证口径一致，再追求性能
6. 所有结果必须能追溯到日级记录

## 5. 总体实施顺序

推荐顺序如下：

1. 回测任务模型与数据表
2. 交易日回放引擎
3. 结果回填引擎
4. 指标聚合与问题诊断
5. 回测查询接口
6. 前端结果页
7. 回归与口径验证

## 6. M0：回测任务与数据表

优先级：`P0`

目标：

- 先把回测系统的数据骨架搭起来

任务：

### 后端数据表

- 建立：
  - `momentum_backtest_run`
  - `momentum_backtest_daily_summary`
  - `momentum_backtest_candidate_record`
  - `momentum_backtest_decision_record`
  - `momentum_backtest_outcome_record`

### 约束

- 冻结版本字段：
  - `engine_version`
  - `entry_baseline_version`
  - `market_scope_version`
  - `real_strength_label_version`
- 明确 `run_id + trade_date + ts_code` 为核心关联键

### 测试

- 表结构 smoke 测试
- 主键 / 唯一键约束测试

## 7. M1：交易日回放引擎

优先级：`P0`

目标：

- 能在固定区间内逐日重放强势筛选和二次决策

任务：

### 后端

- 逐日读取历史交易日
- 对每个 `T`：
  - 构建候选池
  - 形成完整排序集
  - 运行二次决策
  - 冻结日级结论
- 写入：
  - `daily_summary`
  - `candidate_record`
  - `decision_record`

### 约束

- 严格只使用 `T 日` 可见信息
- 不使用未来信息

### 测试

- 历史逐日回放 smoke 测试
- 候选池与二次决策冻结结果一致性测试

## 8. M2：T+1 / T+2 结果回填

优先级：`P0`

目标：

- 把系统结论与真实结果接起来

任务：

### 后端

- 对每个 `T 日` 官方组合股票：
  - 获取 `T+1 / T+2` 数据
  - 计算利润窗口
  - 计算最大回撤
  - 计算触发结果
  - 生成 `real_strength_label`
- 写入：
  - `outcome_record`
- 回填：
  - `daily_summary` 里的结果摘要字段

### 测试

- T+1 / T+2 回填口径测试
- 触发 / 未触发样本测试

## 9. M3：指标聚合层

优先级：`P0`

目标：

- 让回测结果从日级记录变成可读指标

任务：

### 后端

- 聚合候选池层指标：
  - `candidate_coverage_rate`
  - `leader_in_pool_rate`
  - `top10_hit_rate`
- 聚合排序层指标：
  - `top3_vs_top10_alpha`
  - `slot_win_rate_main`
  - `slot_win_rate_secondary`
  - `slot_win_rate_watch`
- 聚合执行层指标：
  - `buy_trigger_rate`
  - `buy_signal_win_rate_t1`
  - `buy_signal_win_rate_t2`
  - `profit_window_t1`
  - `profit_window_t2`
  - `max_drawdown_after_trigger`
- 聚合总闸门层指标：
  - `do_not_trade_precision`
  - `missed_opportunity_rate`
  - `allowed_trade_precision`
- 聚合环境适配指标：
  - `win_rate_bull_regime`
  - `win_rate_neutral_regime`
  - `win_rate_bear_regime`
  - `missed_rate_bull_regime`
  - `false_positive_rate_bear_regime`

### 测试

- 每个聚合指标的口径测试
- 小样本回放验证测试

## 10. M4：问题诊断层

优先级：`P1`

目标：

- 把指标自动收口成结构化问题清单

任务：

### 后端

- 识别：
  - 入口问题
  - 排序问题
  - 执行问题
  - 总闸门问题
  - 市场环境识别问题
- 生成：
  - `top_issues`
  - `regime_issues`
  - `slot_issues`

### 约束

- 每条问题必须带证据指标
- 不允许只输出解释文案而没有证据

### 测试

- 诊断逻辑单测
- 证据字段完整性测试

## 11. M5：回测接口层

优先级：`P1`

目标：

- 把回测结果分层开放成稳定查询接口

任务：

### 接口 1：启动回测

- `POST /api/v1/stocks/screener/momentum/backtests`

### 接口 2：任务详情

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}`

### 接口 3：区间摘要

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/summary`

### 接口 4：日级列表

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/daily`

### 接口 5：单日详情

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/daily/{trade_date}`

### 接口 6：问题清单

- `GET /api/v1/stocks/screener/momentum/backtests/{run_id}/issues`

### 测试

- API schema 测试
- 分页 / 过滤参数测试

## 12. M6：前端结果页

优先级：`P1`

目标：

- 给产品和研发一个可直接使用的回测结果页

任务：

### 页面区块

- 顶部概览区
- 比较基准区
- 分层诊断区
- 市场分桶区
- 日级回放区
- 问题清单区

### 单日详情页

- 市场环境
- 候选池 Top10
- 官方组合 Top3
- 槽位视图
- T+1 / T+2 验证结果
- 单日问题诊断

### 交互

- 支持按：
  - 日期区间
  - 市场分桶
  - 槽位
  - 总闸门级别
  - 主线
  - 版本
  进行过滤

### 测试

- 页面渲染 smoke
- 核心筛选交互测试

## 13. M7：联调与口径验证

优先级：`P1`

目标：

- 确保文档、后端、前端三层口径一致

任务：

### 联调

- 回测任务创建 -> 查询 -> 摘要 -> 日级 -> 单日 -> 问题清单
- 指标和页面字段对齐
- 版本字段对齐

### 口径验证

- 样本总数一致
- 主仓 / 次仓 / 观察仓胜率口径一致
- 强 / 中 / 弱市场分桶一致
- 错杀率 / 劝退准确率口径一致

## 14. 推荐实施节奏

### Sprint 1

- 数据表
- 回放引擎
- 结果回填

### Sprint 2

- 指标聚合
- 问题诊断
- 回测接口

### Sprint 3

- 前端结果页
- 单日详情
- 联调和回归

## 15. P0 / P1 / P2 优先级

### `P0`

- 数据表
- 回放引擎
- 结果回填
- 核心指标聚合

### `P1`

- 问题诊断
- 回测接口
- 前端结果页
- 联调与口径验证

### `P2`

- 更复杂的 challenger 对比页
- 更高级的图表与版本切换能力
- 自动化周期跑批和趋势面板

## 16. 一句话版结论

如果只记这份清单的一句话，可以直接记：

**V1 回测系统要先把“记账、回放、回填、聚合、诊断、查询”这六件事按顺序落下来，前端展示要建立在后端稳定结果之上。**
