# 强势筛选时序质量评分 — 技术开发文档

## 1. 文档信息

- 文档名称：强势筛选时序质量评分 — 技术开发文档
- 英文名称：Momentum Screener Temporal Quality Scoring — Technical Design
- 所属系统：`daily_stock_analysis`
- 文档类型：技术开发文档 / 实现设计
- 当前状态：`v1.0`
- 最后更新：`2026-07-01`
- 关联文档：
  - [时序质量评分 SPEC](./momentum-screener-temporal-quality-scoring-spec.md)
  - [时序质量评分产品设计](./momentum-screener-temporal-quality-product-design.md)
  - [二次决策 SPEC](./momentum-screener-secondary-decision-spec.md)
  - [V1.3 主线增强技术开发文档](./momentum-screener-v1-3-mainline-enhancement-technical-design.md)

## 2. 目标与边界

### 2.1 本次实现范围

1. 在 `_build_features()` 中新增 K 线走势质量和连续强势运计算特征
2. 新增两个独立评分方法：`_score_price_path_quality()` 和 `_score_sector_momentum()`
3. 将两个新维度接入 `_score_standard()` 和 `_score_aggressive()` 的权重计算
4. 新增题材统计快照缓存（落盘到 `data/cache/momentum_sector_stats/`）
5. 回测链路自动适配新维度（历史数据回放时题材缓存用同一套落盘逻辑）

### 2.2 本次明确不做

- 不修改候选池入口规则（最小涨幅 4%/最小成交额 2 亿/最小换手率 2%）
- 不修改二次决策的收口逻辑（主线/角色/买点/总闸门）
- 不修改 `_score_capital_support` 等现有维度的内部计算逻辑
- 不新增 API 接口或响应字段（新维度只影响排序，不对外暴露独立分）
- 不引入新的数据源或 API 调用

## 3. 实现设计

### 3.1 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|:---:|------|
| `src/services/momentum_screener_service.py` | 修改 | 主力改动文件 |
| 路径：`_build_features()` | 新增 | 补充 K 线走势质量特征 |
| 路径：新增 `_score_price_path_quality()` | 新增 | 走势质量评分方法 |
| 路径：新增 `_score_sector_momentum()` | 新增 | 题材时序动量评分方法 |
| 路径：新增 `_load_sector_stats_cache()` | 新增 | 题材缓存读写 |
| 路径：`_score_standard()` | 修改 | 接入新维度权重 |
| 路径：`_score_aggressive()` | 修改 | 接入新维度权重 |
| `data/cache/momentum_sector_stats/` | 新增 | 题材统计快照缓存目录 |

### 3.2 新增特征：K 线走势质量相关

在 `_build_features()` 的 return dict 中新增以下字段，计算完全基于已有的 `history` DataFrame：

```python
{
    # === 连续强势运行 ===
    "consecutive_yang": int,         # 从今天往回连续收阳天数
    "ma5_above_days": int,           # 过去5日中收盘 > MA5 的天数
    "ma10_above_days": int,          # 过去10日中收盘 > MA10 的天数
    "close_to_ma5_ratios": [float],  # 过去5日每天的 close/MA5（用于驾驭/依附判别）
    "volatility_5d": float,           # 过去5日年化波动率

    # === 温和上行结构 ===
    "segments": {                    # 远(D[-20:-11]) 中(D[-10:-6]) 近(D[-5:-1]) 三段
        "far": {"return": float, "max_dd": float, "avg_amp": float},
        "mid": {"return": float, "max_dd": float, "avg_amp": float},
        "near": {"return": float, "max_dd": float, "avg_amp": float},
    },

    # === 量能节奏 ===
    "vol_5d_avg": float,            # 近5日平均量
    "vol_prev_5d_avg": float,       # 前10天中前5日平均量（D[-10:-6]）
    "cum_ret_5d_direction": float,  # 近5日累计涨跌幅

    # === 强度密度 ===
    "strong_day_indices": [int],     # 过去60日中大涨日（pct>=7）距今天的天数（最大的几个值）
}
```

### 3.3 新增评分方法：`_score_price_path_quality()`

```python
def _score_price_path_quality(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
```

