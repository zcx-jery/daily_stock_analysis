# 次日强势股筛选字段级实现映射表

## 1. 文档信息

- 文档名称：次日强势股筛选字段级实现映射表
- 所属系统：`daily_stock_analysis`
- 适用版本：`V1 Standard` / `V1-Aggressive`
- 文档类型：实现前基线文档
- 当前状态：草案 V1
- 关联文档：
  - [次日强势股筛选产品方案](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-product-plan.md)
  - [次日强势股筛选 V1 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)
  - [次日强势股筛选二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-score-rules.md)
  - [次日强势股筛选 V1-Aggressive 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)
  - [次日强势股筛选 V1-Aggressive 二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-aggressive-secondary-score-rules.md)
  - [次日强势股筛选规则画像对照表](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-rule-profiles-comparison.md)

## 2. 文档目的

本文档用于把产品规则进一步收口到“实现前可直接拆任务”的粒度。

本文档回答的问题：

- 每个评分项依赖哪些接口
- 每个评分项依赖哪些原始字段
- 每个评分项如何计算中间特征
- 缺失值如何处理
- Standard 和 Aggressive 哪些特征可以共用

## 3. 实现分层建议

建议后端实现拆成四层：

1. 数据拉取层
   - 只负责从 Tushare 拉数据
2. 特征构建层
   - 把原始字段加工成统一特征
3. 评分规则层
   - 按 `profile=standard/aggressive` 调不同评分规则
4. 输出组装层
   - 生成页面/API 返回字段

这样可以保证：

- 数据只拉一次
- 特征只算一次
- 两套规则复用同一特征集

## 4. 接口与主数据表

| 数据域 | 接口 | 主要用途 |
|---|---|---|
| 日线行情 | `daily` | 涨幅、开高低收、成交量、成交额 |
| 股票基础信息 | `stock_basic` | 名称、市场、上市状态、上市日期 |
| 日线基础指标 | `daily_basic` | 换手率、量比、流通市值 |
| 资金流向 | `moneyflow` | 主力净流入、大单/中单/小单结构 |
| 龙虎榜 | `top_list` | 是否上榜、净买入、上榜原因 |
| 涨跌停价格 | `stk_limit` | 涨停价、跌停价 |
| 行业分类 | `index_classify` | 申万一级行业定义 |
| 行业成分 | `index_member_all` | 股票到申万一级行业映射 |
| 行业日线 | `index_daily` | 申万一级行业涨跌幅、排名 |

## 5. 候选池硬过滤映射

| 规则 | 所需字段 | 来源接口 | 说明 |
|---|---|---|---|
| 今日涨幅阈值 | `pct_chg` | `daily` | `pct_chg >= N` |
| 排除 ST | `name` | `stock_basic` | 名称包含 `ST/*ST` 过滤 |
| 排除停牌/异常状态 | `list_status` | `stock_basic` | 仅保留 `L` |
| 排除新股 | `list_date` | `stock_basic` | 上市时间距今低于阈值过滤 |
| 最低成交额 | `amount` | `daily` | 候选池流动性门槛 |
| 最低换手率 | `turnover_rate` | `daily_basic` | 候选池换手门槛 |
| 主板过滤 | `ts_code` 或市场字段 | `stock_basic` | 默认只保留主板股票 |

## 6. 公共中间特征表

以下特征建议统一在特征构建层计算，两套 profile 共用。

