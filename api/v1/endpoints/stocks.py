# -*- coding: utf-8 -*-
"""
===================================
股票数据接口
===================================

职责：
1. POST /api/v1/stocks/extract-from-image 从图片提取股票代码
2. POST /api/v1/stocks/parse-import 解析 CSV/Excel/剪贴板
3. GET /api/v1/stocks/{code}/quote 实时行情接口
4. GET /api/v1/stocks/{code}/history 历史行情接口
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from api.deps import (
    get_momentum_backtest_service,
    get_momentum_screener_ai_commentary_service,
    get_momentum_screener_service,
    get_momentum_secondary_decision_service,
)
from api.v1.schemas.momentum_ai import (
    MomentumScreenerAIReviewRequest,
    MomentumScreenerAISessionResponse,
)
from api.v1.schemas.stocks import (
    ExtractFromImageResponse,
    ExtractItem,
    KLineData,
    MomentumBacktestCreateRequest,
    MomentumBacktestCreateResponse,
    MomentumBacktestDailyDetailResponse,
    MomentumBacktestDailyListResponse,
    MomentumBacktestDeleteResponse,
    MomentumBacktestIssueListResponse,
    MomentumBacktestRunListResponse,
    MomentumBacktestRunResponse,
    MomentumBacktestSummaryResponse,
    MomentumScreenerRequest,
    MomentumScreenerResponse,
    MomentumSecondaryDecisionIntradayResponse,
    MomentumSecondaryDecisionResponse,
    StockHistoryResponse,
    StockQuote,
)
from api.v1.schemas.common import ErrorResponse
from src.config import get_config
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    extract_stock_codes_from_image,
)
from src.services.import_parser import (
    MAX_FILE_BYTES,
    parse_import_from_bytes,
    parse_import_from_text,
)
from src.services.momentum_backtest_service import MomentumBacktestService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from src.services.stock_service import StockService
from src.services.momentum_screener_service import MomentumScreenerService

if TYPE_CHECKING:
    from src.services.momentum_screener_ai_commentary_service import MomentumScreenerAICommentaryService

logger = logging.getLogger(__name__)

router = APIRouter()

# 须在 /{stock_code} 路由之前定义
ALLOWED_MIME_STR = ", ".join(ALLOWED_MIME)


@router.post(
    "/screener/momentum",
    response_model=MomentumScreenerResponse,
    responses={
        200: {"description": "筛选结果"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="次日强势股筛选",
    description="基于收盘后 Tushare 数据，对今日强势股进行多维评分并输出明日候选，支持 standard 和 aggressive 两种 profile。",
)
def screen_momentum_stocks(
    payload: MomentumScreenerRequest,
    service: MomentumScreenerService = Depends(get_momentum_screener_service),
) -> MomentumScreenerResponse:
    """执行次日强势股筛选，支持 standard 和 aggressive 两种评分画像。"""
    try:
        result = service.screen(
            top_n=payload.top_n,
            trade_date=payload.trade_date,
            profile=payload.profile,
        )
        logger.info(
            "Momentum screener completed: profile=%s trade_date=%s candidates=%s returned=%s sector_cache=%s",
            payload.profile,
            result.get("trade_date"),
            result.get("candidate_count"),
            len(result.get("results", [])),
            MomentumScreenerService.get_sector_cache_stats(),
        )
        return MomentumScreenerResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error(f"次日强势股筛选失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"筛选失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/decision",
    response_model=MomentumSecondaryDecisionResponse,
    responses={
        200: {"description": "筛选结果与二次决策结果"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="强势筛选二次决策",
    description="在现有强势筛选结果基础上，输出主线识别、默认组合、落选原因与执行提示。",
)
def build_momentum_secondary_decision(
    payload: MomentumScreenerRequest,
    wait_for_strategy_health: bool = Query(
        False,
        description="Whether to wait for real 20/60-day strategy health validation before responding.",
    ),
    service: MomentumSecondaryDecisionService = Depends(get_momentum_secondary_decision_service),
) -> MomentumSecondaryDecisionResponse:
    """构建强势筛选二次决策结果。"""
    try:
        result = service.build(
            top_n=payload.top_n,
            trade_date=payload.trade_date,
            profile=payload.profile,
            wait_for_strategy_health=wait_for_strategy_health,
        )
        return MomentumSecondaryDecisionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error("构建强势筛选二次决策失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"二次决策失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/decision/intraday",
    response_model=MomentumSecondaryDecisionIntradayResponse,
    responses={
        200: {"description": "筛选结果、二次决策与盘中信号"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="强势筛选盘中信号",
    description="在现有强势筛选与二次决策基础上，补充盘中买点状态、低置信度与最终买/不买收口提示。",
)
def build_momentum_intraday_signal(
    payload: MomentumScreenerRequest,
    wait_for_strategy_health: bool = Query(
        False,
        description="Whether to wait for real 20/60-day strategy health validation before responding.",
    ),
    service: MomentumSecondaryDecisionService = Depends(get_momentum_secondary_decision_service),
) -> MomentumSecondaryDecisionIntradayResponse:
    """构建强势筛选盘中信号结果。"""
    try:
        result = service.build_intraday(
            top_n=payload.top_n,
            trade_date=payload.trade_date,
            profile=payload.profile,
            wait_for_strategy_health=wait_for_strategy_health,
        )
        return MomentumSecondaryDecisionIntradayResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error("构建强势筛选盘中信号失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"盘中信号失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/backtests",
    response_model=MomentumBacktestCreateResponse,
    responses={
        200: {"description": "已创建或定位到 V1 回测任务"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="创建 V1 强势筛选回测任务",
    description="按交易日重放强势筛选 V1 生产链路，并冻结候选池、二次决策和 T+1/T+2 结果验证。",
)
def create_momentum_backtest_run(
    payload: MomentumBacktestCreateRequest,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestCreateResponse:
    """Create one synchronous momentum screener V1 backtest run."""
    try:
        creator = getattr(service, "create_run_async", None)
        if callable(creator):
            result = creator(
                start_trade_date=payload.start_trade_date,
                end_trade_date=payload.end_trade_date,
                profile=payload.profile,
                top_n=payload.top_n,
            )
        else:
            run = service.create_run(
                start_trade_date=payload.start_trade_date,
                end_trade_date=payload.end_trade_date,
                profile=payload.profile,
                top_n=payload.top_n,
            )
            result = {
                "created_new": True,
                "message": "已创建回测任务，正在后台计算",
                "run": run,
            }
        return MomentumBacktestCreateResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error("创建 V1 回测任务失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"创建回测任务失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests",
    response_model=MomentumBacktestRunListResponse,
    responses={
        200: {"description": "最近的 V1 回测任务列表"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询最近的 V1 回测任务",
)
def list_momentum_backtest_runs(
    limit: int = Query(20, ge=1, le=50, description="返回最近历史任务数量"),
    profile: Optional[str] = Query(None, description="按 standard/aggressive 过滤"),
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestRunListResponse:
    """List recent momentum screener V1 backtest runs."""
    try:
        return MomentumBacktestRunListResponse(**service.list_runs(limit=limit, profile=profile))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测任务列表失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测任务列表失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/backtests/{run_id}/cancel",
    response_model=MomentumBacktestRunResponse,
    responses={
        200: {"description": "V1 回测任务已取消"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        409: {"description": "当前任务状态不支持取消", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="取消 V1 回测任务",
)
def cancel_momentum_backtest_run(
    run_id: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestRunResponse:
    """Cancel one running momentum screener V1 backtest run."""
    try:
        return MomentumBacktestRunResponse(**service.cancel_run(run_id))
    except ValueError as e:
        message = str(e)
        status_code = 404 if "not found" in message.casefold() else 409
        raise HTTPException(
            status_code=status_code,
            detail={"error": "bad_request", "message": message},
        )
    except Exception as e:
        logger.error("取消 V1 回测任务失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"取消回测任务失败: {str(e)}"},
        )


@router.delete(
    "/screener/momentum/backtests/{run_id}",
    response_model=MomentumBacktestDeleteResponse,
    responses={
        200: {"description": "V1 回测任务已删除"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        409: {"description": "当前任务状态不支持删除", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="删除 V1 回测任务",
)
def delete_momentum_backtest_run(
    run_id: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestDeleteResponse:
    """Delete one persisted momentum screener V1 backtest run."""
    try:
        return MomentumBacktestDeleteResponse(**service.delete_run(run_id))
    except ValueError as e:
        message = str(e)
        status_code = 404 if "not found" in message.casefold() else 409
        raise HTTPException(
            status_code=status_code,
            detail={"error": "bad_request", "message": message},
        )
    except Exception as e:
        logger.error("删除 V1 回测任务失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"删除回测任务失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests/{run_id}",
    response_model=MomentumBacktestRunResponse,
    responses={
        200: {"description": "V1 回测任务状态"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询 V1 回测任务状态",
)
def get_momentum_backtest_run(
    run_id: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestRunResponse:
    """Get one momentum screener V1 backtest run by run_id."""
    try:
        return MomentumBacktestRunResponse(**service.get_run(run_id))
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测任务失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测任务失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests/{run_id}/summary",
    response_model=MomentumBacktestSummaryResponse,
    responses={
        200: {"description": "V1 回测区间摘要"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询 V1 回测区间摘要",
)
def get_momentum_backtest_summary(
    run_id: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestSummaryResponse:
    """Get one momentum screener V1 backtest run summary."""
    try:
        return MomentumBacktestSummaryResponse(**service.get_summary(run_id))
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测摘要失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测摘要失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests/{run_id}/daily",
    response_model=MomentumBacktestDailyListResponse,
    responses={
        200: {"description": "V1 回测单日摘要列表"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询 V1 回测单日列表",
)
def list_momentum_backtest_daily(
    run_id: str,
    date_from: Optional[str] = Query(None, description="起始交易日过滤，格式 YYYY-MM-DD 或 YYYYMMDD"),
    date_to: Optional[str] = Query(None, description="结束交易日过滤，格式 YYYY-MM-DD 或 YYYYMMDD"),
    market_regime: Optional[str] = Query(None, description="市场分桶过滤，支持 strong/general/weak 或 bull/neutral/bear"),
    action_level: Optional[str] = Query(None, description="总闸门级别过滤"),
    slot: Optional[str] = Query(None, description="组合槽位过滤，支持 main/secondary/watch"),
    theme_name: Optional[str] = Query(None, description="主线主题关键字过滤"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestDailyListResponse:
    """List daily summaries for one momentum screener V1 backtest run."""
    try:
        return MomentumBacktestDailyListResponse(
            **service.list_daily(
                run_id,
                date_from=date_from,
                date_to=date_to,
                market_regime=market_regime,
                action_level=action_level,
                slot=slot,
                theme_name=theme_name,
                page=page,
                page_size=page_size,
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测单日列表失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测单日列表失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests/{run_id}/daily/{trade_date}",
    response_model=MomentumBacktestDailyDetailResponse,
    responses={
        200: {"description": "V1 回测单日详情"},
        404: {"description": "回测任务或交易日不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询 V1 回测单日详情",
)
def get_momentum_backtest_daily_detail(
    run_id: str,
    trade_date: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestDailyDetailResponse:
    """Get one momentum screener V1 backtest daily detail."""
    try:
        return MomentumBacktestDailyDetailResponse(**service.get_daily_detail(run_id, trade_date))
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测单日详情失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测单日详情失败: {str(e)}"},
        )


@router.get(
    "/screener/momentum/backtests/{run_id}/issues",
    response_model=MomentumBacktestIssueListResponse,
    responses={
        200: {"description": "V1 回测问题诊断"},
        404: {"description": "回测任务不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="查询 V1 回测问题诊断",
)
def get_momentum_backtest_issues(
    run_id: str,
    service: MomentumBacktestService = Depends(get_momentum_backtest_service),
) -> MomentumBacktestIssueListResponse:
    """List issue diagnostics for one momentum screener V1 backtest run."""
    try:
        return MomentumBacktestIssueListResponse(**service.get_issues(run_id))
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": str(e)},
        )
    except Exception as e:
        logger.error("查询 V1 回测问题诊断失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"查询回测问题诊断失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/ai/session",
    response_model=MomentumScreenerAISessionResponse,
    responses={
        200: {"description": "已存在的强势筛选 AI 会话"},
        400: {"description": "参数错误", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="加载强势筛选 AI 会话",
    description="按点评场景和筛选快照推导会话 ID，并返回当前已保存的 AI 点评历史。",
)
def load_momentum_ai_review_session(
    payload: MomentumScreenerAIReviewRequest,
    service: "MomentumScreenerAICommentaryService" = Depends(get_momentum_screener_ai_commentary_service),
) -> MomentumScreenerAISessionResponse:
    """Load one screener AI session by its logical review target."""
    try:
        return MomentumScreenerAISessionResponse(**service.load_session(payload))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": str(e)},
        )
    except Exception as e:
        logger.error("加载强势筛选 AI 会话失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"加载 AI 会话失败: {str(e)}"},
        )


@router.post(
    "/screener/momentum/ai/stream",
    summary="流式生成强势筛选 AI 点评",
    description="基于当前筛选结果快照流式生成 AI 点评，支持 resume/rerun 语义与快捷追问。",
)
async def stream_momentum_ai_review(
    payload: MomentumScreenerAIReviewRequest,
    service: "MomentumScreenerAICommentaryService" = Depends(get_momentum_screener_ai_commentary_service),
):
    """Stream screener AI commentary over SSE."""
    if not get_config().is_agent_available():
        raise HTTPException(status_code=400, detail="Agent mode is not enabled")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def progress_callback(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def run_sync() -> None:
        try:
            result = service.stream_review(payload, progress_callback=progress_callback)
            asyncio.run_coroutine_threadsafe(
                queue.put(
                    {
                        "type": "done",
                        "success": result.get("success", True),
                        "content": result.get("content", ""),
                        "session_id": result.get("session_id"),
                        "context_meta": result.get("context_meta"),
                        "suggested_questions": result.get("suggested_questions", []),
                    }
                ),
                loop,
            )
        except Exception as exc:
            logger.error("强势筛选 AI 点评流式生成失败: %s", exc, exc_info=True)
            asyncio.run_coroutine_threadsafe(
                queue.put({"type": "error", "message": str(exc)}),
                loop,
            )

    async def event_generator():
        fut = loop.run_in_executor(None, run_sync)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield "data: " + json.dumps({"type": "error", "message": "AI 点评超时"}, ensure_ascii=False) + "\n\n"
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in {"done", "error"}:
                    break
        finally:
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                logger.debug("momentum screener ai cleanup timed out")
            except Exception as exc:
                logger.warning("momentum screener ai cleanup error (ignored): %s", exc, exc_info=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/extract-from-image",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "提取的股票代码"},
        400: {"description": "图片无效", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="从图片提取股票代码",
    description="上传截图/图片，通过 Vision LLM 提取股票代码。支持 JPEG、PNG、WebP、GIF，最大 5MB。",
)
def extract_from_image(
    file: Optional[UploadFile] = File(None, description="图片文件（表单字段名 file）"),
    include_raw: bool = Query(False, description="是否在结果中包含原始 LLM 响应"),
) -> ExtractFromImageResponse:
    """
    从上传的图片中提取股票代码（使用 Vision LLM）。

    表单字段请使用 file 上传图片。优先级：Gemini / Anthropic / OpenAI（首个可用）。
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file 上传图片"},
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_type",
                "message": f"不支持的类型: {content_type}。允许: {ALLOWED_MIME_STR}",
            },
        )

    try:
        # 先读取限定大小，再检查是否还有剩余（语义清晰：超出则拒绝）
        data = file.file.read(MAX_SIZE_BYTES)
        if file.file.read(1):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"图片超过 {MAX_SIZE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"读取上传文件失败: {e}")
        raise HTTPException(
            status_code=400,
            detail={"error": "read_failed", "message": "读取上传文件失败"},
        )

    try:
        items, raw_text = extract_stock_codes_from_image(data, content_type)
        extract_items = [
            ExtractItem(code=code, name=name, confidence=conf) for code, name, conf in items
        ]
        codes = [i.code for i in extract_items]
        return ExtractFromImageResponse(
            codes=codes,
            items=extract_items,
            raw_text=raw_text if include_raw else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "extract_failed", "message": str(e)})
    except Exception as e:
        logger.error(f"图片提取失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "图片提取失败"},
        )


