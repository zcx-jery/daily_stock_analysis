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
8. `Backtest Fill-back Layer`

补充约束：

- 二次决策的真实输入源不是“当前页面展示的 Top30 results”，而是“候选池完成全量评分后的完整排序集”。
- `top_n` 在 V1 生产链路固定为 `30`，只控制页面展示、导出和列表截断，不得影响主线识别、角色分配、默认组合和落选说明。
- 标准链路应为：
  - `全市场统一入口 -> 候选池 -> 全量评分排序 -> Standard 二次决策 -> 页面展示 Top30`

### 5.0.1 Backtest Fill-back Service Layer

`momentum_backtest_service.py` 在 T 日冻结候选池与 Standard 官方组合后，使用后续日线做固定的 `T+1/T+2` 回填，并同时产出双层指标。

- 回填窗口：`evaluation_t1_bar = bars[0]`，`evaluation_t2_bar = bars[1]`，始终相对 T 日固定，不随买点触发日漂移。
- 辅助层：`weak_continuity_pass = (T+1 close > T+1 open) AND (T+2 high > T+1 close)`。
- 主验收层：`settlement_rule = v13_tradable_success_v1`，`settlement_pass` 等同于 `tradable_success_pass`。
- Buyability：`T+1` 不能是一字板，代码使用 `open/high/low/close` 四价相等判断 `t1_one_word_limit`。
- Gap_Filter：`T+1 open >= T0 close * 0.99`。
- Confirmation：`T+1 close > T+1 open`。
- Profit_Buffer：`T+2 high >= T1 close * 1.025`，即至少 `2.5%` 退出缓冲。
- 汇总字段：`weak_continuity_pass_rate_pct` 单独展示弱延续率，`tradable_success_rate_pct` 是 V1.3 主验收胜率；`positive_t2_rate_pct` 与 `settlement_pass_rate_pct` 在新结果中保持兼容映射到可交易合格率。

### 5.0.2 二次决策收口层边界（2026-04-27 冻结）

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
  - 如 `slot_fit_bonus / diversification_bonus / execution_clarity_bonus / t1_direction_risk_drag`

约束：

- `decision_adjustment` 不得重写正式 `base_rank_score`
- 若某只股票从 `base_rank=1` 降级，必须携带明确 `hard_blocker_reason`
- 解释字段必须能区分“强度不足落选”与“组合收口落选”
- T 日已可见的重风险 `T+1` 承接信号不得只留在解释层；若会显著削弱次日执行清晰度，应进入 `soft_adjustments` 或 `hard_blockers`
- 若当前主仓是高进攻但高风险的 `front`，且同主题已有 `leader + clear` 候选且正式排序未明显落后，允许主仓向更稳的主线锚点回摆
- 若当前主仓是 `front + waiting`，且同主题 `leader + clear` 只在正式排序上小幅落后、但执行清晰度更高，可优先让清晰龙头承担主仓职责；若 `front` 的 forward alpha 明显更强，则继续保留高进攻主仓
- 若默认组合里的次仓 / 观察仓存在更稳的 `leader + clear` 候选，且与高风险 `front` 的正式优先级差距不大，允许整组收口继续向低 `T+1` 风险方向倾斜
- 若默认组合内已有跨主题但明显更稳的执行锚点，可在不重写正式排序的前提下，把主仓职责回摆给更适合作为组合锚点的标的
- 观察仓不只承担“同主题补位”职责；若存在带 `V1.3` 主线标签、且正式优先级差距不大的候选，可允许其替代普通同主题观察位，用于补足主线确认

#### 6.3.1 Risk Stack 收口合同

V1.3 第三阶段在 `src/services/momentum_secondary_decision_service.py` 中新增 `Risk_Stack_Check`，用于把“多个弱信号叠加”从解释层提升为官方 Top3 硬阻断。它不替代单项评分，而是模拟交易员的风险堆叠判断：允许一个瑕疵，但不允许多个瑕疵同时存在。

四个因子与实现字段：

