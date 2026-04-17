# -*- coding: utf-8 -*-
"""Schemas for momentum screener AI commentary."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from api.v1.schemas.stocks import (
    MomentumIntradaySignal,
    MomentumScreenerRequest,
    MomentumScreenerResponse,
    MomentumSecondaryDecision,
)

MomentumScreenerAIReviewType = Literal["candidate", "decision", "intraday", "excluded"]
MomentumScreenerAIRefreshMode = Literal["resume", "rerun"]


class MomentumScreenerAIContextMeta(BaseModel):
    """Trust-bar metadata for one assistant answer."""

    review_type: MomentumScreenerAIReviewType = Field(..., description="AI 点评场景")
    review_type_label: str = Field(..., description="AI 点评场景中文标签")
    review_target: str = Field(..., description="本次点评对象")
    trade_date: str = Field(..., description="当前规则快照交易日")
    profile: Literal["standard", "aggressive"] = Field(..., description="当前筛选画像")
    rule_conclusion: str = Field(..., description="规则层已经给出的核心结论")
    rule_guardrail: str = Field(..., description="当前不可越过的规则边界")
    market_data_as_of: Optional[str] = Field(None, description="盘中或外部补充数据时间")
    tools_used: List[str] = Field(default_factory=list, description="本轮 AI 点评实际调用的工具")


class MomentumScreenerAIMessage(BaseModel):
    """Parsed message shown in the screener AI panel."""

    id: str = Field(..., description="消息 ID")
    role: Literal["user", "assistant"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息正文")
    created_at: Optional[str] = Field(None, description="消息时间")
    context_meta: Optional[MomentumScreenerAIContextMeta] = Field(
        None,
        description="assistant 消息对应的 trust bar 元信息",
    )
    suggested_questions: List[str] = Field(default_factory=list, description="当前消息推荐的快捷追问")


class MomentumScreenerAISessionResponse(BaseModel):
    """Existing screener AI session payload."""

    session_id: str = Field(..., description="会话 ID")
    review_type: MomentumScreenerAIReviewType = Field(..., description="当前点评场景")
    review_type_label: str = Field(..., description="当前点评场景中文标签")
    session_title: str = Field(..., description="当前会话标题")
    messages: List[MomentumScreenerAIMessage] = Field(default_factory=list, description="会话消息列表")


class MomentumScreenerAIReviewRequest(BaseModel):
    """Request payload for screener AI commentary."""

    review_type: MomentumScreenerAIReviewType = Field(..., description="点评场景")
    review_key: str = Field(..., description="点评对象唯一标识")
    refresh_mode: MomentumScreenerAIRefreshMode = Field(
        "resume",
        description="resume=继续查看当前会话, rerun=基于最新上下文重跑",
    )
    session_id: Optional[str] = Field(None, description="前端已持有的会话 ID")
    message: Optional[str] = Field(None, description="用户追问；为空时系统自动生成首条点评请求")
    payload: MomentumScreenerRequest = Field(..., description="当前筛选参数快照")
    screening: MomentumScreenerResponse = Field(..., description="当前页面筛选结果快照")
    decision: Optional[MomentumSecondaryDecision] = Field(None, description="当前页面二次决策快照")
    intraday_signal: Optional[MomentumIntradaySignal] = Field(None, description="当前页面盘中信号快照")