**输入**：`features` 中包含上述新增字段

**内部四个子项**：

#### 子项 1：连续强势运行（份内权重 20%）

```python
ma5_score   = ma5_above_days / 5 * 0.4
ma10_score  = ma10_above_days / 10 * 0.3
yang_score  = min(consecutive_yang, 5) / 5 * 0.3
combined    = ma5_score + ma10_score + yang_score

# 稳定因子
stability = 1.0 - min(1.0, volatility_5d / 0.05)

# 驾驭/依附判别：过去3日中有 >=2 天 close/MA5 > 1.02 且今日满足 -> 驾驭
close_ratios = features["close_to_ma5_ratios"][-3:]
if sum(1 for r in close_ratios if r > 1.02) >= 2 and close_ratios[-1] > 1.02:
    ratio_bonus = 1.2
elif sum(1 for r in close_ratios if r < 1.01) > len(close_ratios) / 2:
    ratio_bonus = 0.8
else:
    ratio_bonus = 1.0

final = clamp(combined * stability * ratio_bonus, 0, 1)
```

#### 子项 2：温和上行结构（份内权重 35%）

三段区间评分规则：

| 条件 | 得分 |
|------|:---:|
| 三段 return 均 > 0，且 `far.max_dd < 0.05` 且 `mid.max_dd < 0.04` 且 `near.max_dd < 0.03` | 满分 |
| 近段 return > 0 且回撤受控，但远段 return <= 0 | 中高（反转） |
| 三段 return 均 > 0 但某段振幅 > 0.08 | 中（筹码不稳） |
| 近段 return > 0 但已减速（近段 return < 中段 return * 0.5） | 中低 |
| 近段 return <= 0 | 低 |

```python
# 先对各段打分 0-100，再按份内权重加权
far_score  = _score_segment(far, is_far=True)
mid_score  = _score_segment(mid, is_far=False)
near_score = _score_segment(near, is_far=False)
segment_total = far_score * 0.25 + mid_score * 0.30 + near_score * 0.45
```

#### 子项 3：量能节奏配合（份内权重 25%）

```python
vol_ratio = features["vol_5d_avg"] / max(features["vol_prev_5d_avg"], 1.0)
ret_5d = features["cum_ret_5d_direction"]

if vol_ratio >= 1.2 and ret_5d >= 5:
    score = 1.0       # 量增价涨
elif vol_ratio <= 0.8 and ret_5d >= 3:
    score = 0.7       # 量缩价涨（惜售）
elif vol_ratio >= 1.2 and ret_5d <= -2:
    score = 0.2       # 量增价跌
elif vol_ratio <= 0.8 and ret_5d <= -2:
    score = 0.4       # 量缩价跌
else:
    score = 0.5       # 中性
```

#### 子项 4：强度密度（份内权重 20%）

```python
indices = features["strong_day_indices"]  # 距今天的天数，如 [2, 8, 22]
if len(indices) < 3:
    score = 0.5
else:
    gaps = [indices[i] - indices[i+1] for i in range(len(indices)-1)]
    if all(g < 0 for g in gaps):  # 间隔在缩短（加速）
        score = 1.0
    elif indices[0] > 10:  # 最近一次大涨距今 > 10天
        score = 0.3
    elif gaps[0] > gaps[1] * 1.5:  # 最近间隔明显拉长
        score = 0.4
    else:
        score = 0.7
```

**汇总**：

```python
sub_total = (
    strong_run_score * 0.20 +
    segment_score * 0.35 +
    volume_rhythm_score * 0.25 +
    density_score * 0.20
)
# 输出 max_score=12（对应12%总权重，实际得分为 sub_total * 12）
return {"score": round(sub_total * 12, 2), "max_score": 12, "items": {...}}
```

### 3.4 题材统计快照缓存设计

**存储位置**：`data/cache/momentum_sector_stats/{trade_date}.json`

**数据结构**：一个 JSON dict，key 为 sector_name，value 为数组（按 trade_date 逆序排列）：

