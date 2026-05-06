# 首页个股分析 Tushare 6000 积分增强 SPEC

## 1. 文档信息

- 文档类型：工程 SPEC
- 当前状态：Draft
- 最近更新：2026-05-04
- 产品文档：[首页个股分析 Tushare 6000 积分增强产品文档](home-stock-analysis-tushare-enhancement-product-design.md)
- 适用范围：首页个股分析的 A 股增强数据层、LLM 上下文、报告详情字段和数据快照

## 2. 目标和非目标

### 2.1 目标

1. 在不改变首页主流程的前提下，增强 A 股个股分析所需的基本面、资金流、板块联动和筹码结构数据。
2. 复用现有后端分析链路，把增强数据注入 LLM prompt 和 context snapshot。
3. 复用已暴露的报告详情字段，第一阶段尽量减少前端改动。
4. 保持数据源 fail-open：Tushare 不可用时回退到现有 AkShare / fallback 能力。
5. 对接口权限、数据日期、字段缺失和降级原因做结构化记录。

### 2.2 非目标

- 不在本阶段重做首页 UI 或报告详情页信息架构。
- 不承诺港股、美股使用同一套 Tushare 6000 积分能力。
- 不接入独立权限接口，例如分钟、公告、新闻、港美股财报等。
- 不把资金流或筹码数据变成自动交易信号。
- 不修改现有分析 API 的必填参数和返回主结构。

## 3. 当前链路

当前首页个股分析链路可以概括为：

```mermaid
flowchart LR
  A["HomePage 股票输入"] --> B["stockPoolStore.submitAnalysis"]
  B --> C["analysisApi.analyzeAsync"]
  C --> D["/api/v1/analysis/analyze"]
  D --> E["StockAnalysisPipeline"]
  E --> F["DataFetcherManager"]
  F --> G["行情 / 基本面 / 筹码 / 板块 / 新闻"]
  G --> H["LLM 分析"]
  H --> I["报告存储与 context snapshot"]
  I --> J["报告详情 API"]
  J --> K["首页 ReportSummary / ReportMarkdown"]
```

关键现状：

- 前端首页入口在 `apps/dsa-web/src/pages/HomePage.tsx`。
- 前端异步分析调用在 `apps/dsa-web/src/api/analysis.ts` 和 `apps/dsa-web/src/stores/stockPoolStore.ts`。
- 后端主流程在 `src/core/pipeline.py`，已经调用实时行情、筹码、基本面、板块和综合情报。
- 数据源聚合入口在 `data_provider/base.py`，已有 `get_fundamental_context`、`get_capital_flow_context`、`get_board_context` 等能力。
- Tushare 适配入口在 `data_provider/tushare_fetcher.py`，已有资金流、同花顺板块、筹码和板块排名相关方法。
- 报告详情提取在 `api/v1/endpoints/analysis.py` 和 `src/utils/data_processing.py`，已经能暴露 `financial_report`、`dividend_metrics`、`belong_boards`、`sector_rankings`。

## 4. 外部数据权限假设

以下为 2026-05-04 根据 Tushare 官方文档整理的产品和工程假设，最终以实际 token 调用结果为准。

| 能力 | 接口 | 权限假设 | 更新/使用备注 |
| --- | --- | --- | --- |
| 每日估值、换手、股息率 | `daily_basic` | 至少 2000 积分，6000 覆盖 | 交易日 15:00-17:00 左右更新，适合盘后分析 |
| 财务指标 | `fina_indicator` | 至少 2000 积分，6000 覆盖 | 单股历史财务指标，适合补 ROE、毛利率、现金流 |
| 分红 | `dividend` | 以实际 token 权限为准 | 补最近分红、派息率和股息稳定性 |
| 业绩预告/快报 | `forecast`、`express` | 以实际 token 权限为准 | 补业绩事件和报告摘要 |
| THS 个股资金流 | `moneyflow_ths` | 6000 积分可调 | 每日盘后更新，适合盘后复盘 |
| DC 个股资金流 | `moneyflow_dc` | 至少 5000 积分，6000 覆盖 | 可与 THS 资金流互证 |
| 同花顺板块指数 | `ths_index` | 6000 积分可调 | 用于概念、行业、主题、特色指数元数据 |
| 同花顺板块成分 | `ths_member` | 6000 积分可调 | 用于个股所属板块和成分关系 |
| 每日筹码和胜率 | `cyq_perf` | 5000 积分级别可调，6000 覆盖 | 18:00-19:00 左右更新，补成本分位和胜率 |
| 每日筹码分布 | `cyq_chips` | 5000 积分级别可调，6000 覆盖 | 补价格区间持仓占比和筹码密集区 |

