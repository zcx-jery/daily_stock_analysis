# -*- coding: utf-8 -*-
"""Schemas for market review report APIs."""

from typing import List, Optional

from pydantic import BaseModel, Field


class MarketReportItem(BaseModel):
    """Market review report list item."""

    date: str = Field(..., description="报告日期，格式 YYYY-MM-DD")
    title: str = Field(..., description="报告标题")
    file_name: str = Field(..., description="报告文件名")
    updated_at: Optional[str] = Field(None, description="文件最后更新时间")


class MarketReportListResponse(BaseModel):
    """Market review report list response."""

    items: List[MarketReportItem] = Field(default_factory=list, description="报告列表")


class MarketReportDetailResponse(MarketReportItem):
    """Market review report detail response."""

    content: str = Field(..., description="Markdown 报告正文")
