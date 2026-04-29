# 强势筛选 V1.3 主线增强版开发任务清单

## 1. 文档信息

- 文档名称：强势筛选 V1.3 主线增强版开发任务清单
- 英文名称：Momentum Screener V1.3 Development Tasks
- 所属系统：`daily_stock_analysis`
- 文档类型：开发任务清单 / 实施顺序清单
- 当前状态：`draft v0.1`
- 最后更新：`2026-04-24`
- 关联文档：
  - [强势筛选 V1.3 主线增强版产品设计](./momentum-screener-v1-3-mainline-enhancement-product-design.md)
  - [强势筛选 V1.3 主线增强版技术开发文档](./momentum-screener-v1-3-mainline-enhancement-technical-design.md)
  - [强势筛选二次决策与执行辅助 SPEC](./momentum-screener-secondary-decision-spec.md)
  - [强势筛选二次决策与执行辅助技术开发文档](./momentum-screener-secondary-decision-technical-design.md)

## 2. 文档目标

本清单把 V1.3 主线增强版从技术方案继续拆成可执行研发任务，供后端、前端、回测、AI 点评和测试按顺序推进。

重点回答：

1. 先开发哪一层，后开发哪一层。
2. 每一层具体改哪些文件。
3. 每个阶段交付什么可验证结果。
4. 哪些任务必须先完成，哪些可以后置。

一句话：

**V1.3 的开发顺序必须先补数据底座，再接规则，再接页面和回测，最后接 AI 解释。**

## 3. 总体实施原则

- 先保证 V1 官方链路稳定，再增加 V1.3 增强字段。
- 先做 `Standard` 官方主链路，不让 `Aggressive` 参与官方 Top3。
- 先做数据可用性和降级，再做主线评分。
- 先做可解释的简单加权，不一开始引入复杂模型。
- 先让回测能诊断问题，再追求分数最优。
- 所有新增字段默认可选，前端必须兼容旧响应。
- 任一增强数据源失败，不得拖垮强势筛选主链路。

## 4. 推荐实施顺序

推荐按以下顺序开发：

1. `M0` 文档与字段冻结
2. `M1` Tushare V1.3 数据适配
3. `M2` V1.3 数据聚合、缓存与任务化执行基础
4. `M3` 主线识别与主线评分
5. `M4` 短线情绪总闸门
6. `M5` 角色增强与官方 Top3 收口
7. `M6` API / Schema / TypeScript 类型
8. `M7` 前端主线雷达与短线情绪
9. `M8` 盘中快照辅助
10. `M9` 回测诊断升级
11. `M10` AI 点评上下文与护栏
12. `M11` 测试、部署和 60 交易日诊断报告

### 4.1 当前需求池（2026-04-27 冻结）

为避免后续实现再次被“影子分增强”“页面体验补丁”或“局部排序修饰”带偏，当前需求池按以下三层推进：

#### A. 已冻结待实现（必须优先进入正式开发）

1. **全候选主排序引擎重构**
   - 初筛后全部候选股票进入新画像统一重评分。
   - 替换旧 V1 “旧排序 + 局部增强”的过渡态。
2. **用户侧个股列表只保留一个 `官方总分`**
   - 个股列表固定按唯一正式顺序展示。
   - `????` ???????? `official_score`????????????????????? `rank_score`?
3. **移除普通用户可见的多排序入口**
   - 不再开放按延续分、弹性分、风险分、可买分重排。
   - 多排序如需保留，只能留在调试、导出或研发视角。
4. **二次决策退回“收口层”**
   - 不再重新决定“谁更强”。
   - 只负责主仓 / 次仓 / 观察仓收口、动作闸门、执行提示和落选解释。
5. **解释层字段统一降级为辅助维度**
   - `final_score / continuation_score / extension_score / risk_score / buyability_score / v13_shadow_score`
   - 仅解释主排序结果，不再承担平行排序职责。
