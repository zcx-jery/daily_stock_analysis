# 强势筛选二次决策与执行辅助技术开发文档

## 1. 文档信息

- 文档名称：强势筛选二次决策与执行辅助技术开发文档
- 英文名称：Momentum Screener Secondary Decision Technical Design
- 所属系统：`daily_stock_analysis`
- 文档类型：技术开发文档 / 实现设计
- 当前状态：`draft v1.2`
- 最后更新：`2026-04-23`
- 关联文档：
  - [原始 SPEC](./momentum-screener-secondary-decision-spec.md)
  - [完整需求文档](./momentum-screener-secondary-decision-prd.md)
  - [新总闸门产品规则草案](./momentum-screener-new-gate-rules-draft.md)
  - [开发任务清单](./momentum-screener-secondary-decision-development-tasks.md)
  - [字段映射文档](./momentum-screener-field-mapping.md)

## 2. 目标与范围

本技术文档用于把 `二次决策` 功能拆成可实现的后端规则、前端模块、状态机、字段结构和验收要求。

当前版本聚焦：

- T 日收盘后二次决策
- T+1 盘中买点信号辅助
- 主线识别、默认组合、低置信度、停用 / 恢复逻辑
- 新总闸门：
  - `20日进攻许可`
  - `60日主线可信度`
  - `市场环境`
  - `机会质量`
- V1 官方入口与回测基线：
  - 候选池入口固定为 `最小涨幅 4% / 最小成交额 2亿 / 最小换手率 2%`
  - 页面官方展示固定为 `Top30`
  - 官方回测只回放 `Standard` 官方链路
  - `Aggressive` 仅作为折叠式进攻补充观察层

不包含：

- 自动交易
- 完整卖出系统
- 高度参数化配置平台

## 3. 系统边界

### 3.1 上游输入

- 现有强势筛选候选池与全量排序结果
- `Standard` 官方主引擎输出
- `Aggressive` 进攻补充观察层输出
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
- V1 生产入口不再开放 `TopN`、最小涨幅、最小成交额、最小换手率或 profile 作为用户可调项
- 页面必须支持强结论与诚实降级并存
- 在盘中数据异常或信号冲突时，优先保护错误成本而非追求结论完整
- 用户侧移除“策略健康”旧词，统一改为：
  - `20日进攻许可`
  - `60日主线可信度`

## 5. 高层架构建议

建议继续使用一个二次决策聚合服务层，在现有 momentum screener 结果之上做二次加工。

推荐分层：

1. `Candidate Ingestion Layer`
2. `Theme Identification Layer`
3. `Role Assignment Layer`
4. `Portfolio Ordering Layer`
5. `Gate Evaluation Layer`
6. `Evidence Assembly Layer`
7. `Presentation Adapter Layer`

补充约束：

- 二次决策的真实输入源不是“当前页面展示的 Top30 results”，而是“候选池完成全量评分后的完整排序集”。
- `top_n` 在 V1 生产链路固定为 `30`，只控制页面展示、导出和列表截断，不得影响主线识别、角色分配、默认组合和落选说明。
- 标准链路应为：
  - `全市场统一入口 -> 候选池 -> 全量评分排序 -> Standard 二次决策 -> 页面展示 Top30`

### 5.0.1 二次决策收口层边界（2026-04-27 冻结）

技术上，二次决策必须从“重排层”调整为“收口层”。

明确分层如下：

1. **主排序层**
   - 输入：初筛后的全部候选股票
   - 输出：正式 `rank / rank_score / final_score`
   - 职责：回答“谁更强”

2. **二次决策层**
   - 输入：完整正式排序集
   - 输出：`主仓 / 次仓 / 观察仓`、动作级别、执行提示、落选说明
   - 职责：回答“今天怎么用这份排序”

因此，二次决策层禁止：

- 重建一套与主排序平行的正式排序分
- 仅基于页面 `Top30` 或局部子集继续重排官方结果
- 让角色、买点、解释因子大幅推翻正式主排序

允许的修正只分两类：

- `hard_blockers`：硬阻断，阻止某只股票进入主仓或正式执行
- `soft_adjustments`：小幅修正，只影响仓位收口，不推翻谁更强

推荐链路调整为：

