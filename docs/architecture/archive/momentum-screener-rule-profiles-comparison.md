# 次日强势股筛选规则画像对照表

## 1. 文档信息

- 文档名称：次日强势股筛选规则画像对照表
- 所属系统：`daily_stock_analysis`
- 产品决策：`V1 + 可切换 Aggressive`
- 文档类型：规则差异对照文档
- 当前状态：草案 V1
- 关联文档：
  - [次日强势股筛选 V1 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)
  - [次日强势股筛选二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-score-rules.md)
  - [次日强势股筛选 V1-Aggressive 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)
  - [次日强势股筛选 V1-Aggressive 二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-aggressive-secondary-score-rules.md)

## 2. 产品决策

当前产品采用双画像模式：

- `V1`
  - 默认画像
  - 更平衡，适合通用次日延续筛选
- `Aggressive`
  - 可切换画像
  - 更偏进攻，强调强度、加速、换手和可参与性

建议产品层命名：

- `standard`
- `aggressive`

## 3. 一页总览

| 项目 | V1 Standard | V1 Aggressive |
|---|---|---|
| 产品定位 | 平衡型次日延续筛选 | 进攻型短线接力筛选 |
| 默认状态 | 默认启用 | 用户手动切换 |
| 核心目标 | 找“更可能继续涨”的股票 | 找“强且买得到、适合进攻”的股票 |
| 风格偏好 | 平衡强度、板块、资金、位置、风险 | 放大强度、加速、可参与性，弱化保守惩罚 |
| 适合人群 | 通用短线用户 | 偏打板、接力、强势股用户 |
| 风险态度 | 中性偏稳健 | 可接受更高波动 |

## 4. 维度结构对照表

| 维度 | V1 Standard | V1 Aggressive | 实现差异 |
|---|---:|---:|---|
| 强势确认质量 | 20 | 30 | Aggressive 更重强度、涨停接近度、加速确认 |
| 量价结构 / 量价双轨 | 20 | 15 | Standard 用单一路径；Aggressive 分缩量一致和健康换手两套逻辑 |
| 趋势位置与形态 / 趋势位置与弹性 | 15 | 8 | Aggressive 降权，不机械惩罚高位加速 |
| 板块题材共振 | 20 | 12 | 两者都用申万一级行业；Aggressive 降低板块权重 |
| 资金承接质量 | 15 | 20 | Aggressive 更重真实资金推动 |
| 弹性与股性 / 趋势位置与弹性 | 10 | 计入趋势位置与弹性 8 分 | Aggressive 把弹性合并入位置结构 |
| 买入可行性 | 无 | 15 | Aggressive 新增，识别“强且买得到” |
| 风险修正 | 0 ~ -20 | 0 ~ -15 | Aggressive 只保留致命分歧扣分 |

## 5. 关键规则差异表

| 主题 | V1 Standard | V1 Aggressive |
|---|---|---|
| 对高位加速的态度 | 作为风险项审慎处理 | 不机械惩罚；强势加速可加分 |
| 对板块共振的重视度 | 高 | 中 |
| 对买入机会的重视度 | 无独立维度 | 高，单独做 `买入可行性` |
| 对缩量封死板的判断 | 只作为强势体现之一 | 单独奖励“一致性强板” |
| 对换手板的判断 | 以量比、换手率通用评价 | 单独奖励“健康换手板” |
| 对风险的处理 | 维度更全、扣分更完整 | 只惩罚致命分歧，不做过度保守 |
| 对实战交易输出 | 侧重延续概率 | 侧重延续概率 + 可参与性 + 进场区间 |

## 6. 数据口径对照表

| 项目 | V1 Standard | V1 Aggressive | 是否共用 |
|---|---|---|---|
| 候选池过滤 | `pct_chg >= N`、排除 ST、主板优先、最低成交额/换手 | 与 Standard 一致 | 是 |
| 板块口径 | 申万一级行业 | 申万一级行业 | 是 |
| 核心行情接口 | `daily`、`daily_basic`、`moneyflow`、`top_list`、`stk_limit` | 与 Standard 一致 | 是 |
| 盘中实时数据 | 不使用 | 不使用 | 是 |
| 风险数据层级 | 收盘后日线代理口径 | 收盘后日线代理口径 | 是 |

说明：