6. **回测验证口径切到“新官方总分 + 新二次决策”**
   - 回测直接验证新官方排序是否更准。
   - 不再围绕影子分或局部增强是否“看起来更合理”做主验证。

#### B. 待讨论后冻结（主排序主线稳定后继续收口）

7. **详情页里 `官方总分` 的拆解方式**
   - 是否展示为 `官方总分 / 基础总分 / 风险分 / 可买分`
   - 还是进一步改成更产品化的解释话术。
8. **调试模式是否保留多排序**
   - 普通用户不见。
   - 研发 / 回归是否保留，需要单独定义边界。
9. **回测页的新旧排序对比方式**
   - 原始排序 Top3
   - 新官方总分 Top3
   - 二次决策最终 Top3
10. **落选解释枚举是否标准化**
   - 非主线
   - 主线内名次不够
   - 角色重复
   - 买点不清晰
   - 今日总闸门不支持

#### C. 后置但必须排期（核心链路稳定后补齐）

11. **任务状态继续细化**
   - 让前端明确显示：正在拉题材成分 / 正在做资金快照 / 正在补筹码 / 正在生成正式评分。
12. **系统停用 / 恢复链路补齐**
   - 连续双弱后怎么停用
   - 何时退出停用
   - 恢复到什么级别

执行顺序必须坚持：

`全候选主排序重构 -> 唯一官方总分 -> 二次决策收口层 -> 解释层下沉 -> 回测按新口径验证 -> 状态与停用恢复补齐`

## 5. M0：文档与字段冻结

优先级：`P0`

目标：

- 冻结 V1.3 的数据、规则、页面和回测字段。
- 避免前后端并行开发时字段反复漂移。

任务：

1. 确认 V1.3 只追加字段，不删除 V1 字段。
2. 冻结以下顶层字段名：
   - `mainline_radar`
   - `short_term_sentiment`
   - `snapshot_assist`
   - `v13_data_status`
   - `v13_diagnostics`
3. 明确盘中模块只叫 `盘中快照辅助`。
4. 明确禁止输出 `建议买入`、`分钟级买点正式触发`。

交付物：

- 本任务清单。
- 技术文档字段结构。
- 前后端字段对齐说明。

验收：

- 产品文档、技术文档、SPEC、PRD 中 V1.3 命名一致。

## 6. M1：Tushare V1.3 数据适配

优先级：`P0`

目标：

- 在数据源层补齐 6000 积分可用接口封装。

主要文件：

- `data_provider/tushare_fetcher.py`
- `data_provider/base.py`
- `tests/`

后端任务：

1. 在 `TushareFetcher` 中新增或补齐 `stk_limit` 数据读取。
2. 在 `TushareFetcher` 中新增 `limit_list_d` 数据读取。
3. 在 `TushareFetcher` 中新增 `ths_member` 数据读取。
4. 在 `TushareFetcher` 中新增 `ths_hot` 数据读取。
5. 统一输出字段：
   - `ts_code`
   - `trade_date`
   - `name`
   - `data_source`
   - `data_as_of`
   - `is_degraded`
6. 对外部接口异常、权限不足、空数据做可识别错误。

测试任务：

1. Mock Tushare 成功返回。
2. Mock Tushare 空数据返回。
3. Mock 权限不足 / 接口失败。
4. 校验 `NaN / inf` 不进入标准化输出。

验收：

- 单接口失败不会影响其他接口。
- 数据源层能明确区分 `ok / partial / unavailable`。

## 7. M2：V1.3 数据聚合与缓存

优先级：`P0`

目标：

- 建立稳定的 V1.3 数据上下文，供二次决策、回测和盘中辅助复用。

主要文件：

- `src/services/momentum_v13_data_service.py`
- `src/storage.py`
- `tests/test_momentum_v13_data_service.py`

后端任务：

1. 新增 `MomentumV13DataService`。
2. 实现 `build_context(trade_date, ts_codes)`。
3. 实现 `build_replay_context(trade_date, ts_codes)`。
4. 实现 `get_intraday_snapshot(trade_date, ts_codes)`。
5. 实现资源级缓存：
   - `stk_limit`
   - `limit_list_d`
   - `ths_member`
   - `ths_hot`
   - `realtime_quote`
