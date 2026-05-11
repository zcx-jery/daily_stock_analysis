# 次日强势股筛选二级分数规则

## 1. 文档信息

- 文档名称：次日强势股筛选二级分数规则
- 所属系统：`daily_stock_analysis`
- 适用版本：`V1`
- 文档类型：规则基线文档
- 当前状态：草案 V1
- 关联文档：
  - [次日强势股筛选产品方案](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-product-plan.md)
  - [次日强势股筛选 PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-prd.md)
  - [次日强势股筛选 V1 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)

## 2. 文档目的

本文档用于固化 `V1` 中三个二级分数的计算规则：

- `continuation_score`
- `extension_score`
- `risk_score`

设计目标：

- 在总分之外提供更易理解的二级判断
- 把“能不能继续涨”和“如果涨有多大空间”拆开
- 保持结果可解释、可复算、可回测

## 3. 二级分数定义

### 3.1 continuation_score

含义：明日继续上涨的概率分。

它主要回答：

- 今天的强势是否有延续性
- 是否有量价和资金支持
- 是否站在市场主线中

### 3.2 extension_score

含义：如果明日继续上涨，潜在弹性有多大。

它主要回答：

- 继续涨时空间是否足够
- 是否具备板块扩散和趋势延展能力
- 是否具备短线资金喜欢反复交易的股性

### 3.3 risk_score

含义：明日冲高回落、断强、兑现的风险分。

它主要回答：

- 这只股票明日翻车的概率高不高
- 当前是否已经处在容易分歧的位置

## 4. 计算原则

### 4.1 基础原则

- 二级分数不替代基础总分
- 二级分数服务于结果解释和排序辅助
- 风险分单独展示，不揉进正向分解释中

### 4.2 分数范围

三个二级分数统一显示为 `0 ~ 100` 分。

### 4.3 归一化原则

由于各基础维度的满分不同，计算二级分数前先做维度归一化：

```text
normalized_dimension_score = 实际得分 / 该维度满分
```

例如：

- 强势确认质量满分 `20`
- 若实际得分 `15`
- 则归一化得分为 `15 / 20 = 0.75`

## 5. continuation_score 规则

### 5.1 使用维度

- 强势确认质量
- 量价结构
- 板块题材共振
- 资金承接质量

### 5.2 权重

| 维度 | 权重 |
|---|---:|
| 强势确认质量 | 0.30 |
| 量价结构 | 0.30 |
| 板块题材共振 | 0.25 |
| 资金承接质量 | 0.15 |

### 5.3 计算公式

```text
continuation_score
= normalized(强势确认质量) * 0.30
+ normalized(量价结构) * 0.30
+ normalized(板块题材共振) * 0.25
+ normalized(资金承接质量) * 0.15

continuation_score = continuation_score * 100
```

### 5.4 设计原因

- 强势确认质量：回答“今天够不够强”
- 量价结构：回答“涨得有没有质量”
- 板块题材共振：回答“是不是主线”
- 资金承接质量：回答“有没有真实承接”

这四项最直接影响“明天还能不能继续涨”。

## 6. extension_score 规则

### 6.1 使用维度

- 趋势位置与形态
- 板块题材共振
- 弹性与股性

### 6.2 权重

| 维度 | 权重 |
|---|---:|
| 趋势位置与形态 | 0.40 |
| 板块题材共振 | 0.30 |
| 弹性与股性 | 0.30 |

### 6.3 计算公式

```text
extension_score
= normalized(趋势位置与形态) * 0.40
+ normalized(板块题材共振) * 0.30
+ normalized(弹性与股性) * 0.30

extension_score = extension_score * 100
```

### 6.4 设计原因

- 趋势位置与形态：决定是否还在可扩展阶段
- 板块题材共振：决定是否有板块扩散和跟风资金
- 弹性与股性：决定如果继续走强，空间大不大

这三项更偏“如果涨，还能涨多少”。

## 7. risk_score 规则

### 7.1 输入来源

`risk_score` 由风险修正项反向映射而来。

风险修正原始口径：

- 风险修正范围为 `0 ~ -20`
- 绝对值越大，风险越高

### 7.2 计算公式

先定义：

```text
risk_penalty_abs = abs(风险修正)
```

再映射为：