```json
{
  "储存与物流": [
    {"trade_date": "2026-07-01", "sector_rank": 3, "sector_total": 86, "strong_count": 8, "limit_count": 2, "avg_pct": 3.45},
    {"trade_date": "2026-06-22", "sector_rank": 5, "sector_total": 82, "strong_count": 6, "limit_count": 1, "avg_pct": 2.87}
  ]
}
```

**写入时机**：在 `_score_standard()` 或 `_score_aggressive()` 中，**首次处理某个 trade_date 时**，将当天的 `sector_stats` 追加到缓存文件。

**读取逻辑** `_load_sector_stats_cache(sector_name, trade_date, days=5)`：

```python
def _load_sector_stats_cache(self, sector_name, end_trade_date, days):
    # 1. 计算需要回看的日期范围（向前找 days 个有效交易日）
    # 2. 逐一读取对应日期的 JSON 缓存
    # 3. 返回按日期排列的列表
    # 4. 文件不存在 -> 返回空列表
```

注意：缓存 key 是 sector_name，一个 JSON 文件可能包含多个 sector。为减少文件数量，用一个文件覆盖所有 sector：

**改为单文件方案**：`data/cache/momentum_sector_stats/{trade_date}.json` 存储当天所有 sector 的快照：

```json
{
  "trade_date": "2026-07-01",
  "sectors": {
    "储存与物流": {"sector_rank": 3, "sector_total": 86, "strong_count": 8, "limit_count": 2, "avg_pct": 3.45},
    "...": {}
  }
}
```

读取时打开对应日期的文件，提取目标 sector。

### 3.5 新增评分方法：`_score_sector_momentum()`

```python
def _score_sector_momentum(self, row: pd.Series, features: Dict[str, Any], trade_date: str) -> Dict[str, Any]:
```

**输入**：`features["sector"]` + `features["sector_stats"]` + 从缓存读取的历史数据

**内部两个子项**：

#### 子项 1：排名趋势

```python
recent = self._load_sector_stats_cache(sector, trade_date, days=3)
if len(recent) < 2:  # 无历史缓存
    rank_score = 0.5  # 中性
else:
    ranks = [r["sector_rank"] for r in recent]
    if ranks[0] < ranks[1] < ranks[2] and ranks[0] <= 10:
        rank_score = 1.0   # 持续上升+进前10
    elif ranks[0] < ranks[1] < ranks[2]:
        rank_score = 0.8   # 持续上升
    elif ranks[0] == ranks[1] <= 5:
        rank_score = 0.8   # 维持高位
    elif ranks[0] == ranks[1]:
        rank_score = 0.6   # 维持中位
    elif ranks[0] - ranks[1] > 5:
        rank_score = 0.2   # 高位跌落
    else:
        rank_score = 0.5
```

#### 子项 2：扩散/收缩

```python
if len(recent) < 2:
    spread_score = 0.5
else:
    curr = features["sector_stats"]["strong_count"]
    prev = recent[1]["strong_count"]
    rank_curr = features["sector_stats"]["sector_rank"]
    rank_prev = recent[1]["sector_rank"]

    if curr > prev and rank_curr < rank_prev:
        spread_score = 1.0    # 共振扩散
    elif curr > prev:
        spread_score = 0.7    # 基数扩大
    elif curr <= prev and rank_curr < rank_prev:
        spread_score = 0.6    # 龙头聚焦
    elif curr < prev and rank_curr > rank_prev:
        spread_score = 0.2    # 退潮
    else:
        spread_score = 0.5
```

**汇总**：

```python
sub_total = rank_score * 0.5 + spread_score * 0.5
return {"score": round(sub_total * 10, 2), "max_score": 10, "items": {...}}
```

### 3.6 接入现有评分方法

#### `_score_standard()` 修改

```python
# 在现有 break 之后增加两个新维度
breakdown = {
    "strength_confirmation": ...,
    "volume_price_structure": ...,
    "trend_position": ...,
    "sector_resonance": ...,
    "capital_support": ...,
    "elasticity_activity": ...,
    "price_path_quality": self._score_price_path_quality(row, features),       # 新增
    "sector_momentum": self._score_sector_momentum(row, features, trade_date), # 新增
}
```

`continuation_score` 和 `extension_score` 中接入新维度权重。新的加权公式：