6. 实现聚合上下文缓存。
7. 为每个资源输出 `source_status`。

缓存要求：

- 缓存 key 必须包含 `trade_date` 和资源名。
- `ths_member` 可使用较长 TTL。
- `realtime_quote` 必须短 TTL。
- 缓存命中不能跨交易日污染。

测试任务：

1. 同一交易日重复调用命中缓存。
2. 不同交易日不会复用错误缓存。
3. 单资源失败时 `source_status` 正确降级。
4. 聚合上下文中只包含请求股票相关数据。

验收：

- 缓存命中后二次构建上下文明显变快。
- V1.3 上下文可独立打印和调试。

### 7.1 真实性优先任务化执行

目标：

- 把强势筛选从“同步请求直接等待最终结果”切到“创建任务 + 轮询进度 + 完成后回捞结果”。
- 保留完整真值链路，不再为了 120 秒网关超时长期牺牲 V1.3 逐股增强真实性。

主要文件：

- `src/services/momentum_screening_run_service.py`
- `src/repositories/momentum_screening_run_repo.py`
- `api/v1/endpoints/stocks.py`
- `api/v1/schemas/stocks.py`
- `apps/dsa-web/src/pages/MomentumScreenerPage.tsx`

后端任务：

1. 新增 `screening run` 数据结构，至少包含 `run_id / status / truth_mode / current_stage_key / current_stage_label / progress_pct / heartbeat_at`。
2. 新增创建、查询、列表、结果回捞、取消五类 endpoint。
3. 定义阶段口径：`preparing / trade_snapshot / candidate_pool / sector_context / v13_context / scoring / secondary_decision / result_persist / completed / failed / cancelled`。
4. 为每个阶段落盘可复用产物，至少保存 `trade_snapshot / candidate_pool / sector_context / v13_context / ranked_results`。
5. 复用键必须包含筛选参数、`entry_baseline_version`、`market_scope_version`、`screening_cache_version` 和 `truth_mode`。
6. 服务重启后应能恢复未完成任务，且不能误把已取消任务重新拉起。

前端任务：

1. “执行筛选”按钮改为创建 run，而不是阻塞等待同步结果。
2. 页面新增任务进度区，展示阶段、百分比、最近刷新时间和缓存命中提示。
3. 新增“最近任务”列表，支持重新进入页面后继续查看。
4. 任务完成后自动加载最终结果；失败或取消时展示具体阶段原因。

测试任务：

1. 同参数、同版本、同 truth mode 下可正确复用已有 run 或最终结果。
2. 任务运行中页面刷新不会丢失进度。
3. 任务取消后不会在服务重启后被错误恢复。
4. 阶段缓存命中时，重跑会跳过已完成阶段。

验收：

- 页面不再以 504 作为长耗时真值筛选的默认失败表现。
- 用户能看见任务正在做什么、做到哪一层、是否已经复用缓存。
- 同一交易日重复查询时，任务耗时明显下降。

### 7.2 无损快照拉取改造

目标：

- 在不牺牲题材、资金、筹码多维度真实性的前提下，优先把支持批量或分页快照的 Tushare 接口改成快照式抓取。
- 仅把 `cyq_chips` 保留为逐股真查，并围绕其建立更强的缓存与断点续跑能力。

主要文件：

- `data_provider/tushare_fetcher.py`
- `src/services/momentum_v13_data_service.py`
- `src/services/momentum_screener_service.py`
- `tests/test_tushare_fetcher_v13.py`
- `tests/test_momentum_v13_data_service.py`
- `tests/test_momentum_screener_service.py`

后端任务：

