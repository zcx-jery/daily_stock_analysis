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

### 7.10 Anchor Supremacy / 锚点至上制

第十九阶段正式废止 `King's Guard / 龙一绝对主权`。Stage 18 回测显示：当 Raw #1 被更高延续性的锚点组合替换时，替换组合胜率高于 Raw #1 自身，说明“龙一名次”不应继续作为强制保底条件。V1.3 的最终槽位主权改为由 `continuation_score` 与 Risk Stack 安全门共同决定。

核心合同：

- `Abolish King's Guard / 废止龙一保底`：Raw #1 不再拥有不可替换权，也不再享受 Risk Stack 阈值抬高到 4 的特殊豁免；Raw #1 只有在自身 `continuation_score` 足够高且通过安全门时，才进入 Official Top3。
- `Anchor Supremacy / 锚点至上`：Official Top3 在 Raw Top20 精英池中按 `continuation_score` 严格优先排序，目标是提升 T+1 方向确认率与主仓延续确定性。
- `Core Safety Gate / 核心安全门`：Raw 1-7 进入候选重排前必须满足 `Risk_Stack points < 3` 且没有 `mandatory_veto`。
- `Relaxed Deep Challengers / 放宽深度挑战者`：Raw 8-20 若 `continuation_rank` 位于全池 Top10%，且 `Risk_Stack points <= 1`、无强制否决，可以进入 Official Top3 竞争。允许一个轻微软风险，用于把高质量深位锚点从“精品店”扩展为可影响全局的 Alpha 来源。
- `Main Slot Alpha Anchor / 主仓延续锚点`：Official Top3 的第 1 名即为主仓，不再额外按 Raw 名次或旧主仓阻断重排；主仓必须是最终组合中即时延续概率最高的标的。

伪代码：

```text
core_pool = Raw 1-7 where risk_stack_points < 3 and no mandatory_veto
deep_pool = Raw 8-20 where continuation_rank <= ceil(pool_size * 10%) and risk_stack_points <= 1
elite_pool = core_pool + deep_pool
official_top3 = top 3 by continuation_score, then forward_alpha_score, then official_score
main_slot = official_top3[0]
if Raw #1 is not selected:
    continuation_alpha.status = raw_top1_replaced_by_anchor_supremacy
    continuation_alpha.swap_reason = Anchor_Supremacy
```

设计原因：Raw Momentum #1 代表市场名气，但 Stage 18 数据证明名气也会带来 T+1 分歧和流动性毒性。第十九阶段让“大逻辑”从“保护龙一”切换为“保护延续性锚点”，只要锚点通过 Risk Stack 安全门，就允许它替代 Raw #1。

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

### 7.11 Scaled Continuation Alpha / 规模化延续 Alpha

第十七阶段新增 `Continuation-Led Re-ranking / 延续性主导排序`，第十八阶段验证深度挑战者具备更高方向确认率但样本量不足。第十九阶段在此基础上引入 `Anchor Supremacy / 锚点至上制` 与 `Relaxed Deep Challengers / 放宽深度挑战者`，目标是把高质量延续信号从小样本扩展为可拉动 60 日胜率的稳定来源。

核心合同：
- `Selection Pool / 精英池扩展`：候选搜索范围固定为 Raw Top20。Raw 1-7 通过核心安全门即可参与延续重排；Raw 8-20 通过放宽深度挑战者条件后才可进入 Official Top3。
- `Deep Continuation Challenger / 深度挑战者`：Raw 8-20 标的必须同时满足 `continuation_rank <= ceil(pool_size * 10%)` 且 `Risk_Stack points <= 1`，才可挑战 Official Top3。它们不能靠主线热度或综合分插队，必须是“极高延续 + 至多一个轻微软风险”的深位锚点。
- `Raw #1 No Sovereignty / 龙一不再保底`：Raw #1 可以被移出 Official Top3；若被替出，需要在解释字段中标记 `raw_top1_replaced_by_anchor_supremacy` 与 `Anchor_Supremacy`。
- `Main Slot Alpha Anchor / 主仓延续锚点`：Official Top3 按 `continuation_score` 排序后的第 1 名即为主仓；若 Raw #1 仍入选但不在主仓，标记 `Main_Slot_Pivot`。
- `continuation_alpha` 解释字段：每只 Official Top3 需要记录其是否由延续性重排选入、是否为深度挑战者、所属 Raw 名次、`continuation_rank`、延续分、精英池大小，以及 Raw #1 是让出主仓还是被锚点替换。