- `R1 Position Risk`：`close > 1.2 * ma20`。
- `R2 Sealing Risk`：`limit_list_d.first_time > 14:00:00` 或 `first_time != last_time`；`last_time` 透传为 `last_seal_time`。
- `R3 Divergence Risk`：`close >= high_20d` 且 `v13_stock_buy_elg_amount < 0`。
- `R4 Mainline Risk`：同主题 / 同主线在当日候选池中的数量 `< 2`，优先使用 `_theme_pool_count`，其次使用 V1.3 主线候选计数。

Veto Policy：

```text
risk_stack_count >= 3 -> hard_blockers += risk_stack_veto
```

命中 `risk_stack_veto` 的股票不得进入 `main / secondary / watch` 官方组合槽位；若全部候选均被 Risk Stack 否决，官方组合允许为空，不再回退选入高风险标的。输出需在 `risk_stack / risk_stack_count / risk_stack_veto` 中保留诊断证据，方便回测和页面复盘。

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

补充约束：

- `buyability_clear` 不仅看买入区宽度，也要同时检查 T 日已可见的 `T+1` 承接风险
- 若出现 `upper_shadow / late_session_weakness / price_flow_divergence / blowoff_volume` 等重风险标签，或高延伸与高风险共振，默认不得继续判为 `clear`
- `front_turnover` 的 `clear` 口径应严于 `dragon_leader`；当同主题 `leader` 已满足 `clear` 且承接更稳时，前排 `front` 不应仅凭进攻性继续占据默认主仓
- 次仓与观察仓也应复用同一套 `T+1` 承接风险约束，避免高弹性但高风险的 `front` 仅因未占主仓就继续停留在默认 Top3 组合里

#### 6.4.1 日线封板强度诊断

职责：

- 在没有分钟线权限的前提下，复用 `limit_list_d` 的日线涨停事件字段，诊断 T 日封板质量
- 为买点清晰度、轻修正、风险提示和落选解释提供证据
- 只作为二次决策收口层输入，不新增分钟级正式买点，不改写官方主排序

数据来源：

- `limit_list_d.first_time`：首次封板时间
- `limit_list_d.fd_amount`：封单金额
- `limit_list_d.amount`：成交额，用于派生 `seal_amount_ratio = fd_amount / amount`
- `limit_list_d.open_times`：开板次数
- `daily.open / low / close`：辅助识别一字或极端缩量难参与结构

建议字段：

- `first_seal_time`
- `seal_amount_ratio`
- `open_times`
- `sealing_strength_score`
- `sealing_strength_level`: `strong / medium / weak`
- `is_one_word_like`
- `execution_participation_note`

评分建议：

- 首封时间：`first_time <= 10:00:00` 记高分，`10:00:00 ~ 11:00:00` 记中高分，`11:00:00 ~ 14:00:00` 记中分，`14:00:00` 后只记低分
- 封单强度：`seal_amount_ratio` 越高，封板强度越高，但必须设置上限，避免单日异常封单把整体判断拉爆
- 开板稳定性：`open_times == 0` 加分，`open_times >= 3` 明显扣分
- 最终 `sealing_strength_score` 统一压到 `0 ~ 100`

收口规则：

- `sealing_strength_score >= 75`、`open_times <= 1` 且不是一字难参与结构时，可作为 `execution_clarity_bonus` 或 `soft_adjustments` 的正向证据
- `first_seal_time > 14:00:00`、`open_times >= 3` 或 `seal_amount_ratio < 0.05` 时，应降低买点清晰度，必要时把 `clear` 降为 `waiting / unclear`
- 一字板或极端缩量板只代表强度确认，不代表次日可参与性；不得因为 `open == low == close` 就把候选升级为最优执行状态
- 一字板应输出 `强封但难参与` 类解释，可作为主线确认或观察锚点，不得单独触发 `hard_blocker` 或强行进入主仓

降级原则：

- `limit_list_d` 缺失时，不得硬扣分或硬阻断，只能标记 `sealing_strength_unavailable` 并降低解释置信度
- `fd_amount / amount` 任一字段缺失时，允许只用 `first_time + open_times` 生成低置信度诊断

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
  - 且至少 `1` 只满足 V1.3 `tradable_success_pass`
- `breadth_ok = true`
  - 昨日 `Top10` 命中率 `>= 30%`
  - 且 `Top10` 可交易合格率达到诊断阈值；平均利润窗口只作为辅助观察

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