1. 将 `moneyflow_ths / moneyflow_dc` 固化为按交易日分页快照抓取，再按 `ts_code` 本地过滤。
2. 将 `cyq_perf` 从逐股查询改成按交易日分页快照抓取，并保留单股 fallback。
3. 将 `dc_member` 从逐股 `con_code` 查询改成按交易日分页快照，再本地构建股票到板块映射。
4. 将 `ths_member` 改成全表分页快照，再本地构建股票到同花顺概念映射。
5. 将 `ths_index` 改成全表一次拉全，构建 `.TI -> 中文题材名` 字典，不再逐题材循环查询。
6. 保留 `cyq_chips` 逐股真查，但新增更稳定的 `(trade_date, ts_code)` 持久缓存与断点续跑复用。
7. 为分页快照统一实现 `limit / offset` 循环，禁止依赖“当前行数刚好没超上限”的偶然状态。

测试任务：

1. `moneyflow_ths / moneyflow_dc` 在单日全量、翻页和按股票过滤三种场景下结果一致。
2. `cyq_perf` 在按日快照和单股 fallback 两条路径下，对同一股票输出一致。
3. `dc_member / ths_member / ths_index` 的快照路径能恢复当前题材归因结果，不因抓取方式变化丢失主线映射。
4. `cyq_chips` 缓存命中后，重复任务不会再次对同一 `(trade_date, ts_code)` 发起外部查询。

验收：

- full truth 模式下的提速主要来自快照化和缓存命中，而不是减少维度。
- 主线、题材、个股承接和筹码解释口径与改造前保持一致或更完整。
- 当某个批量能力实测失效时，系统能明确 fallback，而不是静默返回空结果。

## 7.1 M2.5：全候选主排序引擎重构需求冻结

优先级：`P0`

目标：

- 将本次 `6000` 积分升级的主目标明确冻结为：**初筛后全部候选股票统一重评分，替换旧 V1 正式排序逻辑。**

主要文件：

- `src/services/momentum_screener_service.py`
- `src/services/momentum_v13_data_service.py`
- `docs/architecture/momentum-screener-v1-3-mainline-enhancement-product-design.md`
- `docs/architecture/momentum-screener-v1-3-mainline-enhancement-technical-design.md`

冻结要求：

1. 不再把 `v13_shadow_score`、`candidate_diagnostics` 或 `二次决策解释层` 当作本轮主交付。
2. 不再把 `Top12`、`Top30` 或页面展示子集增强视为正式排序方案。
3. `Standard` 正式排序必须以全候选新画像为基础重算。
4. `Aggressive` 的补充排序也必须建立在同一套全候选新画像之上。
5. 所有性能优化只能服务于“全候选重评分”，不能用减少评分覆盖范围换速度。

后续开发任务必须围绕以下问题展开：

1. 哪些旧 V1 评分维度要被新数据口径替换，而不是仅做轻量混合。
2. 如何让 `moneyflow_ths / moneyflow_dc / dc_member / ths_member / ths_index / cyq_perf / cyq_chips` 支撑全候选画像。
3. 如何让官方 `rank_score / final_score` 对全候选统一生效，而不是只修正前排样本。
4. 如何用任务化、缓存、快照和断点续跑支撑这一目标。

## 7.2 M2.6：用户侧唯一官方总分口径冻结

优先级：`P0`

目标：

- 冻结用户侧个股列表排序心智：只保留一个正式顺序，不再向普通用户开放多个维度分值的平行重排入口。

主要文件：

- `apps/dsa-web/src/pages/MomentumScreenerPage.tsx`
- `apps/dsa-web/src/types/momentumScreener.ts`
- `docs/architecture/momentum-screener-prd.md`
- `docs/architecture/momentum-screener-v1-3-mainline-enhancement-product-design.md`
- `docs/architecture/momentum-screener-v1-3-mainline-enhancement-technical-design.md`

冻结要求：

