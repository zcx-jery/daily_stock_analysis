# 强势筛选二次决策与执行辅助技术开发文档

## 1. 文档信息

- 文档名称：强势筛选二次决策与执行辅助技术开发文档
- 英文名称：Momentum Screener Secondary Decision Technical Design
- 所属系统：`daily_stock_analysis`
- 文档类型：技术开发文档 / 实现设计
- 当前状态：`draft v1.0`
- 最后更新：`2026-04-12`
- 关联文档：
  - [原始 SPEC](./momentum-screener-secondary-decision-spec.md)
  - [完整需求文档](./momentum-screener-secondary-decision-prd.md)
  - [开发任务清单](./momentum-screener-secondary-decision-development-tasks.md)
  - [字段映射文档](./momentum-screener-field-mapping.md)
  - [开发任务拆分](./momentum-screener-development-tasks.md)

## 2. 目标与范围

本技术文档用于把 `二次决策` 功能拆成可实现的后端规则、前端模块、状态机、字段结构和验收要求。

当前版本聚焦：

- T 日收盘后二次决策
- T+1 盘中买点信号辅助
- 主线识别、默认组合、低置信度、停用 / 恢复逻辑

不包含：

- 自动交易
- 完整卖出系统
- 高度参数化配置平台

## 3. 系统边界

### 3.1 上游输入

- 现有强势筛选候选池与排序结果
- `standard / aggressive` 两套底层 profile 输出
- 主线 / 板块映射数据
- 个股日线与分钟级 / 高频行情数据
- 历史验证样本与统计结果

### 3.2 下游输出

- 二次决策页面 JSON 载荷
- 主线区 / 默认组合 / 推荐卡片 / 证据区 / 行动清单数据
- T+1 盘中状态更新数据

## 4. 关键设计原则

- 核心判定采用 `规则驱动`
- AI 仅用于解释增强，不参与主决策
- 排序是系统正式判断结果，不开放用户手改
- 页面必须支持强结论与诚实降级并存
- 在盘中数据异常或信号冲突时，优先保护错误成本而非追求结论完整

## 5. 高层架构建议

建议新增一个二次决策聚合服务层，在现有 momentum screener 结果之上再做二次加工。

推荐分层：

1. `Candidate Ingestion Layer`
2. `Theme Identification Layer`
3. `Role Assignment Layer`
4. `Portfolio Ordering Layer`
5. `Buyability & Confidence Layer`
6. `Evidence Assembly Layer`
7. `Presentation Adapter Layer`

补充约束：
- 二次决策的真实输入源不是“当前页面展示的 TopN results”，而是“候选池完成全量评分后的完整排序集”。
- `top_n` 只控制页面展示、导出和列表截断，不得影响主线识别、角色分配、默认组合和落选说明。
- 标准链路应为：`候选池 -> 全量评分排序 -> 二次决策 -> 页面展示 TopN`。

## 6. 核心模块拆分

### 6.1 主线识别模块

职责：

- 从候选池中识别 `1-2 条主线`
- 计算主线综合评分
- 判定是否达到 `主线极强`

输入：

- 候选池股票
- 板块 / 行业映射
- 个股强势标签
- 板块内强势股分布
- 盘中 / 日内资金行为摘要

输出：

- `themes[]`
- 每条 theme 的：
  - `theme_id`
  - `theme_name`
  - `theme_score`
  - `is_extreme_theme`
  - `strong_stock_count`
  - `strong_stock_density`
  - `has_core_leader`
  - `has_front_turnover`
  - `money_support_status`

### 6.2 角色识别模块

职责：

- 为每条主线内个股标记角色：
  - `dragon_leader`
  - `front_turnover`
  - `watch_backup`

建议输出字段：

- `role_type`
- `role_score`
- `role_reason`
- `role_anchor_signals[]`

### 6.3 默认组合排序模块

职责：

- 从主线代表股中生成默认 `主仓 / 次仓 / 观察仓`

规则重点：

- `主仓` 优先取买点最清晰者
- `前排换手` 可因买点更清晰而压过 `龙头核心`
- `观察仓` 用于主线确认，不用于凑数
- 不足 3 只时允许留空

建议输出字段：

