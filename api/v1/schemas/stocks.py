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

    top_n: int = Field(10, ge=1, le=100, description="返回前几只股票")
    min_change_pct: float = Field(7.0, ge=0, le=20, description="今日涨幅阈值")
    min_amount: float = Field(3e8, ge=0, description="最低成交额（元）")
    min_turnover: float = Field(3.0, ge=0, le=100, description="最低换手率")
    exclude_st: bool = Field(True, description="是否排除 ST")
    main_board_only: bool = Field(True, description="是否仅保留主板")
    trade_date: Optional[str] = Field(None, description="交易日，格式 YYYY-MM-DD 或 YYYYMMDD")
    profile: Literal["standard", "aggressive"] = Field("standard", description="评分画像")


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
    pct_chg: float = Field(..., description="今日涨幅")
    continuation_score: float = Field(..., description="次日延续分")
    extension_score: float = Field(..., description="上冲弹性分")
    risk_score: float = Field(..., description="风险分")
    buyability_score: Optional[float] = Field(None, description="可买性分，仅 aggressive 使用")
    opportunity_tag: Optional[str] = Field(None, description="机会标签，仅 aggressive 使用")
    entry_range_low: Optional[float] = Field(None, description="建议低位买入区间，仅 aggressive 使用")
    entry_range_high: Optional[float] = Field(None, description="建议高位买入区间，仅 aggressive 使用")
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
    trade_date: str = Field(..., description="交易日")
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


class MomentumDecisionTheme(BaseModel):
    """主线识别结果。"""

    name: str = Field(..., description="主线名称")
    score: float = Field(..., description="主线综合评分")
    strength_label: str = Field(..., description="主线强弱标签")
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
    role: str = Field(..., description="角色标签")
    score: float = Field(..., description="组合优先级分")
    rank_score: float = Field(..., description="原始排序分")
    risk_score: float = Field(..., description="风险分")
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


class MomentumDecisionExcludedCandidate(BaseModel):
    """未进入默认组合的候选股说明。"""

    rank: int = Field(..., description="在当前筛选结果中的排名")
    ts_code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    theme: str = Field(..., description="所属主线")
    role: str = Field(..., description="角色标签")
    reason: str = Field(..., description="主淘汰原因")
    rank_score: float = Field(..., description="排序分")


class MomentumDecisionEvidence(BaseModel):
    """二次决策证据区。"""

    theme_validation: List[str] = Field(default_factory=list, description="主线验证证据")
    today_reasoning: List[str] = Field(default_factory=list, description="今日结论证据")


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
    reason: str = Field(..., description="展示或不展示的原因")
    steps: List[MomentumActionChecklistStep] = Field(default_factory=list, description="按时间组织的行动步骤")


class MomentumStrategyHealthWindow(BaseModel):
    """策略健康的单个窗口状态。"""

    window: Literal["short_20d", "long_60d"] = Field(..., description="窗口枚举")
    window_label: str = Field(..., description="窗口文案")
    status: Literal["healthy", "recovering", "weak"] = Field(..., description="窗口状态")
    status_label: str = Field(..., description="窗口状态文案")
    score: float = Field(..., description="窗口健康分")
    threshold: float = Field(..., description="达到健康状态的阈值")
    summary: str = Field(..., description="窗口状态摘要")


    sample_count: int = Field(..., description="鍙傝瘎鏍锋湰鏁伴噺")
    success_count: int = Field(..., description="婊¤冻缁勫悎鏍囧噯鐨勬牱鏈暟")
    success_rate: float = Field(..., description="缁勫悎鎴愬姛鐜?%)")
    avg_profit_window_pct: float = Field(..., description="1-2 涓氦鏄撴棩鍒╂鼎绐楀彛鍧囧€?%)")
    avg_max_drawdown_pct: float = Field(..., description="1-2 涓氦鏄撴棩鏈€澶у洖鎾ゅ潎鍊?%)")
    avg_selected_count: float = Field(..., description="姣忔棩榛樿缁勫悎鍧囧€煎叆閫夋暟")


class MomentumStrategyHealth(BaseModel):
    """策略健康状态。"""

    status: Literal["healthy", "partial_healthy", "recovery_mode", "disabled"] = Field(
        ...,
        description="策略健康总状态",
    )
    label: str = Field(..., description="策略健康状态文案")
    reason: str = Field(..., description="当前状态的一句话解释")
    recommendation_cap: Literal["full", "limited", "disabled"] = Field(..., description="当前推荐能力上限")
    can_full_recommend: bool = Field(..., description="当前是否允许完整强推荐")
    short_window: MomentumStrategyHealthWindow = Field(..., description="20 日窗口状态")
    long_window: MomentumStrategyHealthWindow = Field(..., description="60 日窗口状态")
    blockers: List[str] = Field(default_factory=list, description="当前阻断项")
    recovery_conditions: List[str] = Field(default_factory=list, description="恢复条件")
    data_source: Literal["historical", "proxy"] = Field("historical", description="当前策略健康结果来源")
    is_warming: bool = Field(False, description="真实历史验证是否仍在后台计算")


class MomentumSecondaryDecision(BaseModel):
    """二次决策静态结果。"""

    profile: Literal["standard", "aggressive"] = Field(..., description="候选引擎来源")
    trade_date: str = Field(..., description="交易日")
    action: MomentumDecisionAction = Field(..., description="今日出手级别")
    strategy_health: MomentumStrategyHealth = Field(..., description="策略健康状态")
    themes: List[MomentumDecisionTheme] = Field(default_factory=list, description="主线识别结果")
    portfolio: List[MomentumDecisionPortfolioSlot] = Field(default_factory=list, description="默认 1-3 票组合")
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
    final_recommendation: Literal["buy", "watch", "do_not_buy"] = Field(
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