1. 个股列表只保留一个正式排序结果，对外统一命名为：`官方总分`。
2. `????` ?????? `official_score`????????????????????????????
3. `final_score`、`continuation_score`、`extension_score`、`risk_score`、`buyability_score` 保留，但仅作为解释层字段。
4. 普通用户界面不再暴露“按延续分 / 按弹性分 / 按风险分 / 按可买分”这类排序切换。
5. 若内部仍需要多排序视角，只能保留在调试模式、导出明细或研发工具中，不能继续占据正式个股列表主入口。

后续开发任务必须围绕以下问题展开：

1. 如何在不破坏现有 API 兼容性的前提下，把用户可见文案统一成 `官方总分`。
2. 如何让详情抽屉、AI 点评和导出明细承担多维分值解释，而不是列表重排。
3. 如何在主排序公式切换后保持对外“唯一正式顺序”的心智不变。

## 7.3 M2.7：全候选主排序引擎第一阶段实施方案

实施进度（2026-04-29）：

- 后端已将 V1.3 `profile map` 的正式输入收口为全候选 `baseline seed candidates`，`official_score` 重评分不再直接消费 provisional 结果载荷。

优先级：`P0`

目标：

- 把“全候选主排序重构”从冻结需求推进到第一阶段正式实现方案。
- 明确后端评分主链如何从“旧评分 + 局部增强”切到“全候选统一画像 + 全候选统一评分”。

主要文件：

- `src/services/momentum_screener_service.py`
- `src/services/momentum_v13_data_service.py`
- `tests/test_momentum_screener_service.py`
- `tests/test_momentum_v13_data_service.py`
- `docs/architecture/momentum-screener-v1-3-mainline-enhancement-technical-design.md`

后端任务：

1. 拆分 `MomentumScreenerService.screen()` 内部主链，明确分为：
   - 候选池准备
   - 全候选画像构建
   - 全候选统一评分
   - 官方总分排序固化
2. 新增全候选 profile map 构建函数，禁止正式口径只覆盖前排样本。
3. 让 `Standard` 在同一套全候选 profile 上完成正式评分，不再依赖 provisional results 先排再补。
4. 让 `Aggressive` 也改成基于同一套全候选画像的补充排序，而不是旧逻辑旁路。
5. 保留 `rank_score / final_score` 等字段兼容，但明确 `rank_score` 对外承担 `官方总分` 语义。
6. `candidate_diagnostics / v13_shadow_score` 改为严格解释层，不再作为正式评分链的隐性输入。

测试任务：

1. 同一候选池下，正式排序对全部候选统一生效，而不是只影响前排样本。
2. `truth_mode=light` 不再被误当成正式生产排序口径。
3. 在保留旧字段兼容的前提下，前端与回测读取 `rank_score` 不需要额外适配即可继续工作。
4. 旧的局部增强路径若仍保留为过渡逻辑，测试必须明确它不再承担正式验收口径。

验收：

- 后端正式排序主链能用一句话清楚描述为“全候选画像 -> 全候选评分 -> 官方总分”。
- 排序升级的主验收不再围绕影子分，而是围绕全候选正式排序质量。
- 后续页面和二次决策实现可以直接消费这份唯一正式顺序，而不是再拼接第二套排序逻辑。

## 8. M3：主线识别与主线评分

优先级：`P0`

目标：

- 从候选池识别当日最强 `1-2` 条主线。

主要文件：

- `src/services/momentum_secondary_decision_service.py`
- `tests/test_momentum_secondary_decision_service.py`

后端任务：

1. 新增 `_build_v13_mainline_context()`。
2. 将候选股映射到一个或多个题材。
3. 聚合题材内候选池密度。
4. 聚合题材内涨停 / 炸板 / 连板证据。
5. 聚合题材热榜集中度。
6. 接入昨日候选池 Top10 + 昨日官方 Top3 反馈。
7. 输出 `mainline_radar[]`。

第一版评分：

| 维度 | 权重 |
| --- | --- |
| 候选池密度 | 30 |
| 涨停强度 | 25 |
| 炸板风险 | -15 |
| 热榜集中度 | 15 |
| 昨日强势反馈 | 25 |

测试任务：