| 特征名 | 计算公式 | 依赖字段 | 用途 |
|---|---|---|---|
| `close_position` | `(close - low) / (high - low)` | `open/high/low/close` | 收盘位置、尾盘强弱代理 |
| `limit_proximity` | `close / up_limit` | `close` + `up_limit` | 涨停接近度 |
| `body_ratio` | `abs(close - open) / (high - low)` | `open/high/low/close` | K线实体强度 |
| `upper_shadow_ratio` | `(high - max(open, close)) / (high - low)` | `open/high/low/close` | 长上影/冲高回落 |
| `gap_open_ratio` | `(open - prev_close) / prev_close` | `open` + 前一日 `close` | 跳空高开强度 |
| `amplitude_ratio` | `(high - low) / close` | `high/low/close` | 日内振幅空间 |
| `volume_expand_5` | `amount / avg(amount_5)` | 当日 `amount` + 前 5 日 `amount` | 放量质量 / 爆量风险 |
| `main_inflow_ratio` | `主力净流入额 / amount` | `moneyflow` + `daily.amount` | 主力净流入强度 |
| `prev_20d_high` | 前 20 日最高价 | 历史 `daily.high` | 突破结构 |
| `prev_60d_high` | 前 60 日最高价 | 历史 `daily.high` | 趋势位置 |
| `cum_ret_3d` | 近 3 日累计涨幅 | 历史 `daily.pct_chg` | 加速判断 |
| `cum_ret_5d` | 近 5 日累计涨幅 | 历史 `daily.pct_chg` | 连续强势 / 风险 |
| `up_days_5d` | 近 5 日上涨天数 | 历史 `daily.pct_chg` | 连续强势 |
| `strong_days_60d` | 近 60 日 `pct_chg >= 7%` 天数 | 历史 `daily.pct_chg` | 历史股性 |
| `limit_up_days_60d` | 近 60 日涨停天数 | 历史 `daily.close` + `stk_limit.up_limit` | 历史股性 |

### 6.1 特殊值处理

若 `high == low`：

- `close_position`
  - 若收涨，记 `1.0`
  - 否则记 `0.5`
- `body_ratio`
  - 若 `close > open`，记 `1.0`
  - 否则记 `0.0`
- `upper_shadow_ratio`
  - 记 `0.0`

## 7. 板块数据映射规则

`V1` 与 `V1-Aggressive` 的板块口径完全共用。

### 7.1 主板块映射

| 步骤 | 逻辑 |
|---|---|
| 1 | 用 `index_member_all` 将 `ts_code` 映射到申万一级行业 |
| 2 | 若一只股票存在多条行业映射，仅保留申万一级行业 |
| 3 | 用 `index_daily` 获取行业当日涨跌幅 |
| 4 | 用 `daily` 在同一行业内统计涨停数、大涨家数、个股排名 |

### 7.2 回退规则

如果某只股票未成功映射到申万一级行业：

- `sector_rank_score` 记中性低分
- `sector_breadth_score` 记低分
- `sector_ladder_score` 记低分
- `sector_leader_score` 记低分

建议回退值：

| 特征 | 默认值 |
|---|---:|
| `sector_rank_score_default` | 2 |
| `sector_breadth_score_default` | 1 |
| `sector_ladder_score_default` | 1 |
| `sector_leader_score_default` | 1 |

## 8. Standard 评分项映射表

### 8.1 强势确认质量

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 今日涨幅强度 | `daily.pct_chg` | 无 | 缺失则剔除候选 |
| 收盘位置 | `daily.open/high/low/close` | `close_position` | 按特殊值规则处理 |
| 涨停接近度 | `daily.close` + `stk_limit.up_limit` | `limit_proximity` | 缺失则该项记中性 `2分` |
| K线实体强度 | `daily.open/high/low/close` | `body_ratio` | 按特殊值规则处理 |

### 8.2 量价结构

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 量比 | `daily_basic.volume_ratio` | 无 | 缺失记中性 `3分` |
| 换手率 | `daily_basic.turnover_rate` | 无 | 缺失记中性 `3分` |
| 成交额分位 | `daily.amount` | 候选池内分位排名 | 缺失则剔除候选 |
| 放量质量 | 当日 `daily.amount` + 历史 `amount` | `volume_expand_5` | 缺历史时记中性 `2分` |

### 8.3 趋势位置与形态

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 均线结构 | 历史 `daily.close` | `MA5/MA10/MA20` | 历史不足时记中性 `2分` |
| 突破结构 | 历史 `daily.high` + 当日 `close/high` | `prev_20d_high`、`prev_60d_high` | 历史不足时记 `1分` |
| 连续强势状态 | 历史 `daily.pct_chg` | `cum_ret_5d`、`up_days_5d` | 历史不足时记 `1分` |