```text
完整正式排序集
-> 决策候选池裁剪（如 Top8/Top12）
-> 硬阻断判断
-> 槽位选择（主仓 / 次仓 / 观察仓）
-> 动作闸门修正
-> 执行与解释输出
```

### 5.1 V1 官方入口基线

后端必须把官方入口基线固化为服务端口径，前端只展示不允许普通用户修改：

- `min_change_pct = 4.0`
- `min_amount = 200000000`
- `min_turnover = 2.0`
- `exclude_st = true`
- `main_board_only = false`
- 市场范围固定为 `主板 + 创业板 + 科创板`
- 页面展示数量固定为 `top_n = 30`

兼容旧客户端时可以继续接受旧字段，但官方生产链路必须在服务端归一化为上述值。

## 6. 核心模块拆分

### 6.1 主线识别模块

职责：

- 从候选池中识别 `1-2` 条主线
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
- 每条 `theme` 的：
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

- 从完整正式排序集里收口生成默认 `主仓 / 次仓 / 观察仓`

规则重点：

- `主仓` 默认取正式主排序中的第一优先票
- 只有命中 `hard_blockers` 时，主仓候选才允许降级
- `次仓` 与 `观察仓` 负责组合补强，不重新定义谁更强
- `soft_adjustments` 只允许做小幅槽位修正
- `观察仓` 用于主线确认，不用于凑数
- 不足 `3` 只时允许留空

建议输出字段：

- `portfolio_slots[]`
- 每个 slot 包含：
  - `slot_type`: `primary / secondary / observe`
  - `base_rank`
  - `base_rank_score`
  - `decision_adjustment`
  - `decision_adjustment_reason`
  - `stock_code`
  - `theme_id`
  - `role_type`
  - `slot_reason`
  - `actionability_status`

建议新增内部结构：

- `decision_candidate_pool[]`
  - 来自完整排序集的前排裁剪样本，建议 `Top8 ~ Top12`
- `hard_blockers[]`
  - 如 `buy_point_unclear / action_gate_blocked / duplicate_role_conflict / risk_redline`
- `soft_adjustments[]`
  - 如 `slot_fit_bonus / diversification_bonus / execution_clarity_bonus`

约束：

- `decision_adjustment` 不得重写正式 `base_rank_score`
- 若某只股票从 `base_rank=1` 降级，必须携带明确 `hard_blocker_reason`
- 解释字段必须能区分“强度不足落选”与“组合收口落选”

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

- `dragon_leader`
  - 优先锚定盘中强承接位
  - 最优买入区宽度 `<= 2%`
- `front_turnover`
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

- `dragon_leader`
  - 当回踩承接位潜在跌幅 > 次日预期溢价时，判定偏离过大
- `front_turnover`
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

## 7. 新总闸门实现设计

### 7.1 核心思路

新总闸门不再把“最近还能不能用”“这套主线值不值得信”“今天该不该做”混进一个总词。

技术上需要拆成四个独立计算模块：

1. `twenty_day_attack_permission`
2. `sixty_day_theme_confidence`
3. `market_environment`
4. `opportunity_quality`

最终输出：

- `action_level`
- `action_level_reason`
- `twenty_day_attack_permission_card`
- `sixty_day_theme_confidence_card`
- `risk_banner`（可选）

### 7.2 20日进攻许可模块

目标：

- 评估“最近还能不能正常进攻”

输入：

- 最近 20 交易日历史样本
- 每日推荐组合
- 买点触发结果
- 触发后利润窗口结果

建议输出字段：

- `attack_permission_score`
- `attack_permission_status`
- `valid_sample_count`
- `triggered_sample_count`
- `hit_sample_count`
- `hit_rate`
- `explanation`

状态词固定为：

- `attack_open` -> 用户侧映射 `可进攻`
- `attack_recovering` -> 用户侧映射 `恢复中`
- `attack_paused` -> 用户侧映射 `暂停进攻`

状态规则：

- `attack_open`
  - `valid_sample_count >= 5`
  - 且 `hit_rate >= 55%`
- `attack_recovering`
  - `valid_sample_count >= 3`
  - 且 `hit_rate >= 40%`
- 其他情况：
  - `attack_paused`

组合整体表现只作为：

