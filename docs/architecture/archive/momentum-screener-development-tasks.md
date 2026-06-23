# 次日强势股筛选开发任务拆分

## 1. 文档信息

- 文档名称：次日强势股筛选开发任务拆分
- 所属系统：`daily_stock_analysis`
- 文档类型：开发任务清单
- 当前状态：草案 V1
- 关联文档：
  - [Architecture Docs Index](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\README.md)
  - [次日强势股筛选 PRD](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-prd.md)
  - [次日强势股筛选字段级实现映射表](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-field-mapping.md)

## 2. 开发目标

将“次日强势股筛选”从产品设计落地为可运行的系统能力，支持：

- `standard` 默认画像
- `aggressive` 可切换画像
- 收盘后候选池筛选
- 多维评分和排序
- 页面展示与解释输出

## 3. 总体开发顺序

建议顺序：

1. 后端数据与特征层
2. 后端评分引擎
3. API 与 Schema
4. 前端页面与 profile 切换
5. 测试与验证

## 4. 后端任务拆分

### 4.1 数据接入层

任务目标：

- 从 Tushare 拉取候选池和评分所需主数据

任务项：

- 封装 `daily` 拉取逻辑
- 封装 `stock_basic` 拉取逻辑
- 封装 `daily_basic` 拉取逻辑
- 封装 `moneyflow` 拉取逻辑
- 封装 `top_list` 拉取逻辑
- 封装 `stk_limit` 拉取逻辑
- 封装 `index_classify / index_member_all / index_daily` 拉取逻辑

交付结果：

- 可复用的数据获取函数
- 统一错误处理与缓存策略

### 4.2 候选池过滤层

任务目标：

- 实现硬过滤规则

任务项：

- 今日涨幅阈值过滤
- ST 过滤
- 主板过滤
- 新股过滤
- 最低成交额过滤
- 最低换手率过滤

交付结果：

- 候选池构建函数
- 候选池统计信息

### 4.3 特征构建层

任务目标：

- 统一计算中间特征，供两套 profile 共用

任务项：

- 计算 `close_position`
- 计算 `limit_proximity`
- 计算 `body_ratio`
- 计算 `upper_shadow_ratio`
- 计算 `gap_open_ratio`
- 计算 `amplitude_ratio`
- 计算 `volume_expand_5`
- 计算 `main_inflow_ratio`
- 计算 `prev_20d_high / prev_60d_high`
- 计算 `cum_ret_3d / cum_ret_5d / up_days_5d`
- 计算 `strong_days_60d / limit_up_days_60d`
- 构建行业映射与板块特征

交付结果：

- 公共特征对象
- 缺失值处理结果

### 4.4 评分规则层

任务目标：

- 按 profile 计算维度得分、风险分和排序分

任务项：

- 实现 `standard` 评分器
- 实现 `aggressive` 评分器
- 实现风险修正
- 实现二级分数：
  - `continuation_score`
  - `extension_score`
  - `risk_score`
  - `buyability_score`（仅 aggressive）
- 实现 `final_score` 与 `rank_score`

交付结果：

- `profile=standard/aggressive` 的可切换评分引擎

### 4.5 输出解释层

任务目标：

- 生成用户可读的解释字段

任务项：

- 生成 `top_reasons`
- 生成 `risk_tags`
- 生成 `leader_level`
- 生成板块标签
- Aggressive 模式下生成：
  - `buyability_score`
  - `opportunity_tag`
  - 可选 `entry_range_low / entry_range_high`

交付结果：

- 最终输出对象

## 5. API 任务拆分

### 5.1 路由与请求设计

建议新增筛选接口，例如：

- `POST /api/v1/stocks/screener/momentum`

任务项：

- 设计请求参数
- 增加 `profile` 参数
- 增加 `trade_date` 参数
- 增加筛选阈值参数

### 5.2 响应 Schema

任务项：

- 设计结果列表 Schema
- 设计维度拆解 Schema
- 设计市场概况 Schema

关键响应字段：

- `profile`
- `trade_date`
- `candidate_count`
- `results`
- `score_breakdown`
- `top_reasons`
- `risk_tags`

## 6. 前端任务拆分

### 6.1 页面骨架

任务目标：

- 增加独立页面，例如 `/screener`

任务项：

- 新建页面组件
- 接入路由
- 接入侧边栏入口

### 6.2 条件区

任务项：

- 涨幅阈值输入
- TopN 输入
- 市场范围选择
- 最低成交额输入
- 最低换手率输入
- `profile` 切换控件

### 6.3 结果区

任务项：

- 排名表格
- 分数字段展示
- profile 差异展示
- 单股详情侧栏/抽屉

### 6.4 Profile 差异展示

任务项：

- `standard` 展示：
  - continuation
  - extension
  - risk
  - final/rank
- `aggressive` 额外展示：
  - buyability
  - opportunity 标签
  - 可选买入区间

## 7. 测试任务拆分

### 7.1 单元测试

任务项：

- 中间特征计算测试
- 各维度打分测试
- 风险修正测试
- 二级分数公式测试

### 7.2 集成测试

任务项：

- 接口参数测试
- profile 切换测试
- 缺失值处理测试
- 候选池过滤测试

### 7.3 回归测试

任务项：

- Standard 结果稳定性校验
- Aggressive 结果差异校验
- 输出字段兼容性校验

## 8. 实现优先级

### P0

- 数据接入层
- 候选池过滤
- 公共特征层
- Standard 评分器
- 基础 API

### P1

- Aggressive 评分器
- 前端 profile 切换
- 解释字段

### P2

- 买入区间输出
- 快照保存
- 与回测页打通

## 9. 推荐交付顺序

最小可交付顺序建议：

1. 完成 Standard 后端能力
2. 完成 Standard 页面
3. 接入 Aggressive profile
4. 增加解释字段和增强输出

## 10. 验收标准

至少应满足：

- 可按交易日生成候选池
- 可按 `profile` 返回不同排序结果
- 前端可切换 `standard/aggressive`
- 结果中可展示评分拆解和风险标签
- 输出字段与文档一致

## 11. 待补充项

开发前仍建议再定稿以下细节：

- 是否首版即支持结果保存
- 是否首版即展示买入区间
- `leader_level` 与 `top_reasons` 的最终生成方式
- 是否首版支持创业板/科创板切换

## 12. 变更记录

### 2026-04-10

- 创建开发任务拆分文档
- 完成后端、API、前端、测试任务拆分
- 确定 `V1 + 可切换 Aggressive` 的实现优先级