- 两套规则的数据源完全兼容
- 差异主要在打分权重、分档和解释逻辑
- 这意味着后续开发可以共用一套数据装载流程，只切换评分 profile

## 7. 二级分数对照表

| 分数 | V1 Standard | V1 Aggressive | 说明 |
|---|---|---|---|
| `continuation_score` | 有 | 有 | 两者都有，但权重不同 |
| `extension_score` | 有 | 有 | 两者都有，但 Aggressive 更强调可博弈空间 |
| `risk_score` | 有 | 有 | 两者都有，Aggressive 风险口径更窄 |
| `buyability_score` | 无 | 有 | Aggressive 新增，建议前端仅在该模式显示 |
| `rank_score` | 有 | 有 | 两者都有，但公式不同 |

## 8. 二级分数公式对照表

### 8.1 Standard

```text
continuation_score
= normalized(强势确认质量) * 0.30
+ normalized(量价结构) * 0.30
+ normalized(板块题材共振) * 0.25
+ normalized(资金承接质量) * 0.15

extension_score
= normalized(趋势位置与形态) * 0.40
+ normalized(板块题材共振) * 0.30
+ normalized(弹性与股性) * 0.30

risk_score = abs(风险修正) / 20 * 100

rank_score
= continuation_score * 0.65
+ extension_score * 0.25
- risk_score * 0.10
```

### 8.2 Aggressive

```text
continuation_score
= normalized(强势确认质量) * 0.35
+ normalized(资金承接质量) * 0.25
+ normalized(量价双轨) * 0.20
+ normalized(板块题材共振) * 0.10
+ normalized(趋势位置与弹性) * 0.10

extension_score
= normalized(强势确认质量) * 0.25
+ normalized(板块题材共振) * 0.20
+ normalized(趋势位置与弹性) * 0.30
+ normalized(买入可行性) * 0.25

buyability_score
= normalized(买入可行性) * 0.50
+ normalized(量价双轨) * 0.30
+ normalized(资金承接质量) * 0.20

risk_score = abs(风险修正) / 15 * 100

rank_score
= continuation_score * 0.55
+ buyability_score * 0.25
+ extension_score * 0.20
- risk_score * 0.12
```

## 9. 前端配置建议

前端建议将“规则画像”做成显式可切换项。

### 9.1 建议控件

- 字段名：`profile`
- 类型：单选
- 可选值：
  - `standard`
  - `aggressive`

### 9.2 建议展示文案

| 值 | 标题 | 副文案 |
|---|---|---|
| `standard` | 平衡模式 | 更看重延续性、板块和风险控制 |
| `aggressive` | 进攻模式 | 更看重强度、换手和买入机会 |

### 9.3 前端差异展示

| 页面元素 | Standard | Aggressive |
|---|---|---|
| 主分数卡片 | continuation / extension / risk / final | continuation / extension / buyability / risk / rank |
| 维度拆解 | 6 大正向维度 + 风险 | 6 大正向维度 + 风险 |
| 标签 | 延续、弹性、风险 | 强更强、分歧转一致、可打板、可低吸 |
| 说明文案 | 平衡型 | 进攻型 |

## 10. 后端配置建议

### 10.1 请求参数

建议后端 API 增加：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `profile` | enum | 否 | `standard` / `aggressive`，默认 `standard` |

### 10.2 配置实现建议

后端评分引擎建议分为两层：

1. 公共层
   - 候选池过滤
   - 数据拉取
   - 公共特征计算
2. 画像层
   - 不同 profile 的权重、分档、公式

### 10.3 建议配置结构

```text
profile_config = {
  "standard": {...},
  "aggressive": {...}
}
```

其中差异配置至少包含：

- 维度权重
- 子项阈值
- 风险扣分阈值
- 二级分数公式
- 排序分公式
- 输出标签集

## 11. 实现优先级建议

建议实现顺序：

1. 先实现 `standard`
2. 再复用同一特征层实现 `aggressive`
3. 最后把前端 profile 切换接进页面

原因：

- Standard 规则更稳定，适合先验证基础特征和数据口径
- Aggressive 是规则变体，不应该重建一套数据链路

## 12. 变更记录

### 2026-04-10

- 确认产品采用 `V1 + 可切换 Aggressive`
- 新增规则画像差异对照文档
- 固化前端与后端的 profile 化配置建议