工程要求：

- 运行时必须把接口成功、权限不足、空数据、超时和异常分别记录。
- 文档权限与实际 token 不一致时，以实际 token 能力探测结果为准。
- 不把 6000 积分误认为独立权限接口的通行证。

## 5. 功能需求

### FR-1 基本面增强

后端应为 A 股个股分析补充：

- `valuation`：PE、PE TTM、PB、PS TTM、股息率、总市值、流通市值。
- `profitability`：ROE、扣非 ROE、ROA、ROIC、毛利率、净利率。
- `growth`：营收、净利润、扣非净利润、EPS、现金流相关指标。
- `financial_report`：最新报告期、公告日、财报摘要。
- `dividend_metrics`：最近分红、股息率、派息稳定性。

验收：

- A 股且 Tushare 可用时，`fundamental_context` 至少包含估值和财务指标两个 block。
- 旧数据必须带 `report_period` 或 `ann_date`，不得当成实时数据解释。
- `daily_basic` 和 `fina_indicator` 任一失败时，另一个成功结果仍可进入上下文。

### FR-2 资金流增强

后端应为 A 股个股分析补充：

- THS 当日资金流：`net_amount`、`net_d5_amount`、`buy_lg_amount_rate`、`buy_md_amount_rate`、`buy_sm_amount_rate`。
- DC 当日资金流：`net_amount`、`net_amount_rate`、`buy_elg_amount_rate`、`buy_lg_amount_rate`、`buy_md_amount_rate`、`buy_sm_amount_rate`。
- 多日趋势：近 3/5/10 个交易日主力净流入方向。
- 冲突解释：THS 与 DC 方向不一致时标记 `mixed_signal`。

验收：

- 资金流 block 应进入 LLM prompt，用于趋势预测和操作建议。
- 数据日期不是最近交易日时，必须标记 `stale`。
- 资金流缺失不影响报告生成。

### FR-3 板块联动增强

后端应为 A 股个股分析补充：

- 同花顺概念、行业、主题、特色指数归属。
- 所属板块成分数量和个股在板块中的相对表现。
- 个股相对板块强弱：`leading`、`aligned`、`lagging`、`isolated`。
- 板块排名和领先/落后板块解释。

验收：

- `belong_boards` 和 `sector_rankings` 优先从增强后的 Tushare + fallback 统一结构中提取。
- 同一股票属于多个板块时，应按板块强度、相关性和数据新鲜度排序。
- 板块数据失败时，报告保留个股自身分析。

### FR-4 筹码结构增强

后端应为 A 股个股分析补充：

- `winner_rate`：胜率。
- `weight_avg`：加权平均成本。
- `cost_percentiles`：5%、15%、50%、85%、95% 成本分位。
- `chip_distribution`：价格区间持仓占比、主要筹码密集区、上方套牢区。
- `chip_signal`：`supportive`、`neutral`、`overheated`、`pressure_heavy`。

验收：

- 筹码 block 应解释支撑位、压力位和追涨风险。
- `cyq_perf` 成功但 `cyq_chips` 失败时，仍输出成本分位和胜率。
- 筹码数据不是最近交易日时，必须降低信号强度。

### FR-5 透明度和可追踪快照

每个增强 block 都必须具备以下元信息：

```json
{
  "status": "complete",
  "source": "tushare",
  "api": "daily_basic",
  "as_of": "20260504",
  "updated_at": "2026-05-04T17:10:00+08:00",
  "fields": ["pe_ttm", "pb", "dv_ttm"],
  "warnings": []
}
```

状态枚举：

- `complete`：字段完整且数据日期可用。
- `partial`：接口成功但关键字段缺失。
- `fallback`：Tushare 不可用，使用其他数据源。
- `missing`：无可用数据。
- `stale`：数据日期落后于最近交易日。
- `permission_denied`：疑似积分或权限不足。
- `error`：接口异常或解析失败。

验收：

- context snapshot 中能定位每个 block 的来源、日期和状态。
- 报告详情可选展示这些元信息。
- 日志中不输出 token 或敏感配置。

## 6. 数据结构设计

### 6.1 `fundamental_context` 目标结构