- 分数微调
- 文案解释补充

不直接改变主状态。

### 7.3 60日主线可信度模块

目标：

- 评估“主线识别框架最近值不值得信”

输入：

- 最近 60 交易日历史样本
- 每日第一主线
- 次日最强核心票
- 次日强票 `Top3 / Top5`

建议输出字段：

- `theme_confidence_score`
- `theme_confidence_status`
- `valid_sample_count`
- `average_daily_score`
- `core_hit_rate`
- `top3_coverage_rate`
- `top5_bonus_rate`
- `explanation`

状态词固定为：

- `credible` -> 用户侧映射 `可信`
- `recovering` -> 用户侧映射 `恢复中`
- `questionable` -> 用户侧映射 `存疑`

单日评分：

- 次日最强核心票落在第一主线：`0.6`
- 第一主线覆盖次日强票 `Top3` 至少 `2` 只：`0.4`
- 第一主线覆盖次日强票 `Top5` 至少 `3` 只：额外 `+0.1`
- 单日封顶：`1.0`

状态规则：

- `credible`
  - `valid_sample_count >= 12`
  - 且 `average_daily_score >= 0.60`
- `recovering`
  - `valid_sample_count >= 8`
  - 且 `average_daily_score >= 0.45`
- 其他情况：
  - `questionable`

### 7.4 市场环境模块

目标：

- 评估“市场今天愿不愿意继续为强势股付溢价”

输入：

- 昨日二次决策 `Top3`
- 昨日候选池 `Top10`
- 次日买点触发结果
- 次日利润窗口结果

建议输出字段：

- `market_environment_level`
- `has_core_premium`
- `breadth_hit_rate`
- `breadth_avg_profit_window`
- `explanation`

判定规则：

- `has_core_premium = true`
  - 昨日 `Top3` 中至少 `1` 只先满足买点触发
  - 且 `T+1/T+2 profit_window >= 2.0%`
- `breadth_ok = true`
  - 昨日 `Top10` 命中率 `>= 30%`
  - 且平均利润窗口 `>= 2.0%`

三档：

- `strong`
  - 核心有溢价 + 广度达标
- `medium`
  - 只好一边
- `weak`
  - 两边都不行

### 7.5 机会质量模块

目标：

- 评估“今天系统手上的这批票是否足够适合出手”

输入：

- 默认组合
- 买点清晰状态
- 主仓盈亏比
- 组合内主线归属

建议输出字段：

- `opportunity_quality_level`
- `clear_buy_count`
- `main_slot_rr_ratio`
- `theme_concentration_ok`
- `explanation`

#### 7.5.1 买点清晰度

- `3 clear = strong`
- `2 clear = upper_mid`
- `1 clear = mid`
- `0 clear = weak`

#### 7.5.2 主仓盈亏比

主仓最低门槛：

- `expected_profit_space / expected_invalidation_space >= 1.5`

#### 7.5.3 主线集中度

- 默认组合中至少 `2` 只来自同一主题，视为 `theme_concentration_ok = true`
- 若该主题与雷达第一主线不完全一致，可在 `V1.3 diagnostics` 中继续作为 off-mainline 偏差单独提示，但不再直接把机会质量降成“未集中”。

#### 7.5.4 合成规则

- `3 clear`
  - 默认 `strong`
  - 仅在主仓盈亏比不过线时下调
- `2 clear`
  - 默认 `upper_mid`
  - 仅在“主仓盈亏比过线 + 主线集中度达标”时上调到 `strong`
- `1 clear`
  - 默认 `mid`
  - 主仓盈亏比过线则维持 `mid`
  - 不过线则降为 `weak`
- `0 clear`
  - 固定 `weak`
  - 不允许抬高

### 7.6 今日出手级别主矩阵

先由 `market_environment × opportunity_quality` 得到基础 `action_level`：

| market_environment | opportunity_quality | action_level |
| --- | --- | --- |
| `strong` | `strong` | `strong_go` |
| `strong` | `upper_mid` | `normal_go` |
| `strong` | `mid` | `cautious_go` |
| `strong` | `weak` | `observe_only` |
| `medium` | `strong` | `normal_go` |
| `medium` | `upper_mid` | `cautious_go` |
| `medium` | `mid` | `observe_only` |
| `medium` | `weak` | `no_action` |
| `weak` | `strong` | `cautious_go` |
| `weak` | `upper_mid` | `observe_only` |
| `weak` | `mid` | `no_action` |
| `weak` | `weak` | `no_action` |

