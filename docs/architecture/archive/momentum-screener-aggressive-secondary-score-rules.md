# 次日强势股筛选 V1-Aggressive 二级分数规则

## 1. 文档信息

- 文档名称：次日强势股筛选 V1-Aggressive 二级分数规则
- 所属系统：`daily_stock_analysis`
- 适用版本：`V1-Aggressive`
- 文档类型：进攻型二级分数规则文档
- 当前状态：草案 V1
- 关联文档：
  - [次日强势股筛选 V1-Aggressive 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)

## 2. 设计原则

`V1-Aggressive` 保留标准版的三个主二级分数：

- `continuation_score`
- `extension_score`
- `risk_score`

同时新增一个更适合进攻型风格的辅助分数：

- `buyability_score`

目的：

- 既评估“会不会继续涨”
- 也评估“能不能买进去”
- 保持接口结构与标准版兼容

## 3. 分数范围

所有二级分数统一映射为 `0 ~ 100`。

归一化口径：

```text
normalized_dimension_score = 实际得分 / 该维度满分
```

## 4. continuation_score

含义：明日继续走强的概率分。

### 4.1 使用维度

- 强势确认质量
- 资金承接质量
- 量价双轨
- 板块题材共振
- 趋势位置与弹性

### 4.2 权重

| 维度 | 权重 |
|---|---:|
| 强势确认质量 | 0.35 |
| 资金承接质量 | 0.25 |
| 量价双轨 | 0.20 |
| 板块题材共振 | 0.10 |
| 趋势位置与弹性 | 0.10 |

### 4.3 公式

```text
continuation_score
= normalized(强势确认质量) * 0.35
+ normalized(资金承接质量) * 0.25
+ normalized(量价双轨) * 0.20
+ normalized(板块题材共振) * 0.10
+ normalized(趋势位置与弹性) * 0.10

continuation_score = continuation_score * 100
```

## 5. extension_score

含义：若继续上涨，潜在弹性有多大。

### 5.1 使用维度

- 强势确认质量
- 板块题材共振
- 趋势位置与弹性
- 买入可行性

### 5.2 权重

| 维度 | 权重 |
|---|---:|
| 强势确认质量 | 0.25 |
| 板块题材共振 | 0.20 |
| 趋势位置与弹性 | 0.30 |
| 买入可行性 | 0.25 |

### 5.3 公式

```text
extension_score
= normalized(强势确认质量) * 0.25
+ normalized(板块题材共振) * 0.20
+ normalized(趋势位置与弹性) * 0.30
+ normalized(买入可行性) * 0.25

extension_score = extension_score * 100
```

说明：

- 进攻型版本中，`extension_score` 不再只是“空间”
- 它也纳入“是否有足够博弈空间和参与空间”

## 6. buyability_score

含义：这只股票是否强且具备较好的参与性。

### 6.1 使用维度

- 买入可行性
- 量价双轨
- 资金承接质量

### 6.2 权重

| 维度 | 权重 |
|---|---:|
| 买入可行性 | 0.50 |
| 量价双轨 | 0.30 |
| 资金承接质量 | 0.20 |

### 6.3 公式

```text
buyability_score
= normalized(买入可行性) * 0.50
+ normalized(量价双轨) * 0.30
+ normalized(资金承接质量) * 0.20

buyability_score = buyability_score * 100
```

## 7. risk_score

含义：明日强转弱、冲高回落、兑现的风险分。

### 7.1 输入来源

- 风险修正范围：`0 ~ -15`

### 7.2 公式

```text
risk_score = abs(风险修正) / 15 * 100
```

## 8. 最终排序分

`V1-Aggressive` 的排序分更强调强度和可参与性。

### 8.1 公式

```text
rank_score
= continuation_score * 0.55
+ buyability_score * 0.25
+ extension_score * 0.20
- risk_score * 0.12
```

说明：

- 延续性仍然是主因子
- 可买性被单独拉高
- 风险继续保留惩罚项，但不做过度保守处理

## 9. 展示建议

建议同时展示：

- `continuation_score`
- `extension_score`
- `buyability_score`
- `risk_score`
- `rank_score`

推荐标签：

- `强更强`
- `分歧转一致`
- `可打板`
- `可低吸`
- `高位博弈`

## 10. 变更记录

### 2026-04-10

- 创建 `V1-Aggressive` 二级分数规则文档
- 新增 `buyability_score`
- 调整进攻型排序分公式
