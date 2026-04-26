# Architecture Docs Index

## 次日强势股筛选文档索引

本文档用于汇总 `daily_stock_analysis` 中“次日强势股筛选”产品线的相关设计文档，便于后续新会话、开发实现和迭代维护时快速定位上下文。

## 文档清单

### 1. 产品方案与版本规划

- [次日强势股筛选产品方案](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-product-plan.md)

用途：

- 记录产品目标
- 记录 `V1 / V1.3 / V1.5 / V2` 版本规划
- 记录 Tushare 权限映射
- 记录升级路线和维护规则

### 2. 产品需求文档 PRD

- [次日强势股筛选 PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-prd.md)
- [强势筛选 V1 产品原则 + 总闸门规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-product-principles-and-gate-rules.md)
- [强势筛选 V1.3 主线增强版产品设计](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-mainline-enhancement-product-design.md)
- [强势筛选 V1.3 主线增强版技术开发文档](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-mainline-enhancement-technical-design.md)
- [强势筛选 V1.3 主线增强版开发任务清单](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-development-tasks.md)

用途：

- 记录用户场景
- 记录页面结构
- 记录输入输出设计
- 记录核心交互流程
- 记录 V1 入口标准、画像边界与总闸门规则
- 记录 V1.3 在 6000 积分数据权限下的主线增强、短线情绪、盘中快照辅助和回测诊断边界
- 记录 V1.3 的数据适配、缓存、服务层、API、前端、回测和 AI 点评实现方案
- 记录 V1.3 的里程碑拆分、文件落点、测试验收和最小可交付范围

### 3. Standard 评分规则

- [次日强势股筛选 V1 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)
- [次日强势股筛选二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-score-rules.md)

用途：

- 固化标准版 `V1` 评分维度
- 固化每个评分项的打分逻辑
- 固化 `continuation_score / extension_score / risk_score`

### 4. Aggressive 补充观察规则

- [次日强势股筛选 V1-Aggressive 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)
- [次日强势股筛选 V1-Aggressive 二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-aggressive-secondary-score-rules.md)

用途：

- 固化进攻型评分规则
- 固化 `buyability_score`
- 固化进攻补充观察层的排序公式
- 说明 `Aggressive` 只做补充观察，不作为第二套官方答案

### 5. 两套规则差异对照

- [次日强势股筛选规则画像对照表](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-rule-profiles-comparison.md)

用途：

- 对比 `standard` 与 `aggressive`
- 供前端解释官方主链路与补充观察层的边界
- 供后端保留补充观察层 profile 参数化

### 6. 字段级实现映射

- [次日强势股筛选字段级实现映射表](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-field-mapping.md)

用途：

- 记录接口与字段来源
- 记录中间特征
- 记录缺失值处理
- 记录推荐计算顺序

### 7. 开发任务拆分

- [次日强势股筛选开发任务拆分](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-development-tasks.md)

用途：

- 把产品设计拆成开发任务
- 供后端、前端、测试协作执行

### 8. 回测验收与诊断

- [强势筛选 V1 回测验收标准](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-backtest-acceptance-criteria.md)
- [强势筛选 V1 回测与问题诊断框架](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-and-diagnosis-framework.md)
- [强势筛选 V1 回测数据口径与结果面板设计](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-metrics-and-dashboard.md)

用途：

- 固定 60 交易日官方验收窗口
- 固定短线延续合格率、相对基准、风险和总闸门验收标准
- 供其他开发者按同一套口径输出回测诊断报告

## 推荐阅读顺序

如果是第一次接手这条产品线，建议按以下顺序阅读：

1. 产品方案
2. PRD
3. 规则画像对照表
4. Standard 评分规则
5. Aggressive 评分规则
6. 字段级实现映射
7. 回测验收标准
8. 开发任务拆分

## 当前产品决策

当前已确定：

- 产品采用 `V1 Standard 官方链路 + Aggressive 折叠补充观察层`
- `standard` 是唯一官方主引擎
- `aggressive` 只作为进攻补充观察层，不输出第二套官方组合
- `V1` 板块口径固定为申万一级行业
- `V1` 候选池入口固定为全市场统一 `4 / 2亿 / 2%`
- `V1` 官方页面展示固定为 `Top30`
- `V1` 普通用户不可调整入口参数，不保留研究模式
- `V1` 官方回测只回放 `Standard` 生产链路
- `V1` 回测验收以 60 交易日为标准窗口，主胜率统一使用 `短线延续合格率`
- `V1` 总闸门采用 `市场环境 × 当日机会质量` 主矩阵，并由 `20日进攻许可` 做动作封顶；`60日主线可信度` 只做结构提示
- `V1.3` 基于 6000 积分升级主线增强能力，接入题材成分、涨停炸板、涨跌停价和热榜证据，但不承诺分钟级买点

## 维护建议

后续若继续迭代，请优先同步更新以下文档：

- 规则变更：更新评分规则文档
- 页面变更：更新 PRD
- 接口字段变更：更新字段级实现映射表
- 回测诊断口径变更：更新回测验收标准
- 版本规划变化：更新产品方案
- 实现拆分变化：更新开发任务拆分文档
## Additional Docs

- [Momentum Screener V1 Backtest and Diagnosis Framework](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-and-diagnosis-framework.md)
- [Momentum Screener V1 Backtest Acceptance Criteria](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-backtest-acceptance-criteria.md)
- [Momentum Screener V1 Backtest Metrics and Dashboard Design](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-metrics-and-dashboard.md)
- [Momentum Screener V1 Backtest Data and API Draft](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-data-and-api-draft.md)
- [Momentum Screener V1 Development Refactor Checklist](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-development-refactor-checklist.md)
- [Momentum Screener V1 Backtest Development Tasks](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-backtest-development-tasks.md)
- [Momentum Screener Launch Readiness](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-launch-readiness.md)
- [Momentum Screener Internal Beta Notes](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-internal-beta-notes.md)
- [Momentum Screener Release Notes](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-release-notes.md)
- [Momentum Screener Commit Scope](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-commit-scope.md)
- [Momentum Screener PR Summary](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pr-summary.md)
- [Momentum Screener Final Release Summary](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-final-release-summary.md)
- [Momentum Screener PR Body](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pr-body.md)
- [Momentum Screener Functional Test Checklist](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-functional-test-checklist.md)
- [Momentum Screener Pressure Test Template](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pressure-test-template.md)
- [Momentum Screener Functional Test Report 2026-04-11](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-functional-test-report-2026-04-11.md)
- [Momentum Screener Pressure Test Report 2026-04-11](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-pressure-test-report-2026-04-11.md)

## Secondary Decision Docs

- [Momentum Screener New Gate Rules Draft](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-new-gate-rules-draft.md)
- [Momentum Screener Secondary Decision SPEC](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-spec.md)
- [Momentum Screener Secondary Decision PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-prd.md)
- [Momentum Screener Secondary Decision Technical Design](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-technical-design.md)
- [Momentum Screener Secondary Decision Development Tasks](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-development-tasks.md)
- [Momentum Screener V1.3 Mainline Enhancement Product Design](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-mainline-enhancement-product-design.md)
- [Momentum Screener V1.3 Mainline Enhancement Technical Design](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-mainline-enhancement-technical-design.md)
- [Momentum Screener V1.3 Development Tasks](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-3-development-tasks.md)
