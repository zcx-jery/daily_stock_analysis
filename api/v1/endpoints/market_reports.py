# -*- coding: utf-8 -*-
"""Endpoints for market review report browsing."""

import logging

from fastapi import APIRouter, HTTPException

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.market_reports import (
    MarketReportDetailResponse,
    MarketReportItem,
    MarketReportListResponse,
)
from src.services.market_report_service import MarketReportService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=MarketReportListResponse,
    responses={
        200: {"description": "大盘复盘报告列表"},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取大盘复盘报告列表",
    description="从 reports 目录读取市场复盘 Markdown 报告列表。",
)
def list_market_reports() -> MarketReportListResponse:
    try:
        service = MarketReportService()
        return MarketReportListResponse(
            items=[MarketReportItem(**item) for item in service.list_reports()]
        )
    except Exception as exc:
        logger.error("Failed to list market reports: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取大盘复盘报告列表失败: {exc}",
            },
        ) from exc


@router.get(
    "/{report_date}",
    response_model=MarketReportDetailResponse,
    responses={
        200: {"description": "大盘复盘报告详情"},
        404: {"description": "报告不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取大盘复盘报告详情",
    description="根据报告日期读取对应的市场复盘 Markdown 报告内容。",
)
def get_market_report(report_date: str) -> MarketReportDetailResponse:
    try:
        service = MarketReportService()
        item = service.get_report(report_date)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到日期为 {report_date} 的大盘复盘报告",
                },
            )
        return MarketReportDetailResponse(**item)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load market report %s: %s", report_date, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取大盘复盘报告详情失败: {exc}",
            },
        ) from exc