```json
{
  "stock_code": "600519",
  "market": "cn",
  "enhanced_by_tushare": true,
  "coverage": {
    "fundamental": "complete",
    "capital_flow": "complete",
    "boards": "partial",
    "chip": "complete"
  },
  "valuation": {
    "status": "complete",
    "source": "tushare",
    "api": "daily_basic",
    "as_of": "20260504",
    "data": {
      "pe_ttm": 21.5,
      "pb": 7.8,
      "dv_ttm": 2.4,
      "total_mv": 188000000
    }
  },
  "profitability": {
    "status": "complete",
    "source": "tushare",
    "api": "fina_indicator",
    "report_period": "20251231",
    "data": {
      "roe": 31.2,
      "grossprofit_margin": 91.4,
      "netprofit_margin": 51.0
    }
  },
  "capital_flow": {
    "status": "complete",
    "source": "tushare",
    "apis": ["moneyflow_ths", "moneyflow_dc"],
    "as_of": "20260504",
    "data": {
      "ths_net_amount": 12345.6,
      "dc_net_amount": 11890.2,
      "net_d5_amount": 45678.9,
      "signal": "inflow_confirmed"
    }
  },
  "boards": {
    "status": "partial",
    "source": "tushare",
    "apis": ["ths_index", "ths_member"],
    "data": {
      "belong_boards": [],
      "sector_rankings": []
    },
    "warnings": ["部分板块排名来自 fallback 数据源"]
  },
  "chip": {
    "status": "complete",
    "source": "tushare",
    "apis": ["cyq_perf", "cyq_chips"],
    "as_of": "20260504",
    "data": {
      "winner_rate": 64.2,
      "weight_avg": 1690.3,
      "cost_50pct": 1688.0,
      "chip_signal": "supportive"
    }
  },
  "source_chain": []
}
```

### 6.2 API 详情字段

第一阶段优先复用已有字段：

- `financial_report`
- `dividend_metrics`
- `belong_boards`
- `sector_rankings`

后续可追加字段，但必须保持兼容：

- `capital_flow_metrics`
- `chip_metrics`
- `data_quality`
- `tushare_enhancement`

兼容要求：

- 新字段全部可选。
- 前端类型新增字段时使用 nullable / optional。
- 旧报告详情不因缺少新字段出错。

## 7. 实现方案

### 7.1 Provider 层

建议在现有 `data_provider/tushare_fetcher.py` 基础上补齐统一的 normalized 方法，或者新增薄适配层包装 Tushare 原始返回。

建议方法：

- `get_daily_basic_metrics(ts_code, trade_date=None, lookback_days=10)`
- `get_financial_indicator_summary(ts_code, periods=4)`
- `get_dividend_summary(ts_code, years=5)`
- `get_performance_event_summary(ts_code, periods=4)`
- `get_moneyflow_summary(ts_code, start_date, end_date)`
- `get_ths_board_membership(ts_code)`
- `get_chip_summary(ts_code, trade_date=None, lookback_days=10)`

Provider 层职责：

- 统一 TS code 格式和 A 股市场判断。
- 控制每个接口超时和重试。
- 把 pandas / dict 原始结果标准化为 JSON-safe dict。
- 不在 Provider 层生成投资结论，只输出事实和轻量信号。

### 7.2 DataFetcherManager 层

建议在 `data_provider/base.py` 的现有上下文聚合入口中接入增强数据。

优先级：

1. A 股 + Tushare token 可用：优先拉取 Tushare 增强数据。
2. Tushare 部分失败：保留成功 block，失败 block 走 fallback。
3. Tushare 不可用或非 A 股：使用现有数据源。
4. 所有数据不可用：返回 `missing` block，不抛出到主流程。

缓存建议：

- `daily_basic`、资金流、筹码：按 `ts_code + trade_date` 缓存。
- `fina_indicator`、分红、业绩事件：按 `ts_code + report_period` 或自然日缓存。
- `ths_index`：全量板块元数据可长 TTL 缓存。
- `ths_member`：按板块或个股映射缓存，需记录 `is_new`。

### 7.3 Pipeline 层

建议在 `src/core/pipeline.py` 复用现有节点：

- `get_fundamental_context`：承载估值、财务指标、分红、业绩事件。
- `get_capital_flow_context`：承载 THS/DC 个股资金流。
- `get_board_context`：承载同花顺板块和成分关系。
- `get_chip_distribution`：承载筹码和胜率。
- `_build_context_snapshot`：记录完整增强上下文。

Pipeline 层职责：

- 组合增强 block。
- 把关键证据送入 LLM prompt。
- 保存 snapshot 便于报告详情、回放和排障。
- 在异常时降低对应 block 状态，不中断整次分析。

### 7.4 LLM 上下文

Prompt 需要新增约束：