```python
continuation_score = (
    (breakdown["strength_confirmation"]["score"] / 20.0) * 0.22    # 旧 0.28
    + (breakdown["volume_price_structure"]["score"] / 18.0) * 0.22 # 旧 0.27
    + (breakdown["sector_resonance"]["score"] / 25.0) * 0.22       # 旧 0.25
    + (breakdown["capital_support"]["score"] / 17.0) * 0.18        # 旧 0.20
    + (breakdown["price_path_quality"]["score"] / 12.0) * 0.16     # 新
) * 100
extension_score = (
    (breakdown["trend_position"]["score"] / 12.0) * 0.32           # 旧 0.38
    + (breakdown["sector_resonance"]["score"] / 25.0) * 0.28       # 旧 0.34
    + (breakdown["elasticity_activity"]["score"] / 8.0) * 0.22     # 旧 0.28
    + (breakdown["sector_momentum"]["score"] / 10.0) * 0.18        # 新
) * 100
```

`_score_aggressive()` 同理调整。权重分配见 SPEC 3.3 节。

### 3.7 特征计算的数据依赖

所有新特征基于 `history` DataFrame（已有 80 天日 K，在 `_build_features()` 中已加载）。不新增任何数据拉取。

| 特征 | 计算方式 | 时间复杂度 |
|------|------|:---:|
| `consecutive_yang` | 从最新行往回遍历 pct_chg > 0 | O(n) |
| `ma5_above_days` / `ma10_above_days` | `sum(close.tail(N) > close.tail(N).rolling(N).mean())` | O(N) |
| `close_to_ma5_ratios` | 直接除 | O(N) |
| `volatility_5d` | `close.tail(5).pct_change().std() * sqrt(252)` | O(N) |
| `segments` | 对三段的 pct_change 分别计算 return / min / std | O(N) |
| `vol_5d_avg` / `vol_prev_5d_avg` | mean | O(N) |
| `strong_day_indices` | 遍历 pct_series.tail(60) 找 >= 7 的索引 | O(N) |

全部 O(N) 且 N <= 60，对全市场 1000+ 只股票的总计算量完全可忽略。

### 3.8 回测兼容性

回测链路中使用 `_evaluate_strategy_health_trade_date()` 调用 `screener_service.screen(trade_date=...)` 进行历史重放。当 `trade_date` 是过去日期时：

1. 题材统计快照缓存按历史日期写入（与实时路径一致）
2. 第一次回测到某天时缓存不存在，`sector_momentum` 得中性分
3. 之后再次回测同一天时，缓存命中，完全复现

回测结果中 `price_path_quality` 得分可直接对比新老版本的排序差异。

## 4. 实现顺序

1. **Phase 1**：扩展 `_build_features()` 新增特征字段（不改变现有方法签名）
2. **Phase 2**：实现 `_score_price_path_quality()` 和 `_score_sector_momentum()`
3. **Phase 3**：实现 `_load_sector_stats_cache()` 和缓存落盘
4. **Phase 4**：修改 `_score_standard()` 和 `_score_aggressive()` 接入新维度
5. **Phase 5**：回测验证、权重微调
6. **Phase 6**：清理临时日志

## 5. 配置项

以下常量添加到 `momentum_screener_service.py` 顶部：

```python
# === 时序质量评分配置 ===
SECTOR_STATS_CACHE_TTL = timedelta(days=30)
SECTOR_STATS_CACHE_DIRNAME = "momentum_sector_stats"
PRICE_PATH_QUALITY_MAX_SCORE = 12.0          # 对应 12% 总权重
SECTOR_MOMENTUM_MAX_SCORE = 10.0             # 对应 10% 总权重
CONSECUTIVE_YANG_MAX_LOOKBACK = 5            # 连阳统计最大回看天数
MA5_ABOVE_WINDOW = 5                         # MA5 上方统计窗口
MA10_ABOVE_WINDOW = 10                       # MA10 上方统计窗口
STRONG_DAY_THRESHOLD_PCT = 7.0               # 大涨阈值
STRONG_DAY_LOOKBACK = 60                     # 大涨统计回看天数
```