```text
risk_score = (risk_penalty_abs / 20) * 100
```

### 7.3 示例

| 风险修正 | risk_score |
|---|---:|
| `0` | 0 |
| `-5` | 25 |
| `-10` | 50 |
| `-15` | 75 |
| `-20` | 100 |

### 7.4 设计原因

- 保持和风险修正主规则完全一致
- 风险越高，分值越高，更符合用户直觉
- 页面上更容易做标签分层和颜色表达

### 7.5 Risk_Stack_Check 风险堆叠合同

`risk_score` 仍是单项风险解释分；V1.3 第三阶段新增 `Risk_Stack_Check`，用于判断“多个小瑕疵同时出现时是否必须从官方 Top3 剥离”。它不是硬 Veto 的替代品，而是二次决策收口层的组合风险闸门。

五个风险因子：

- `R1 Position Risk`：`close > 1.2 * MA20`，代表价格已经显著高于 20 日均线，次日承接更依赖情绪继续加速。
- `R2 Sealing Risk`：`first_seal_time > 14:00:00` 或 `first_seal_time != last_seal_time`，代表尾盘封板或日内开板回封，封板稳定性存疑。
- `R3 Divergence Risk`：价格处于 20 日新高，且 `buy_elg_amount < 0`，代表创新高时超大单并未同步承接。
- `R4 Mainline Risk`：同主题 / 同主线在当日候选池中的数量 `< 2`，代表缺少板块共振，单票独涨的次日溢价更不稳定；若 `limit_list_d.limit_times` 显示该股为当前市场 `Space Leader / 空间龙头`（最高连板且至少 2 板），则 R4 豁免，因为最高板本身可以创造主线。
- `R5 Exhaustion Risk / 量能竭尽风险`：若 `Volume_T0 > 2.0 * Volume_Avg_5D` 且 `Price_Gain < 5%`，代表爆量但没有继续加速；或 `Turnover_Rate_F > 25%`，代表自由流通盘极端换手，存在派发 / A 字顶风险。实现字段优先使用 `volume_expand_5` 与 `turnover_rate_f`；若数据源缺少成交量字段，`volume_expand_5` 可降级使用成交额近 5 日均值。

收口规则：

```text
risk_stack_points = triggered(R1, R2, R3, R4) * 1 + triggered(R5) * 2
risk_stack_veto = risk_stack_points >= 3
```

第十二阶段新增 `Leader Veto Tiering / 龙头分层否决权`：

- `Hard Risks / 核心红线`：`R1 Position Risk` 与 `R3 Divergence Risk`。这两项代表高位承接透支或资金背离，是崩塌的领先信号。
- `Soft Risks / 波动分歧`：`R2 Sealing Risk`、`R4 Mainline Risk` 与 `R5 Exhaustion Risk`。这三项对普通票仍是风险，但对 Raw Top3 龙头可能是分歧转一致、弱转强和爆量换手确认。

Raw Top3 的 Veto 政策：

```text
base_veto = risk_stack_points >= 3
has_hard_risk = triggered(R1) OR triggered(R3)
mainline_position_churn =
    triggered(R1) AND triggered(R5)
    AND NOT triggered(R2) AND NOT triggered(R3) AND NOT triggered(R4)
    AND mainline_count >= 3
mainline_reseal_churn =
    triggered(R1) AND triggered(R2/R5)
    AND NOT triggered(R3) AND NOT triggered(R4)
    AND mainline_count >= 3
    AND risk_stack_points <= 4

if raw_rank <= 3 AND base_veto AND NOT has_hard_risk:
    risk_stack_veto = false
    raw_alpha_shield.status = RETAINED_LEADER_DIVERGENCE
elif raw_rank <= 3 AND base_veto AND mainline_position_churn:
    risk_stack_veto = false
    raw_alpha_shield.status = RETAINED_LEADER_DIVERGENCE
elif raw_rank <= 3 AND base_veto AND mainline_reseal_churn:
    risk_stack_veto = false
    raw_alpha_shield.status = RETAINED_LEADER_DIVERGENCE
else:
    risk_stack_veto = base_veto
```