- `portfolio_slots[]`
- 每个 slot 包含：
  - `slot_type`: `primary / secondary / observe`
  - `stock_code`
  - `theme_id`
  - `role_type`
  - `slot_reason`
  - `actionability_status`

### 6.4 买点清晰判定模块

职责：

- 计算是否达到 `buyability_clear`
- 生成买入区与相关解释

建议字段：

- `is_buyability_clear`
- `best_buy_zone`
- `secondary_buy_zone`
- `buy_zone_width_pct`
- `buy_zone_anchor_type`
- `trigger_conditions[]`
- `chase_limit`
- `invalidation_level`

角色规则：

- `dragon_leader`：
  - 优先锚定盘中强承接位
  - 最优买入区宽度 `<= 2%`
- `front_turnover`：
  - 优先锚定分时均价线附近
  - 最优买入区宽度 `<= 3%`

### 6.5 价格偏离判定模块

职责：

- 判断当前价格是否已偏离可执行区

建议字段：

- `is_overextended`
- `overextended_reason`
- `expected_upside_pct`
- `expected_pullback_pct`
- `risk_reward_ratio`
- `do_not_chase`

角色规则：

- `dragon_leader`：
  - 当回踩承接位潜在跌幅 > 次日预期溢价时，判定偏离过大
- `front_turnover`：
  - `price_vs_vwap_pct > 3%`
  - 或 `remaining_upside_to_limit < potential_pullback * 1.5`

### 6.6 低置信度模块

职责：

- 判断排序与盘中实际走法是否冲突
- 控制是否允许继续输出明确买入信号

建议字段：

- `confidence_level`: `high / medium / low`
- `is_low_confidence`
- `confidence_drop_reason`
- `can_emit_buy_signal`
- `recovery_conditions[]`

主要触发条件：

- 主仓未接近预设买点
- 主仓竞价 / 开盘 / 承接明显低于预期
- 次仓 / 观察仓强度明显反超主仓
- 数据延迟或异常影响关键盘中判断

### 6.7 证据组装模块

职责：

- 汇总主线证据、当日推荐证据、历史相似案例

建议字段：

- `evidence.theme_validation`
- `evidence.today_reasoning`
- `evidence.similar_cases[]`
- `evidence.portfolio_validation`
- `evidence.role_validation`

历史案例字段建议：

- `case_id`
- `similarity_type`
- `entry_pattern_summary`
- `profit_window_1d`
- `profit_window_2d`
- `max_drawdown`
- `best_exit_hint`
- `conservative_exit_hint`

## 7. 状态机设计

### 7.1 今日出手级别状态机

建议枚举：

- `strong_action`
- `normal_action`
- `cautious_action`
- `observe_only`
- `no_action`

建议伴随字段：

- `action_level_reason`
- `action_level_blockers[]`

### 7.2 策略健康状态机

建议枚举：

- `healthy`
- `partial_healthy`
- `recovery_mode`
- `disabled`

输入条件：

- 20 日窗口
- 60 日窗口

映射关系：

- `20 ok + 60 ok` -> `healthy`
- `one ok / one weak` -> `partial_healthy` 或 `recovery_mode`
- `both weak` -> `disabled`

### 7.3 盘中执行状态机

建议枚举：

- `not_started`
- `watching_preopen`
- `watching_opening`
- `watching_first_hour`
- `buy_signal_ready`
- `do_not_buy`
- `low_confidence`

## 8. 页面数据模型建议

建议为 `二次决策` 页面输出单独 payload，而不是前端拼接多个旧接口。

建议顶层结构：

```json
{
  "trade_date": "2026-04-12",
  "action_level": {},
  "strategy_health": {},
  "themes": [],
  "portfolio": [],
  "candidates": [],
  "excluded_candidates": [],
  "evidence": {},
  "action_checklist": {},
  "intraday_signal": {}
}
```

### 8.1 action_level

```json
{
  "level": "normal_action",
  "label": "可正常出手",
  "reason": "主线够强，2 只票具备清晰买点",
  "blockers": []
}
```

### 8.2 strategy_health

当前实现说明：

