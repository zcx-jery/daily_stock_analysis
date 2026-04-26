# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线与导入解析模型
3. 定义强势筛选与二次决策模型
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    """股票实时行情。"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅(%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    update_time: Optional[str] = Field(None, description="更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "current_price": 1800.00,
                "change": 15.00,
                "change_percent": 0.84,
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "prev_close": 1785.00,
                "volume": 10000000,
                "amount": 18000000000,
                "update_time": "2024-01-01T15:00:00",
            }
        }


class KLineData(BaseModel):
    """K 线数据点。"""

    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅(%)")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-01",
                "open": 1785.00,
                "high": 1810.00,
                "low": 1780.00,
                "close": 1800.00,
                "volume": 10000000,
                "amount": 18000000000,
                "change_percent": 0.84,
            }
        }


class ExtractItem(BaseModel):
    """单条提取结果。"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片或导入内容解析响应。"""

    codes: List[str] = Field(..., description="提取后的股票代码列表")
    items: List[ExtractItem] = Field(default_factory=list, description="提取明细")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应，调试用")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应。"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: str = Field(..., description="K 线周期")
    data: List[KLineData] = Field(default_factory=list, description="K 线数据列表")

    class Config:
        json_schema_extra = {
            "example": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "period": "daily",
                "data": [],
            }
        }


class MomentumScreenerRequest(BaseModel):
    """次日强势股筛选请求。"""

    top_n: int = Field(30, ge=1, le=100, description="V1 生产链路固定展示 Top30；请求值会被服务端归一化")
    min_change_pct: float = Field(4.0, ge=0, le=20, description="V1 生产链路固定使用的最小涨幅 4%；请求值会被忽略")
    min_amount: float = Field(2e8, ge=0, description="V1 生产链路固定使用的最小成交额 2 亿；请求值会被忽略")
    min_turnover: float = Field(2.0, ge=0, le=100, description="V1 生产链路固定使用的最小换手率 2%；请求值会被忽略")
    exclude_st: bool = Field(True, description="V1 生产链路固定排除 ST；请求值会被忽略")
    main_board_only: bool = Field(False, description="V1 生产链路固定纳入主板、创业板、科创板；请求值会被忽略")
    trade_date: Optional[str] = Field(None, description="交易日，格式 YYYY-MM-DD 或 YYYYMMDD")
    profile: Literal["standard", "aggressive"] = Field(
        "standard",
        description="评分画像；官方二次决策与回测固定 standard，aggressive 仅用于进攻补充观察",
    )


class MomentumScoreBreakdown(BaseModel):
    """单个维度评分拆解。"""

    score: float = Field(..., description="维度得分")
    max_score: float = Field(..., description="维度满分")
    items: Dict[str, Any] = Field(default_factory=dict, description="子项得分")