1. 单主线极强样本。
2. 双主线接近样本。
3. 主线不清晰样本。
4. 题材成分缺失降级样本。
5. 炸板过高导致主线扣分样本。

验收：

- 页面展示 TopN 变化不影响 `mainline_radar`。
- 主线不清晰时系统不强行归因。

## 9. M4：短线情绪总闸门

优先级：`P0`

目标：

- 判断当天市场是否愿意奖励强势股和主线核心票。

主要文件：

- `src/services/momentum_secondary_decision_service.py`
- `tests/test_momentum_secondary_decision_service.py`

后端任务：

1. 新增 `_build_v13_short_term_sentiment()`。
2. 计算全市场涨停数量。
3. 计算全市场炸板率。
4. 计算连板高度。
5. 计算主线内涨停与炸板表现。
6. 计算昨日强势反馈。
7. 计算热榜集中度。
8. 输出 `short_term_sentiment`。
9. 将短线情绪接入总闸门。

情绪档位：

| 档位 | 影响 |
| --- | --- |
| `高涨` | 可上调一档，但不得绕过风险边界 |
| `可做` | 保持原结论 |
| `分歧` | 限制强信任表达 |
| `退潮` | 最高优先保留观察 |

测试任务：

1. 情绪高涨上调样本。
2. 情绪退潮压制样本。
3. 主线极强但情绪分歧样本。
4. `limit_list_d` 缺失低置信度样本。

验收：

- 短线情绪只能影响总闸门，不得单独绕过买点规则。
- 数据缺失时显示低置信度，不直接当作弱。

## 10. M5：角色增强与官方 Top3 收口

优先级：`P0`

目标：

- 将官方 Top3 从单股排序升级为 `单股强度 + 主线强度 + 情绪环境 + 角色地位` 联合收口。

主要文件：

- `src/services/momentum_secondary_decision_service.py`
- `tests/test_momentum_secondary_decision_service.py`

后端任务：

1. 为候选股补充：
   - `mainline_id`
   - `mainline_name`
   - `mainline_score`
   - `theme_rank`
   - `role_evidence`
   - `v13_role_score`
2. 调整主仓优先级：
   - 买点清晰度
   - 主线强度
   - 角色地位
   - 单股 `rank_score`
   - 价格位置
3. 调整次仓优先级。
4. 调整观察仓优先级。
5. 保持不足 `3` 只时不强凑。
6. 保持 `Aggressive` 不参与官方组合。

测试任务：

1. 龙头核心买点不清晰，前排换手升主仓。
2. 强主线里只输出两只，不强凑第三只。
3. 非主线高分股被落选。
4. 同主线角色重复时正确淘汰。
5. 修改页面展示数量不影响官方 Top3。

验收：

- 官方 Top3 有明确主线、角色和仓位理由。
- 落选说明能说明非主线、角色重复、买点不清晰等主因。

## 11. M6：API / Schema / TypeScript 类型

优先级：`P0`

目标：

- 把 V1.3 结果以兼容方式暴露给前端和 AI 点评。

主要文件：

- `api/v1/schemas/stocks.py`
- `api/v1/endpoints/stocks.py`
- `apps/dsa-web/src/types/momentumScreener.ts`
- `apps/dsa-web/src/types/momentumBacktest.ts`
- `apps/dsa-web/src/api/momentumScreener.ts`

后端任务：

1. 新增 `MomentumMainlineRadarItem`。
2. 新增 `MomentumShortTermSentiment`。
3. 新增 `MomentumSnapshotAssist`。
4. 在 `MomentumSecondaryDecision` 中追加 V1.3 字段。
5. 在盘中信号响应中追加 `snapshot_assist`。
6. 在回测 summary / daily detail 中追加 `v13_diagnostics`。

前端任务：

1. 同步 TypeScript 类型。
2. 所有新增字段设为 optional。
3. 统一处理 `null`、空数组、降级状态。

测试任务：

1. 旧响应不含 V1.3 字段时前端不崩。
2. 新响应字段完整时能被正确解析。
3. API schema smoke 测试通过。