### 7.7 20日进攻许可封顶规则

再由 `20日进攻许可` 封顶：

- `attack_open`
  - 不压级
- `attack_recovering`
  - 最高封顶到 `normal_go`
- `attack_paused`
  - 若基础主矩阵是 `strong_go`，则只能降到 `cautious_go`
  - 若基础主矩阵落在“只强一边”的中间状态，则最高 `observe_only`
  - 若基础主矩阵本就偏弱，则 `no_action`

### 7.8 停用与恢复

建议输出字段：

- `system_disabled`
- `disabled_streak`
- `disable_reason`
- `can_exit_disabled`
- `recovery_stage`

规则：

- `system_disabled = true`
  - 当连续 `5` 个交易日
  - `attack_permission_status = attack_paused`
  - 且 `theme_confidence_status = questionable`
- 退出停用：
  - `attack_permission_status` 回到 `attack_recovering`
  - 且 `market_environment != weak`
- 退出停用后，只允许：
  - `observe_only`
  - 或最多 `cautious_go`

## 8. Aggressive 进攻补充观察层实现设计

### 8.1 技术定位

`Aggressive` 不再作为与 `Standard` 并列的官方 profile。技术上仍可复用 aggressive 评分器生成候选，但它只进入补充观察层，不参与：

- 官方 `action_level`
- 官方 `主仓 / 次仓 / 观察仓`
- 官方行动清单
- 官方回测胜率口径

### 8.2 输入与过滤

补充层输入来自同一交易日、同一官方入口基线下的 `Aggressive` 排序结果。进入展示前必须过滤：

1. 不得与 `Standard` 官方 Top3 重复
2. 必须满足 `高进攻度`
3. 买点允许比 `Standard` 宽半档，但必须已有买入区间和触发条件
4. 不得触发风险红线

高进攻度定义：

- 弹性分或进攻特征靠前
- 在主线里不是边缘票
- 风险不过红线

风险红线定义：

- 明显追高
- 没有买点区间
- 已接近失效位

### 8.3 输出与排序

补充层最多输出 `2` 只新增补充票，排序采用 `进攻弹性` 优先。每张补充观察卡至少包含：

- 进攻理由
- 主线角色
- 买点区间
- 触发条件
- 失效位
- `仅补充观察，不纳入官方组合` 标记

当 `Standard` 为 `仅观察` 或 `今日不做` 时，补充层仍可保留折叠入口，但必须提示：

`有进攻补充观察机会，但不改变官方结论`

### 8.4 治理与诊断

官方复盘仍只计算 `Standard`。`Aggressive` 只保留补充命中诊断，核心指标为 `supplement_gain_rate`。

`supplement_gain_rate` 定义为：

- `Aggressive` 补充票不在 `Standard` 官方 Top3 中
- 且后续表现优于 `Standard` 观察仓或未入选边界票

内部治理状态：

- `normal`
- `calibration_required`
- `observing_recovery`
- `fully_recovered`

用户侧简化状态：

- `正常`
- `增益有限`
- `恢复中`

降级阈值：

- `20日补充增益率 < 20%`
- 且 `60日补充增益率 < 25%`
- 进入 `calibration_required`

恢复阈值：

- `20日补充增益率 >= 25%` 进入 `observing_recovery`
- `60日补充增益率 >= 30%` 进入 `fully_recovered`

`增益有限` 用户侧解释固定为：

`当前进攻补充层近期有效增益偏少，仅保留观察参考。`

## 9. V1 官方回测基线

官方回测只回答一个问题：`Standard 官方生产链路是否有效`。

因此 V1 回测实现必须统一为：

- `profile = standard`
- `top_n = 30`
- `min_change_pct = 4.0`
- `min_amount = 200000000`
- `min_turnover = 2.0`
- 市场范围：`主板 + 创业板 + 科创板`

兼容旧任务数据时可以继续读取历史 `profile` 字段，但新建任务必须归一化为 `standard`。如果后续需要评估 `Aggressive`，应作为补充诊断指标，而不是第二套官方回测 run。