也就是说，Raw Top3 若只命中 `R2/R4/R5`，即使风险点达到 3，也必须保留在 Official Top3，并由 AI 和页面标记为 `Weak-to-Strong / 弱转强` 高风险高弹性候选。若 Raw Top3 命中 `R1 + R5` 且没有 `R2/R3/R4`，同时主线池计数 `>= 3`，则解释为 `mainline_position_churn / 主线高位换手`。第十六阶段进一步补充 `mainline_reseal_churn / 主线回封换手`：Raw Top3 只触发一个硬风险 `R1`，并叠加 `R2/R5` 分歧换手，但没有 `R3` 资金背离、没有 `R4` 主线不足、主线池计数 `>= 3` 且风险点不超过 4 时，继续保留为强主线分歧候选。`R3` 资金背离、多硬风险，或无主线支撑的高位弱封，Raw Top3 主权才失效。

对非 Raw Top3，`risk_stack_veto = true` 时仍不得进入官方 Top3；系统应在 `hard_blockers`、`candidate_diagnostics` 和落选说明中暴露 `risk_stack` 详情。若仅命中 R1-R4 中的 1-2 项，不做一票否决，继续由主线强度、买点清晰度和封板质量做轻量修正。R5 从第十一阶段起不再是 `MANDATORY_VETO`，而是 `Conditional Risk`：单独触发只记 2 个风险点，只有叠加其他风险使总点数达到 3 时才构成硬否决。

设计原因：短线博弈允许单点瑕疵，例如封板稍晚或题材稍弱；但“高位 + 弱封 + 资金背离 + 无主线”同时出现时，实盘可交易性会断崖式下降，必须优先保护官方组合。爆量滞涨或自由流通盘极端换手更接近“量能终结”信号，但在强势股加速阶段也可能是分歧转一致，因此第十一阶段改为条件风险点，不再单点一票否决。

### 7.6 Mainline_Intensity 加分校准

V1.3 第八阶段将主线加分从“计数即加分”改为“簇成立才加分”：

```text
if count_in_pool < 2:
    mainline_intensity_multiplier = 1.0
else:
    mainline_intensity_multiplier = min(1.3, 1 + 0.1 * count_in_pool)

if R1 Position Risk triggered:
    mainline_intensity_multiplier = min(mainline_intensity_multiplier, 1.1)
```

这意味着孤立强势票不能获得主线共振 bonus；若标的已经触发高位风险，即使题材热度很强，也最多只允许 1.1x 的主线加权，避免系统被“伪主线热度”遮蔽高位派发风险。

### 7.7 Mainline Privilege 与买点健康度

V1.3 第九阶段新增 `Mainline Privilege / 主线优先权`，用于避免用“妖股秒板”的单一尺子误伤大市值中军或主线龙头。

触发条件：

```text
mainline_privilege = Mainline_Intensity > 1.2x
```

若命中主线优先权，`first_seal_time` 的重罚窗口后移：

- 普通标的：必须在 `10:30:00` 前完成首次封板，`10:30:00` 后开始明显衰减。
- 主线标的：允许在 `11:30:00` 前完成首次封板而不触发重罚，`11:30:00` 后才按弱化封板处理。

`Buy Point Health / 买点健康度` 将晚封拆成两类：

- `Late Seal due to weakness`：尾盘封板、多次开板、封单偏弱或炸板，视为买点不清晰。
- `Late Seal due to healthy rotation`：主线强度成立，且 `turnover_rate_f` 处于 `5% ~ 8%` 的充分换手区间，即使封板晚于普通票，也可视为“主线换手确认”，不再自动把 `waiting` 买点压成 `unclear`。

实现边界：

- 该规则只放宽主线中军 / 主线龙头的封板时间惩罚，不直接豁免 R5 条件风险；若 R5 叠加其他风险使 `risk_stack_points >= 3`，默认仍按硬否决处理。例外情况仅限 Raw Top3 的 `mainline_position_churn` 与 `mainline_reseal_churn`：强主线池计数 `>= 3`、无 R3/R4 时，`R1 + R5` 或 `R1 + R2/R5` 可被解释为主线高位换手 / 回封换手，而非立即出货。
- 若晚封同时伴随炸板、尾盘封板或极端低封单，仍按 R2 / 买点不清晰处理。
- `ticker_swap_log.dropped_by_v13` 必须输出 `primary_rejection_reason`，用于区分“好错过”（例如 A 字顶被剔除）和“误杀”（例如主线换手票被买点规则剔除）。