class MomentumScreenerResult(BaseModel):
    """单只股票筛选结果。"""

    rank: int = Field(..., description="当前排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    market_segment: str = Field(..., description="市场板块归属枚举")
    market_segment_label: str = Field(..., description="市场板块归属文案")
    pct_chg: float = Field(..., description="今日涨幅")
    continuation_score: float = Field(..., description="次日延续分")
    extension_score: float = Field(..., description="上冲弹性分")
    risk_score: float = Field(..., description="风险分")
    buyability_score: Optional[float] = Field(None, description="可买性分，仅 aggressive 使用")
    opportunity_tag: Optional[str] = Field(None, description="机会标签，仅 aggressive 使用")
    entry_range_low: Optional[float] = Field(None, description="建议低位买入区间，二次决策可复用")
    entry_range_high: Optional[float] = Field(None, description="建议高位买入区间，二次决策可复用")
    final_score: float = Field(..., description="最终总分")
    rank_score: float = Field(..., description="排序分")
    themes: List[str] = Field(default_factory=list, description="所属板块/主线")
    leader_level: str = Field(..., description="板块地位")
    top_reasons: List[str] = Field(default_factory=list, description="主要加分原因")
    risk_tags: List[str] = Field(default_factory=list, description="风险标签")
    score_breakdown: Dict[str, MomentumScoreBreakdown] = Field(default_factory=dict, description="维度拆解")


class MomentumScreenerResponse(BaseModel):
    """次日强势股筛选响应。"""

    profile: Literal["standard", "aggressive"] = Field(..., description="评分画像")
    trade_date: str = Field(..., description="实际用于筛选的交易日")
    requested_trade_date: Optional[str] = Field(None, description="用户请求的交易日；自动模式下为空")
    trade_date_note: Optional[str] = Field(None, description="交易日自动回退或数据未就绪时的提示文案")
    entry_baseline_version: str = Field(..., description="候选池统一入口基线版本")
    market_scope_version: str = Field(..., description="候选池市场范围版本")
    candidate_count: int = Field(..., description="候选池数量")
    results: List[MomentumScreenerResult] = Field(default_factory=list, description="筛选结果")


class MomentumDecisionAction(BaseModel):
    """二次决策的今日出手级别。"""

    level: Literal["strong_go", "normal_go", "cautious_go", "observe_only", "stand_aside"] = Field(
        ...,
        description="今日出手级别枚举",
    )
    label: str = Field(..., description="今日出手级别文案")
    reason: str = Field(..., description="系统给出该级别的一句话理由")
    source_profile: Literal["standard", "aggressive"] = Field(..., description="当前候选引擎来源")


class MomentumDecisionThemeRepresentative(BaseModel):
    """主线代表股摘要。"""

    rank: int = Field(..., description="在当前筛选结果中的排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    role: str = Field(..., description="在主线中的角色")
    buy_point_label: str = Field(..., description="买点状态标签")
    rank_score: float = Field(..., description="排序分")
    v13_mainline_score: Optional[float] = Field(None, description="V1.3 主线雷达分")


class MomentumDecisionTheme(BaseModel):
    """主线识别结果。"""

    name: str = Field(..., description="主线名称")
    score: float = Field(..., description="主线综合评分")
    strength_label: str = Field(..., description="主线强弱标签")
    rule_theme_score: Optional[float] = Field(None, description="原规则主线分")
    v13_theme_id: Optional[str] = Field(None, description="V1.3 同花顺概念/主线 ID")
    v13_mainline_score: Optional[float] = Field(None, description="V1.3 主线雷达分")
    v13_summary: Optional[str] = Field(None, description="V1.3 主线雷达摘要")
    candidate_count: int = Field(..., description="该主线下的候选股数量")
    clear_buy_point_count: int = Field(..., description="买点清晰的数量")
    leader_count: int = Field(..., description="龙头核心数量")
    summary: str = Field(..., description="主线一句话总结")
    representatives: List[MomentumDecisionThemeRepresentative] = Field(
        default_factory=list,
        description="该主线下的代表股列表",
    )


class MomentumDecisionPortfolioSlot(BaseModel):
    """默认 1-3 票组合中的单个仓位。"""

    slot: Literal["main", "secondary", "watch"] = Field(..., description="仓位槽位键")
    slot_label: str = Field(..., description="仓位槽位文案")
    rank: int = Field(..., description="在当前筛选结果中的排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: str = Field(..., description="所属主线")
    v13_theme_id: Optional[str] = Field(None, description="V1.3 同花顺概念/主线 ID")
    v13_mainline_score: Optional[float] = Field(None, description="V1.3 主线雷达分")
    v13_mainline_level: Optional[str] = Field(None, description="V1.3 主线强弱枚举")
    v13_mainline_level_label: Optional[str] = Field(None, description="V1.3 主线强弱文案")
    role: str = Field(..., description="角色标签")
    score: float = Field(..., description="组合优先级分")
    rank_score: float = Field(..., description="原始排序分")
    risk_score: float = Field(..., description="风险分")
    rule_base_score: Optional[float] = Field(None, description="规则底座分")
    decision_score: Optional[float] = Field(None, description="二次决策规则分")
    forward_alpha_score: Optional[float] = Field(None, description="未来 1-2 日延续潜力先验分")
    t1_direction_risk_adjustment: Optional[float] = Field(None, description="T+1 方向风险修正分")
    buy_point_status: Literal["clear", "waiting", "unclear"] = Field(..., description="买点状态枚举")
    buy_point_label: str = Field(..., description="买点状态文案")
    suggested_action: Literal["ready", "wait_for_trigger", "observe_only"] = Field(
        ...,
        description="当前建议动作枚举",
    )
    suggested_action_label: str = Field(..., description="当前建议动作文案")
    primary_reason: str = Field(..., description="该票进入默认组合的主因")
    role_reason: str = Field(..., description="为什么放在这个仓位")
    execution_plan: str = Field(..., description="次日执行提示")
    entry_hint: Optional[str] = Field(None, description="优先买入区提示")
    entry_range_low: Optional[float] = Field(None, description="建议买入区间下沿")
    entry_range_high: Optional[float] = Field(None, description="建议买入区间上沿")
    opportunity_tag: Optional[str] = Field(None, description="机会标签")
    risk_tags: List[str] = Field(default_factory=list, description="风险标签")


class MomentumDecisionExcludedCandidate(BaseModel):
    """未进入默认组合的候选股说明。"""

    rank: int = Field(..., description="在当前筛选结果中的排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: str = Field(..., description="所属主线")
    role: str = Field(..., description="角色标签")
    reason: str = Field(..., description="主淘汰原因")
    rank_score: float = Field(..., description="排序分")


class MomentumDecisionCandidateDiagnostic(BaseModel):
    """二次决策候选股级别排序诊断。"""

    rank: int = Field(..., description="完整排序集排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: str = Field(..., description="所属主线")
    theme_score: float = Field(..., description="主线评分")
    v13_theme_id: Optional[str] = Field(None, description="V1.3 同花顺概念/主线 ID")
    v13_mainline_score: Optional[float] = Field(None, description="V1.3 主线雷达分")
    v13_mainline_level: Optional[str] = Field(None, description="V1.3 主线强弱枚举")
    v13_mainline_level_label: Optional[str] = Field(None, description="V1.3 主线强弱文案")
    role_key: str = Field(..., description="角色枚举")
    role: str = Field(..., description="角色标签")
    buy_point_status: str = Field(..., description="买点状态枚举")
    buy_point_label: str = Field(..., description="买点状态文案")
    rank_score: float = Field(..., description="原始排序分")
    continuation_score: float = Field(..., description="延续分")
    extension_score: float = Field(..., description="弹性分")
    extension_signal_score: float = Field(..., description="用于延续判断的弹性信号分")
    buyability_score: Optional[float] = Field(None, description="可买性分")
    risk_score: float = Field(..., description="风险分")
    rule_base_score: float = Field(..., description="规则底座分")
    explain_adjustment_score: float = Field(..., description="解释修正分")
    t1_direction_risk_adjustment: Optional[float] = Field(None, description="T+1 方向风险修正分")
    decision_score: float = Field(..., description="二次决策规则分")
    forward_alpha_score: float = Field(..., description="未来 1-2 日延续潜力先验分")
    forward_alpha_adjustment: float = Field(..., description="前瞻先验对组合排序的修正值")
    portfolio_priority: float = Field(..., description="最终组合排序优先级")
    selected_slot: Optional[str] = Field(None, description="入选槽位")
    is_selected: bool = Field(False, description="是否进入默认组合")


class MomentumDecisionEvidence(BaseModel):
    """二次决策证据区。"""

    theme_validation: List[str] = Field(default_factory=list, description="主线验证证据")
    today_reasoning: List[str] = Field(default_factory=list, description="今日结论证据")


class MomentumDecisionGateModule(BaseModel):
    """总闸门单个子模块。"""

    key: str = Field(..., description="子模块键")
    label: str = Field(..., description="子模块强弱标签")
    level: str = Field(..., description="子模块强弱枚举")
    score: float = Field(..., description="子模块评分")
    summary: str = Field(..., description="子模块摘要")


class MomentumDecisionMarketEnvironment(BaseModel):
    """市场环境层。"""

    level: Literal["strong", "medium", "weak"] = Field(..., description="市场环境级别")
    label: str = Field(..., description="市场环境级别文案")
    score: float = Field(..., description="市场环境综合得分")
    reason: str = Field(..., description="市场环境一句话总结")
    modules: List[MomentumDecisionGateModule] = Field(default_factory=list, description="市场环境子模块")


class MomentumDecisionOpportunityQuality(BaseModel):
    """当日机会质量层。"""

    level: Literal["strong", "medium", "weak"] = Field(..., description="机会质量级别")
    label: str = Field(..., description="机会质量级别文案")
    matrix_level: Optional[Literal["strong", "upper_mid", "mid", "weak"]] = Field(
        None,
        description="用于今日出手主矩阵的机会质量细分档",
    )
    matrix_label: Optional[str] = Field(None, description="机会质量细分档文案")
    score: float = Field(..., description="机会质量综合得分")
    reason: str = Field(..., description="机会质量一句话总结")
    modules: List[MomentumDecisionGateModule] = Field(default_factory=list, description="机会质量子模块")
    clear_count: Optional[int] = Field(None, description="默认组合中明日买点计划清晰的数量")
    clear_buy_point_count: Optional[int] = Field(None, description="默认组合中明日买点计划清晰的数量")
    main_risk_reward_pass: Optional[bool] = Field(None, description="主仓盈亏比是否达标")
    theme_concentration_pass: Optional[bool] = Field(None, description="默认组合是否至少 2 只来自第一主线")
    main_buy_point_clear: Optional[bool] = Field(None, description="主仓明日买点计划是否清晰")
    secondary_buy_point_clear: Optional[bool] = Field(None, description="次仓明日买点计划是否清晰")
    core_overextended_count: Optional[int] = Field(None, description="主仓/次仓中过度偏离的数量")
    portfolio_unresolved: Optional[bool] = Field(None, description="默认组合是否仍未形成完整结构")


class MomentumDecisionHistoricalValidity(BaseModel):
    """20 日进攻封顶兼容层。"""

    level: Literal["healthy", "general", "weak"] = Field(..., description="兼容层级")
    label: str = Field(..., description="兼容层文案")
    score: float = Field(..., description="兼容层得分")
    reason: str = Field(..., description="兼容层一句话总结")
    max_action_level: Literal["strong_go", "normal_go", "cautious_go"] = Field(
        ...,
        description="由 20 日进攻许可折算出的兼容最高出手级别",
    )
    recommendation_cap: Literal["full", "limited"] = Field(..., description="当前推荐能力上限")
    attack_permission_status: Optional[Literal["open", "recovering", "paused"]] = Field(
        None,
        description="20 日进攻许可状态",
    )
    attack_permission_label: Optional[str] = Field(None, description="20 日进攻许可状态文案")


class MomentumDecisionAttackPermission(BaseModel):
    """20 日进攻许可。"""

    status: Literal["open", "recovering", "paused"] = Field(..., description="20 日进攻许可状态")
    status_label: str = Field(..., description="20 日进攻许可状态文案")
    label: str = Field(..., description="20 日进攻许可状态文案")
    score: float = Field(..., description="20 日进攻许可分")
    window: Literal["short_20d"] = Field(..., description="窗口枚举")
    window_label: str = Field(..., description="窗口文案")
    valid_sample_count: int = Field(..., description="有效样本数量")
    hit_rate: float = Field(..., description="买点触发后单票命中率(%)")
    avg_profit_window_pct: float = Field(..., description="平均利润窗口(%)")
    avg_max_drawdown_pct: float = Field(..., description="平均最大回撤(%)")
    reason: str = Field(..., description="一句话解释")
    summary: str = Field(..., description="摘要说明")


class MomentumDecisionThemeConfidence(BaseModel):
    """60 日主线可信度。"""

    status: Literal["credible", "recovering", "questionable"] = Field(..., description="60 日主线可信度状态")
    status_label: str = Field(..., description="60 日主线可信度状态文案")
    label: str = Field(..., description="60 日主线可信度状态文案")
    score: float = Field(..., description="60 日主线可信度分")
    window: Literal["long_60d"] = Field(..., description="窗口枚举")
    window_label: str = Field(..., description="窗口文案")
    valid_sample_count: int = Field(..., description="有效样本数量")
    core_hit_rate: float = Field(..., description="当前主线识别代理命中率或结构分参考(%)")
    reason: str = Field(..., description="一句话解释")
    summary: str = Field(..., description="摘要说明")


class MomentumDecisionRiskBanner(BaseModel):
    """二次决策顶部风险提示条。"""

    tone: Literal["warning"] = Field(..., description="提示条语气")
    title: str = Field(..., description="提示标题")
    message: str = Field(..., description="提示正文")


class MomentumActionChecklistStep(BaseModel):
    """明日行动清单中的单个时间阶段。"""

    phase: Literal["pre_open", "first_30m", "first_60m"] = Field(..., description="行动阶段枚举")
    phase_label: str = Field(..., description="行动阶段文案")
    objective: str = Field(..., description="该阶段目标")
    focus_items: List[str] = Field(default_factory=list, description="该阶段优先关注对象")
    tasks: List[str] = Field(default_factory=list, description="该阶段建议执行动作")
    expected_outcome: str = Field(..., description="该阶段期望收口结果")


class MomentumActionChecklist(BaseModel):
    """明日行动清单。"""

    enabled: bool = Field(..., description="当前是否展示行动清单")
    mode: Literal["full", "simplified", "disabled"] = Field(..., description="行动清单模式")
    reason: str = Field(..., description="展示或不展示的原因")
    steps: List[MomentumActionChecklistStep] = Field(default_factory=list, description="按时间组织的行动步骤")


class MomentumStrategyHealthWindow(BaseModel):
    """20/60 日验证的单个窗口状态。"""

    window: Literal["short_20d", "long_60d"] = Field(..., description="窗口枚举")
    window_label: str = Field(..., description="窗口文案")
    status: Literal["healthy", "recovering", "weak"] = Field(..., description="窗口状态")
    status_label: str = Field(..., description="窗口状态文案")
    score: float = Field(..., description="窗口分")
    threshold: float = Field(..., description="达到可用状态的阈值")
    summary: str = Field(..., description="窗口状态摘要")


    sample_count: int = Field(..., description="参评样本数量")
    success_count: int = Field(..., description="满足组合标准的样本数")
    success_rate: float = Field(..., description="组合成功率(%)")
    avg_profit_window_pct: float = Field(..., description="1-2 个交易日利润窗口均值(%)")
    avg_max_drawdown_pct: float = Field(..., description="1-2 个交易日最大回撤均值(%)")
    avg_selected_count: float = Field(..., description="每日默认组合平均入选数")


class MomentumStrategyHealthProgress(BaseModel):
    """20/60 日历史验证进度。"""

    status: Literal["proxy", "queued", "running", "partial", "final", "failed"] = Field(
        "proxy",
        description="当前 20/60 日验证计算进度状态",
    )
    processed_trade_date_count: int = Field(0, description="已处理的历史交易日数量")
    total_trade_date_count: int = Field(0, description="待处理的历史交易日总数量")
    valid_sample_count: int = Field(0, description="已累计的有效样本数量")
    target_sample_count: int = Field(60, description="目标有效样本数量")
    progress_pct: float = Field(0.0, description="按历史交易日处理进度计算的百分比")
    last_evaluated_trade_date: Optional[str] = Field(None, description="最近一次完成验证的历史交易日")
    updated_at: Optional[str] = Field(None, description="最近一次进度更新时间")


class MomentumStrategyHealth(BaseModel):
    """20/60 日验证兼容状态。"""

    status: Literal["healthy", "partial_healthy", "recovery_mode", "disabled"] = Field(
        ...,
        description="兼容总状态",
    )
    label: str = Field(..., description="兼容状态文案")
    reason: str = Field(..., description="当前状态的一句话解释")
    recommendation_cap: Literal["full", "limited", "disabled"] = Field(..., description="当前推荐能力上限")
    can_full_recommend: bool = Field(..., description="当前是否允许完整强推荐")
    short_window: MomentumStrategyHealthWindow = Field(..., description="20 日窗口状态")
    long_window: MomentumStrategyHealthWindow = Field(..., description="60 日窗口状态")
    blockers: List[str] = Field(default_factory=list, description="当前阻断项")
    recovery_conditions: List[str] = Field(default_factory=list, description="恢复条件")
    data_source: Literal["historical", "proxy"] = Field("historical", description="当前 20/60 日验证结果来源")
    is_warming: bool = Field(False, description="真实历史验证是否仍在后台计算")

    validation_status: Literal["proxy", "partial", "final"] = Field(
        "final",
        description="历史验证结果当前处于代理、部分结果还是正式结果",
    )
    progress: MomentumStrategyHealthProgress = Field(
        default_factory=MomentumStrategyHealthProgress,
        description="历史验证进度信息",
    )


class MomentumSecondaryDecision(BaseModel):
    """二次决策静态结果。"""

    profile: Literal["standard", "aggressive"] = Field(..., description="候选引擎来源")
    trade_date: str = Field(..., description="交易日")
    action: MomentumDecisionAction = Field(..., description="今日出手级别")
    market_environment: MomentumDecisionMarketEnvironment = Field(..., description="市场环境层")
    opportunity_quality: MomentumDecisionOpportunityQuality = Field(..., description="当日机会质量层")
    historical_validity: MomentumDecisionHistoricalValidity = Field(..., description="20 日进攻封顶兼容层")
    strategy_health: MomentumStrategyHealth = Field(..., description="20/60 日验证兼容状态")
    attack_permission: MomentumDecisionAttackPermission = Field(..., description="20 日进攻许可")
    theme_confidence: MomentumDecisionThemeConfidence = Field(..., description="60 日主线可信度")
    risk_banner: Optional[MomentumDecisionRiskBanner] = Field(None, description="顶部风险提示条")
    mainline_radar: List[Dict[str, Any]] = Field(default_factory=list, description="V1.3 主线雷达证据")
    short_term_sentiment: Optional[Dict[str, Any]] = Field(None, description="V1.3 短线情绪评分")
    v13_data_status: Optional[Dict[str, Any]] = Field(None, description="V1.3 数据接入与降级状态")
    themes: List[MomentumDecisionTheme] = Field(default_factory=list, description="主线识别结果")
    portfolio: List[MomentumDecisionPortfolioSlot] = Field(default_factory=list, description="默认 1-3 票组合")
    candidate_diagnostics: List[MomentumDecisionCandidateDiagnostic] = Field(
        default_factory=list,
        description="候选股级别排序诊断",
    )
    excluded_candidates: List[MomentumDecisionExcludedCandidate] = Field(
        default_factory=list,
        description="未进入默认组合的候选股说明",
    )
    evidence: MomentumDecisionEvidence = Field(..., description="证据区内容")
    action_checklist: MomentumActionChecklist = Field(..., description="明日行动清单")


class MomentumSecondaryDecisionResponse(BaseModel):
    """强势筛选 + 二次决策组合响应。"""

    screening: MomentumScreenerResponse = Field(..., description="原始筛选结果")
    decision: MomentumSecondaryDecision = Field(..., description="二次决策结果")


class MomentumIntradayPortfolioItem(BaseModel):
    """盘中视角下的组合仓位状态。"""

    slot: Literal["main", "secondary", "watch"] = Field(..., description="仓位槽位键")
    slot_label: str = Field(..., description="仓位槽位文案")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: str = Field(..., description="所属主线")
    role: str = Field(..., description="角色标签")
    status: Literal["triggered", "watching", "do_not_chase", "observe_only", "data_unavailable"] = Field(
        ...,
        description="盘中状态枚举",
    )
    status_label: str = Field(..., description="盘中状态文案")
    reason: str = Field(..., description="盘中状态理由")
    quote_available: bool = Field(..., description="是否有可用的盘中行情")
    signal_triggered: bool = Field(..., description="是否已触发买点信号")
    do_not_chase: bool = Field(..., description="是否判定为不建议追入")
    current_price: Optional[float] = Field(None, description="当前价格")
    change_percent: Optional[float] = Field(None, description="当前涨跌幅(%)")
    open_price: Optional[float] = Field(None, description="开盘价")
    entry_range_low: Optional[float] = Field(None, description="建议买入区间下沿")
    entry_range_high: Optional[float] = Field(None, description="建议买入区间上沿")
    price_vs_open_pct: Optional[float] = Field(None, description="当前价格相对开盘价的偏离(%)")
    price_vs_entry_high_pct: Optional[float] = Field(
        None,
        description="当前价格相对建议区间上沿的偏离(%)",
    )
    missing_conditions: List[str] = Field(default_factory=list, description="未触发时还差的条件")
    update_time: Optional[str] = Field(None, description="盘中行情更新时间")


class MomentumIntradaySignal(BaseModel):
    """盘中信号汇总。"""

    market_phase: Literal[
        "pre_open",
        "call_auction",
        "first_30m",
        "first_60m",
        "after_first_hour",
        "midday_break",
        "afternoon",
        "closed",
    ] = Field(..., description="盘中时段枚举")
    market_phase_label: str = Field(..., description="盘中时段文案")
    confidence_level: Literal["high", "medium", "low"] = Field(..., description="盘中置信度")
    confidence_label: str = Field(..., description="盘中置信度文案")
    can_emit_buy_signal: bool = Field(..., description="当前是否可以给出明确买入信号")
    status: Literal[
        "not_started",
        "watching",
        "buy_ready",
        "low_confidence",
        "do_not_buy",
        "stand_aside",
        "not_applicable",
    ] = Field(..., description="盘中结论状态")
    status_label: str = Field(..., description="盘中结论状态文案")
    reason: str = Field(..., description="当前盘中结论的一句话原因")
    watch_items: List[str] = Field(default_factory=list, description="当前需继续关注的事项")
    final_recommendation: Literal["buy", "main_only_consider", "watch", "do_not_buy"] = Field(
        ...,
        description="盘中收口后的最终建议",
    )
    final_recommendation_label: str = Field(..., description="最终建议文案")
    closing_note: str = Field(..., description="盘中收口说明")
    updated_at: str = Field(..., description="最后一次评估时间")
    focus_order: List[str] = Field(default_factory=list, description="最终优先关注顺序说明")
    portfolio_items: List[MomentumIntradayPortfolioItem] = Field(
        default_factory=list,
        description="默认组合在盘中的状态列表",
    )


class MomentumSecondaryDecisionIntradayResponse(BaseModel):
    """强势筛选 + 二次决策 + 盘中信号组合响应。"""

    screening: MomentumScreenerResponse = Field(..., description="原始筛选结果")
    decision: MomentumSecondaryDecision = Field(..., description="二次决策结果")
    intraday_signal: MomentumIntradaySignal = Field(..., description="盘中信号结果")
    snapshot_assist: Optional[Dict[str, Any]] = Field(None, description="V1.3 低置信度盘中快照辅助")


class MomentumBacktestCreateRequest(BaseModel):
    """V1 强势筛选回测任务创建请求。"""

    start_trade_date: str = Field(..., description="回测起始交易日，格式 YYYY-MM-DD 或 YYYYMMDD")
    end_trade_date: str = Field(..., description="回测结束交易日，格式 YYYY-MM-DD 或 YYYYMMDD")
    profile: Literal["standard", "aggressive"] = Field(
        "standard",
        description="兼容旧请求字段；V1 官方回测固定归一化为 Standard 主引擎",
    )
    top_n: int = Field(30, ge=1, le=100, description="兼容旧请求字段；V1 官方回测固定归一化为 Top30")
    strict_strategy_health: bool = Field(
        False,
        description="是否启用严格 20/60 窗口回测口径；开启后会逐日等待真实窗口验证完成再冻结当日结论。",
    )


class MomentumBacktestSummary(BaseModel):
    """V1 回测区间摘要。"""

    strategy_health_mode: str = Field("cached_only", description="20/60 窗口验证口径")
    strategy_health_mode_label: str = Field("兼容缓存口径", description="20/60 窗口验证口径文案")
    strategy_health_validation_status_breakdown: Dict[str, int] = Field(default_factory=dict, description="20/60 窗口验证状态分布")
    attack_permission_breakdown: Dict[str, int] = Field(default_factory=dict, description="20 日进攻许可状态分布")
    theme_confidence_breakdown: Dict[str, int] = Field(default_factory=dict, description="60 日主线可信度状态分布")
    completed_trade_dates: int = Field(..., description="已成功完成回放的交易日数量")
    action_breakdown: Dict[str, int] = Field(default_factory=dict, description="各今日出手级别分布")
    market_environment_breakdown: Dict[str, int] = Field(default_factory=dict, description="市场环境分桶分布")
    opportunity_quality_breakdown: Dict[str, int] = Field(default_factory=dict, description="机会质量分桶分布")
    historical_validity_breakdown: Dict[str, int] = Field(default_factory=dict, description="20 日进攻封顶兼容分桶分布")
    avg_candidate_count: Optional[float] = Field(None, description="候选池数量均值")
    avg_selected_count: Optional[float] = Field(None, description="默认组合入选数量均值")
    avg_buy_ready_count: Optional[float] = Field(None, description="默认组合中 ready 数量均值")
    candidate_top10_buy_trigger_rate: Optional[float] = Field(None, description="候选池 Top10 买点触发率(%)")
    candidate_top10_positive_t2_rate: Optional[float] = Field(None, description="候选池 Top10 短线延续合格率(%)")
    candidate_top10_settlement_pass_rate: Optional[float] = Field(None, description="候选池 Top10 短线延续合格率，同 positive_t2_rate")
    candidate_top10_t1_direction_pass_rate: Optional[float] = Field(None, description="候选池 Top10 T+1 收盘强于开盘占比(%)")
    candidate_top10_t2_continuation_pass_rate: Optional[float] = Field(None, description="候选池 Top10 T+2 最高价高于 T+1 收盘价占比(%)")
    candidate_top10_avg_t2_profit_window_pct: Optional[float] = Field(None, description="候选池 Top10 T+2 利润窗口均值(%)")
    candidate_top10_avg_t2_max_drawdown_pct: Optional[float] = Field(None, description="候选池 Top10 T+2 最大回撤均值(%)")
    decision_top3_buy_trigger_rate: Optional[float] = Field(None, description="二次决策 Top3 买点触发率(%)")
    decision_top3_positive_t1_rate: Optional[float] = Field(None, description="二次决策 Top3 T+1 收盘强于开盘占比(%)")
    decision_top3_positive_t2_rate: Optional[float] = Field(None, description="二次决策 Top3 短线延续合格率(%)")
    decision_top3_settlement_pass_rate: Optional[float] = Field(None, description="二次决策 Top3 短线延续合格率，同 positive_t2_rate")
    decision_top3_t1_direction_pass_rate: Optional[float] = Field(None, description="二次决策 Top3 T+1 收盘强于开盘占比(%)")
    decision_top3_t2_continuation_pass_rate: Optional[float] = Field(None, description="二次决策 Top3 T+2 最高价高于 T+1 收盘价占比(%)")
    decision_top3_avg_t1_profit_window_pct: Optional[float] = Field(None, description="二次决策 Top3 T+1 利润窗口均值(%)")
    decision_top3_avg_t2_profit_window_pct: Optional[float] = Field(None, description="二次决策 Top3 T+2 利润窗口均值(%)")
    decision_top3_avg_t2_max_drawdown_pct: Optional[float] = Field(None, description="二次决策 Top3 T+2 最大回撤均值(%)")
    benchmark_comparison: List["MomentumBacktestBenchmarkItem"] = Field(default_factory=list, description="官方 Top3 与各基准的对比结果")
    layer_diagnostics: List["MomentumBacktestLayerDiagnostic"] = Field(default_factory=list, description="候选池/排序/执行/总闸门/环境适配五层诊断")
    gate_module_breakdown: List["MomentumBacktestGateModuleBreakdownItem"] = Field(default_factory=list, description="总闸门细分模块的区间聚合诊断")
    regime_breakdown: List["MomentumBacktestRegimeBreakdownItem"] = Field(default_factory=list, description="强/中/弱市场分桶指标")
    v13_diagnostics: Dict[str, Any] = Field(default_factory=dict, description="V1.3 主线雷达、短线情绪和数据降级聚合诊断")


class MomentumBacktestBenchmarkItem(BaseModel):
    """V1 回测单个比较基准摘要。"""

    key: str = Field(..., description="基准键")
    label: str = Field(..., description="基准名称")
    sample_count: int = Field(..., description="样本数量")
    trigger_rate_pct: Optional[float] = Field(None, description="买点触发率(%)")
    positive_t2_rate_pct: Optional[float] = Field(None, description="短线延续合格率：T+1 收盘价 > T+1 开盘价，且 T+2 最高价 > T+1 收盘价(%)")
    settlement_pass_rate_pct: Optional[float] = Field(None, description="短线延续合格率，同 positive_t2_rate_pct")
    t1_direction_pass_rate_pct: Optional[float] = Field(None, description="T+1 收盘强于开盘占比(%)")
    t2_continuation_pass_rate_pct: Optional[float] = Field(None, description="T+2 最高价高于 T+1 收盘价占比(%)")
    avg_t2_profit_window_pct: Optional[float] = Field(None, description="T+2 平均利润窗口(%)")
    avg_t2_max_drawdown_pct: Optional[float] = Field(None, description="T+2 平均最大回撤(%)")
    alpha_vs_official_top3_pct: Optional[float] = Field(None, description="相对官方 Top3 的 T+2 利润窗口差值(%)")
    alpha_vs_candidate_top10_pct: Optional[float] = Field(None, description="相对候选池 Top10 的 T+2 利润窗口差值(%)")


class MomentumBacktestLayerDiagnostic(BaseModel):
    """V1 回测单层诊断卡片。"""

    key: str = Field(..., description="诊断层级键")
    label: str = Field(..., description="诊断层级名称")
    level: Literal["strong", "general", "weak"] = Field(..., description="层级当前状态")
    score: float = Field(..., description="展示用层级评分")
    summary: str = Field(..., description="该层的简要诊断结论")
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict, description="该层关键指标")


class MomentumBacktestGateModuleBreakdownItem(BaseModel):
    """V1 回测总闸门细分模块区间聚合。"""

    key: str = Field(..., description="模块键")
    label: str = Field(..., description="模块名称")
    group_key: str = Field(..., description="所属分组键")
    group_label: str = Field(..., description="所属分组名称")
    sample_days: int = Field(..., description="纳入统计的交易日数量")
    strong_days: int = Field(..., description="模块处于强状态的交易日数量")
    medium_days: int = Field(..., description="模块处于中状态的交易日数量")
    weak_days: int = Field(..., description="模块处于弱状态的交易日数量")
    blocker_days: int = Field(..., description="模块成为弱项的交易日数量")
    restricted_days: int = Field(..., description="模块为弱项且当天限制出手的交易日数量")
    avg_score: Optional[float] = Field(None, description="模块平均分")
    weak_day_candidate_positive_t2_rate_pct: Optional[float] = Field(None, description="模块为弱项时候选池短线延续合格率均值(%)")
    weak_day_decision_positive_t2_rate_pct: Optional[float] = Field(None, description="模块为弱项时默认组合短线延续合格率均值(%)")
    weak_day_candidate_avg_t2_profit_window_pct: Optional[float] = Field(None, description="模块为弱项时候选池 T+2 利润窗口均值(%)")
    weak_day_decision_avg_t2_profit_window_pct: Optional[float] = Field(None, description="模块为弱项时默认组合 T+2 利润窗口均值(%)")
    strong_day_decision_avg_t2_profit_window_pct: Optional[float] = Field(None, description="模块为强项时默认组合 T+2 利润窗口均值(%)")
    summary: str = Field(..., description="模块区间诊断结论")


class MomentumBacktestGateSnapshotModule(BaseModel):
    """V1 回测单日总闸门模块快照。"""

    key: str = Field(..., description="模块键")
    label: str = Field(..., description="模块名称")
    group_key: str = Field(..., description="所属分组键")
    group_label: str = Field(..., description="所属分组名称")
    level: str = Field(..., description="模块状态枚举")
    level_label: str = Field(..., description="模块状态文案")
    score: Optional[float] = Field(None, description="模块分数")
    summary: str = Field(..., description="模块摘要")


class MomentumBacktestGateSnapshotGroup(BaseModel):
    """V1 回测单日总闸门分组快照。"""

    key: str = Field(..., description="分组键")
    label: str = Field(..., description="分组名称")
    level: str = Field(..., description="分组状态枚举")
    level_label: str = Field(..., description="分组状态文案")
    score: Optional[float] = Field(None, description="分组分数")
    reason: str = Field(..., description="分组判断理由")
    modules: List[MomentumBacktestGateSnapshotModule] = Field(default_factory=list, description="分组下的细分模块")


class MomentumBacktestRegimeBreakdownItem(BaseModel):
    """V1 回测按市场分桶的摘要。"""

    level: Literal["strong", "general", "weak"] = Field(..., description="市场分桶枚举")
    label: str = Field(..., description="市场分桶名称")
    trade_days: int = Field(..., description="该分桶交易日数量")
    decision_positive_t2_rate_pct: Optional[float] = Field(None, description="官方组合短线延续合格率(%)")
    decision_avg_t2_profit_window_pct: Optional[float] = Field(None, description="官方组合 T+2 平均利润窗口(%)")
    decision_avg_t2_max_drawdown_pct: Optional[float] = Field(None, description="官方组合 T+2 平均最大回撤(%)")
    missed_opportunity_rate_pct: Optional[float] = Field(None, description="该分桶下限制日的错杀率(%)")
    allowed_trade_precision_pct: Optional[float] = Field(None, description="该分桶下放行准确率(%)")
    stand_aside_rate_pct: Optional[float] = Field(None, description="该分桶下今日不做占比(%)")


class MomentumBacktestRunResponse(BaseModel):
    """V1 回测任务状态。"""

    run_id: str = Field(..., description="回测任务 ID")
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = Field(..., description="回测任务状态")
    profile: Literal["standard", "aggressive"] = Field(..., description="回放使用的画像")
    engine_version: str = Field(..., description="回测引擎版本")
    strategy_health_mode: str = Field("cached_only", description="20/60 窗口验证口径")
    strategy_health_mode_label: str = Field("兼容缓存口径", description="20/60 窗口验证口径文案")
    entry_baseline_version: str = Field(..., description="候选池入口基线版本")
    market_scope_version: str = Field(..., description="候选池市场范围版本")
    top_n: int = Field(..., description="回放时保留的展示结果数量")
    start_trade_date: str = Field(..., description="回测起始交易日")
    end_trade_date: str = Field(..., description="回测结束交易日")
    total_trade_dates: int = Field(..., description="区间内交易日总数")
    processed_trade_dates: int = Field(..., description="已处理交易日数量")
    failed_trade_dates: int = Field(..., description="失败交易日数量")
    current_trade_date: Optional[str] = Field(None, description="当前正在处理的交易日")
    current_stage_key: Optional[str] = Field(None, description="当前阶段键")
    current_stage_label: Optional[str] = Field(None, description="当前阶段文案")
    heartbeat_at: Optional[str] = Field(None, description="最近一次进度心跳时间")
    started_at: Optional[str] = Field(None, description="任务实际开始时间")
    finished_at: Optional[str] = Field(None, description="任务实际结束时间")
    cancel_requested: bool = Field(False, description="当前是否已经请求取消")
    summary: Optional[MomentumBacktestSummary] = Field(None, description="当前区间摘要")
    error_message: Optional[str] = Field(None, description="任务错误信息")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")


class MomentumBacktestCreateResponse(BaseModel):
    """V1 回测任务创建结果。"""

    created_new: bool = Field(..., description="是否本次新建了任务")
    message: str = Field(..., description="前端可直接展示的提示文案")
    run: MomentumBacktestRunResponse = Field(..., description="当前定位到的回测任务")


class MomentumBacktestRunSectionResponse(BaseModel):
    """V1 回测任务列表的单个分区。"""

    total: int = Field(..., description="该分区内的任务数量")
    limit: Optional[int] = Field(None, description="该分区的默认展示上限")
    items: List[MomentumBacktestRunResponse] = Field(default_factory=list, description="该分区的任务列表")


class MomentumBacktestRunListResponse(BaseModel):
    """V1 回测任务列表响应。"""

    current_running: Optional[MomentumBacktestRunResponse] = Field(None, description="当前正在后台计算的任务")
    queued: MomentumBacktestRunSectionResponse = Field(..., description="排队中的任务列表")
    history: MomentumBacktestRunSectionResponse = Field(..., description="历史任务列表")
    refreshed_at: Optional[str] = Field(None, description="最近一次列表刷新时间")


class MomentumBacktestDeleteResponse(BaseModel):
    """V1 回测任务删除响应。"""

    run_id: str = Field(..., description="已删除的回测任务 ID")
    deleted: bool = Field(..., description="是否已成功删除")
    message: str = Field(..., description="前端可直接展示的提示文案")


class MomentumBacktestSummaryResponse(BaseModel):
    """V1 回测区间摘要响应。"""

    run_id: str = Field(..., description="回测任务 ID")
    profile: Literal["standard", "aggressive"] = Field(..., description="回放使用的画像")
    engine_version: str = Field(..., description="回测引擎版本")
    strategy_health_mode: str = Field("cached_only", description="20/60 窗口验证口径")
    strategy_health_mode_label: str = Field("兼容缓存口径", description="20/60 窗口验证口径文案")
    summary: MomentumBacktestSummary = Field(..., description="区间摘要")


class MomentumBacktestDailyItem(BaseModel):
    """V1 回测单日摘要。"""

    trade_date: str = Field(..., description="交易日")
    action_level: str = Field(..., description="今日出手级别枚举")
    action_label: str = Field(..., description="今日出手级别文案")
    recommendation_cap: str = Field(..., description="当日推荐上限")
    action_checklist_mode: str = Field(..., description="当日行动清单模式")
    market_environment_level: str = Field(..., description="市场环境层级别")
    opportunity_quality_level: str = Field(..., description="当日机会质量级别")
    historical_validity_level: str = Field(..., description="20 日进攻封顶兼容级别")
    candidate_count: int = Field(..., description="候选池数量")
    result_count: int = Field(..., description="完整排序集数量")
    selected_count: int = Field(..., description="默认组合数量")
    buy_ready_count: int = Field(..., description="默认组合中 ready 数量")
    main_ts_code: Optional[str] = Field(None, description="主仓股票代码")
    secondary_ts_code: Optional[str] = Field(None, description="次仓股票代码")
    watch_ts_code: Optional[str] = Field(None, description="观察仓股票代码")


class MomentumBacktestDailyListResponse(BaseModel):
    """V1 回测单日列表响应。"""

    run_id: str = Field(..., description="回测任务 ID")
    total: int = Field(..., description="符合过滤条件的总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="当前页大小")
    has_more: bool = Field(..., description="是否还有更多结果")
    items: List[MomentumBacktestDailyItem] = Field(default_factory=list, description="回测单日摘要列表")


class MomentumBacktestOutcomeItem(BaseModel):
    """V1 回测单条结果验证记录。"""

    view_scope: str = Field(..., description="结果验证所属视图")
    slot: Optional[str] = Field(None, description="默认组合槽位")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    buy_triggered: bool = Field(..., description="是否命中建议买点")
    reference_entry_price: Optional[float] = Field(None, description="参考入场价")
    trigger_price: Optional[float] = Field(None, description="实际触发价")
    trigger_trade_date: Optional[str] = Field(None, description="实际触发交易日")
    t1_trade_date: Optional[str] = Field(None, description="T+1 交易日")
    t1_close_return_pct: Optional[float] = Field(None, description="T+1 收盘收益(%)")
    t1_profit_window_pct: Optional[float] = Field(None, description="T+1 利润窗口(%)")
    t1_max_drawdown_pct: Optional[float] = Field(None, description="T+1 最大回撤(%)")
    t2_trade_date: Optional[str] = Field(None, description="T+2 交易日")
    t2_close_return_pct: Optional[float] = Field(None, description="T+2 收盘收益(%)")
    t2_profit_window_pct: Optional[float] = Field(None, description="T+2 利润窗口(%)")
    t2_max_drawdown_pct: Optional[float] = Field(None, description="T+2 最大回撤(%)")
    real_strength_label: Optional[str] = Field(None, description="真实后续强弱标签")
    settlement_rule: Optional[str] = Field(None, description="短线延续合格规则")
    t1_direction_pass: Optional[bool] = Field(None, description="T+1 收盘价是否大于 T+1 开盘价")
    t2_continuation_pass: Optional[bool] = Field(None, description="T+2 最高价是否大于 T+1 收盘价")
    settlement_pass: Optional[bool] = Field(None, description="是否满足短线延续合格规则")


class MomentumBacktestOutcomeMetrics(BaseModel):
    """V1 回测视图级结果指标。"""

    sample_count: int = Field(..., description="样本数量")
    trigger_rate_pct: Optional[float] = Field(None, description="买点触发率(%)")
    positive_t1_rate_pct: Optional[float] = Field(None, description="T+1 收盘强于开盘占比(%)")
    positive_t2_rate_pct: Optional[float] = Field(None, description="短线延续合格率(%)")
    settlement_pass_rate_pct: Optional[float] = Field(None, description="短线延续合格率，同 positive_t2_rate_pct")
    t1_direction_pass_rate_pct: Optional[float] = Field(None, description="T+1 收盘价 > 开盘价占比(%)")
    t2_continuation_pass_rate_pct: Optional[float] = Field(None, description="T+2 最高价 > T+1 收盘价占比(%)")
    avg_t1_profit_window_pct: Optional[float] = Field(None, description="T+1 平均利润窗口(%)")
    avg_t2_profit_window_pct: Optional[float] = Field(None, description="T+2 平均利润窗口(%)")
    avg_t2_max_drawdown_pct: Optional[float] = Field(None, description="T+2 平均最大回撤(%)")
    best_t2_profit_window_pct: Optional[float] = Field(None, description="最佳 T+2 利润窗口(%)")


class MomentumBacktestOutcomeGroup(BaseModel):
    """V1 回测某个视图的结果验证分组。"""

    metrics: MomentumBacktestOutcomeMetrics = Field(..., description="该视图聚合指标")
    items: List[MomentumBacktestOutcomeItem] = Field(default_factory=list, description="该视图逐票结果")


class MomentumBacktestCandidateDetailItem(BaseModel):
    """V1 回测候选池 Top10 单项详情。"""

    rank: int = Field(..., description="候选池排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: Optional[str] = Field(None, description="所属主线")
    role: Optional[str] = Field(None, description="角色标签")
    market_segment: Optional[str] = Field(None, description="市场板块枚举")
    rank_score: Optional[float] = Field(None, description="排序分")
    final_score: Optional[float] = Field(None, description="最终总分")
    continuation_score: Optional[float] = Field(None, description="延续分")
    extension_score: Optional[float] = Field(None, description="弹性分")
    risk_score: Optional[float] = Field(None, description="风险分")
    buyability_score: Optional[float] = Field(None, description="可买性分")
    decision_diagnostics: Optional[Dict[str, Any]] = Field(None, description="二次决策排序诊断快照")
    outcome: Optional[MomentumBacktestOutcomeItem] = Field(None, description="该候选股的真实结果")


class MomentumBacktestDecisionDetailItem(BaseModel):
    """V1 回测默认组合单项详情。"""

    slot: str = Field(..., description="默认组合槽位")
    rank: Optional[int] = Field(None, description="原始排序排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: Optional[str] = Field(None, description="所属主线")
    role: Optional[str] = Field(None, description="角色标签")
    decision_score: Optional[float] = Field(None, description="组合优先级分")
    rank_score: Optional[float] = Field(None, description="排序分")
    risk_score: Optional[float] = Field(None, description="风险分")
    buy_point_status: Optional[str] = Field(None, description="买点状态")
    suggested_action: Optional[str] = Field(None, description="静态建议动作")
    entry_range_low: Optional[float] = Field(None, description="建议买入区间下沿")
    entry_range_high: Optional[float] = Field(None, description="建议买入区间上沿")
    opportunity_tag: Optional[str] = Field(None, description="机会标签")
    risk_tags: List[str] = Field(default_factory=list, description="风险标签")
    outcome: Optional[MomentumBacktestOutcomeItem] = Field(None, description="该组合票的真实结果")


class MomentumBacktestIssueItem(BaseModel):
    """V1 回测问题诊断项。"""

    issue_key: str = Field(..., description="问题类型键")
    severity: Literal["critical", "warning", "info"] = Field(..., description="问题严重程度")
    title: str = Field(..., description="问题标题")
    summary: str = Field(..., description="问题描述")
    affected_codes: List[str] = Field(default_factory=list, description="受影响股票代码")
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict, description="该问题对应的关键指标")


class MomentumBacktestDailyDiagnosis(BaseModel):
    """V1 回测单日问题诊断。"""

    summary_lines: List[str] = Field(default_factory=list, description="单日诊断摘要")
    candidate_metrics: MomentumBacktestOutcomeMetrics = Field(..., description="候选池结果指标")
    decision_metrics: MomentumBacktestOutcomeMetrics = Field(..., description="默认组合结果指标")
    gate_snapshot: List[MomentumBacktestGateSnapshotGroup] = Field(default_factory=list, description="当日总闸门三层快照")
    gate_blockers: List[MomentumBacktestGateSnapshotModule] = Field(default_factory=list, description="当日拖后腿的总闸门模块")
    issues: List[MomentumBacktestIssueItem] = Field(default_factory=list, description="单日诊断问题列表")


class MomentumBacktestDailyDetailResponse(BaseModel):
    """V1 回测单日详情。"""

    run_id: str = Field(..., description="回测任务 ID")
    trade_date: str = Field(..., description="交易日")
    daily_context: MomentumBacktestDailyItem = Field(..., description="当日回放上下文")
    candidate_top10: List[MomentumBacktestCandidateDetailItem] = Field(default_factory=list, description="候选池 Top10 详情")
    decision_top3: List[MomentumBacktestDecisionDetailItem] = Field(default_factory=list, description="默认组合详情")
    slot_view: List[MomentumBacktestDecisionDetailItem] = Field(default_factory=list, description="按槽位排序的默认组合视图")
    outcomes: Dict[str, MomentumBacktestOutcomeGroup] = Field(default_factory=dict, description="候选池与默认组合的结果验证分组")
    diagnosis: MomentumBacktestDailyDiagnosis = Field(..., description="单日问题诊断")
    v13_diagnostics: Dict[str, Any] = Field(default_factory=dict, description="V1.3 单日主线雷达、短线情绪和数据降级诊断")


class MomentumBacktestIssueListItem(MomentumBacktestIssueItem):
    """V1 回测区间问题列表项。"""

    trade_date: str = Field(..., description="问题发生交易日")
    action_level: str = Field(..., description="当日出手级别枚举")
    action_label: str = Field(..., description="当日出手级别文案")


class MomentumBacktestIssueListResponse(BaseModel):
    """V1 回测问题清单响应。"""

    run_id: str = Field(..., description="回测任务 ID")
    total_issues: int = Field(..., description="问题总数")
    severity_breakdown: Dict[str, int] = Field(default_factory=dict, description="按严重度聚合的问题数量")
    issue_key_breakdown: Dict[str, int] = Field(default_factory=dict, description="按问题类型聚合的问题数量")
    items: List[MomentumBacktestIssueListItem] = Field(default_factory=list, description="区间问题列表")


MomentumBacktestSummary.model_rebuild()