### 9.1 V1.3 双层验收指标

官方回测报告必须同时展示 `弱延续率` 与 `可交易合格率`，但二者职责不同。

- `弱延续率`：用于判断系统是否捕捉到短线方向偏置，规则为 `T+1 close > T+1 open` 且 `T+2 high > T+1 close`。
- `可交易合格率`：用于判断是否真的具备可执行获利窗口，规则为 `T+1 非一字板`、`T+1 open >= 0.99 * T0 close`、`T+1 close > T+1 open`、`T+2 high >= 1.025 * T1 close`。
- 报告主结论、Benchmark、Regime、每日诊断和明细表的主胜率使用 `tradable_success_rate_pct`；弱延续只作为旁路参考，不能覆盖主标签。

### 9.2 Performance Auditing

Stage 2 起，官方回测必须同时输出 `strategy_alpha_report`，用于证明二次决策和画像过滤是否真的产生增量，而不是只消耗数据流量：

- Group A（V1.3 Official）：`decision_top3`，即最终官方 Top3。
- Group B（Raw Momentum）：每日从完整 `candidate_pool` 中按初始 `rank_score` 选出的 Top3，不经过二次决策、主线收口和画像过滤。
- Group C（Market Base）：固定入口 `涨幅 >= 4% / 成交额 >= 2亿 / 换手率 >= 2%` 形成的完整候选池平均表现。

审计指标：

- `V1.3 Alpha vs Pool = Group A 可交易合格率 - Group C 可交易合格率`。
- `Selection Efficiency = Group A 可交易合格率 - Group B 可交易合格率`。
- 如果 `Group A < Group C`，必须输出 `LOGIC FAILURE: Screener is destroying Pool Alpha`。
- 如果 `Group A < Group B` 但仍高于全池，优先进入参数复核，不直接判定链路失败。

实现约束：

- 新建回测在冻结日内结果时必须额外写入 `candidate_pool` 视图的 candidate/outcome 记录。
- Raw Momentum Top3 必须从 `candidate_pool` 选取，不能用页面 Top10 近似。
- 历史旧 run 若缺少 `candidate_pool` 记录，可以用 `candidate_top10` 兼容展示，但下一轮正式验收必须重新跑新版本回测。

Stage 3 起，`momentum_backtest_service.py` 还必须输出 `gate_justification_report`，用于校准总闸门是否“该收伞时收伞、该出手时没有误报”：

- 仅审计 `action_level = stand_aside`（今日不做）的交易日。
- 若当日 `Pool_Base_WinRate = candidate_pool.tradable_success_rate_pct < 35%`，记为 `Successful_Defensive_Gate`。
- 若当日 `Pool_Base_WinRate > 55%`，记为 `False_Alarm_Warning`，用于后续调低过紧参数。
- 输出字段包括 `stand_aside_days / evaluated_stand_aside_days / successful_defensive_gate_count / false_alarm_warning_count` 以及两类明细列表。

Stage 4 起，`gate_justification_report` 同时作为动态阈值输入：

- `evaluated_gate_days` 必须保留最近可审计交易日的日期、总闸门状态、全池可交易合格率和分类结果。
- `recent_gate_lookback_days` 固定观察最近 5 个可审计交易日；`recent_successful_defensive_gate_rate_pct` 统计其中 `Successful_Defensive_Gate` 占比。
- 若最近 5 日防守成功率 `> 80%`，`MomentumSecondaryDecisionService` 进入弱市动态收口：Official Top3 必须满足 `mainline_intensity_count >= 3`，否则写入 `adaptive_mainline_threshold` 硬阻断并剥离官方槽位。
- 动态收口只提高主线共振要求，不改变 Risk Stack 的 `>= 3` 否决阈值，也不覆盖可交易合格率标签。

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
- 官方回测是否同时输出 `weak_continuity_pass_rate_pct` 与 `tradable_success_rate_pct`，并以 `tradable_success_rate_pct` 作为 V1.3 主验收胜率
- T+1/T+2 回填阈值是否与代码保持一致：`0.99` 跳空过滤、`1.025` 利润缓冲、T+1 非一字、T+1 收阳
