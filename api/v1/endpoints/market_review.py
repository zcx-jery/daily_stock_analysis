# -*- coding: utf-8 -*-
"""Endpoints for structured market review browsing."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.market_review import (
    MarketReviewItem,
    MarketReviewListItem,
    MarketReviewListResponse,
    MarketReviewResponse,
)
from src.services.market_review_service import MarketReviewService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=MarketReviewListResponse,
    responses={
        200: {"description": "结构化大盘复盘报告列表"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取结构化大盘复盘报告列表",
    description="从 reports 目录读取大盘复盘 Markdown 报告，并返回结构化列表数据。",
)
def list_market_reviews(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 30,
) -> MarketReviewListResponse:
    try:
        service = MarketReviewService()
        items = service.list_reviews(start_date=start_date, end_date=end_date, limit=limit)
        return MarketReviewListResponse(
            items=[MarketReviewListItem(**item) for item in items],
            total=len(items),
        )
    except Exception as exc:
        logger.error("Failed to list market reviews: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取结构化大盘复盘报告列表失败: {exc}",
            },
        ) from exc


@router.get(
    "/{report_date}",
    response_model=MarketReviewResponse,
    responses={
        200: {"description": "结构化大盘复盘报告详情"},
        404: {"description": "报告不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取结构化大盘复盘报告详情",
    description="根据报告日期读取对应的 Markdown 报告，并提取指数、涨跌家数和策略等结构化字段。",
)
def get_market_review(report_date: str) -> MarketReviewResponse:
    try:
        service = MarketReviewService()
        item = service.get_review(report_date)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到日期为 {report_date} 的结构化大盘复盘报告",
                },
            )
        return MarketReviewResponse(item=MarketReviewItem(**item))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load market review %s: %s", report_date, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取结构化大盘复盘报告详情失败: {exc}",
            },
        ) from exc
