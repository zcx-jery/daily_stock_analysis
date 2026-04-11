# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
"""

from typing import Optional, List, Dict, Any, Literal

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    """股票实时行情"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
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
                "update_time": "2024-01-01T15:00:00"
            }
        }


class KLineData(BaseModel):
    """K 线数据点"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    
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
                "change_percent": 0.84
            }
        }


class ExtractItem(BaseModel):
    """单条提取结果（代码、名称、置信度）"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片股票代码提取响应"""

    codes: List[str] = Field(..., description="提取的股票代码（已去重，向后兼容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取结果明细（代码+名称+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应（调试用）")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应"""
    
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
                "data": []
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
    continuation_score: float = Field(..., description="次日延续概率分")
    extension_score: float = Field(..., description="上涨弹性分")
    risk_score: float = Field(..., description="风险分")
    buyability_score: Optional[float] = Field(None, description="可买性分，仅 aggressive 使用")
    opportunity_tag: Optional[str] = Field(None, description="交易机会标签，仅 aggressive 使用")
    entry_range_low: Optional[float] = Field(None, description="建议低位买入区间，仅 aggressive 使用")
    entry_range_high: Optional[float] = Field(None, description="建议高位买入区间，仅 aggressive 使用")
    final_score: float = Field(..., description="最终总分")
    rank_score: float = Field(..., description="排序分")
    themes: List[str] = Field(default_factory=list, description="所属板块")
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