### 8.4 板块题材共振

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 板块涨幅排名 | `index_daily` | 行业涨幅排名 | 映射失败按回退值 |
| 板块涨停/大涨家数 | 行业内 `daily.pct_chg` + `stk_limit` | 板块 breadth 统计 | 映射失败按回退值 |
| 板块梯队完整度 | 行业内 `pct_chg/amount/close_position` | 板块梯队判定 | 映射失败按回退值 |
| 个股板块地位 | 行业内 `pct_chg/amount/close_position` | 行业内综合排序 | 映射失败按回退值 |

### 8.5 资金承接质量

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 主力净流入绝对额 | `moneyflow` 主力净流入额 | 候选池内排名 | 缺失记中性 `1分` |
| 主力净流入强度 | `moneyflow` + `daily.amount` | `main_inflow_ratio` | 缺失记中性 `1分` |
| 龙虎榜质量 | `top_list` | 上榜/净买入标签 | 未上榜按规则记 `1分` |
| 价资一致性 | `daily.pct_chg` + `moneyflow` | 方向一致性标签 | 资金缺失记中性 `1分` |

### 8.6 弹性与股性

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 流通市值弹性 | `daily_basic.circ_mv` | 无 | 缺失记中性 `1分` |
| 历史股性 | 历史 `daily.pct_chg` + `stk_limit` | `strong_days_60d`、`limit_up_days_60d` | 历史不足时记 `1分` |
| 短线辨识度 | 历史强势记录 + `top_list` | 近 20 日强势标记 | 缺失记 `0分` 或中性 `1分`，实现前定一版 |

## 9. Aggressive 评分项映射表

### 9.1 强势确认质量

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 涨停/准涨停强度 | `daily.close` + `stk_limit.up_limit` | `limit_proximity` | 缺失记中性 `4分` |
| 跳空高开强度 | 当日 `open` + 前一日 `close` | `gap_open_ratio` | 前收缺失则记中性 `3分` |
| 收盘地位 | `daily.open/high/low/close` | `close_position` | 按特殊值规则处理 |
| 加速确认 | 历史 `pct_chg` + `limit_proximity` | `cum_ret_3d` | 历史不足记 `0分` |

### 9.2 资金承接质量

与 Standard 共用字段，但权重和分档不同。

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 主力净流入绝对额 | `moneyflow` | 候选池内排名 | 缺失记中性 `2分` |
| 主力净流入强度 | `moneyflow` + `daily.amount` | `main_inflow_ratio` | 缺失记中性 `1分` |
| 价资一致性 | `daily.pct_chg` + `moneyflow` | 一致性标签 | 资金缺失记 `1分` |
| 龙虎榜质量 | `top_list` | 上榜/净买入标签 | 未上榜按规则记 `1分` |

### 9.3 买入可行性

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 日内振幅空间 | `daily.high/low/close` | `amplitude_ratio` | 缺失则该项记 `0分` |
| 成交额黄金区 | `daily.amount` | 无 | 缺失则剔除候选 |
| 换手率黄金区 | `daily_basic.turnover_rate` | 无 | 缺失记中性 `2分` |

### 9.4 量价双轨

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 缩量一致型 | `limit_proximity` + `volume_ratio` | 一致型标签 | 任一字段缺失记 `0分` |
| 健康换手型 | `volume_ratio` + `turnover_rate` + `amplitude_ratio` | 换手型标签 | 任一字段缺失记中性 `3分` |

### 9.5 板块题材共振

与 Standard 共用板块口径和中间特征，只是权重更低。

### 9.6 趋势位置与弹性

| 评分项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 突破结构 | 历史 `daily.high` + 当日 `close/high` | `prev_20d_high`、`prev_60d_high` | 历史不足记 `1分` |
| 流通市值弹性 | `daily_basic.circ_mv` | 无 | 缺失记中性 `1分` |
| 历史股性 | 历史 `daily.pct_chg` + `stk_limit` | `strong_days_60d`、`limit_up_days_60d` | 历史不足记 `0分` |