- `strategy_health` 不再使用纯当前截面的代理分数，而是按当前这套筛选参数回放最近交易日。
- `short_window` 对应最近 20 个已完成验证样本，`long_window` 对应最近 60 个已完成验证样本。
- 每个历史样本会先生成当时的默认组合，再基于后续 1-2 个交易日的利润窗口、回撤和组合成功率判断窗口状态。
- 返回载荷除 `score` / `threshold` 外，还会包含 `sample_count`、`success_count`、`success_rate`、`avg_profit_window_pct`、`avg_max_drawdown_pct`、`avg_selected_count`。
- API 运行时默认启用 `strategy_health` 后台预热：若真实历史验证结果尚未缓存，则当前响应先返回代理健康度，同时在后台异步计算真实 20/60 日结果。
- 真实历史验证结果会同时写入进程内缓存与磁盘缓存；同一交易日、同一套筛选参数再次请求时优先命中缓存，避免重复跑 60 日回放。
- 前端通过 `data_source` 与 `is_warming` 区分“真实历史验证”与“代理预热中”两种状态，避免把首轮代理结果误认为最终验证结果。

```json
{
  "status": "recovery_mode",
  "label": "恢复中",
  "reason": "20 日窗口先恢复，但 60 日结构可信度还没完全修复，先降级到观察 / 少量推荐。",
  "recommendation_cap": "limited",
  "can_full_recommend": false,
  "data_source": "historical",
  "is_warming": false,
  "short_window": {
    "window": "short_20d",
    "window_label": "20 日当前可用性",
    "status": "healthy",
    "status_label": "健康",
    "score": 72.0,
    "threshold": 68.0,
    "sample_count": 20,
    "success_count": 14,
    "success_rate": 70.0,
    "avg_profit_window_pct": 2.6,
    "avg_max_drawdown_pct": 2.1,
    "avg_selected_count": 2.1,
    "summary": "20 日窗口当前可用性已达健康阈值，可继续支撑当前判断。"
  },
  "long_window": {
    "window": "long_60d",
    "window_label": "60 日结构可信度",
    "status": "recovering",
    "status_label": "恢复中",
    "score": 59.0,
    "threshold": 64.0,
    "sample_count": 60,
    "success_count": 35,
    "success_rate": 58.3,
    "avg_profit_window_pct": 1.9,
    "avg_max_drawdown_pct": 3.8,
    "avg_selected_count": 1.9,
    "summary": "60 日窗口开始修复，但还没恢复到完整强推荐状态。"
  },
  "blockers": [
    "60 日窗口结构可信度不足，当前更适合观察或少量推荐。"
  ],
  "recovery_conditions": [
    "60 日窗口需要恢复到主线、角色与组合结构重新稳定。"
  ]
}
```

### 8.3 action_checklist

```json
{
  "enabled": true,
  "reason": "当前出手级别为“可正常出手”，系统会补充明日行动清单，帮助你在次日 60 分钟内完成收口。",
  "steps": [
    {
      "phase": "pre_open",
      "phase_label": "开盘前",
      "objective": "先确认昨晚这套 1-3 票组合，今天是否还值得继续盯。",
      "focus_items": [
        "主仓：振江股份（电力设备 / 前排换手）",
        "次仓：长城电工（电力设备 / 龙头核心）"
      ],
      "tasks": [
        "先看主仓、次仓的竞价强弱，判断是否明显低于昨晚预期。",
        "观察仓只保留主线确认价值，不因为单票冲高就临时改顺序。"
      ],
      "expected_outcome": "明确开盘后先盯主仓、次仓，观察仓只保留辅助确认作用。"
    }
  ]
}
```

### 8.4 portfolio slot

```json
{
  "slot_type": "primary",
  "stock_code": "603507.SH",
  "stock_name": "振江股份",
  "theme_id": "theme_power_equipment",
  "role_type": "front_turnover",
  "slot_reason": "买点最清晰，适合作为主仓",
  "is_buyability_clear": true,
  "do_not_chase": false
}
```

### 8.5 intraday_signal

