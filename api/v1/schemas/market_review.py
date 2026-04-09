# -*- coding: utf-8 -*-
"""Schemas for structured market review APIs."""

from typing import List, Optional

from pydantic import BaseModel, Field


class MarketReviewListItem(BaseModel):
    """Structured market review list item."""

    report_date: str = Field(..., description="报告日期，格式 YYYY-MM-DD")
    title: str = Field(..., description="报告标题")
    sentiment: str = Field(..., description="市场情绪图标")
    sentiment_label: str = Field(..., description="市场情绪说明")
    file_size: int = Field(..., description="报告文件大小（字节）")


class MarketReviewItem(BaseModel):
    """Structured market review detail payload."""

    report_date: str = Field(..., description="报告日期，格式 YYYY-MM-DD")
    title: str = Field(..., description="报告标题")
    sentiment: str = Field(..., description="市场情绪图标")
    sentiment_label: str = Field(..., description="市场情绪说明")
    shanghai_index: Optional[float] = Field(None, description="上证指数")
    shanghai_change: Optional[float] = Field(None, description="上证指数涨跌幅（%）")
    shenzhen_index: Optional[float] = Field(None, description="深证成指")
    shenzhen_change: Optional[float] = Field(None, description="深证成指涨跌幅（%）")
    chi_index: Optional[float] = Field(None, description="创业板指")
    chi_change: Optional[float] = Field(None, description="创业板指涨跌幅（%）")
    total_volume: Optional[float] = Field(None, description="两市成交额（亿）")
    rising_count: Optional[int] = Field(None, description="上涨家数")
    falling_count: Optional[int] = Field(None, description="下跌家数")
    limit_up: Optional[int] = Field(None, description="涨停家数")
    limit_down: Optional[int] = Field(None, description="跌停家数")
    top_sectors: List[str] = Field(default_factory=list, description="领涨板块")
    bottom_sectors: List[str] = Field(default_factory=list, description="领跌板块")
    strategy: Optional[str] = Field(None, description="策略判断")
    content: str = Field(..., description="完整 Markdown 报告内容")


class MarketReviewListResponse(BaseModel):
    """Structured market review list response."""

    items: List[MarketReviewListItem] = Field(default_factory=list, description="报告列表")
    total: int = Field(..., description="符合条件的总数")


class MarketReviewResponse(BaseModel):
    """Structured market review detail response."""

    item: MarketReviewItem = Field(..., description="报告详情")