## 10. 风险修正映射表

### 10.1 Standard

| 风险项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 长上影 / 冲高回落 | `daily.open/high/low/close` | `upper_shadow_ratio` | 按特殊值规则 |
| 爆量滞涨 | `daily.amount` + 历史 `amount` + `close_position` | `volume_expand_5` | 缺历史记 `0分` |
| 尾盘走弱 | `daily.open/high/low/close` | `close_position` | 按特殊值规则 |
| 高位连续加速 | 历史 `pct_chg` | `cum_ret_3d`、`cum_ret_5d` | 历史不足记 `0分` |
| 板块退潮 | 行业板块数据 | 板块跟随标签 | 映射失败记 `-1` 或 `0`，实现前定稿 |
| 资金背离 | `daily.pct_chg` + `moneyflow` | 背离标签 | 资金缺失记 `0分` |
| 龙虎榜偏兑现 | `top_list` | 净卖出标签 | 未上榜记 `0分` |

### 10.2 Aggressive

| 风险项 | 原始字段 | 中间特征 | 缺失值处理 |
|---|---|---|---|
| 价资严重背离 | `daily.pct_chg` + `moneyflow` | 背离标签 | 资金缺失记 `0分` |
| 爆量滞涨 | `daily.amount` + 历史 `amount` + `close_position` | `volume_expand_5` | 缺历史记 `0分` |
| 长上影 / 冲高回落 | `daily.open/high/low/close` | `upper_shadow_ratio` | 按特殊值规则 |
| 板块退潮 | 行业板块数据 | 板块跟随标签 | 映射失败记 `0分` |

## 11. 输出字段映射表

| 输出字段 | 来源 | 说明 |
|---|---|---|
| `ts_code` | `stock_basic` / `daily` | 股票代码 |
| `name` | `stock_basic.name` | 股票名称 |
| `pct_chg` | `daily.pct_chg` | 今日涨幅 |
| `continuation_score` | 二级分数规则 | 两个 profile 均输出 |
| `extension_score` | 二级分数规则 | 两个 profile 均输出 |
| `risk_score` | 二级分数规则 | 两个 profile 均输出 |
| `buyability_score` | Aggressive 二级分数规则 | 仅 Aggressive 输出，Standard 可返回 `null` |
| `final_score` | 基础总分 - 风险修正 | 主评分 |
| `rank_score` | 二级分数排序公式 | 排名主依据 |
| `themes` | 申万一级行业 | `V1` 主板块 |
| `leader_level` | 板块内排序标签 | 龙头/前排/中位/后排 |
| `top_reasons` | 评分项高分标签 | 解释项 |
| `risk_tags` | 风险修正标签 | 风险项 |
| `score_breakdown` | 维度得分明细 | 维度拆解 |
| `profile` | 请求参数 | `standard` / `aggressive` |

## 12. 计算顺序建议

建议严格按以下顺序实现：

1. 拉取交易日和股票池
2. 执行候选池硬过滤
3. 拉取候选池当日主数据
4. 拉取候选池历史窗口数据
5. 构建公共中间特征
6. 构建行业映射和板块特征
7. 按 `profile` 计算维度得分
8. 计算风险修正
9. 计算二级分数
10. 计算 `final_score` 和 `rank_score`
11. 生成解释字段和风险标签

## 13. 当前待定实现项

以下点已足够进入开发，但在真正编码前建议再定一次：

- `短线辨识度` 缺失时到底记 `0` 还是中性 `1`
- `板块退潮` 在板块映射失败时是记 `0` 还是小额扣分
- `top_reasons` 的生成是按阈值标签还是按 Top 3 高分项
- `leader_level` 的切分是固定名次还是按百分位

## 14. 变更记录

### 2026-04-10

- 创建字段级实现映射表
- 固化 Standard 与 Aggressive 的公共特征集
- 固化评分项与接口、字段、缺失值处理的映射关系
- 固化推荐计算顺序
