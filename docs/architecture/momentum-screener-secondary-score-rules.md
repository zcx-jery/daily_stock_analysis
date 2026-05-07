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
risk_stack_count = triggered(R1, R2, R3, R4, R5)
risk_stack_veto = risk_stack_count >= 3 OR triggered(R5)
```

当 `risk_stack_veto = true` 时，该股无论官方总分多高，都不得进入官方 Top3；系统应在 `hard_blockers`、`candidate_diagnostics` 和落选说明中暴露 `risk_stack` 详情。若仅命中 R1-R4 中的 1-2 项，不做一票否决，继续由主线强度、买点清晰度和封板质量做轻量修正；但 R5 属于 `MANDATORY_VETO`，一旦触发即不得进入官方 Top3。

设计原因：短线博弈允许单点瑕疵，例如封板稍晚或题材稍弱；但“高位 + 弱封 + 资金背离 + 无主线”同时出现时，实盘可交易性会断崖式下降，必须优先保护官方组合。爆量滞涨或自由流通盘极端换手更接近“量能终结”信号，不能只作为 AI 文字提醒，必须升级为评分引擎的一票否决项。

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