```json
{
  "confidence_level": "low",
  "can_emit_buy_signal": false,
  "status": "low_confidence",
  "reason": "昨晚主仓排序与早盘实际走法明显背离",
  "closing_note": "今天结论是不建议买入；主仓 / 次仓 / 观察仓仍按昨晚固定顺序跟踪。",
  "focus_order": [
    "优先关注：主仓 振江股份（继续等待触发）",
    "次选关注：次仓 长城电工（仅保留观察）"
  ],
  "watch_items": [
    "主仓仍未接近预设买点",
    "次仓分时强度明显反超主仓"
  ]
}
```

## 9. 后端实现建议

### 9.1 服务层

建议新增或扩展服务：

- `MomentumSecondaryDecisionService`
- `ThemeStrengthEvaluator`
- `PortfolioSlotAllocator`
- `BuyabilityEvaluator`
- `IntradayConfidenceEvaluator`
- `MomentumEvidenceAssembler`

### 9.2 API 层

建议新增接口：

- `POST /api/v1/stocks/screener/momentum/decision`
- `POST /api/v1/stocks/screener/momentum/decision/intraday`

可选：

- `POST /api/v1/stocks/screener/momentum/decision/refresh`

### 9.3 缓存与刷新

建议区分：

- 收盘后二次决策结果缓存
- 盘中信号短周期刷新缓存

盘中接口需考虑：

- 高频数据拉取频率
- 缓存 TTL
- 数据源异常回退

## 10. 前端实现建议

### 10.1 页面模块

建议拆分组件：

- `ActionLevelBanner`
- `ThemeRecognitionPanel`
- `PortfolioDecisionPanel`
- `DecisionStockCard`
- `ExcludedReasonList`
- `EvidencePanel`
- `SimilarCaseCard`
- `ActionChecklistPanel`
- `IntradaySignalBanner`

### 10.2 状态处理

前端必须区分：

- 正常推荐状态
- 观察状态
- 不建议执行状态
- 低置信度状态
- 策略停用状态

### 10.3 UX 重点

- 不自动跳详情页
- 不自动执行筛选
- 盘中信号默认手动刷新，不在静态结果返回后自动拉盘中数据
- 不在低置信度时继续显示强烈操作按钮
- 明确展示 `不建议追入`
- 明确展示 `还差哪些条件才会触发`

## 11. 数据质量与降级策略

### 11.1 数据依赖

核心依赖：

- 候选池结果
- 分钟级 / 高频行情
- 板块映射
- 历史验证统计

### 11.2 降级原则

- 数据不完整时，可进入 `低置信度`
- 低置信度时，不再输出明确建议买
- 盘中高频数据不可用时，可保留收盘后静态排序与观察信息

## 12. 日志与可观测性

建议记录以下诊断字段：

- 主线识别输入样本量
- 极强判定各分项结果
- 默认组合 slot 分配理由
- 买点清晰判定结果与区间宽度
- 低置信度触发原因
- 价格偏离判定结果
- 盘中恢复正常置信度的触发原因

## 13. 测试建议

### 13.1 单元测试

- 主线极强判定
- 买点清晰判定
- 价格偏离判定
- 低置信度触发 / 恢复
- 默认组合排序

### 13.2 集成测试

- 收盘后二次决策完整 payload
- 盘中信号接口返回状态变化
- 低置信度下不再输出 `建议买`
- 策略停用时页面数据降级

### 13.3 前端测试

- 五档出手级别渲染
- 推荐卡片内容顺序
- 落选主因显示
- 证据区顺序
- 停用 / 低置信度 / 不建议追入等状态文案

## 14. 验收建议

### 14.1 功能验收

- 能正确识别主线与默认组合
- 能按规则识别买点清晰与价格偏离过大
- 能在盘中触发低置信度并暂停明确买信号
- 能在策略停用时保留候选池但不再给强推荐

### 14.2 指标验收

- 策略统计指标达标
- 页面在 60 分钟内能收口为明确结论
- 关键状态切换有清晰 UI 表达

### 14.3 观察指标

- 用户在 60 分钟内明确做出 `买 / 不买` 的天数上升
- 用户在未触发买点时提前买入的次数下降

## 15. 开发拆分建议

推荐按以下顺序实施：

1. 收盘后二次决策静态结果
2. 主线极强 / 默认组合 / 落选解释
3. 证据区与历史相似案例
4. 盘中信号与低置信度
5. 策略停用 / 恢复状态
6. 全链路验收与回测校验
