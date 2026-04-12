# Architecture Docs Index

## 次日强势股筛选文档索引

本文档用于汇总 `daily_stock_analysis` 中“次日强势股筛选”产品线的相关设计文档，便于后续新会话、开发实现和迭代维护时快速定位上下文。

## 文档清单

### 1. 产品方案与版本规划

- [次日强势股筛选产品方案](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-product-plan.md)

用途：

- 记录产品目标
- 记录 `V1 / V1.5 / V2` 版本规划
- 记录 Tushare 权限映射
- 记录升级路线和维护规则

### 2. 产品需求文档 PRD

- [次日强势股筛选 PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-prd.md)

用途：

- 记录用户场景
- 记录页面结构
- 记录输入输出设计
- 记录核心交互流程

### 3. Standard 评分规则

- [次日强势股筛选 V1 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)
- [次日强势股筛选二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-score-rules.md)

用途：

- 固化标准版 `V1` 评分维度
- 固化每个评分项的打分逻辑
- 固化 `continuation_score / extension_score / risk_score`

### 4. Aggressive 评分规则

- [次日强势股筛选 V1-Aggressive 评分规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)
- [次日强势股筛选 V1-Aggressive 二级分数规则](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-aggressive-secondary-score-rules.md)

用途：

- 固化进攻型评分规则
- 固化 `buyability_score`
- 固化进攻型排序公式

### 5. 两套规则差异对照

- [次日强势股筛选规则画像对照表](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-rule-profiles-comparison.md)

用途：

- 对比 `standard` 与 `aggressive`
- 供前端做模式切换
- 供后端做 profile 参数化

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

## 推荐阅读顺序

如果是第一次接手这条产品线，建议按以下顺序阅读：

1. 产品方案
2. PRD
3. 规则画像对照表
4. Standard 评分规则
5. Aggressive 评分规则
6. 字段级实现映射
7. 开发任务拆分

## 当前产品决策

当前已确定：

- 产品采用 `V1 + 可切换 Aggressive`
- `standard` 作为默认画像
- `aggressive` 作为进攻型可选画像
- `V1` 板块口径固定为申万一级行业

## 维护建议

后续若继续迭代，请优先同步更新以下文档：

- 规则变更：更新评分规则文档
- 页面变更：更新 PRD
- 接口字段变更：更新字段级实现映射表
- 版本规划变化：更新产品方案
- 实现拆分变化：更新开发任务拆分文档
## Additional Docs

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

- [Momentum Screener Secondary Decision SPEC](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-spec.md)
- [Momentum Screener Secondary Decision PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-prd.md)
- [Momentum Screener Secondary Decision Technical Design](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-decision-technical-design.md)