### 7.8 Alpha Shield Protocol / Raw Alpha 保卫

第十一阶段新增 `Alpha Shield Protocol`，用于修正 Official Top3 相对 Raw Momentum Top3 的 Alpha 侵蚀问题。

核心合同：

- `Raw Top 3 Sovereignty / 原始前三主权`：Raw Top3 默认受保护；第十三阶段起，只有出现有效硬否决才允许移出 Official Top3。有效硬否决包括 `R3` 资金背离、多硬风险，或 `R1` 高位风险叠加无主线 / 资金背离；若仅是强主线下的 `R1 + R5` 高位换手，或 `R1 + R2/R5` 回封换手，且主线池计数 `>= 3`、无 R3/R4，则分别保留为 `mainline_position_churn` / `mainline_reseal_churn`。
- `Conditional R5 / R5 条件风险`：R5 只贡献 2 个风险点，不再一票否决；爆量可以是分歧转一致，只有叠加高位、弱封板、资金背离或主线不足时才视为毒性风险。
- `Anti-Displacement Guard / 防替换护栏`：非 Raw Top3 插入票必须是 `Perfect Profile`（未触发 R1-R5 任一风险），且组合综合分必须满足动态溢价门槛，才能替换 Raw 龙头。Raw #1 默认门槛为 `1.25x`；Raw #2 / Raw #3 从第十六阶段起提升为 `1.40x`，用于终结低置信度槽位切换。
- `Stable Main Slot / 稳定主仓锚点`：主仓不再强制归属 Raw #1，而是在已选组合内选择 `Mainline_Intensity` 更高、主线池计数更强、Risk Stack 更低的稳定锚点；Raw 龙头的进攻弹性由次仓 / 观察仓承接。
- `AI Audit`：AI 点评必须说明 Raw Top3 是因何被保留或被剔除；若剔除，必须给出 `risk_stack_points >= 3` 的硬证据，不能只用“买点不干净”作为理由。

### 7.9 Weak-to-Strong Protocol / 弱转强协议

第十二阶段新增 `Weak-to-Strong Protocol`，用于修复 Raw 龙头因 `R2 + R5` 被误杀的问题。

- `R2 + R5` 对普通票代表封板不稳和量能过载；但对 Raw Top3，若没有 `R1` 高位透支或 `R3` 资金背离，优先解释为“爆量换手后的分歧转一致”。
- 命中该协议的 Raw Top3 必须设置 `raw_alpha_shield.status = RETAINED_LEADER_DIVERGENCE`，并继续参与 Official Top3 槽位竞争。
- AI 点评必须使用 `Weak-to-Strong / 弱转强` 语言说明：晚封、炸板或爆量并不自动等于出货，关键是 T+1 是否不深低开、是否能突破首 30 分钟高点并维持承接。
- 若同一票命中 `R3`，或 `R1` 同时叠加无主线、资金背离、多硬风险等非健康换手证据，弱转强豁免失效，继续按硬否决处理；强主线 Raw Top3 的 `R1 + R5` 可按 `mainline_position_churn` 保留，强主线 Raw Top3 的 `R1 + R2/R5` 可按 `mainline_reseal_churn` 保留。

### 7.10 King's Guard Protocol / 龙一绝对主权

第十六阶段新增 `King's Guard / 龙一绝对主权`，用于修复 Official Top3 最后一段负 Alpha：二阶段槽位竞优仍会把 Raw 龙头踢出，换入低回撤但弹性不足的平庸标的。

触发条件：

```text
kings_guard =
    raw_momentum_rank == 1
    AND mainline_intensity_multiplier > 1.25
```

收口合同：