@router.post(
    "/parse-import",
    response_model=ExtractFromImageResponse,
    responses={
        200: {"description": "解析结果"},
        400: {"description": "未提供数据或解析失败", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="解析 CSV/Excel/剪贴板",
    description="上传 CSV/Excel 文件或粘贴文本，自动解析股票代码。文件上限 2MB，文本上限 100KB。",
)
async def parse_import(request: Request) -> ExtractFromImageResponse:
    """
    解析 CSV/Excel 文件或剪贴板文本。

    - multipart/form-data + file: 上传文件
    - application/json + {"text": "..."}: 粘贴文本
    - 优先使用 file，若同时提供则忽略 text
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            logger.warning("[parse_import] JSON parse failed: %s", e)
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_json", "message": f"JSON 解析失败: {e}"},
            )
        text = body.get("text") if isinstance(body, dict) else None
        if not text or not isinstance(text, str):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供 text，请使用 {\"text\": \"...\"}"},
            )
        try:
            items = parse_import_from_text(text)
        except ValueError as e:
            text_bytes = len(text.encode("utf-8"))
            logger.warning(
                "[parse_import] parse_import_from_text failed: text_bytes=%d, error=%s",
                text_bytes,
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    elif "multipart" in content_type:
        form = await request.form()
        file = form.get("file")
        if not file or not hasattr(file, "read"):
            raise HTTPException(
                status_code=400,
                detail={"error": "bad_request", "message": "未提供文件，请使用表单字段 file"},
            )
        file_size = getattr(file, "size", None)
        if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "file_too_large",
                    "message": f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                },
            )
        try:
            data = file.file.read(MAX_FILE_BYTES)
            if file.file.read(1):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "file_too_large",
                        "message": f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制",
                    },
                )
        except HTTPException:
            raise
        except Exception as e:
            filename = getattr(file, "filename", None) or ""
            size = getattr(file, "size", None)
            logger.warning(
                "[parse_import] file read failed: filename=%r, size=%s, error=%s",
                filename,
                size,
                e,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "read_failed", "message": "读取文件失败"},
            )
        filename = getattr(file, "filename", None) or ""
        try:
            items = parse_import_from_bytes(data, filename=filename)
        except ValueError as e:
            ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            logger.warning(
                "[parse_import] parse_import_from_bytes failed: filename=%r, ext=%r, bytes=%d, error=%s",
                filename,
                ext,
                len(data),
                e,
            )
            raise HTTPException(status_code=400, detail={"error": "parse_failed", "message": str(e)})
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bad_request",
                "message": "请使用 multipart/form-data 上传文件，或 application/json 提交 {\"text\": \"...\"}",
            },
        )

    extract_items = [
        ExtractItem(code=code, name=name, confidence=conf)
        for code, name, conf in items
    ]
    codes = list(dict.fromkeys(i.code for i in extract_items if i.code))
    return ExtractFromImageResponse(codes=codes, items=extract_items, raw_text=None)


@router.get(
    "/{stock_code}/quote",
    response_model=StockQuote,
    responses={
        200: {"description": "行情数据"},
        404: {"description": "股票不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票实时行情",
    description="获取指定股票的最新行情数据"
)
def get_stock_quote(stock_code: str) -> StockQuote:
    """
    获取股票实时行情
    
    获取指定股票的最新行情数据
    
    Args:
        stock_code: 股票代码（如 600519、00700、AAPL）
        
    Returns:
        StockQuote: 实时行情数据
        
    Raises:
        HTTPException: 404 - 股票不存在
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_realtime_quote(stock_code)
        
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_found",
                    "message": f"未找到股票 {stock_code} 的行情数据"
                }
            )
        
        return StockQuote(
            stock_code=result.get("stock_code", stock_code),
            stock_name=result.get("stock_name"),
            current_price=result.get("current_price", 0.0),
            change=result.get("change"),
            change_percent=result.get("change_percent"),
            open=result.get("open"),
            high=result.get("high"),
            low=result.get("low"),
            prev_close=result.get("prev_close"),
            volume=result.get("volume"),
            amount=result.get("amount"),
            update_time=result.get("update_time")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实时行情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取实时行情失败: {str(e)}"
            }
        )