验收：

- 新字段只追加不破坏旧客户端。

## 12. M7：前端主线雷达与短线情绪

优先级：`P1`

目标：

- 页面能直观看到“今天强在哪里”和“今天适不适合做”。

主要文件：

- `apps/dsa-web/src/pages/MomentumScreenerPage.tsx`
- `apps/dsa-web/src/components/screener/MainlineRadarPanel.tsx`
- `apps/dsa-web/src/components/screener/ShortTermSentimentCard.tsx`
- `apps/dsa-web/src/components/screener/V13DataStatusBadge.tsx`

前端任务：

1. 新增 `主线雷达` 模块。
2. 新增 `短线情绪` 卡片。
3. 新增数据降级状态标识。
4. 在官方 Top3 卡片中展示所属主线与角色证据。
5. 个股列表固定按 `官方总分` 展示，并移除普通用户可见的多排序下拉。
6. 调整空态：
   - 主线不清晰
   - 情绪低置信度
   - 数据源缺失

测试任务：

1. 主线极强展示。
2. 主线不清晰展示。
3. 情绪退潮展示。
4. 数据降级展示。
5. 移动端布局不遮挡核心卡片。

验收：

- 用户不看明细也能知道今日最强主线和情绪档位。

## 13. M8：盘中快照辅助

优先级：`P1`

目标：

- 在没有分钟线权限时，提供诚实的低置信度盘中辅助。

主要文件：

- `src/services/momentum_secondary_decision_service.py`
- `api/v1/endpoints/stocks.py`
- `apps/dsa-web/src/components/screener/SnapshotAssistPanel.tsx`

后端任务：

1. 用 `realtime_quote` 获取当前价、开盘价、最高价、最低价。
2. 判断是否接近观察区。
3. 判断是否偏离过大。
4. 判断是否触及涨跌停边界。
5. 输出 `snapshot_assist`。

前端任务：

1. 模块标题固定为 `盘中快照辅助`。
2. 显示置信度和数据时间。
3. 显示“还需要人工确认什么”。
4. 禁止使用“买点已确认”类文案。

测试任务：

1. 价格接近观察区。
2. 价格偏离过大。
3. 实时快照缺失。
4. 收盘后查看历史日期。

验收：

- 页面只输出辅助观察，不输出正式买入指令。

## 14. M9：回测诊断升级

进展更新（2026-04-29）：

- 已在回测 `summary` / `daily detail` 的 `v13_diagnostics` 中补齐 `mainline_quality`、`theme_concentration`、`sentiment_alignment`、`role_fit`、`price_position`、`candidate_pool_bias` 六个结构化诊断键。
- 已新增区间级 `failure_attribution_breakdown` 与单日 `failure_attribution`，前端回测面板同步展示结构化诊断和主要拖累归因。

优先级：`P1`

目标：

- 用回测验证 V1.3 是否真正提升主链路，而不是只让页面更好看。

主要文件：

- `src/services/momentum_backtest_service.py`
- `src/repositories/momentum_backtest_repo.py`
- `api/v1/schemas/stocks.py`
- `apps/dsa-web/src/components/history/MomentumBacktestPanel.tsx`
- `tests/test_momentum_backtest_service.py`

后端任务：

1. 回测每日冻结 V1.3 上下文。
2. summary 新增 V1.3 诊断：
   - `mainline_quality`
   - `theme_concentration`
   - `sentiment_alignment`
   - `role_fit`
   - `price_position`
   - `candidate_pool_bias`
3. daily detail 新增单日失败归因。
4. 新增同主线 Top3、非主线高分股比较。
5. 严格回测标注当前题材成分近似风险。

前端任务：

1. 回测结果页展示 V1.3 诊断总览。
2. 单日详情展示主线、情绪、角色、价格位置分解。
3. 问题清单展示失败归因 TopN。

测试任务：

