# -*- coding: utf-8 -*-
"""
===================================
API 依赖注入模块
===================================

职责：
1. 提供数据库 Session 依赖
2. 提供配置依赖
3. 提供服务层依赖
"""

from typing import TYPE_CHECKING, Generator

from fastapi import Request
from sqlalchemy.orm import Session

from src.storage import DatabaseManager
from src.config import get_config, Config
from src.services.momentum_screener_service import MomentumScreenerService
from src.services.momentum_backtest_service import MomentumBacktestService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from src.services.stock_service import StockService
from src.services.system_config_service import SystemConfigService

if TYPE_CHECKING:
    from src.services.momentum_screener_ai_commentary_service import MomentumScreenerAICommentaryService


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库 Session 依赖
    
    使用 FastAPI 依赖注入机制，确保请求结束后自动关闭 Session
    
    Yields:
        Session: SQLAlchemy Session 对象
        
    Example:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            ...
    """
    db_manager = DatabaseManager.get_instance()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def get_config_dep() -> Config:
    """
    获取配置依赖
    
    Returns:
        Config: 配置单例对象
    """
    return get_config()


def get_database_manager() -> DatabaseManager:
    """
    获取数据库管理器依赖
    
    Returns:
        DatabaseManager: 数据库管理器单例对象
    """
    return DatabaseManager.get_instance()


def get_system_config_service(request: Request) -> SystemConfigService:
    """Get app-lifecycle shared SystemConfigService instance."""
    service = getattr(request.app.state, "system_config_service", None)
    if service is None:
        service = SystemConfigService()
        request.app.state.system_config_service = service
    return service


def get_momentum_screener_service(request: Request) -> MomentumScreenerService:
    """Get app-lifecycle shared MomentumScreenerService instance."""
    service = getattr(request.app.state, "momentum_screener_service", None)
    if service is None:
        service = MomentumScreenerService()
        request.app.state.momentum_screener_service = service
    return service


def get_momentum_secondary_decision_service(request: Request) -> MomentumSecondaryDecisionService:
    """Get app-lifecycle shared MomentumSecondaryDecisionService instance."""
    service = getattr(request.app.state, "momentum_secondary_decision_service", None)
    if service is None:
        screener_service = getattr(request.app.state, "momentum_screener_service", None)
        stock_service = getattr(request.app.state, "stock_service", None)
        if stock_service is None:
            stock_service = StockService()
            request.app.state.stock_service = stock_service
        service = MomentumSecondaryDecisionService(
            screener_service=screener_service,
            stock_service=stock_service,
            strategy_health_async=True,
            strategy_health_async_delay_seconds=0.0,
        )
        request.app.state.momentum_secondary_decision_service = service
    return service


def get_momentum_backtest_service(request: Request) -> MomentumBacktestService:
    """Get app-lifecycle shared MomentumBacktestService instance."""
    service = getattr(request.app.state, "momentum_backtest_service", None)
    if service is None:
        screener_service = getattr(request.app.state, "momentum_screener_service", None)
        if screener_service is None:
            screener_service = MomentumScreenerService()
            request.app.state.momentum_screener_service = screener_service
        decision_service = getattr(request.app.state, "momentum_secondary_decision_service", None)
        if decision_service is None:
            decision_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                strategy_health_async=False,
            )
            request.app.state.momentum_secondary_decision_service = decision_service
        service = MomentumBacktestService(
            screener_service=screener_service,
            decision_service=decision_service,
        )
        request.app.state.momentum_backtest_service = service
    return service


def _get_momentum_screener_ai_commentary_service_cls():
    from src.services.momentum_screener_ai_commentary_service import MomentumScreenerAICommentaryService

    return MomentumScreenerAICommentaryService


def get_momentum_screener_ai_commentary_service(request: Request) -> "MomentumScreenerAICommentaryService":
    """Get app-lifecycle shared MomentumScreenerAICommentaryService instance."""
    service = getattr(request.app.state, "momentum_screener_ai_commentary_service", None)
    if service is None:
        service = _get_momentum_screener_ai_commentary_service_cls()()
        request.app.state.momentum_screener_ai_commentary_service = service
    return service