- 基本面证据必须区分报告期和交易日。
- 资金流证据必须区分 THS/DC，并说明冲突。
- 板块联动必须说明个股相对板块是领先、跟随、落后还是孤立。
- 筹码结构必须说明支撑、压力和追涨风险。
- 数据缺失时必须说明“未能确认”，不能臆造数值。

推荐输出结构：

1. 核心结论。
2. 价格与趋势。
3. 基本面底色。
4. 资金流确认。
5. 板块联动。
6. 筹码结构。
7. 操作建议。
8. 风险和数据缺口。

### 7.5 前端

Phase 1 不要求新增前端页面。

如需轻量展示，优先在已有报告详情区域中追加：

- 基本面摘要。
- 分红摘要。
- 所属板块和板块排名。
- 数据质量状态。

后续新增资金流和筹码卡片时，应先更新 `apps/dsa-web/src/types/analysis.ts`，再更新对应组件，确保旧报告兼容。

## 8. 错误处理

| 场景 | 处理方式 |
| --- | --- |
| 未配置 `TUSHARE_TOKEN` | 不调用 Tushare，使用现有 fallback，并标记 `fallback` |
| token 无权限或积分不足 | 捕获异常，标记 `permission_denied`，不阻断分析 |
| 接口超时 | 标记 `error` 或 `partial`，保留其他成功 block |
| 返回空表 | 标记 `missing`，记录接口、参数和日期 |
| 字段缺失 | 标记 `partial`，跳过缺失字段 |
| 数据日期过旧 | 标记 `stale`，降低信号强度 |
| 非 A 股股票 | 跳过 A 股专属增强，保留现有港股/美股链路 |

## 9. 测试方案

### 9.1 单元测试

- Tushare normalized 方法：mock 原始返回、空表、异常、权限错误。
- DataFetcherManager 聚合：验证成功、部分失败、无 token、非 A 股。
- `data_processing` 提取：验证 `financial_report`、`dividend_metrics`、`belong_boards`、`sector_rankings` 和新增字段兼容。
- Prompt 构建：验证缺失数据不会生成伪造字段。

### 9.2 集成测试

- 使用 mock Tushare client 跑完整首页分析 API。
- 验证 context snapshot 包含增强 block 和状态。
- 验证报告详情 API 兼容旧报告。
- 验证单接口失败时分析仍完成。

### 9.3 手工验证

- 无 `TUSHARE_TOKEN`：首页分析可以完成，报告说明基础模式。
- 6000 积分 token：A 股报告出现基本面、资金流、板块和筹码证据。
- 权限不足 token：报告完成且标记权限不足。
- 非 A 股股票：不触发 A 股专属增强。
- 盘前、盘中、盘后分别验证数据日期和 stale 状态。

## 10. 验收标准

1. A 股首页分析不改变输入和提交流程。
2. 配置可用 Tushare token 后，报告上下文至少包含基本面、资金流、板块、筹码四类 block 中的三类。
3. `financial_report`、`dividend_metrics`、`belong_boards`、`sector_rankings` 继续能从报告详情中读取。
4. 任一 Tushare 接口异常不阻断报告生成。
5. context snapshot 能追踪数据源、接口、日期、状态和降级原因。
6. 前端旧报告和非 A 股报告保持兼容。

## 11. 回滚方案

- 如果增强数据造成报告不稳定，可在 DataFetcherManager 层临时关闭 Tushare enhanced block，保留现有 fallback。
- 如果新增 API 字段造成前端问题，可仅停止返回新增可选字段，保留旧字段。
- 如果 LLM prompt 质量下降，可先回滚 prompt 增强，保留 snapshot 数据用于排查。
- 如果接口频率触达 Tushare 限制，可降低拉取范围、启用缓存或仅在盘后分析中启用资金流和筹码增强。

## 12. 参考资料

- Tushare 积分与频次权限对应表：https://tushare.pro/document/1?doc_id=290
- Tushare `daily_basic` 文档：https://tushare.pro/document/2?doc_id=32
- Tushare `fina_indicator` 文档：https://tushare.pro/document/2?doc_id=79
- Tushare `moneyflow_ths` 文档：https://tushare.pro/document/2?doc_id=348
- Tushare `moneyflow_dc` 文档：https://tushare.pro/document/2?doc_id=349
- Tushare `ths_index` 文档：https://tushare.pro/document/2?doc_id=259
- Tushare `ths_member` 文档：https://tushare.pro/document/2?doc_id=261
- Tushare `cyq_perf` 文档：https://tushare.pro/document/2?doc_id=293
- Tushare `cyq_chips` 文档：https://tushare.pro/document/2?doc_id=294