- `Displacement Immunity / 不可替换权`：若命中 `kings_guard`，该 Raw #1 不允许被任何 Secondary / Waiting 插入票替换；即使挑战者是零风险画像且综合分大幅更高，也只能作为备选解释，不能挤掉龙一。
- `Open Slot Fill / 空槽补位权`：若 Official Top3 因买点、槽位或硬阻断只形成 1-2 只组合，未触发有效硬否决的 Raw Top3 必须先补入空槽，再考虑替换逻辑；不能因为没有可替换对象而让 Raw 主权失效。
- `Hard Risk Softening / 硬风险软化`：若 Raw #1 所在主线 / 行业簇计数 `>= 3`，Risk Stack 硬否决阈值从 `>= 3` 提升到 `>= 4`。在此条件下，Raw #1 允许单独触发一个硬风险（`R1` 或 `R3`）而不自动出局。
- `Two-Hard-Risk Exception / 双硬风险例外`：若 Raw #1 同时触发 `R1` 与 `R3`，并再叠加其他风险使 `risk_stack_points >= 3`，仍视为有效硬否决；龙一主权不保护“高位 + 资金背离 + 额外瑕疵”的组合毒性。
- `Follower Buffer / 二三名溢价缓冲`：Raw #2 / Raw #3 的替换门槛提升至 `1.40x`，只有挑战者形成真正的降维打击时才允许替换，减少“干净但平庸”的无效换入。
- `Deep Raw Coverage / 深位 Raw 覆盖`：V1.3 主线上下文采样在控制 30 只成本上限的同时，必须把 Raw Momentum Top3 纳入样本；若 Raw Top3 位于基础排序 30 名之后，则替换掉尾部非 Raw 样本，避免深位高 `rank_score` 龙头缺少主线 / 封板上下文。

实现输出：

```text
raw_alpha_shield.status = retained_by_kings_guard
raw_alpha_shield.kings_guard = true
raw_alpha_shield.filled_open_slot = watch
raw_alpha_shield.replacement_premium_threshold = 1.25  # Raw #1 基础门槛；命中 King's Guard 时实际不可替换

risk_stack.leader_resilience_profile = raw_top1_hard_risk_softened
risk_stack.threshold = 4
```

设计原因：Raw Momentum #1 是市场最直接的强势表达。V1.3 允许二阶段决策做风险审计，但不能用“买点更规整”“回撤画像更温顺”这类细节推翻龙一的主线地位。防守已经由 Total Gate 完成，选股层必须保留足够的进攻上限。

## 8. 最终排序分规则

在二级分数基础上，最终排序分建议如下：

```text
rank_score
= continuation_score * 0.65
+ extension_score * 0.25
- risk_score * 0.10
```

说明：

- 优先看是否继续上涨
- 其次看上涨弹性
- 最后扣除风险

## 9. 展示建议

页面建议同时展示：

- `continuation_score`
- `extension_score`
- `risk_score`
- `final_score` 或 `rank_score`

推荐解释口径：

- `continuation_score`：明日延续概率
- `extension_score`：若延续，上涨弹性
- `risk_score`：明日分歧或兑现风险

## 10. 分层建议

### 10.1 continuation_score 分层

| 分数 | 标签 |
|---|---|
| `>= 85` | 很强 |
| `75 ~ 84` | 较强 |
| `60 ~ 74` | 中等 |
| `< 60` | 偏弱 |

### 10.2 extension_score 分层

| 分数 | 标签 |
|---|---|
| `>= 85` | 高弹性 |
| `75 ~ 84` | 较高弹性 |
| `60 ~ 74` | 一般弹性 |
| `< 60` | 低弹性 |

### 10.3 risk_score 分层

| 分数 | 标签 |
|---|---|
| `0 ~ 24` | 低风险 |
| `25 ~ 49` | 可控风险 |
| `50 ~ 74` | 中高风险 |
| `75 ~ 100` | 高风险 |

## 11. 实现注意事项

### 11.1 四舍五入

建议：

- 中间计算保留至少 4 位小数
- 最终展示保留 1 位小数或整数

### 11.2 缺失值处理

若某维度缺失：

- 不建议直接记满分或记零分
- 建议采用该维度的中性分，或在接口层补默认值

### 11.3 和总分的关系

- `final_score` 仍然是基础总分减风险后的主分
- 二级分数主要承担解释和排序辅助作用
- 若后续产品只保留一个展示主分，应优先保留 `final_score`

## 12. 变更记录

### 2026-04-10

- 创建二级分数规则文档
- 固化 `continuation_score` 计算规则
- 固化 `extension_score` 计算规则
- 固化 `risk_score` 计算规则
- 固化 `rank_score` 计算规则