## 10. 状态机设计

### 8.1 今日出手级别状态机

建议枚举：

- `strong_go`
- `normal_go`
- `cautious_go`
- `observe_only`
- `no_action`

建议伴随字段：

- `action_level_reason`
- `matrix_reason`
- `attack_permission_cap_applied`

### 8.2 盘中状态机

单票建议状态：

- `triggered`
- `near_trigger`
- `not_triggered`
- `trigger_failed`
- `overextended`
- `observe_only`

整页收口状态：

- `buy_recommended`
- `primary_only_consider`
- `observe_but_do_not_execute`
- `do_not_buy`

### 8.3 风险提示状态

建议补充页面风险提示条状态：

- `none`
- `sixty_day_questionable_warning`
- `low_confidence_warning`
- `system_disabled_warning`

其中：

- 若 `action_level` 仍可做，但 `theme_confidence_status = questionable`
  - 输出 `sixty_day_questionable_warning`

## 11. API 载荷建议

### 11.1 顶层结构补充

建议在二次决策响应顶层增加：

- `action_level`
- `action_level_reason`
- `market_environment`
- `opportunity_quality`
- `attack_permission_card`
- `theme_confidence_card`
- `risk_banner`
- `system_disable_state`

### 11.2 attack_permission_card

建议字段：

- `title`: `20日进攻许可`
- `score`
- `status`
- `summary`
- `valid_sample_count`
- `hit_rate`
- `role_thresholds`

### 11.3 theme_confidence_card

建议字段：

- `title`: `60日主线可信度`
- `score`
- `status`
- `summary`
- `valid_sample_count`
- `average_daily_score`
- `core_hit_rate`
- `top3_coverage_rate`

### 11.4 risk_banner

建议字段：

- `type`
- `title`
- `message`

示例场景：

- `60日主线可信度 = 存疑`，但当天仍可做
- 盘中进入低置信度
- 系统进入停用或恢复期

## 12. 前端实现建议

### 12.1 页面改名与文案替换

- 用户侧彻底移除“策略健康”
- 用户侧不再提供 `TopN`、入口阈值或 `Standard / Aggressive` 并列切换控件
- 官方入口基线只作为说明卡展示：`4% / 2亿 / 2% / Top30`
- 所有原有依赖 `strategy_health` 展示文案的区域，改为：
  - `20日进攻许可`
  - `60日主线可信度`

### 12.2 顶部区块

顶部展示：

- 今日出手级别
- 今日一句理由
- 两张卡摘要
- 风险提示条（如有）

### 12.3 双卡布局

两张卡统一格式：

- 一句结论
- 分数和状态
- 一句解释
- 展开后可查看样本数与关键指标

### 12.4 风险提示条

若当天仍可做，但 `60日主线可信度 = 存疑`：

- 用黄色提示条展示
- 不下调动作级别

### 12.5 Aggressive 折叠区

`Aggressive` 不在顶部与 `Standard` 并列。页面应放入折叠区：

- 默认折叠
- 只有补出新增高进攻票时提示可展开
- 最多展示 `2` 只
- 每张卡标注 `仅补充观察，不纳入官方组合`
- 当官方结论为 `仅观察 / 今日不做` 时，提示 `有进攻补充观察机会，但不改变官方结论`

### 12.6 向后兼容

若后端仍短期返回旧字段：

- 前端应优先适配新字段
- 旧字段仅作为兼容 fallback
- 用户侧文案不再显示旧术语

## 13. 验收重点

- `今日出手级别` 是否先由 `市场环境 × 机会质量` 计算，再被 `20日进攻许可` 正确封顶
- `60日主线可信度` 是否只做提示，不再直接压同日动作
- 页面是否彻底移除“策略健康”旧词
- `60日主线可信度 = 存疑` 时，是否出现黄色风险提示条
- `系统停用` 是否只在连续 `5` 个交易日 `20日暂停进攻 + 60日存疑` 时触发
- `0只清晰` 的机会质量是否始终为 `弱`
- `20日进攻许可 = 暂停进攻` 时，是否仍允许在“强环境 + 强机会”下给出 `谨慎出手`