@router.get(
    "/{stock_code}/history",
    response_model=StockHistoryResponse,
    responses={
        200: {"description": "历史行情数据"},
        422: {"description": "不支持的周期参数", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取股票历史行情",
    description="获取指定股票的历史 K 线数据"
)
def get_stock_history(
    stock_code: str,
    period: str = Query("daily", description="K 线周期", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365, description="获取天数")
) -> StockHistoryResponse:
    """
    获取股票历史行情
    
    获取指定股票的历史 K 线数据
    
    Args:
        stock_code: 股票代码
        period: K 线周期 (daily/weekly/monthly)
        days: 获取天数
        
    Returns:
        StockHistoryResponse: 历史行情数据
    """
    try:
        service = StockService()
        
        # 使用 def 而非 async def，FastAPI 自动在线程池中执行
        result = service.get_history_data(
            stock_code=stock_code,
            period=period,
            days=days
        )
        
        # 转换为响应模型
        data = [
            KLineData(
                date=item.get("date"),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                amount=item.get("amount"),
                change_percent=item.get("change_percent")
            )
            for item in result.get("data", [])
        ]
        
        return StockHistoryResponse(
            stock_code=stock_code,
            stock_name=result.get("stock_name"),
            period=period,
            data=data
        )
    
    except ValueError as e:
        # period 参数不支持的错误（如 weekly/monthly）
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_period",
                "message": str(e)
            }
        )
    except Exception as e:
        logger.error(f"获取历史行情失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": f"获取历史行情失败: {str(e)}"
            }
        )