排序伪代码：

```text
core_pool = Raw 1-7 where risk_stack_points < 3 and no mandatory_veto
deep_pool = Raw 8-20 where continuation_rank <= ceil(pool_size * 10%) and risk_stack_points <= 1
elite_pool = core_pool + deep_pool
official_top3 = top 3 by continuation_score, then forward_alpha_score, then official_score
Main Slot = official_top3[0]
if Raw #1 selected but slot != main:
    continuation_alpha.swap_reason = Main_Slot_Pivot
if Raw #1 not selected:
    continuation_alpha.swap_reason = Anchor_Supremacy
```

验收目标：全量 60 日回测中，Official 可交易合格率应达到 `24%+`，Official `T+1 direction pass` 应提升到 `55%+`；同时输出 Anchors vs Raw #1 对照，确认锚点组合是否真正优于 Raw #1。

### 7.12 T+1 Support & Sovereign Defense / 次日承接与槽位主权防御

第二十阶段把“延续性锚点”继续拆细为 `T+1 Support Probability / 次日承接概率`。`continuation_score` 仍表示静态延续基因，但最终槽位排序必须使用承接修正后的延续分，避免高延续、晚封板、无资金惯性的标的在 T+1 给用户制造“折磨式持仓”。

核心合同：
- `T+1 Support Probability` 由三项组成：`Sealing_Speed / 封板速度`、`MoneyFlow_Inertia / 资金惯性`、`Cluster_Resonance / 板块共振`。
- `Sealing_Speed` 优先读取 `limit_list_d.first_time` 或 `v13_sealing_strength.first_seal_time_score`；`first_seal_time < 10:00` 获得 `1.10x` 承接惯性系数。
- `MoneyFlow_Inertia` 优先读取 `buy_elg_amount_30m_delta` / `buy_elg_amount_delta_30m` 等尾盘超大单增量字段；若最近 30 分钟超大单净买入改善，获得 `1.10x` 承接惯性系数。
- `Cluster_Resonance` 使用 `mainline_intensity_count` / `mainline_intensity_multiplier`，主线池计数 `>= 3` 或主线强度 `>= 1.20x` 视为强共振。
- `Support_Penalty`：若 `continuation_score >= 85` 但封板速度低于中性，或 `first_seal_time > 14:00`，扣减承接概率并下调 `support_adjusted_continuation_score`，防止尾盘偷板伪装成高延续。

排序口径：

```text
support_inertia_coefficient = 1.0
if first_seal_time < 10:00:
    support_inertia_coefficient *= 1.10
if buy_elg_amount_30m_delta > 0:
    support_inertia_coefficient *= 1.10

t1_support_probability =
    40% * Sealing_Speed
  + 30% * MoneyFlow_Inertia
  + 30% * Cluster_Resonance
  - Support_Penalty

support_adjusted_continuation_score =
    continuation_score * support_inertia_coefficient
  - 0.5 * Support_Penalty

official_top3 = top 3 by support_adjusted_continuation_score,
                then t1_support_probability,
                then continuation_score
```

`Secondary Sovereign Guard / 次席主权护卫`：
- Raw #2 / Raw #3 若 `Risk_Stack points == 0`，默认拥有槽位主权。
- 非 Raw Top3 挑战者只有同时满足 `t1_support_probability >= protected_raw + 20` 且 `composite_score >= protected_raw * 1.30`，才能替换无风险 Raw #2 / Raw #3。
- 若挑战者未达标，被标记为 `blocked_by_secondary_sovereign_guard`；若 Raw #2 / Raw #3 因护卫回归，`continuation_alpha.secondary_sovereign_guard = true`。
- 该护卫只保护次席/观察席的真实动量，不恢复第十九阶段已经废止的 Raw #1 保底。

`Sentiment_Lag_Filter`：
- 总闸门继续保留 `Market_Pool_Avg_Return < -3%` 的强制不做规则。
- 环境分从“核心溢价偏重”调整为：`40% core_premium + 45% breadth_premium + 15% current_pool_breadth`。
- `current_pool_breadth` 使用当日候选池规模和主题簇数量，目的是降低指数滞后权重、提高涨停家数 / 候选池规模对早周期启动的识别权重，修复类似 2026-01-07 的早周期漏判。

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