1. 60 交易日回测能完成。
2. summary 字段完整。
3. daily detail 可追溯到当日输入。
4. 严格回测不使用未来 T+1/T+2 信息参与 T 日决策。

验收：

- 回测报告能回答 V1.3 三个问题：
  - 主线识别是否有效？
  - 短线情绪是否有过滤价值？
  - 官方 Top3 是否优于原始排序？

## 15. M10：AI 点评上下文与护栏

优先级：`P2`

目标：

- AI 能解释 V1.3 规则结论，但不能覆盖规则。

主要文件：

- `src/services/momentum_screener_ai_commentary_service.py`
- `apps/dsa-web/src/api/momentumScreenerAi.ts`
- `apps/dsa-web/src/components/screener/ScreenerAiDrawer.tsx`

后端任务：

1. 将 `mainline_radar` 纳入 AI 上下文。
2. 将 `short_term_sentiment` 纳入 AI 上下文。
3. 将 `snapshot_assist` 纳入 AI 上下文。
4. 增加 guardrail：
   - 不得输出建议买入。
   - 不得把快照辅助说成分钟级买点。
   - 必须先复述规则结论。
5. 对工具调用失败给出友好降级。

前端任务：

1. AI 抽屉中展示规则边界。
2. AI 输出区域避免遮挡输入框。
3. 快捷问题围绕主线、情绪、风险、人工确认条件。

测试任务：

1. `今日不做` 场景下 AI 不建议追。
2. `快照辅助` 场景下 AI 不说买点确认。
3. 工具调用失败时提示可重试。

验收：

- AI 点评能增强理解，不改变官方决策。

## 16. M11：测试、部署和诊断报告

优先级：`P0`

目标：

- 完成开发闭环，上测试环境真实点测，并跑一轮 60 交易日回测。

验证命令：

```bash
python -m py_compile data_provider/tushare_fetcher.py src/services/momentum_v13_data_service.py src/services/momentum_secondary_decision_service.py src/services/momentum_backtest_service.py api/v1/endpoints/stocks.py api/v1/schemas/stocks.py
python -m pytest tests/test_momentum_secondary_decision_service.py tests/test_momentum_backtest_service.py tests/test_momentum_screener_api.py
cd apps/dsa-web && npm run lint && npm run build
```

部署任务：

1. 部署测试环境。
2. 打开 `http://163.7.12.193/` 真实点测强势筛选。
3. 检查主线雷达、短线情绪、盘中快照辅助。
4. 创建 60 交易日回测。
5. 跑完后输出《V1.3 60 交易日回测诊断报告》。

验收：

- 测试环境页面可用。
- 回测任务可创建、刷新、完成。
- 诊断报告指出主链路问题和下一轮校准建议。

## 17. 风险与依赖

### 17.1 外部依赖

- Tushare Pro `6000` 积分权限实际开通。
- `ths_member`、`ths_hot`、`limit_list_d` 字段可稳定返回。
- 测试服务器网络和 Docker 服务稳定。

### 17.2 主要风险

- 题材成分是当前口径，历史回放可能不是严格历史口径。
- 热榜历史数据可能不完整，不能一开始给高权重。
- 增强字段过多，前端页面信息密度可能过载。
- 盘中快照被误解为正式买点。

### 17.3 回滚方式

- 隐藏 V1.3 前端模块，回退 V1 页面。
- 后端关闭 V1.3 数据上下文构建，保留旧二次决策。
- 回测忽略 V1.3 诊断字段，继续展示旧 summary。
- AI prompt 移除 V1.3 上下文。

## 18. 最小可交付版本

如果需要先压缩上线范围，最小版本只做：

1. `M1` 数据适配中的 `ths_member / limit_list_d / stk_limit`。
2. `M2` 数据聚合与降级状态。
3. `M3` 主线雷达。
4. `M5` 官方 Top3 主线增强。
5. `M6` API / 类型。
6. `M7` 页面主线雷达。
7. `M9` 回测主线质量诊断。

`ths_hot`、盘中快照辅助和 AI 点评可后置。
