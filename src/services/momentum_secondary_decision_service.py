# -*- coding: utf-8 -*-
"""Momentum screener secondary decision service."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import hashlib
import json
import logging
from math import ceil, isfinite
from pathlib import Path
import pandas as pd
from statistics import mean
from threading import Lock, Timer
import time as time_module
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.repositories.stock_repo import StockRepository
from src.services.momentum_screener_service import (
    MOMENTUM_DEFAULT_MIN_AMOUNT,
    MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
    MOMENTUM_DEFAULT_MIN_TURNOVER,
    MOMENTUM_DEFAULT_TOP_N,
    MomentumScreenerService,
)
from src.services.momentum_v13_data_service import MomentumV13DataService
from src.services.stock_service import StockService

ACTION_LEVEL_SEQUENCE = [
    "strong_go",
    "normal_go",
    "cautious_go",
    "observe_only",
    "stand_aside",
]

ACTION_LEVEL_LABELS = {
    "strong_go": "强烈可做",
    "normal_go": "可正常出手",
    "cautious_go": "谨慎出手",
    "observe_only": "仅观察",
    "stand_aside": "今日不做",
}
GATE_LEVEL_LABELS = {
    "strong": "强",
    "medium": "中",
    "weak": "弱",
}
OPPORTUNITY_MATRIX_LEVEL_LABELS = {
    "strong": "强",
    "upper_mid": "中上",
    "mid": "中",
    "weak": "弱",
}
HISTORICAL_VALIDITY_LABELS = {
    "healthy": "健康",
    "general": "一般",
    "weak": "偏弱",
}
ATTACK_PERMISSION_STATUS_LABELS = {
    "open": "可进攻",
    "recovering": "恢复中",
    "paused": "暂停进攻",
}
THEME_CONFIDENCE_STATUS_LABELS = {
    "credible": "可信",
    "recovering": "恢复中",
    "questionable": "存疑",
}

SLOT_LABELS = {
    "main": "主仓",
    "secondary": "次仓",
    "watch": "观察仓",
}

BUY_POINT_LABELS = {
    "clear": "买点清晰",
    "waiting": "等待触发",
    "unclear": "买点不清晰",
}

SUGGESTED_ACTION_LABELS = {
    "ready": "可准备执行",
    "wait_for_trigger": "继续等触发",
    "observe_only": "保留观察但不建议执行",
}

ROLE_LABELS = {
    "leader": "龙头核心",
    "front": "前排换手",
    "mid": "观察备选",
    "back": "观察备选",
}

ROLE_PRIORITY = {
    "leader": 12.0,
    "front": 8.0,
    "mid": 3.0,
    "back": 0.0,
}

BUY_POINT_PRIORITY = {
    "clear": 12.0,
    "waiting": 5.0,
    "unclear": 0.0,
}

# Portfolio sorting now treats role and buy-point labels as explainability
# tie-breakers instead of hard ranking drivers. The old priority constants are
# kept for compatibility with older reports and comments.
ROLE_TIEBREAKER_PRIORITY = {
    "leader": 3.0,
    "front": 4.0,
    "mid": 2.0,
    "back": 0.0,
}

BUY_POINT_TIEBREAKER_PRIORITY = {
    "clear": 4.0,
    "waiting": 3.0,
    "unclear": -4.0,
}

DIVERSIFICATION_PRIORITY_TOLERANCE = 2.0
MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE = 2.5
MAINLINE_CONFIRMATION_PRIORITY_TOLERANCE = 3.0
SAME_THEME_CONFIRMATION_PRIORITY_TOLERANCE = 3.0
WAITING_FRONT_CLEAR_LEADER_OFFICIAL_GAP_TOLERANCE = 1.2
WAITING_FRONT_CLEAR_LEADER_FORWARD_ALPHA_ADVANTAGE_CAP = 7.5
V13_CONTEXT_MAX_TS_CODES = 30
DECISION_CANDIDATE_POOL_LIMIT = 12
ADAPTIVE_GATE_LOOKBACK_DAYS = 5
ADAPTIVE_GATE_DEFENSIVE_RATE_THRESHOLD_PCT = 80.0
ADAPTIVE_MAINLINE_MIN_POOL_COUNT = 3

EXCLUDED_REASON_LABELS = {
    "non_mainline_weak": "非主线 / 主线过弱",
    "buy_point_unclear": "买点不清晰",
    "role_duplicate": "角色重复",
    "mainline_rank_not_enough": "主线内名次不够",
    "hard_blocked": "命中硬阻断",
    "slot_capacity": "本轮收口优先级更低",
}

BUY_SIGNAL_ACTION_LEVELS = {"strong_go", "normal_go", "cautious_go"}
ACTION_CHECKLIST_ENABLED_LEVELS = {"strong_go", "normal_go", "cautious_go"}
ACTION_CHECKLIST_PHASE_LABELS = {
    "pre_open": "开盘前",
    "first_30m": "开盘后 30 分钟",
    "first_60m": "开盘后 60 分钟内",
}
STRATEGY_HEALTH_LABELS = {
    "healthy": "正常",
    "partial_healthy": "谨慎",
    "recovery_mode": "恢复中",
    "disabled": "停用",
}
STRATEGY_HEALTH_WINDOW_LABELS = {
    "short_20d": "20 日当前可用性",
    "long_60d": "60 日结构可信度",
}
STRATEGY_HEALTH_WINDOW_STATUS_LABELS = {
    "healthy": "健康",
    "recovering": "恢复中",
    "weak": "失效",
}

STRATEGY_HEALTH_WINDOW_THRESHOLDS = {
    "short_20d": 68.0,
    "long_60d": 64.0,
}
STRATEGY_HEALTH_WINDOW_TARGETS = {
    "short_20d": {
        "lookback": 20,
        "min_samples_healthy": 8,
        "min_samples_recovering": 5,
        "healthy_success_rate": 65.0,
        "recovering_success_rate": 55.0,
        "healthy_profit_window_pct": 2.0,
        "recovering_profit_window_pct": 1.2,
        "healthy_drawdown_pct": 3.5,
        "recovering_drawdown_pct": 4.0,
    },
    "long_60d": {
        "lookback": 60,
        "min_samples_healthy": 18,
        "min_samples_recovering": 12,
        "healthy_success_rate": 60.0,
        "recovering_success_rate": 52.0,
        "healthy_profit_window_pct": 2.0,
        "recovering_profit_window_pct": 1.4,
        "healthy_drawdown_pct": 4.0,
        "recovering_drawdown_pct": 4.5,
    },
}
ROLE_VALIDATION_TARGETS = {
    "leader": {"profit_window_pct": 2.0, "max_drawdown_pct": 3.0},
    "front": {"profit_window_pct": 3.0, "max_drawdown_pct": 5.0},
    "mid": {"profit_window_pct": 2.0, "max_drawdown_pct": 4.0},
    "back": {"profit_window_pct": 2.0, "max_drawdown_pct": 4.0},
}
STRATEGY_HEALTH_CACHE_TTL = timedelta(hours=12)
STRATEGY_HEALTH_CACHE_VERSION = "v4"
STRATEGY_HEALTH_SAMPLE_CACHE_TTL = timedelta(days=30)
STRATEGY_HEALTH_SAMPLE_CACHE_VERSION = "v1"
STRATEGY_HEALTH_DISK_CACHE_DIRNAME = "momentum_strategy_health"
STRATEGY_HEALTH_SAMPLE_DISK_CACHE_DIRNAME = "samples"
STRATEGY_HEALTH_ASYNC_DEFAULT_DELAY_SECONDS = 20.0
STRATEGY_HEALTH_WAIT_TIMEOUT_SECONDS = 8.0
STRATEGY_HEALTH_WAIT_POLL_INTERVAL_SECONDS = 0.1
STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS = 75.0
STRATEGY_HEALTH_MIN_PARTIAL_SAMPLE_COUNT = 5
STRATEGY_HEALTH_MAX_SCORED_CANDIDATES = 30
STRATEGY_HEALTH_TARGET_SAMPLE_COUNT = STRATEGY_HEALTH_WINDOW_TARGETS["long_60d"]["lookback"]
STRATEGY_HEALTH_IN_PROGRESS_STATUSES = {"queued", "running", "partial"}
MARKET_ENVIRONMENT_BREADTH_SAMPLE_SIZE = 10
ATTACK_PERMISSION_MIN_SAMPLES = {
    "open": 5,
    "recovering": 3,
}
ATTACK_PERMISSION_HIT_RATE_THRESHOLDS = {
    "open": 55.0,
    "recovering": 40.0,
}
ATTACK_PERMISSION_SCORE_THRESHOLDS = {
    "open": 44.0,
    "recovering": 34.0,
}
ATTACK_PERMISSION_PROFIT_WINDOW_THRESHOLDS = {
    "open": 5.8,
    "recovering": 5.8,
}
ATTACK_PERMISSION_DRAWDOWN_THRESHOLDS = {
    "open": 4.4,
    "recovering": 5.0,
}
THEME_CONFIDENCE_MIN_SAMPLES = {
    "credible": 12,
    "recovering": 8,
}
THEME_CONFIDENCE_SCORE_THRESHOLDS = {
    "credible": 60.0,
    "recovering": 45.0,
}
STRATEGY_HEALTH_WARMING_REASON = (
    "真实 20/60 日历史验证正在后台计算，本次先展示代理健康度，稍后刷新即可切换为真实结果。"
)
STRATEGY_HEALTH_MODE_DEFAULT = "default"
STRATEGY_HEALTH_MODE_CACHED_ONLY = "cached_only"
STRATEGY_HEALTH_MODE_STRICT_FINAL = "strict_final"

StrategyHealthProgressCallback = Callable[[Dict[str, Any]], None]

INTRADAY_PHASE_LABELS = {
    "pre_open": "开盘前",
    "call_auction": "集合竞价",
    "first_30m": "开盘后 30 分钟",
    "first_60m": "开盘后 60 分钟内",
    "after_first_hour": "60 分钟后",
    "midday_break": "午间休市",
    "afternoon": "午后",
    "closed": "收盘后",
}

INTRADAY_STATUS_LABELS = {
    "not_started": "等待开盘",
    "watching": "继续观察",
    "buy_ready": "买点已触发",
    "low_confidence": "低置信度",
    "do_not_buy": "不建议执行",
    "stand_aside": "今日不做",
    "not_applicable": "仅支持最新交易日",
}

INTRADAY_CONFIDENCE_LABELS = {
    "high": "高置信度",
    "medium": "中等置信度",
    "low": "低置信度",
}

INTRADAY_FINAL_RECOMMENDATION_LABELS = {
    "buy": "建议买",
    "main_only_consider": "仅主仓可考虑",
    "watch": "继续观察",
    "do_not_buy": "不建议买",
}

INTRADAY_ITEM_STATUS_LABELS = {
    "triggered": "买点已触发",
    "watching": "继续等待",
    "do_not_chase": "不建议追入",
    "observe_only": "仅观察",
    "data_unavailable": "盘中数据不足",
}

logger = logging.getLogger(__name__)

MARKET_ENVIRONMENT_INDEX_GROUPS = (
    {
        "label": "上证指数",
        "history_codes": ("000001.SH",),
        "snapshot_codes": {"000001", "000001.SH", "SH000001", "sh000001"},
    },
    {
        "label": "创业板指",
        "history_codes": ("399006.SZ",),
        "snapshot_codes": {"399006", "399006.SZ", "SZ399006", "sz399006"},
    },
    {
        "label": "国证2000",
        "history_codes": ("399303.SZ",),
        "snapshot_codes": {"399303", "399303.SZ", "SZ399303", "sz399303"},
        "snapshot_fallback_codes": {"000688", "000688.SH", "SH000688", "sh000688"},
        "snapshot_fallback_label": "科创50（代理）",
    },
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        parsed = float(value)
        if not isfinite(parsed):
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _clamp_float(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _normalize_leader_level(value: Any) -> str:
    normalized = _safe_str(value).strip().lower()
    if normalized in {"龙头", "leader"}:
        return "leader"
    if normalized in {"前排", "front"}:
        return "front"
    if normalized in {"中位", "mid"}:
        return "mid"
    return "back"


def _official_sort_score(item: Dict[str, Any]) -> float:
    official_score = item.get("official_score")
    if official_score is not None and official_score != "":
        return _safe_float(official_score)
    return _safe_float(item.get("rank_score"))


class MomentumSecondaryDecisionService:
    """Aggregate raw screener output into a static decision view."""

    def __init__(
        self,
        screener_service: Optional[MomentumScreenerService] = None,
        stock_service: Optional[StockService] = None,
        stock_repo: Optional[StockRepository] = None,
        v13_data_service: Optional[MomentumV13DataService] = None,
        enable_v13_mainline: bool = True,
        strategy_health_async: bool = False,
        strategy_health_async_delay_seconds: float = 0.0,
        strategy_health_cache_dir: Optional[Path] = None,
        adaptive_gate_audit_provider: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        self.screener_service = screener_service
        self.stock_service = stock_service
        self.stock_repo = stock_repo or getattr(stock_service, "repo", None) or StockRepository()
        self.v13_data_service = v13_data_service
        self.enable_v13_mainline = enable_v13_mainline
        self.adaptive_gate_audit_provider = adaptive_gate_audit_provider
        self.strategy_health_async = strategy_health_async
        self.strategy_health_async_delay_seconds = max(0.0, float(strategy_health_async_delay_seconds))
        self._strategy_health_cache: Dict[str, Dict[str, Any]] = {}
        self._strategy_health_sample_cache: Dict[str, Dict[str, Any]] = {}
        self._strategy_health_jobs: Dict[str, Any] = {}
        self._strategy_health_jobs_lock = Lock()
        self._strategy_health_executor = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="momentum-health")
            if strategy_health_async
            else None
        )
        self._strategy_health_cache_dir = (
            Path(strategy_health_cache_dir)
            if strategy_health_cache_dir is not None
            else Path.cwd() / "data" / "cache" / STRATEGY_HEALTH_DISK_CACHE_DIRNAME
        )
        self._strategy_health_sample_cache_dir = self._strategy_health_cache_dir / STRATEGY_HEALTH_SAMPLE_DISK_CACHE_DIRNAME

    def build(
        self,
        *,
        top_n: int = MOMENTUM_DEFAULT_TOP_N,
        min_change_pct: float = MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
        min_amount: float = MOMENTUM_DEFAULT_MIN_AMOUNT,
        min_turnover: float = MOMENTUM_DEFAULT_MIN_TURNOVER,
        exclude_st: bool = True,
        main_board_only: bool = False,
        trade_date: Optional[str] = None,
        profile: str = "standard",
        wait_for_strategy_health: bool = False,
        strategy_health_mode: str = STRATEGY_HEALTH_MODE_DEFAULT,
    ) -> Dict[str, Any]:
        screener_service = self.screener_service or MomentumScreenerService()
        self.screener_service = screener_service
        screening = screener_service.screen(
            top_n=top_n,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
            trade_date=trade_date,
            profile=profile,
        )
        request_params = self._build_request_params(
            top_n=top_n,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
            trade_date=trade_date,
            profile=profile,
        )
        screening["_request_params"] = request_params
        return {
            "screening": screening,
            "decision": self.build_from_screening(
                screening,
                request_params=request_params,
                wait_for_strategy_health=wait_for_strategy_health,
                strategy_health_mode=strategy_health_mode,
            ),
        }

    def build_intraday(
        self,
        *,
        top_n: int = MOMENTUM_DEFAULT_TOP_N,
        min_change_pct: float = MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
        min_amount: float = MOMENTUM_DEFAULT_MIN_AMOUNT,
        min_turnover: float = MOMENTUM_DEFAULT_MIN_TURNOVER,
        exclude_st: bool = True,
        main_board_only: bool = False,
        trade_date: Optional[str] = None,
        profile: str = "standard",
        now: Optional[datetime] = None,
        wait_for_strategy_health: bool = False,
    ) -> Dict[str, Any]:
        result = self.build(
            top_n=top_n,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
            trade_date=trade_date,
            profile=profile,
            wait_for_strategy_health=wait_for_strategy_health,
        )
        result["intraday_signal"] = self.build_intraday_from_decision(
            result["decision"],
            now=now,
        )
        result["snapshot_assist"] = self._build_snapshot_assist_from_intraday_signal(
            result["intraday_signal"],
        )
        return result

    def build_from_screening(
        self,
        screening: Dict[str, Any],
        *,
        request_params: Optional[Dict[str, Any]] = None,
        wait_for_strategy_health: bool = False,
        strategy_health_progress_callback: Optional[StrategyHealthProgressCallback] = None,
        strategy_health_mode: str = STRATEGY_HEALTH_MODE_DEFAULT,
    ) -> Dict[str, Any]:
        results = self._extract_decision_source_results(screening)
        profile = _safe_str(screening.get("profile"), "standard")
        trade_date = _safe_str(screening.get("trade_date"))
        if strategy_health_mode not in {
            STRATEGY_HEALTH_MODE_DEFAULT,
            STRATEGY_HEALTH_MODE_CACHED_ONLY,
            STRATEGY_HEALTH_MODE_STRICT_FINAL,
        }:
            strategy_health_mode = STRATEGY_HEALTH_MODE_DEFAULT
        request_params = dict(screening.get("_request_params") or request_params or self._build_request_params(profile=profile))

        if not results:
            strategy_health = self._build_strategy_health(
                [],
                [],
                [],
                trade_date=trade_date,
                request_params=request_params,
                wait_for_strategy_health=wait_for_strategy_health,
                strategy_health_progress_callback=strategy_health_progress_callback,
                strategy_health_mode=strategy_health_mode,
            )
            action_reason = "当前没有形成足够强的候选池，系统不建议今天给出强推荐。"
            attack_permission = self._build_attack_permission(strategy_health)
            theme_confidence = self._build_theme_confidence(strategy_health)
            historical_validity = self._build_historical_validity(
                strategy_health,
                attack_permission=attack_permission,
            )
            market_environment = {
                "level": "weak",
                "label": GATE_LEVEL_LABELS["weak"],
                "score": 0.0,
                "reason": "当前没有候选池，无法形成强势股溢价判断。",
                "modules": [],
            }
            opportunity_quality = {
                "level": "weak",
                "label": GATE_LEVEL_LABELS["weak"],
                "matrix_level": "weak",
                "matrix_label": OPPORTUNITY_MATRIX_LEVEL_LABELS["weak"],
                "score": 0.0,
                "reason": "当前没有默认组合，机会质量直接判弱。",
                "modules": [],
            }
            return {
                "profile": profile,
                "trade_date": trade_date,
                "action": {
                    "level": "stand_aside",
                    "label": ACTION_LEVEL_LABELS["stand_aside"],
                    "reason": action_reason,
                    "source_profile": profile,
                },
                "market_environment": market_environment,
                "opportunity_quality": opportunity_quality,
                "historical_validity": historical_validity,
                "strategy_health": strategy_health,
                "attack_permission": attack_permission,
                "theme_confidence": theme_confidence,
                "risk_banner": None,
                "mainline_radar": [],
                "short_term_sentiment": None,
                "v13_data_status": {
                    "enabled": bool(self.enable_v13_mainline),
                    "status": "not_applicable",
                    "reason": "当前没有候选池，跳过 V1.3 主线增强数据。",
                },
                "adaptive_gate": self._default_adaptive_gate_context(),
                "themes": [],
                "portfolio": [],
                "candidate_diagnostics": [],
                "excluded_candidates": [],
                "action_checklist": {
                    "enabled": False,
                    "mode": "disabled",
                    "reason": "当前没有可执行的默认组合，因此不生成明日行动清单。",
                    "steps": [],
                },
                "evidence": {
                    "theme_validation": ["暂无可用主线，等待候选池重新形成集中强势方向。"],
                    "today_reasoning": [action_reason],
                },
            }

        enriched_candidates = [self._build_candidate_view(item) for item in results]
        v13_context, mainline_radar, short_term_sentiment, v13_data_status = self._build_v13_mainline_context(
            trade_date=trade_date,
            candidates=enriched_candidates,
        )
        enriched_candidates = self._apply_v13_mainline_to_candidates(
            enriched_candidates,
            context=v13_context,
            mainline_radar=mainline_radar,
        )
        themes = self._build_theme_summaries(enriched_candidates)
        theme_score_map = {theme["name"]: theme["score"] for theme in themes}
        adaptive_gate_context = self._build_adaptive_gate_context(profile=profile)
        enriched_candidates = self._apply_adaptive_mainline_threshold(
            enriched_candidates,
            adaptive_gate_context,
        )
        portfolio = self._build_portfolio(enriched_candidates, themes, theme_score_map)
        excluded = self._build_excluded_candidates(enriched_candidates, portfolio, themes, theme_score_map)
        strategy_health = self._build_strategy_health(
            enriched_candidates,
            themes,
            portfolio,
            trade_date=trade_date,
            request_params=request_params,
            wait_for_strategy_health=wait_for_strategy_health,
            strategy_health_progress_callback=strategy_health_progress_callback,
            strategy_health_mode=strategy_health_mode,
        )
        attack_permission = self._build_attack_permission(strategy_health)
        theme_confidence = self._build_theme_confidence(strategy_health)
        market_environment = self._build_market_environment(
            trade_date=trade_date,
            profile=profile,
            request_params=request_params,
            candidates=enriched_candidates,
            themes=themes,
            portfolio=portfolio,
        )
        opportunity_quality = self._build_opportunity_quality(
            candidates=enriched_candidates,
            themes=themes,
            portfolio=portfolio,
        )
        historical_validity = self._build_historical_validity(
            strategy_health,
            attack_permission=attack_permission,
        )
        raw_action = self._build_action(
            profile,
            market_environment=market_environment,
            opportunity_quality=opportunity_quality,
            historical_validity=historical_validity,
            portfolio=portfolio,
        )
        action = self._apply_historical_validity_to_action(
            raw_action,
            historical_validity,
            market_environment=market_environment,
            opportunity_quality=opportunity_quality,
        )
        portfolio = self._apply_action_permissions_to_portfolio(portfolio, action, historical_validity)
        candidate_diagnostics = self._build_candidate_diagnostics(
            enriched_candidates,
            portfolio,
            theme_score_map,
        )
        action_checklist = self._build_action_checklist(action, portfolio, historical_validity)
        risk_banner = self._build_decision_risk_banner(
            action=action,
            theme_confidence=theme_confidence,
        )
        evidence = self._build_evidence(
            profile,
            action,
            strategy_health,
            themes,
            portfolio,
            excluded,
            market_environment=market_environment,
            opportunity_quality=opportunity_quality,
            historical_validity=historical_validity,
        )

        return {
            "profile": profile,
            "trade_date": trade_date,
            "action": action,
            "market_environment": market_environment,
            "opportunity_quality": opportunity_quality,
            "historical_validity": historical_validity,
            "strategy_health": strategy_health,
            "attack_permission": attack_permission,
            "theme_confidence": theme_confidence,
            "risk_banner": risk_banner,
            "mainline_radar": mainline_radar,
            "short_term_sentiment": short_term_sentiment,
            "v13_data_status": v13_data_status,
            "adaptive_gate": adaptive_gate_context,
            "themes": themes,
            "portfolio": portfolio,
            "candidate_diagnostics": candidate_diagnostics,
            "excluded_candidates": excluded,
            "action_checklist": action_checklist,
            "evidence": evidence,
        }

    @staticmethod
    def _build_request_params(
        *,
        top_n: int = MOMENTUM_DEFAULT_TOP_N,
        min_change_pct: float = MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
        min_amount: float = MOMENTUM_DEFAULT_MIN_AMOUNT,
        min_turnover: float = MOMENTUM_DEFAULT_MIN_TURNOVER,
        exclude_st: bool = True,
        main_board_only: bool = False,
        trade_date: Optional[str] = None,
        profile: str = "standard",
    ) -> Dict[str, Any]:
        return {
            "top_n": top_n,
            "min_change_pct": min_change_pct,
            "min_amount": min_amount,
            "min_turnover": min_turnover,
            "exclude_st": exclude_st,
            "main_board_only": main_board_only,
            "trade_date": trade_date,
            "profile": profile,
        }

    @staticmethod
    def _extract_decision_source_results(screening: Dict[str, Any]) -> List[Dict[str, Any]]:
        ranked_results = screening.get("ranked_results")
        if isinstance(ranked_results, list) and ranked_results:
            return [dict(item) for item in ranked_results]
        return [dict(item) for item in screening.get("results", [])]

    def _get_v13_data_service(self) -> Optional[MomentumV13DataService]:
        if not self.enable_v13_mainline:
            return None
        if self.v13_data_service is not None:
            return self.v13_data_service
        if self.screener_service is None:
            return None

        fetcher = getattr(self.screener_service, "fetcher", None)
        try:
            self.v13_data_service = MomentumV13DataService(fetcher=fetcher) if fetcher is not None else MomentumV13DataService()
        except Exception as exc:  # pragma: no cover - defensive guard for env/config drift
            logger.warning("Failed to initialize V1.3 data service: %s", exc)
            return None
        return self.v13_data_service

    def _build_v13_mainline_context(
        self,
        *,
        trade_date: str,
        candidates: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
        status = {
            "enabled": bool(self.enable_v13_mainline),
            "status": "skipped",
            "reason": "V1.3 主线增强未启用或当前没有可用数据服务。",
            "source_status": {},
            "degraded_reasons": [],
        }
        if not self.enable_v13_mainline:
            status["reason"] = "V1.3 主线增强已关闭。"
            return {}, [], None, status

        sampled_candidates = sorted(
            candidates,
            key=lambda item: _safe_float(item.get("rank"), 999.0),
        )[:V13_CONTEXT_MAX_TS_CODES]
        ts_codes = [
            _safe_str(candidate.get("ts_code") or candidate.get("code"))
            for candidate in sampled_candidates
            if candidate.get("ts_code") or candidate.get("code")
        ]
        if not trade_date or not ts_codes:
            status["status"] = "not_applicable"
            status["reason"] = "交易日或候选股代码为空，跳过 V1.3 主线增强。"
            return {}, [], None, status

        v13_service = self._get_v13_data_service()
        if v13_service is None:
            return {}, [], None, status

        try:
            context = v13_service.build_context(trade_date=trade_date, ts_codes=ts_codes)
            mainline_radar = v13_service.build_mainline_radar(candidates=candidates, context=context)
            short_term_sentiment = v13_service.build_short_term_sentiment(
                mainline_radar=mainline_radar,
                context=context,
            )
        except Exception as exc:  # pragma: no cover - keep old decision path alive on data-source bugs
            logger.warning("Failed to build V1.3 mainline context: %s", exc)
            status.update(
                {
                    "status": "failed",
                    "reason": f"V1.3 主线增强计算失败，已回退旧二次决策链路：{exc}",
                }
            )
            return {}, [], None, status

        source_status = dict(context.get("source_status") or {})
        degraded_reasons = list(context.get("degraded_reasons") or [])
        status.update(
            {
                "status": "degraded" if context.get("is_degraded") else "ok",
                "reason": (
                    "V1.3 主线增强数据已接入，但部分数据源降级。"
                    if context.get("is_degraded")
                    else "V1.3 主线增强数据已接入二次决策。"
                ),
                "data_as_of": context.get("data_as_of"),
                "source_status": source_status,
                "degraded_reasons": degraded_reasons,
                "mainline_count": len(mainline_radar),
                "sampled_code_count": len(ts_codes),
                "candidate_count": len(candidates),
                "short_term_sentiment_level": (
                    short_term_sentiment.get("level")
                    if isinstance(short_term_sentiment, dict)
                    else None
                ),
            }
        )
        return context, mainline_radar, short_term_sentiment, status

    @staticmethod
    def _default_adaptive_gate_context() -> Dict[str, Any]:
        return {
            "enabled": False,
            "mode": "normal",
            "required_mainline_count": 1,
            "lookback_days": ADAPTIVE_GATE_LOOKBACK_DAYS,
            "evaluated_days": 0,
            "successful_defensive_gate_rate_pct": None,
            "source_run_id": None,
            "reason": "暂无可用总闸门审计样本，沿用常规主线阈值。",
        }

    def _build_adaptive_gate_context(self, *, profile: str) -> Dict[str, Any]:
        payload = self._load_latest_gate_justification_payload(profile=profile)
        if not payload:
            return self._default_adaptive_gate_context()

        report = payload.get("report") if isinstance(payload, dict) else None
        if not isinstance(report, dict):
            return self._default_adaptive_gate_context()

        recent_days = self._extract_recent_gate_audit_days(report)[:ADAPTIVE_GATE_LOOKBACK_DAYS]
        if recent_days:
            evaluated_days = len(recent_days)
            successful_days = sum(
                1
                for item in recent_days
                if _safe_str(item.get("classification")) == "Successful_Defensive_Gate"
            )
        else:
            evaluated_days = int(_safe_float(report.get("evaluated_stand_aside_days")))
            successful_days = int(_safe_float(report.get("successful_defensive_gate_count")))

        if evaluated_days <= 0:
            context = self._default_adaptive_gate_context()
            context["source_run_id"] = payload.get("run_id")
            context["reason"] = "最近回测没有可审计的不做样本，沿用常规主线阈值。"
            return context

        defensive_rate = round(successful_days / evaluated_days * 100.0, 2)
        strict_enabled = defensive_rate > ADAPTIVE_GATE_DEFENSIVE_RATE_THRESHOLD_PCT
        required_count = ADAPTIVE_MAINLINE_MIN_POOL_COUNT if strict_enabled else 1
        return {
            "enabled": strict_enabled,
            "mode": "strict_mainline" if strict_enabled else "normal",
            "required_mainline_count": required_count,
            "lookback_days": ADAPTIVE_GATE_LOOKBACK_DAYS,
            "evaluated_days": evaluated_days,
            "successful_defensive_gate_count": successful_days,
            "successful_defensive_gate_rate_pct": defensive_rate,
            "source_run_id": payload.get("run_id"),
            "threshold_pct": ADAPTIVE_GATE_DEFENSIVE_RATE_THRESHOLD_PCT,
            "recent_gate_days": recent_days,
            "reason": (
                f"最近 {evaluated_days} 个总闸门不做样本中，防守成功率 {defensive_rate:.2f}% "
                f"> {ADAPTIVE_GATE_DEFENSIVE_RATE_THRESHOLD_PCT:.0f}%，弱市自动要求主线池计数 >= {required_count}。"
                if strict_enabled
                else f"最近总闸门防守成功率 {defensive_rate:.2f}%，未触发动态收口，沿用常规主线阈值。"
            ),
        }

    def _load_latest_gate_justification_payload(self, *, profile: str) -> Optional[Dict[str, Any]]:
        if callable(self.adaptive_gate_audit_provider):
            try:
                provided = self.adaptive_gate_audit_provider(profile)
            except Exception:  # noqa: BLE001
                logger.warning("Adaptive gate audit provider failed", exc_info=True)
                return None
            if not isinstance(provided, dict):
                return None
            if isinstance(provided.get("report"), dict):
                return provided
            return {"run_id": provided.get("run_id"), "report": provided}

        try:
            from src.repositories.momentum_backtest_repo import MomentumBacktestRepository

            repository = MomentumBacktestRepository()
            for run in repository.list_runs(limit=5, profile=profile, statuses=("completed",)):
                try:
                    summary = json.loads(run.summary_json or "{}")
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(summary, dict):
                    continue
                report = summary.get("gate_justification_report")
                if isinstance(report, dict):
                    return {"run_id": run.run_id, "report": report}
        except Exception:  # noqa: BLE001
            logger.debug("No adaptive gate audit report available", exc_info=True)
        return None

    @staticmethod
    def _extract_recent_gate_audit_days(report: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = report.get("evaluated_gate_days")
        if isinstance(rows, list) and rows:
            normalized = [dict(item) for item in rows if isinstance(item, dict)]
        else:
            normalized = []
            for key in ("successful_defensive_gate", "false_alarm_warnings"):
                items = report.get(key)
                if isinstance(items, list):
                    normalized.extend(dict(item) for item in items if isinstance(item, dict))

        return sorted(
            normalized,
            key=lambda item: _safe_str(item.get("trade_date")),
            reverse=True,
        )

    @staticmethod
    def _resolve_adaptive_mainline_count(item: Dict[str, Any]) -> int:
        count = MomentumSecondaryDecisionService._first_available_int(
            item,
            (
                "_theme_pool_count",
                "_v13_mainline_pool_count",
                "v13_mainline_candidate_count",
                "_official_mainline_intensity_count",
                "mainline_intensity_count",
                "candidate_count",
            ),
        )
        return max(0, int(count or 0))

    def _apply_adaptive_mainline_threshold(
        self,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return candidates
        enabled = bool(context.get("enabled"))
        required_count = int(_safe_float(context.get("required_mainline_count"), 1.0))
        for candidate in candidates:
            count = self._resolve_adaptive_mainline_count(candidate)
            candidate["_adaptive_gate_context"] = dict(context)
            candidate["_adaptive_gate_enabled"] = enabled
            candidate["_adaptive_mainline_count"] = count
            candidate["_adaptive_mainline_min_count"] = required_count
            candidate["_adaptive_mainline_pass"] = (not enabled) or count >= required_count
        return candidates

    def _apply_v13_mainline_to_candidates(
        self,
        candidates: List[Dict[str, Any]],
        *,
        context: Dict[str, Any],
        mainline_radar: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not candidates or not context:
            return candidates

        stock_theme_map = context.get("stock_theme_map") or {}
        has_theme_mapping = any(stock_theme_map.get(_safe_str(candidate.get("ts_code"))) for candidate in candidates)

        radar_by_id = {
            _safe_str(item.get("theme_id")): item
            for item in mainline_radar
            if item.get("theme_id")
        }
        radar_by_name = {
            _safe_str(item.get("theme_name")): item
            for item in mainline_radar
            if item.get("theme_name")
        }
        enhanced: List[Dict[str, Any]] = []
        for candidate in candidates:
            updated = dict(candidate)
            ts_code = _safe_str(updated.get("ts_code"))
            self._attach_v13_sealing_strength_signal(updated, context=context)
            self._attach_v13_ladder_position_signal(updated, context=context)
            self._refresh_candidate_buy_point_fields(updated)
            theme_rows = stock_theme_map.get(ts_code) or []
            best_radar: Optional[Dict[str, Any]] = None
            best_theme_id = ""
            best_theme_name = ""

            if has_theme_mapping and mainline_radar:
                for row in theme_rows:
                    theme_id = _safe_str(row.get("theme_code") or row.get("ths_code"))
                    theme_name = _safe_str(row.get("theme_name") or row.get("ths_name") or theme_id)
                    radar = radar_by_id.get(theme_id) or radar_by_name.get(theme_name)
                    if radar is None:
                        continue
                    if best_radar is None or _safe_float(radar.get("score")) > _safe_float(best_radar.get("score")):
                        best_radar = radar
                        best_theme_id = theme_id
                        best_theme_name = theme_name or _safe_str(radar.get("theme_name"))

            if best_radar is not None:
                theme_name = _safe_str(best_radar.get("theme_name"), best_theme_name)
                updated["_theme"] = theme_name
                updated["_v13_theme_id"] = _safe_str(best_radar.get("theme_id"), best_theme_id)
                updated["_v13_theme_name"] = theme_name
                updated["_v13_mainline_score"] = round(_safe_float(best_radar.get("score")), 2)
                updated["_v13_mainline_level"] = _safe_str(best_radar.get("level"))
                updated["_v13_mainline_level_label"] = _safe_str(best_radar.get("level_label"))
                updated["_v13_mainline_summary"] = _safe_str(best_radar.get("summary"))
                updated["_v13_mainline_pool_count"] = int(_safe_float(best_radar.get("candidate_count")))
                themes = list(updated.get("themes") or [])
                if theme_name and theme_name not in themes:
                    updated["themes"] = [theme_name, *themes]
                self._attach_v13_shadow_scores(updated, context=context, radar=best_radar)
            self._refresh_candidate_buy_point_fields(updated)
            enhanced.append(updated)
        return enhanced

    def _attach_v13_shadow_scores(
        self,
        candidate: Dict[str, Any],
        *,
        context: Dict[str, Any],
        radar: Dict[str, Any],
    ) -> None:
        theme_strength_score = round(_safe_float(radar.get("score"), 50.0), 2)
        stock_flow_signal = self._v13_stock_flow_shadow_signal(candidate, context, radar)
        chip_signal = self._v13_chip_shadow_signal(candidate, context, radar)
        sealing_signal = self._attach_v13_sealing_strength_signal(candidate, context=context)
        fund_support_score = round(
            self._v13_fund_support_score(radar, stock_flow_signal=stock_flow_signal),
            2,
        )
        limit_structure_score = round(self._v13_limit_structure_score(candidate, context), 2)
        buyability_score = round(
            self._v13_buyability_shadow_score(candidate, context, chip_signal=chip_signal),
            2,
        )
        chip_risk_score = round(_safe_float(chip_signal.get("risk_score"), 50.0), 2)
        shadow_score = round(
            _clamp_float(
                theme_strength_score * 0.30
                + fund_support_score * 0.25
                + limit_structure_score * 0.20
                + buyability_score * 0.15
                + (100.0 - chip_risk_score) * 0.10
            ),
            2,
        )
        candidate["_v13_theme_strength_score"] = theme_strength_score
        candidate["_v13_fund_support_score"] = fund_support_score
        candidate["_v13_limit_structure_score"] = limit_structure_score
        candidate["_v13_buyability_score"] = buyability_score
        candidate["_v13_chip_risk_score"] = chip_risk_score
        candidate["_v13_chip_tags"] = list(chip_signal.get("tags") or [])
        candidate["_v13_chip_signal_available"] = bool(chip_signal.get("available"))
        candidate["_v13_shadow_score"] = shadow_score
        candidate["_v13_shadow_summary"] = (
            f"V1.3影子分 {shadow_score:.1f}：题材 {theme_strength_score:.1f}、"
            f"资金 {fund_support_score:.1f}、涨停结构 {limit_structure_score:.1f}、"
            f"买点 {buyability_score:.1f}；{self._describe_v13_chip_shadow_signal(chip_signal)}；"
            f"{self._describe_v13_sealing_strength_signal(sealing_signal)}。"
        )

    @staticmethod
    def _build_v13_shadow_profile(
        candidate: Dict[str, Any],
        context: Dict[str, Any],
        radar: Dict[str, Any],
    ) -> Dict[str, Any]:
        ts_code = _safe_str(candidate.get("ts_code"))
        stock_flow = (context.get("stock_moneyflow") or {}).get(ts_code) or {}
        chip_snapshot = (context.get("chip_snapshots") or {}).get(ts_code) or {}
        return {
            "theme_name": _safe_str(radar.get("theme_name")),
            "theme_fund_strength_score": _safe_float(radar.get("fund_strength_score") or radar.get("score"), 50.0),
            "stock_fund_net_amount": stock_flow.get("net_amount"),
            "stock_fund_net_amount_rate": stock_flow.get("net_amount_rate"),
            "stock_fund_net_d5_amount": stock_flow.get("net_d5_amount"),
            "stock_fund_buy_lg_amount": stock_flow.get("buy_lg_amount"),
            "stock_fund_buy_lg_amount_rate": stock_flow.get("buy_lg_amount_rate"),
            "stock_fund_sources": list(stock_flow.get("sources") or []),
            "chip_winner_rate": chip_snapshot.get("winner_rate"),
            "chip_weight_avg": chip_snapshot.get("weight_avg"),
            "chip_avg_cost": chip_snapshot.get("avg_cost"),
            "chip_cost_15pct": chip_snapshot.get("cost_15pct"),
            "chip_cost_50pct": chip_snapshot.get("cost_50pct"),
            "chip_cost_85pct": chip_snapshot.get("cost_85pct"),
            "chip_cost_95pct": chip_snapshot.get("cost_95pct"),
            "chip_concentration_90": chip_snapshot.get("concentration_90"),
            "chip_concentration_70": chip_snapshot.get("concentration_70"),
            "chip_distribution_points": chip_snapshot.get("distribution_points"),
            "chip_sources": list(chip_snapshot.get("sources") or []),
        }

    @staticmethod
    def _build_v13_shadow_candidate_series(
        candidate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> pd.Series:
        row = dict(candidate)
        ts_code = _safe_str(candidate.get("ts_code"))
        stock_flow = (context.get("stock_moneyflow") or {}).get(ts_code) or {}
        close_price = _safe_float(row.get("close"))
        if close_price <= 0:
            close_price = _safe_float(stock_flow.get("close"))
        if close_price <= 0:
            entry_low = _safe_float(candidate.get("entry_range_low"))
            entry_high = _safe_float(candidate.get("entry_range_high"))
            if entry_low > 0 and entry_high > 0:
                close_price = (entry_low + entry_high) / 2.0
            else:
                close_price = max(entry_low, entry_high, 0.0)
        if close_price > 0:
            row["close"] = close_price
        return pd.Series(row)

    @classmethod
    def _v13_stock_flow_shadow_signal(
        cls,
        candidate: Dict[str, Any],
        context: Dict[str, Any],
        radar: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = cls._build_v13_shadow_profile(candidate, context, radar)
        row = cls._build_v13_shadow_candidate_series(candidate, context)
        return MomentumScreenerService._resolve_v13_stock_flow(profile, row)

    @classmethod
    def _v13_chip_shadow_signal(
        cls,
        candidate: Dict[str, Any],
        context: Dict[str, Any],
        radar: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile = cls._build_v13_shadow_profile(candidate, context, radar)
        row = cls._build_v13_shadow_candidate_series(candidate, context)
        return MomentumScreenerService._resolve_v13_chip_signal(profile, row)

    @staticmethod
    def _describe_v13_chip_shadow_signal(chip_signal: Dict[str, Any]) -> str:
        if not chip_signal.get("available"):
            return "筹码风险缺少快照，按中性解释"

        risk_score = round(_safe_float(chip_signal.get("risk_score"), 50.0), 1)
        if risk_score >= 75:
            level = "高风险"
        elif risk_score >= 60:
            level = "偏高"
        elif risk_score <= 35:
            level = "低风险"
        else:
            level = "中性"

        tags = set(chip_signal.get("tags") or [])
        note = ""
        if "chip_overheat" in tags:
            note = "，获利盘过热"
        elif "chip_overhead_supply" in tags:
            note = "，上方筹码偏重"
        elif "chip_high_profit" in tags:
            note = "，获利盘拥挤"
        elif risk_score <= 35:
            note = "，结构相对健康"
        return f"筹码风险 {risk_score:.1f}（{level}{note}）"

    @classmethod
    def _attach_v13_sealing_strength_signal(
        cls,
        candidate: Dict[str, Any],
        *,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        signal = cls._v13_sealing_strength_signal(candidate, context)
        candidate["_v13_sealing_strength_signal"] = signal
        candidate["_v13_sealing_strength_score"] = (
            round(_safe_float(signal.get("score")), 2)
            if signal.get("score") is not None
            else None
        )
        candidate["_v13_sealing_strength_level"] = signal.get("level")
        candidate["_v13_sealing_strength_level_label"] = signal.get("level_label")
        return signal

    @classmethod
    def _v13_sealing_strength_signal(
        cls,
        candidate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        event = cls._select_v13_limit_event(candidate, context)
        if not event:
            return {
                "available": False,
                "score": None,
                "level": "unknown",
                "level_label": "封板数据不足",
                "summary": "limit_list_d 未返回当日封板事件，二次决策按中性处理。",
                "confidence": "low",
            }

        limit_flag = _safe_str(event.get("limit")).upper()
        first_time = _safe_str(event.get("first_time")).strip()
        last_time = _safe_str(event.get("last_time")).strip()
        first_minutes = cls._parse_limit_time_minutes(first_time)
        time_score = cls._sealing_time_score(first_minutes)
        fd_amount = _safe_float(event.get("fd_amount"))
        amount = _safe_float(event.get("amount"))
        seal_amount_ratio = fd_amount / amount if fd_amount > 0 and amount > 0 else None
        amount_score = cls._sealing_amount_score(seal_amount_ratio)
        raw_open_times = event.get("open_times")
        open_times = int(_safe_float(raw_open_times)) if raw_open_times not in (None, "") else None
        open_score = cls._sealing_open_score(open_times)

        score = (
            (time_score if time_score is not None else 50.0) * 0.55
            + (amount_score if amount_score is not None else 50.0) * 0.25
            + (open_score if open_score is not None else 50.0) * 0.20
        )
        if limit_flag == "Z":
            score = min(score, 40.0)
        elif limit_flag == "D":
            score = min(score, 20.0)
        score = round(_clamp_float(score), 2)

        late_seal = first_minutes is not None and first_minutes > 14 * 60
        multi_open = open_times is not None and open_times >= 3
        low_seal_ratio = seal_amount_ratio is not None and seal_amount_ratio < 0.05
        broken_limit = limit_flag == "Z"
        is_one_word_like = cls._is_one_word_like(candidate, event)

        if score >= 80:
            level = "strong"
            level_label = "强封"
        elif score >= 60:
            level = "medium"
            level_label = "常规封板"
        else:
            level = "weak"
            level_label = "弱封/待确认"

        degraded_reasons: List[str] = []
        if time_score is None:
            degraded_reasons.append("missing_first_seal_time")
        if amount_score is None:
            degraded_reasons.append("missing_seal_amount_ratio")

        notes: List[str] = []
        if first_minutes is not None:
            if first_minutes < 10 * 60:
                notes.append("早盘封板")
            elif late_seal:
                notes.append("尾盘封板")
        if multi_open:
            notes.append("多次开板")
        if low_seal_ratio:
            notes.append("封单偏弱")
        if broken_limit:
            notes.append("炸板风险")
        if is_one_word_like:
            notes.append("一字板/极端缩量")

        if is_one_word_like:
            execution_bias = "hard_to_participate"
            participation_note = "强封但难参与"
        elif late_seal or multi_open or low_seal_ratio or broken_limit or level == "weak":
            execution_bias = "caution"
            participation_note = "封板质量偏弱，买点需等待确认"
        elif level == "strong":
            execution_bias = "support"
            participation_note = "早封强封，可作为强度确认"
        else:
            execution_bias = "neutral"
            participation_note = "封板质量中性"

        return {
            "available": True,
            "score": score,
            "level": level,
            "level_label": level_label,
            "limit": limit_flag or None,
            "first_seal_time": first_time or None,
            "last_seal_time": last_time or None,
            "first_seal_time_score": round(time_score, 2) if time_score is not None else None,
            "fd_amount": fd_amount if fd_amount > 0 else None,
            "amount": amount if amount > 0 else None,
            "seal_amount_ratio": round(seal_amount_ratio, 4) if seal_amount_ratio is not None else None,
            "seal_amount_score": round(amount_score, 2) if amount_score is not None else None,
            "open_times": open_times,
            "open_times_score": round(open_score, 2) if open_score is not None else None,
            "is_one_word_like": is_one_word_like,
            "execution_bias": execution_bias,
            "execution_participation_note": participation_note,
            "downgrade_buy_point": bool(is_one_word_like or late_seal or multi_open or low_seal_ratio or broken_limit),
            "degraded_reasons": degraded_reasons,
            "summary": "、".join(notes) if notes else participation_note,
            "confidence": "medium" if degraded_reasons else "high",
        }

    @staticmethod
    def _select_v13_limit_event(
        candidate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        limit_events = context.get("limit_events") or {}
        events = limit_events.get(_safe_str(candidate.get("ts_code"))) or []
        if not isinstance(events, list):
            return None
        normalized = [event for event in events if isinstance(event, dict)]
        if not normalized:
            return None

        def event_priority(event: Dict[str, Any]) -> Tuple[int, float, float]:
            limit_flag = _safe_str(event.get("limit")).upper()
            limit_priority = {"U": 3, "Z": 2, "D": 1}.get(limit_flag, 0)
            return (
                limit_priority,
                _safe_float(event.get("limit_times")),
                _safe_float(event.get("fd_amount")),
            )

        return max(normalized, key=event_priority)

    @staticmethod
    def _parse_limit_time_minutes(value: Any) -> Optional[int]:
        text = _safe_str(value).strip()
        if not text:
            return None
        digits = "".join(char for char in text if char.isdigit())
        if len(digits) >= 6:
            hour = int(digits[:2])
            minute = int(digits[2:4])
        elif len(digits) == 4:
            hour = int(digits[:2])
            minute = int(digits[2:4])
        else:
            return None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour * 60 + minute

    @staticmethod
    def _sealing_time_score(first_minutes: Optional[int]) -> Optional[float]:
        if first_minutes is None:
            return None
        if first_minutes < 10 * 60:
            return 100.0
        if first_minutes <= 11 * 60 + 30:
            return 75.0
        if first_minutes <= 14 * 60:
            return 55.0
        return 30.0

    @staticmethod
    def _sealing_amount_score(seal_amount_ratio: Optional[float]) -> Optional[float]:
        if seal_amount_ratio is None:
            return None
        if seal_amount_ratio >= 0.20:
            return 100.0
        if seal_amount_ratio >= 0.10:
            return 80.0
        if seal_amount_ratio >= 0.05:
            return 60.0
        if seal_amount_ratio > 0:
            return 35.0
        return None

    @staticmethod
    def _sealing_open_score(open_times: Optional[int]) -> Optional[float]:
        if open_times is None:
            return None
        if open_times <= 0:
            return 100.0
        if open_times == 1:
            return 80.0
        if open_times == 2:
            return 60.0
        return 30.0

    @staticmethod
    def _is_one_word_like(candidate: Dict[str, Any], event: Dict[str, Any]) -> bool:
        open_price = _safe_float(candidate.get("open"))
        low_price = _safe_float(candidate.get("low"))
        close_price = _safe_float(candidate.get("close"), _safe_float(event.get("close")))
        if open_price <= 0 or low_price <= 0 or close_price <= 0:
            return False
        tolerance = max(0.01, close_price * 0.0002)
        return abs(open_price - low_price) <= tolerance and abs(low_price - close_price) <= tolerance

    @staticmethod
    def _describe_v13_sealing_strength_signal(signal: Dict[str, Any]) -> str:
        if not signal.get("available"):
            return "封板质量缺少日线事件，按中性解释"
        score = _safe_float(signal.get("score"))
        label = _safe_str(signal.get("level_label"), "封板质量")
        note = _safe_str(signal.get("execution_participation_note"))
        first_time = _safe_str(signal.get("first_seal_time"))
        time_part = f"，首次封板 {first_time}" if first_time else ""
        return f"封板质量 {score:.1f}（{label}{time_part}，{note}）"

    @staticmethod
    def _public_v13_sealing_strength_signal(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        signal = item.get("_v13_sealing_strength_signal")
        if not isinstance(signal, dict) or not signal.get("available"):
            return None
        return {
            "score": signal.get("score"),
            "level": signal.get("level"),
            "level_label": signal.get("level_label"),
            "first_seal_time": signal.get("first_seal_time"),
            "last_seal_time": signal.get("last_seal_time"),
            "first_seal_time_score": signal.get("first_seal_time_score"),
            "seal_amount_ratio": signal.get("seal_amount_ratio"),
            "seal_amount_score": signal.get("seal_amount_score"),
            "fd_amount": signal.get("fd_amount"),
            "amount": signal.get("amount"),
            "open_times": signal.get("open_times"),
            "open_times_score": signal.get("open_times_score"),
            "is_one_word_like": bool(signal.get("is_one_word_like")),
            "execution_bias": signal.get("execution_bias"),
            "execution_participation_note": signal.get("execution_participation_note"),
            "summary": signal.get("summary"),
            "confidence": signal.get("confidence"),
            "degraded_reasons": list(signal.get("degraded_reasons") or []),
        }

    @classmethod
    def _attach_v13_ladder_position_signal(
        cls,
        candidate: Dict[str, Any],
        *,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        signal = cls._v13_ladder_position_signal(candidate, context)
        candidate["_v13_ladder_position"] = signal
        candidate["_v13_board_count"] = signal.get("board_count")
        candidate["_v13_market_height"] = signal.get("market_height")
        candidate["_v13_space_leader"] = bool(signal.get("is_space_leader"))
        return signal

    @classmethod
    def _v13_ladder_position_signal(
        cls,
        candidate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        event = cls._select_v13_limit_event(candidate, context)
        limit_events = context.get("limit_events") or {}
        all_events = [
            row
            for rows in limit_events.values()
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
        ]
        limit_up_events = [
            row
            for row in all_events
            if _safe_str(row.get("limit")).upper() in {"", "U"}
        ]
        market_height = max(
            [int(_safe_float(row.get("limit_times"))) for row in limit_up_events] or [0]
        )
        if not event:
            return {
                "available": False,
                "board_count": None,
                "market_height": market_height or None,
                "is_space_leader": False,
                "same_height_count": 0,
                "gap_to_leader": None,
                "label": "梯队数据不足",
                "summary": "limit_list_d 未返回该股涨停梯队事件，按普通主线约束处理。",
            }

        board_count = int(_safe_float(event.get("limit_times")))
        same_height_count = sum(
            1
            for row in limit_up_events
            if int(_safe_float(row.get("limit_times"))) == board_count and board_count > 0
        )
        gap_to_leader = max(market_height - board_count, 0) if market_height > 0 and board_count > 0 else None
        is_space_leader = board_count >= 2 and market_height > 0 and board_count == market_height
        if is_space_leader:
            label = "空间龙头"
            summary = f"当前 {board_count} 连板，与市场最高板持平；空间龙可豁免无主线 R4。"
        elif board_count > 0 and market_height > 0:
            label = f"{board_count} 连板梯队"
            summary = f"当前 {board_count} 连板，市场最高 {market_height} 板，距离空间高度 {gap_to_leader} 板。"
        else:
            label = "非连板梯队"
            summary = "该股未形成明确连板梯队，仍需依赖题材共振确认。"

        return {
            "available": True,
            "board_count": board_count,
            "market_height": market_height,
            "is_space_leader": is_space_leader,
            "same_height_count": same_height_count,
            "gap_to_leader": gap_to_leader,
            "label": label,
            "summary": summary,
            "source": "limit_list_d.limit_times",
        }

    @staticmethod
    def _public_v13_ladder_position(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        signal = item.get("_v13_ladder_position")
        if not isinstance(signal, dict) or not signal.get("available"):
            return None
        return dict(signal)

    @staticmethod
    def _v13_fund_support_score(
        radar: Dict[str, Any],
        *,
        stock_flow_signal: Optional[Dict[str, Any]] = None,
    ) -> float:
        score = _safe_float(radar.get("fund_strength_score"), 50.0)
        if radar.get("fund_strength_score") is None:
            net_amount = _safe_float(radar.get("net_amount"))
            if net_amount > 0:
                score += min(28.0, net_amount / 500000000.0 * 6.0)
            elif net_amount < 0:
                score -= min(22.0, abs(net_amount) / 500000000.0 * 6.0)

            board_rank = int(_safe_float(radar.get("board_rank") or radar.get("rank"), 0.0))
            if 0 < board_rank <= 5:
                score += 18.0
            elif board_rank <= 15 and board_rank > 0:
                score += 10.0
            elif board_rank <= 30 and board_rank > 0:
                score += 5.0

            net_amount_rate = _safe_float(radar.get("net_amount_rate"))
            if net_amount_rate > 0:
                score += min(10.0, net_amount_rate * 1.5)
            elif net_amount_rate < 0:
                score -= min(10.0, abs(net_amount_rate) * 1.5)

            pct_change = _safe_float(radar.get("pct_change"))
            if pct_change > 0:
                score += min(8.0, pct_change * 1.2)
            elif pct_change < 0:
                score -= min(8.0, abs(pct_change) * 1.2)

        signal = stock_flow_signal or {}
        if signal.get("sources"):
            net_amount = _safe_float(signal.get("net_amount"))
            net_ratio = _safe_float(signal.get("net_ratio"))
            d5_amount = _safe_float(signal.get("net_d5_amount"))
            buy_lg_ratio = _safe_float(signal.get("buy_lg_ratio"))
            source_count = len(signal.get("sources") or [])

            if net_amount > 0:
                if net_ratio >= 0.06:
                    score += 16.0
                elif net_ratio >= 0.04:
                    score += 12.0
                elif net_ratio >= 0.02:
                    score += 8.0
                else:
                    score += 4.0
            elif net_amount < 0:
                if abs(net_ratio) >= 0.04:
                    score -= 16.0
                elif abs(net_ratio) >= 0.02:
                    score -= 10.0
                else:
                    score -= 5.0

            if d5_amount is not None:
                if d5_amount > 0 and net_amount > 0:
                    score += 8.0
                elif d5_amount < 0:
                    score -= 8.0

            if buy_lg_ratio >= 0.02:
                score += 7.0
            elif buy_lg_ratio >= 0.01:
                score += 4.0
            elif net_amount < 0:
                score -= 3.0

            if source_count >= 2:
                score += 3.0
        return _clamp_float(score)

    @staticmethod
    def _v13_limit_structure_score(candidate: Dict[str, Any], context: Dict[str, Any]) -> float:
        limit_events = context.get("limit_events") or {}
        events = limit_events.get(_safe_str(candidate.get("ts_code"))) or []
        score = 50.0
        if events:
            for event in events:
                limit_flag = _safe_str(event.get("limit")).upper()
                if limit_flag == "U":
                    score += 26.0
                elif limit_flag == "Z":
                    score -= 22.0
                elif limit_flag == "D":
                    score -= 35.0
                limit_times = int(_safe_float(event.get("limit_times")))
                open_times = int(_safe_float(event.get("open_times")))
                score += min(16.0, limit_times * 8.0)
                score -= min(18.0, open_times * 4.0)
                score += min(10.0, _safe_float(event.get("fd_amount")) / 100000000.0 * 2.0)
            return _clamp_float(score)

        pct_chg = _safe_float(candidate.get("pct_chg"))
        extension_score = _safe_float(candidate.get("extension_score"))
        if pct_chg >= 9.7:
            score += 18.0
        elif pct_chg >= 7.0:
            score += 10.0
        elif pct_chg <= 0:
            score -= 8.0
        if extension_score >= 90:
            score += 8.0
        elif extension_score < 60:
            score -= 6.0
        return _clamp_float(score)

    @staticmethod
    def _v13_buyability_shadow_score(
        candidate: Dict[str, Any],
        context: Dict[str, Any],
        *,
        chip_signal: Optional[Dict[str, Any]] = None,
    ) -> float:
        del context
        score = _safe_float(candidate.get("buyability_score"), 55.0)
        if candidate.get("entry_range_low") is not None and candidate.get("entry_range_high") is not None:
            score += 12.0
        buy_point_status = _safe_str(candidate.get("_buy_point_status"))
        if buy_point_status == "clear":
            score += 10.0
        elif buy_point_status == "waiting":
            score += 4.0
        risk_score = _safe_float(candidate.get("risk_score"))
        if risk_score >= 70:
            score -= 22.0
        elif risk_score >= 55:
            score -= 12.0
        elif risk_score <= 25:
            score += 8.0
        if "high_acceleration" in set(candidate.get("risk_tags") or []):
            score -= 8.0
        signal = chip_signal or {}
        if signal.get("available"):
            chip_buyability_score = int(_safe_float(signal.get("buyability_score"), 2.0))
            chip_risk_score = _safe_float(signal.get("risk_score"), 50.0)
            if chip_buyability_score >= 3:
                score += 10.0
            elif chip_buyability_score == 2:
                score += 4.0
            elif chip_buyability_score == 1:
                score -= 5.0
            else:
                score -= 12.0

            if chip_risk_score >= 75:
                score -= 10.0
            elif chip_risk_score >= 60:
                score -= 5.0
            elif chip_risk_score <= 32:
                score += 4.0
        return _clamp_float(score)

    def build_intraday_from_decision(
        self,
        decision: Dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        current_time = now or datetime.now()
        market_phase = self._resolve_market_phase(current_time)
        market_phase_label = INTRADAY_PHASE_LABELS[market_phase]
        portfolio = [dict(item) for item in decision.get("portfolio", [])]
        action = dict(decision.get("action", {}))
        trade_date = _safe_str(decision.get("trade_date"))

        if not portfolio:
            return {
                "market_phase": market_phase,
                "market_phase_label": market_phase_label,
                "confidence_level": "low",
                "confidence_label": INTRADAY_CONFIDENCE_LABELS["low"],
                "can_emit_buy_signal": False,
                "status": "not_applicable",
                "status_label": INTRADAY_STATUS_LABELS["not_applicable"],
                "reason": "当前没有默认组合，盘中信号仅保留静态筛选结果。",
                "watch_items": [],
                "final_recommendation": "do_not_buy",
                "final_recommendation_label": INTRADAY_FINAL_RECOMMENDATION_LABELS["do_not_buy"],
                "closing_note": "当前没有可跟踪的主仓 / 次仓 / 观察仓组合，今天不建议买入。",
                "updated_at": current_time.isoformat(),
                "focus_order": [],
                "portfolio_items": [],
            }

        if self._is_historical_trade_date(trade_date, current_time):
            portfolio_items = [
                self._build_intraday_item_without_quote(
                    item,
                    reason="当前盘中信号仅支持最新交易日附近，历史日期暂保留静态结果。",
                )
                for item in portfolio
            ]
            return {
                "market_phase": market_phase,
                "market_phase_label": market_phase_label,
                "confidence_level": "low",
                "confidence_label": INTRADAY_CONFIDENCE_LABELS["low"],
                "can_emit_buy_signal": False,
                "status": "not_applicable",
                "status_label": INTRADAY_STATUS_LABELS["not_applicable"],
                "reason": "历史交易日暂不提供真实盘中信号，请以收盘后二次决策为主。",
                "watch_items": [],
                "final_recommendation": "do_not_buy",
                "final_recommendation_label": INTRADAY_FINAL_RECOMMENDATION_LABELS["do_not_buy"],
                "closing_note": "当前为历史交易日，页面仅保留昨晚组合顺序与静态结论，不能作为实时执行依据。",
                "updated_at": current_time.isoformat(),
                "focus_order": self._build_intraday_focus_order(portfolio_items),
                "portfolio_items": portfolio_items,
            }

        if market_phase in {"pre_open", "call_auction"}:
            portfolio_items = [
                self._build_intraday_item_without_quote(
                    item,
                    reason="盘中买点需要等开盘后再确认，当前先保留昨晚排序。",
                )
                for item in portfolio
            ]
            return {
                "market_phase": market_phase,
                "market_phase_label": market_phase_label,
                "confidence_level": "medium",
                "confidence_label": INTRADAY_CONFIDENCE_LABELS["medium"],
                "can_emit_buy_signal": False,
                "status": "not_started",
                "status_label": INTRADAY_STATUS_LABELS["not_started"],
                "reason": "等待开盘后再确认承接、强度与是否进入买点区间。",
                "watch_items": [],
                "final_recommendation": "watch",
                "final_recommendation_label": INTRADAY_FINAL_RECOMMENDATION_LABELS["watch"],
                "closing_note": self._build_intraday_closing_note("watch", portfolio_items),
                "updated_at": current_time.isoformat(),
                "focus_order": self._build_intraday_focus_order(portfolio_items),
                "portfolio_items": portfolio_items,
            }

        stock_service = self.stock_service or StockService()
        portfolio_items = [
            self._build_intraday_item_signal(
                item,
                stock_service.get_realtime_quote(item["ts_code"]),
                action_level=action.get("level"),
            )
            for item in portfolio
        ]

        confidence_level, confidence_reason, watch_items = self._evaluate_intraday_confidence(
            action.get("level"),
            portfolio_items,
        )
        can_emit_buy_signal = action.get("level") in BUY_SIGNAL_ACTION_LEVELS and confidence_level != "low"
        status, final_recommendation, reason = self._build_intraday_overall_conclusion(
            action.get("level"),
            action.get("reason"),
            market_phase,
            confidence_level,
            confidence_reason,
            portfolio_items,
        )

        if not watch_items:
            watch_items = self._collect_watch_items(portfolio_items)

        focus_order = self._build_intraday_focus_order(portfolio_items)
        closing_note = self._build_intraday_closing_note(final_recommendation, portfolio_items)

        return {
            "market_phase": market_phase,
            "market_phase_label": market_phase_label,
            "confidence_level": confidence_level,
            "confidence_label": INTRADAY_CONFIDENCE_LABELS[confidence_level],
            "can_emit_buy_signal": can_emit_buy_signal and final_recommendation in {"buy", "main_only_consider"},
            "status": status,
            "status_label": INTRADAY_STATUS_LABELS[status],
            "reason": reason,
            "watch_items": watch_items[:3],
            "final_recommendation": final_recommendation,
            "final_recommendation_label": INTRADAY_FINAL_RECOMMENDATION_LABELS[final_recommendation],
            "closing_note": closing_note,
            "updated_at": current_time.isoformat(),
            "focus_order": focus_order,
            "portfolio_items": portfolio_items,
        }

    def _build_candidate_view(self, item: Dict[str, Any]) -> Dict[str, Any]:
        theme = item.get("themes", ["未分类"])[0] if item.get("themes") else "未分类"
        role_key = _normalize_leader_level(item.get("leader_level"))
        role_label = ROLE_LABELS[role_key]
        primary_reason = next(iter(item.get("top_reasons", [])), "综合强度更优")
        extension_signal_score = self._extension_signal_score(item)
        official_score = _official_sort_score(item)
        rule_base_score = (
            official_score * 0.75
            + _safe_float(item.get("continuation_score")) * 0.15
            + _safe_float(item.get("buyability_score"), extension_signal_score) * 0.10
            - _safe_float(item.get("risk_score")) * 0.05
        )

        enriched = dict(item)
        enriched.update(
            {
                "_theme": theme,
                "_role_key": role_key,
                "_role_label": role_label,
                "_official_score": round(official_score, 2),
                "_rule_base_score": round(rule_base_score, 2),
                "_primary_reason": primary_reason,
            }
        )
        self._refresh_candidate_buy_point_fields(enriched)
        return enriched

    def _refresh_candidate_buy_point_fields(self, item: Dict[str, Any]) -> None:
        role_key = _safe_str(item.get("_role_key")) or _normalize_leader_level(item.get("leader_level"))
        role_label = ROLE_LABELS.get(role_key, ROLE_LABELS["back"])
        item["_role_key"] = role_key
        item["_role_label"] = role_label

        buy_point_status, buy_point_label = self._classify_buy_point(item, role_key)
        explain_adjustment_score = (
            ROLE_TIEBREAKER_PRIORITY.get(role_key, 0.0)
            + BUY_POINT_TIEBREAKER_PRIORITY[buy_point_status]
        )
        t1_direction_risk_adjustment = self._t1_direction_risk_adjustment(item, buy_point_status)
        decision_score = (
            _safe_float(item.get("_rule_base_score"))
            + explain_adjustment_score
            + t1_direction_risk_adjustment
        )
        forward_alpha_score = self._forward_alpha_score(item, role_key, buy_point_status)

        item["_buy_point_status"] = buy_point_status
        item["_buy_point_label"] = buy_point_label
        item["_explain_adjustment_score"] = round(explain_adjustment_score, 2)
        item["_t1_direction_risk_adjustment"] = round(t1_direction_risk_adjustment, 2)
        item["_decision_score"] = round(decision_score, 2)
        item["_forward_alpha_score"] = round(forward_alpha_score, 2)

    def _build_theme_summaries(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate["_theme"]].append(candidate)

        summaries: List[Dict[str, Any]] = []
        for theme, items in grouped.items():
            sorted_items = sorted(items, key=self._decision_candidate_sort_key, reverse=True)
            for item in sorted_items:
                item["_theme_pool_count"] = len(sorted_items)
            clear_count = sum(item["_buy_point_status"] == "clear" for item in sorted_items)
            leader_count = sum(item["_role_key"] == "leader" for item in sorted_items)
            front_count = sum(item["_role_key"] == "front" for item in sorted_items)
            avg_rank_score = mean(_official_sort_score(item) for item in sorted_items)
            rule_theme_score = min(
                100.0,
                avg_rank_score * 0.60
                + min(len(sorted_items), 3) * 7.0
                + leader_count * 6.0
                + front_count * 3.0
                + clear_count * 4.0,
            )
            v13_mainline_score = max(_safe_float(item.get("_v13_mainline_score")) for item in sorted_items)
            theme_score = max(rule_theme_score, v13_mainline_score)
            strength_label = self._theme_strength_label(theme_score)
            v13_theme_id = next((_safe_str(item.get("_v13_theme_id")) for item in sorted_items if item.get("_v13_theme_id")), "")
            v13_summary = next(
                (_safe_str(item.get("_v13_mainline_summary")) for item in sorted_items if item.get("_v13_mainline_summary")),
                "",
            )
            summaries.append(
                {
                    "name": theme,
                    "score": round(theme_score, 1),
                    "strength_label": strength_label,
                    "rule_theme_score": round(rule_theme_score, 1),
                    "v13_theme_id": v13_theme_id or None,
                    "v13_mainline_score": round(v13_mainline_score, 1) if v13_mainline_score > 0 else None,
                    "v13_summary": v13_summary or None,
                    "candidate_count": len(sorted_items),
                    "clear_buy_point_count": clear_count,
                    "leader_count": leader_count,
                    "summary": (
                        f"{theme} 当前聚集 {len(sorted_items)} 只强势候选，"
                        f"其中 {leader_count} 只龙头核心、{clear_count} 只买点清晰。"
                    ),
                    "representatives": [
                        {
                            "rank": int(item.get("rank", 0)),
                            "ts_code": item["ts_code"],
                            "name": item["name"],
                            "role": item["_role_label"],
                            "buy_point_label": item["_buy_point_label"],
                            "official_score": round(_official_sort_score(item), 1),
                            "v13_mainline_score": (
                                round(_safe_float(item.get("_v13_mainline_score")), 1)
                                if item.get("_v13_mainline_score")
                                else None
                            ),
                        }
                        for item in sorted_items[:3]
                    ],
                }
            )

        summaries.sort(key=lambda item: item["score"], reverse=True)
        return summaries[:2]

    def _build_portfolio(
        self,
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        sorted_candidates = self._build_decision_candidate_pool(candidates)
        selected: List[Tuple[str, Dict[str, Any]]] = []
        selected_codes: set[str] = set()
        selected_themes: List[str] = []

        main_candidate = self._pick_main_candidate(sorted_candidates, theme_score_map)
        if main_candidate is None:
            return []
        selected.append(("main", main_candidate))
        selected_codes.add(main_candidate["ts_code"])
        selected_themes.append(main_candidate["_theme"])

        secondary_candidate = self._pick_secondary_candidate(
            sorted_candidates,
            selected_codes,
            main_candidate,
            themes,
            theme_score_map,
        )
        if secondary_candidate is not None:
            selected.append(("secondary", secondary_candidate))
            selected_codes.add(secondary_candidate["ts_code"])
            selected_themes.append(secondary_candidate["_theme"])

        watch_candidate = self._pick_watch_candidate(
            sorted_candidates,
            selected_codes,
            selected_themes,
            theme_score_map,
        )
        if watch_candidate is not None:
            selected.append(("watch", watch_candidate))

        selected = self._rebalance_same_theme_main_slot(selected, theme_score_map)
        selected = self._rebalance_portfolio_anchor(selected, theme_score_map)

        return [
            self._build_portfolio_slot(slot, candidate, theme_score_map)
            for slot, candidate in selected
        ]

    def _build_excluded_candidates(
        self,
        candidates: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        selected_codes = {item["ts_code"] for item in portfolio}
        selected_theme_names = {item["theme"] for item in portfolio}
        selected_roles = {(item["theme"], item["role"]) for item in portfolio}
        top_theme_name = themes[0]["name"] if themes else ""

        excluded: List[Dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: int(item.get("rank", 999))):
            if candidate["ts_code"] in selected_codes:
                continue

            theme_name = candidate["_theme"]
            role_label = candidate["_role_label"]
            official_score = round(_official_sort_score(candidate), 1)
            hard_blockers = self._collect_candidate_hard_blocker_items(candidate, theme_score_map)
            soft_adjustments = self._portfolio_adjustment_items(candidate, theme_score_map)
            decision_adjustment = round(
                self._portfolio_priority(candidate, theme_score_map) - _official_sort_score(candidate),
                2,
            )

            if theme_name not in selected_theme_names and theme_score_map.get(theme_name, 0.0) < 60:
                reason_key = "non_mainline_weak"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = "当前题材不在默认主线内，且题材强度偏弱，因此本轮不优先收口。"
            elif candidate["_buy_point_status"] == "unclear":
                reason_key = "buy_point_unclear"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = "当前买点还没有收清晰，先放回观察池，等待更明确的触发。"
            elif hard_blockers:
                reason_key = "hard_blocked"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = self._describe_adjustments([], blockers=hard_blockers)
            elif (theme_name, role_label) in selected_roles:
                reason_key = "role_duplicate"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = "同主题同角色已有更优先候选入选，本票本轮作为重复角色落选。"
            elif theme_name == top_theme_name:
                reason_key = "mainline_rank_not_enough"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = "虽然属于当日主线，但在主线内部的正式排序还不够靠前，暂未收入口袋组合。"
            else:
                reason_key = "slot_capacity"
                reason = EXCLUDED_REASON_LABELS[reason_key]
                reason_detail = "当前组合槽位已经被更高优先级候选占用，本票保留观察但暂不入选。"

            excluded.append(
                {
                    "rank": int(candidate.get("rank", 0)),
                    "base_rank": int(candidate.get("rank", 0)),
                    "ts_code": candidate["ts_code"],
                    "name": candidate["name"],
                    "theme": theme_name,
                    "role": role_label,
                    "reason_key": reason_key,
                    "reason": reason,
                    "reason_detail": reason_detail,
                    "official_score": official_score,
                    "base_rank_score": official_score,
                    "v13_sealing_strength": self._public_v13_sealing_strength_signal(candidate),
                    "v13_ladder_position": self._public_v13_ladder_position(candidate),
                    "v13_sealing_strength_score": (
                        round(_safe_float(candidate.get("_v13_sealing_strength_score")), 1)
                        if candidate.get("_v13_sealing_strength_score") is not None
                        else None
                    ),
                    "v13_sealing_strength_level": candidate.get("_v13_sealing_strength_level"),
                    "v13_sealing_strength_level_label": candidate.get("_v13_sealing_strength_level_label"),
                    "risk_stack": candidate.get("_risk_stack_check"),
                    "risk_stack_count": candidate.get("_risk_stack_count"),
                    "risk_stack_veto": candidate.get("_risk_stack_veto"),
                    "mainline_intensity_count": int(_safe_float(candidate.get("_official_mainline_intensity_count"))),
                    "mainline_intensity_multiplier": round(
                        _safe_float(candidate.get("_official_mainline_intensity_multiplier"), 1.0),
                        2,
                    ),
                    "mainline_intensity_bonus": round(
                        _safe_float(candidate.get("_official_mainline_intensity_bonus")),
                        2,
                    ),
                    "adaptive_gate": candidate.get("_adaptive_gate_context"),
                    "adaptive_mainline_count": candidate.get("_adaptive_mainline_count"),
                    "adaptive_mainline_min_count": candidate.get("_adaptive_mainline_min_count"),
                    "adaptive_mainline_pass": candidate.get("_adaptive_mainline_pass"),
                    "decision_adjustment": decision_adjustment,
                    "decision_adjustment_reason": self._describe_adjustments(soft_adjustments),
                    "hard_blockers": hard_blockers,
                    "soft_adjustments": soft_adjustments,
                }
            )

        return excluded[:8]

    def _build_candidate_diagnostics(
        self,
        candidates: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
        *,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        selected_slot_by_code = {
            _safe_str(item.get("ts_code")): _safe_str(item.get("slot"))
            for item in portfolio
            if item.get("ts_code")
        }
        diagnostics: List[Dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: int(item.get("rank", 999)))[:limit]:
            ts_code = _safe_str(candidate.get("ts_code"))
            selected_slot = selected_slot_by_code.get(ts_code)
            forward_alpha_score = _safe_float(candidate.get("_forward_alpha_score"), 50.0)
            base_rank = int(candidate.get("rank") or 0)
            base_rank_score = round(_official_sort_score(candidate), 2)
            soft_adjustments = self._portfolio_adjustment_items(candidate, theme_score_map)
            preferred_slot = selected_slot or self._preferred_slot_for_candidate(candidate)
            hard_blockers = self._slot_hard_blocker_items(preferred_slot, candidate, theme_score_map)
            portfolio_priority = round(self._portfolio_priority(candidate, theme_score_map), 2)
            decision_adjustment = round(portfolio_priority - _official_sort_score(candidate), 2)
            diagnostics.append(
                {
                    "rank": base_rank,
                    "base_rank": base_rank,
                    "ts_code": ts_code,
                    "name": _safe_str(candidate.get("name")),
                    "theme": candidate["_theme"],
                    "theme_score": round(_safe_float(theme_score_map.get(candidate["_theme"]), 50.0), 2),
                    "v13_theme_id": candidate.get("_v13_theme_id"),
                    "v13_mainline_score": (
                        round(_safe_float(candidate.get("_v13_mainline_score")), 2)
                        if candidate.get("_v13_mainline_score")
                        else None
                    ),
                    "v13_mainline_level": candidate.get("_v13_mainline_level"),
                    "v13_mainline_level_label": candidate.get("_v13_mainline_level_label"),
                    "v13_theme_strength_score": (
                        round(_safe_float(candidate.get("_v13_theme_strength_score")), 2)
                        if candidate.get("_v13_theme_strength_score") is not None
                        else None
                    ),
                    "v13_fund_support_score": (
                        round(_safe_float(candidate.get("_v13_fund_support_score")), 2)
                        if candidate.get("_v13_fund_support_score") is not None
                        else None
                    ),
                    "v13_limit_structure_score": (
                        round(_safe_float(candidate.get("_v13_limit_structure_score")), 2)
                        if candidate.get("_v13_limit_structure_score") is not None
                        else None
                    ),
                    "v13_sealing_strength": self._public_v13_sealing_strength_signal(candidate),
                    "v13_ladder_position": self._public_v13_ladder_position(candidate),
                    "v13_sealing_strength_score": (
                        round(_safe_float(candidate.get("_v13_sealing_strength_score")), 2)
                        if candidate.get("_v13_sealing_strength_score") is not None
                        else None
                    ),
                    "v13_sealing_strength_level": candidate.get("_v13_sealing_strength_level"),
                    "v13_sealing_strength_level_label": candidate.get("_v13_sealing_strength_level_label"),
                    "v13_buyability_score": (
                        round(_safe_float(candidate.get("_v13_buyability_score")), 2)
                        if candidate.get("_v13_buyability_score") is not None
                        else None
                    ),
                    "v13_chip_risk_score": (
                        round(_safe_float(candidate.get("_v13_chip_risk_score")), 2)
                        if candidate.get("_v13_chip_risk_score") is not None
                        else None
                    ),
                    "risk_stack": candidate.get("_risk_stack_check"),
                    "risk_stack_count": candidate.get("_risk_stack_count"),
                    "risk_stack_veto": candidate.get("_risk_stack_veto"),
                    "mainline_intensity_count": int(_safe_float(candidate.get("_official_mainline_intensity_count"))),
                    "mainline_intensity_multiplier": round(
                        _safe_float(candidate.get("_official_mainline_intensity_multiplier"), 1.0),
                        2,
                    ),
                    "mainline_intensity_bonus": round(
                        _safe_float(candidate.get("_official_mainline_intensity_bonus")),
                        2,
                    ),
                    "adaptive_gate": candidate.get("_adaptive_gate_context"),
                    "adaptive_mainline_count": candidate.get("_adaptive_mainline_count"),
                    "adaptive_mainline_min_count": candidate.get("_adaptive_mainline_min_count"),
                    "adaptive_mainline_pass": candidate.get("_adaptive_mainline_pass"),
                    "v13_shadow_score": (
                        round(_safe_float(candidate.get("_v13_shadow_score")), 2)
                        if candidate.get("_v13_shadow_score") is not None
                        else None
                    ),
                    "v13_shadow_summary": candidate.get("_v13_shadow_summary"),
                    "role_key": candidate["_role_key"],
                    "role": candidate["_role_label"],
                    "buy_point_status": candidate["_buy_point_status"],
                    "buy_point_label": candidate["_buy_point_label"],
                    "official_score": base_rank_score,
                    "base_rank_score": base_rank_score,
                    "continuation_score": round(_safe_float(candidate.get("continuation_score")), 2),
                    "extension_score": round(_safe_float(candidate.get("extension_score")), 2),
                    "extension_signal_score": round(self._extension_signal_score(candidate), 2),
                    "buyability_score": (
                        round(_safe_float(candidate.get("buyability_score")), 2)
                        if candidate.get("buyability_score") is not None
                        else None
                    ),
                    "risk_score": round(_safe_float(candidate.get("risk_score")), 2),
                    "rule_base_score": round(_safe_float(candidate.get("_rule_base_score")), 2),
                    "decision_adjustment": decision_adjustment,
                    "decision_adjustment_reason": self._describe_adjustments(
                        soft_adjustments,
                        blockers=hard_blockers if hard_blockers and not selected_slot else None,
                    ),
                    "hard_blockers": hard_blockers,
                    "soft_adjustments": soft_adjustments,
                    "explain_adjustment_score": round(_safe_float(candidate.get("_explain_adjustment_score")), 2),
                    "t1_direction_risk_adjustment": round(
                        _safe_float(candidate.get("_t1_direction_risk_adjustment")),
                        2,
                    ),
                    "forward_alpha_score": round(forward_alpha_score, 2),
                    "forward_alpha_adjustment": round((forward_alpha_score - 50.0) * 0.55, 2),
                    "portfolio_priority": portfolio_priority,
                    "selected_slot": selected_slot,
                    "is_selected": bool(selected_slot),
                }
            )
        return diagnostics

    def _build_attack_permission(self, strategy_health: Dict[str, Any]) -> Dict[str, Any]:
        short_window = strategy_health.get("short_window", {})
        sample_count = int(_safe_float(short_window.get("sample_count"), 0))
        short_window_score = round(_safe_float(short_window.get("score"), 0.0), 1)
        hit_rate = round(_safe_float(short_window.get("success_rate"), 0.0), 1)
        avg_profit_window_pct = round(_safe_float(short_window.get("avg_profit_window_pct"), 0.0), 2)
        avg_max_drawdown_pct = round(_safe_float(short_window.get("avg_max_drawdown_pct"), 0.0), 2)
        score = round(
            _clamp_float(
                hit_rate * 0.75
                + min(avg_profit_window_pct, 3.0) / 3.0 * 18.0
                + max(0.0, 1.0 - avg_max_drawdown_pct / 6.0) * 7.0
            ),
            1,
        )
        meets_open_hit_rate = (
            sample_count >= ATTACK_PERMISSION_MIN_SAMPLES["open"]
            and hit_rate >= ATTACK_PERMISSION_HIT_RATE_THRESHOLDS["open"]
        )
        meets_recovering_hit_rate = (
            sample_count >= ATTACK_PERMISSION_MIN_SAMPLES["recovering"]
            and hit_rate >= ATTACK_PERMISSION_HIT_RATE_THRESHOLDS["recovering"]
        )
        meets_open_quality_recovery = (
            sample_count >= 8
            and short_window_score >= ATTACK_PERMISSION_SCORE_THRESHOLDS["open"]
            and avg_profit_window_pct >= ATTACK_PERMISSION_PROFIT_WINDOW_THRESHOLDS["open"]
            and avg_max_drawdown_pct <= ATTACK_PERMISSION_DRAWDOWN_THRESHOLDS["open"]
        )
        meets_recovering_quality_recovery = (
            sample_count >= 8
            and short_window_score >= ATTACK_PERMISSION_SCORE_THRESHOLDS["recovering"]
            and avg_profit_window_pct >= ATTACK_PERMISSION_PROFIT_WINDOW_THRESHOLDS["recovering"]
            and avg_max_drawdown_pct <= ATTACK_PERMISSION_DRAWDOWN_THRESHOLDS["recovering"]
        )

        if meets_open_hit_rate or meets_open_quality_recovery:
            status = "open"
            if meets_open_quality_recovery and not meets_open_hit_rate:
                summary = "最近 20 日命中率还没完全回到高位，但利润窗口与回撤结构已回到可进攻区间，当前可恢复进攻。"
            else:
                summary = "最近 20 日里，系统仍能稳定打出可执行的核心票，当前可继续进攻。"
        elif meets_recovering_hit_rate or meets_recovering_quality_recovery:
            status = "recovering"
            if meets_recovering_quality_recovery and not meets_recovering_hit_rate:
                summary = "最近 20 日命中率仍偏低，但利润窗口和回撤已回到可跟进区间，进攻许可先恢复到谨慎放行。"
            else:
                summary = "最近 20 日的进攻命中开始修复，但还没恢复到完整进攻节奏。"
        else:
            status = "paused"
            summary = "最近 20 日的进攻命中仍不足，今天不适合把进攻节奏开满。"

        return {
            "status": status,
            "status_label": ATTACK_PERMISSION_STATUS_LABELS[status],
            "label": ATTACK_PERMISSION_STATUS_LABELS[status],
            "score": score,
            "window": "short_20d",
            "window_label": "20 日进攻许可",
            "valid_sample_count": sample_count,
            "short_window_score": short_window_score,
            "hit_rate": hit_rate,
            "avg_profit_window_pct": avg_profit_window_pct,
            "avg_max_drawdown_pct": avg_max_drawdown_pct,
            "reason": summary,
            "summary": summary,
        }

    def _build_theme_confidence(self, strategy_health: Dict[str, Any]) -> Dict[str, Any]:
        long_window = strategy_health.get("long_window", {})
        sample_count = int(_safe_float(long_window.get("sample_count"), 0))
        score = round(_safe_float(long_window.get("score"), 0.0), 1)
        core_hit_rate = round(_safe_float(long_window.get("success_rate"), 0.0), 1)

        if (
            sample_count >= THEME_CONFIDENCE_MIN_SAMPLES["credible"]
            and score >= THEME_CONFIDENCE_SCORE_THRESHOLDS["credible"]
        ):
            status = "credible"
            summary = "最近 60 日主线识别整体仍稳定，当前可继续把它作为主判断框架。"
        elif (
            sample_count >= THEME_CONFIDENCE_MIN_SAMPLES["recovering"]
            and score >= THEME_CONFIDENCE_SCORE_THRESHOLDS["recovering"]
        ):
            status = "recovering"
            summary = "最近 60 日主线识别质量正在恢复，但结构信任度仍需要打折。"
        else:
            status = "questionable"
            summary = "最近 60 日主线结构的可信度偏弱，今天可做也要明确降低信任度。"

        return {
            "status": status,
            "status_label": THEME_CONFIDENCE_STATUS_LABELS[status],
            "label": THEME_CONFIDENCE_STATUS_LABELS[status],
            "score": score,
            "window": "long_60d",
            "window_label": "60 日主线可信度",
            "valid_sample_count": sample_count,
            "core_hit_rate": core_hit_rate,
            "reason": summary,
            "summary": summary,
        }

    @staticmethod
    def _build_decision_risk_banner(
        *,
        action: Dict[str, Any],
        theme_confidence: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        action_level = _safe_str(action.get("level"))
        theme_status = _safe_str(theme_confidence.get("status"))
        if action_level not in {"strong_go", "normal_go", "cautious_go"}:
            return None
        if theme_status != "questionable":
            return None
        return {
            "tone": "warning",
            "title": "60 日主线可信度存疑",
            "message": "今天仍可以按当前动作级别跟踪，但这套主线结构的可信度在下降，信任度需要打折。",
        }

    def _build_market_environment(
        self,
        *,
        trade_date: str,
        profile: str,
        request_params: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        profitability = self._build_market_environment_profitability(
            trade_date=trade_date,
            profile=profile,
            request_params=request_params,
        )
        core_success_rate = round(_safe_float(profitability.get("core_success_rate"), 0.0), 1)
        core_profit_window_pct = round(_safe_float(profitability.get("core_profit_window_pct"), 0.0), 2)
        broad_success_rate = round(_safe_float(profitability.get("broad_success_rate"), 0.0), 1)
        broad_profit_window_pct = round(_safe_float(profitability.get("broad_profit_window_pct"), 0.0), 2)

        core_level = self._classify_core_premium_level(core_success_rate, core_profit_window_pct)
        breadth_level = self._classify_breadth_premium_level(
            broad_success_rate,
            broad_profit_window_pct,
        )

        if core_level == "strong" and breadth_level == "strong":
            level = "strong"
        elif core_level == "weak" and breadth_level == "weak":
            level = "weak"
        else:
            level = "medium"

        modules = [
            {
                "key": "core_premium",
                "label": GATE_LEVEL_LABELS[core_level],
                "level": core_level,
                "score": round(
                    _clamp_float(core_success_rate * 0.7 + min(core_profit_window_pct, 4.0) / 4.0 * 30.0),
                    1,
                ),
                "summary": (
                    f"昨日默认 Top3 命中率 {core_success_rate:.1f}% ，"
                    f"核心溢价利润窗口 {core_profit_window_pct:.2f}% 。"
                ),
            },
            {
                "key": "breadth_premium",
                "label": GATE_LEVEL_LABELS[breadth_level],
                "level": breadth_level,
                "score": round(
                    _clamp_float(
                        broad_success_rate * 0.7 + min(broad_profit_window_pct, 4.0) / 4.0 * 30.0
                    ),
                    1,
                ),
                "summary": (
                    f"昨日候选池 Top10 命中率 {broad_success_rate:.1f}% ，"
                    f"平均利润窗口 {broad_profit_window_pct:.2f}% 。"
                ),
            },
        ]
        score = round(_clamp_float(modules[0]["score"] * 0.55 + modules[1]["score"] * 0.45), 1)

        return {
            "level": level,
            "label": GATE_LEVEL_LABELS[level],
            "score": score,
            "reason": (
                f"核心溢价为{GATE_LEVEL_LABELS[core_level]}，"
                f"广度溢价为{GATE_LEVEL_LABELS[breadth_level]}，"
                f"市场环境判定为{GATE_LEVEL_LABELS[level]}。"
            ),
            "modules": modules,
        }

    @staticmethod
    def _classify_core_premium_level(success_rate: float, profit_window_pct: float) -> str:
        """Core premium is noisy on only three names, so keep it graded instead of binary."""

        if success_rate >= 40.0 and profit_window_pct >= 2.0:
            return "strong"
        if success_rate >= 10.0 or profit_window_pct >= 1.2:
            return "medium"
        return "weak"

    @staticmethod
    def _classify_breadth_premium_level(success_rate: float, profit_window_pct: float) -> str:
        if success_rate >= 30.0 and profit_window_pct >= 2.0:
            return "strong"
        if success_rate >= 20.0 or profit_window_pct >= 1.2:
            return "medium"
        return "weak"

    def _get_market_environment_current_datetime(self) -> datetime:
        get_china_now = getattr(self.screener_service, "_get_china_now", None)
        if callable(get_china_now):
            try:
                return get_china_now()
            except Exception:
                logger.debug("Failed to use screener_service._get_china_now for gate evaluation", exc_info=True)
        return datetime.now()

    @staticmethod
    def _normalize_market_environment_index_code(value: Any) -> str:
        normalized = _safe_str(value).strip().upper()
        if "." in normalized:
            return normalized
        if normalized.startswith(("SH", "SZ", "BJ")) and len(normalized) > 2:
            return f"{normalized[2:]}.{normalized[:2]}"
        return normalized

    def _load_market_environment_index_history_rows(self) -> List[Dict[str, Any]]:
        fetcher = getattr(self.screener_service, "fetcher", None)
        api = getattr(fetcher, "_api", None)
        if api is None:
            return []

        current_time = self._get_market_environment_current_datetime()
        end_date = current_time.strftime("%Y%m%d")
        start_date = (current_time - timedelta(days=15)).strftime("%Y%m%d")
        rows: List[Dict[str, Any]] = []

        for config in MARKET_ENVIRONMENT_INDEX_GROUPS:
            for ts_code in config.get("history_codes", ()):
                try:
                    frame = api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                except Exception:
                    logger.debug("Failed to load index history for %s", ts_code, exc_info=True)
                    continue

                if frame is None or frame.empty or "close" not in frame.columns:
                    continue

                working = frame.copy()
                if "trade_date" in working.columns:
                    working["trade_date"] = pd.to_datetime(
                        working["trade_date"].astype(str),
                        format="%Y%m%d",
                        errors="coerce",
                    )
                    working = working.sort_values("trade_date")
                else:
                    working = working.iloc[::-1]

                closes = pd.to_numeric(working["close"], errors="coerce").dropna()
                if len(closes) < 5:
                    continue

                latest_close = float(closes.iloc[-1])
                ma5 = float(closes.tail(5).mean())
                slope_base = float(closes.iloc[-4]) if len(closes) >= 4 else float(closes.iloc[0])
                slope_pct = ((latest_close / slope_base) - 1.0) * 100 if slope_base > 0 else 0.0
                distance_to_ma5_pct = ((latest_close / ma5) - 1.0) * 100 if ma5 > 0 else 0.0

                if latest_close >= ma5 and slope_pct >= 0.2:
                    level = "strong"
                    summary = (
                        f"{config['label']} 站上 5 日线，3 日斜率 {slope_pct:+.2f}% ，"
                        f"当前高于 5 日线 {distance_to_ma5_pct:+.2f}%。"
                    )
                elif latest_close < ma5 and slope_pct <= -0.2:
                    level = "weak"
                    summary = (
                        f"{config['label']} 跌破 5 日线，3 日斜率 {slope_pct:+.2f}% ，"
                        f"当前低于 5 日线 {distance_to_ma5_pct:+.2f}%。"
                    )
                else:
                    level = "medium"
                    summary = (
                        f"{config['label']} 围绕 5 日线震荡，3 日斜率 {slope_pct:+.2f}% ，"
                        f"当前偏离 5 日线 {distance_to_ma5_pct:+.2f}%。"
                    )

                rows.append(
                    {
                        "label": config["label"],
                        "code": ts_code,
                        "level": level,
                        "close": latest_close,
                        "ma5": ma5,
                        "slope_pct": slope_pct,
                        "distance_to_ma5_pct": distance_to_ma5_pct,
                        "summary": summary,
                    }
                )
                break

        return rows

    def _select_market_environment_index_snapshot_rows(
        self,
        index_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized_rows = {
            self._normalize_market_environment_index_code(row.get("code")): row
            for row in index_rows
            if isinstance(row, dict) and row.get("code")
        }
        selected: List[Dict[str, Any]] = []
        for config in MARKET_ENVIRONMENT_INDEX_GROUPS:
            matched_row = next(
                (
                    normalized_rows.get(self._normalize_market_environment_index_code(code))
                    for code in config.get("snapshot_codes", set())
                    if normalized_rows.get(self._normalize_market_environment_index_code(code)) is not None
                ),
                None,
            )
            label = config["label"]
            if matched_row is None:
                matched_row = next(
                    (
                        normalized_rows.get(self._normalize_market_environment_index_code(code))
                        for code in config.get("snapshot_fallback_codes", set())
                        if normalized_rows.get(self._normalize_market_environment_index_code(code)) is not None
                    ),
                    None,
                )
                if matched_row is not None:
                    label = _safe_str(config.get("snapshot_fallback_label"), config["label"])

            if matched_row is not None:
                selected.append({"label": label, "row": matched_row})
        return selected

    def _build_market_environment_index_trend(self) -> Dict[str, Any]:
        history_rows = self._load_market_environment_index_history_rows()
        if len(history_rows) >= 2:
            strong_count = sum(1 for row in history_rows if row["level"] == "strong")
            weak_count = sum(1 for row in history_rows if row["level"] == "weak")
            avg_slope = mean(row["slope_pct"] for row in history_rows)
            score = _clamp_float(60.0 + strong_count * 10.0 - weak_count * 12.0 + avg_slope * 1.8, 22.0, 88.0)
            if strong_count >= 2:
                level = "strong"
            elif weak_count >= 2:
                level = "weak"
            else:
                level = "medium"
            return {
                "key": "index_trend",
                "label": GATE_LEVEL_LABELS[level],
                "level": level,
                "score": round(score, 1),
                "summary": "；".join(row["summary"] for row in history_rows),
            }

        fetcher = getattr(self.screener_service, "fetcher", None)
        get_main_indices = getattr(fetcher, "get_main_indices", None)
        if not callable(get_main_indices):
            return {
                "key": "index_trend",
                "label": "中",
                "level": "medium",
                "score": 60.0,
                "summary": "暂无可靠指数数据，指数趋势先按中性处理。",
            }

        index_rows = get_main_indices(region="cn") or []
        if not index_rows:
            return {
                "key": "index_trend",
                "label": "中",
                "level": "medium",
                "score": 60.0,
                "summary": "未取到主要指数快照，指数趋势先按中性处理。",
            }

        tracked = self._select_market_environment_index_snapshot_rows(index_rows)
        positive = sum(1 for item in tracked if _safe_float(item["row"].get("change_pct")) >= 0.5)
        negative = sum(1 for item in tracked if _safe_float(item["row"].get("change_pct")) <= -0.5)
        if positive >= 2:
            level = "strong"
            score = 82.0
        elif negative >= 2:
            level = "weak"
            score = 28.0
        else:
            level = "medium"
            score = 60.0
        summary = "；".join(
            f"{item['label']} {(_safe_float(item['row'].get('change_pct'))):+.2f}%"
            for item in tracked
        ) or "主要指数暂无有效快照"
        return {
            "key": "index_trend",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": summary,
        }

    @staticmethod
    def _classify_profitability_level(success_rate: float, profit_window_pct: float) -> str:
        if success_rate >= 60.0 and profit_window_pct >= 2.0:
            return "strong"
        if success_rate < 40.0 and profit_window_pct < 0.5:
            return "weak"
        return "medium"

    def _build_market_environment_profitability(
        self,
        *,
        trade_date: str,
        profile: str,
        request_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        previous_dates = self._load_strategy_health_trade_dates(end_trade_date=trade_date, limit=1)
        if not previous_dates or self.screener_service is None:
            return {
                "key": "profitability",
                "label": "中",
                "level": "medium",
                "score": 60.0,
                "summary": "上一交易日样本不足，赚钱效应暂按中性处理。",
            }

        previous_trade_date = previous_dates[0]
        try:
            screening = self.screener_service.screen(
                top_n=max(int(_safe_float(request_params.get("top_n"), MOMENTUM_DEFAULT_TOP_N)), MOMENTUM_DEFAULT_TOP_N),
                min_change_pct=_safe_float(request_params.get("min_change_pct"), MOMENTUM_DEFAULT_MIN_CHANGE_PCT),
                min_amount=_safe_float(request_params.get("min_amount"), MOMENTUM_DEFAULT_MIN_AMOUNT),
                min_turnover=_safe_float(request_params.get("min_turnover"), MOMENTUM_DEFAULT_MIN_TURNOVER),
                exclude_st=bool(request_params.get("exclude_st", True)),
                main_board_only=bool(request_params.get("main_board_only", False)),
                trade_date=previous_trade_date,
                profile=profile,
                use_sector_context=False,
                max_scored_candidates=STRATEGY_HEALTH_MAX_SCORED_CANDIDATES,
            )
        except Exception:
            logger.warning(
                "Failed to build market-environment profitability sample for %s; fallback to medium",
                previous_trade_date,
                exc_info=True,
            )
            return {
                "key": "profitability",
                "label": GATE_LEVEL_LABELS["medium"],
                "level": "medium",
                "score": 60.0,
                "summary": f"{previous_trade_date} 的赚钱效应样本获取失败，暂按中性处理。",
            }
        results = self._extract_decision_source_results(screening)
        if not results:
            return {
                "key": "profitability",
                "label": "中",
                "level": "medium",
                "score": 60.0,
                "summary": "上一交易日没有形成有效强势样本，赚钱效应暂按中性处理。",
            }

        enriched = [self._build_candidate_view(item) for item in results]
        themes = self._build_theme_summaries(enriched)
        theme_score_map = {theme["name"]: theme["score"] for theme in themes}
        portfolio = self._build_portfolio(enriched, themes, theme_score_map)
        candidate_map = {item["ts_code"]: item for item in enriched}
        broad_codes = [item["ts_code"] for item in enriched[:10]]
        core_codes = [item["ts_code"] for item in portfolio]
        core_results = [
            self._evaluate_market_environment_sample_item(previous_trade_date, candidate_map[ts_code])
            for ts_code in core_codes
            if ts_code in candidate_map
        ]
        broad_results = [
            self._evaluate_market_environment_sample_item(previous_trade_date, candidate_map[ts_code])
            for ts_code in broad_codes
            if ts_code in candidate_map
        ]
        core_results = [item for item in core_results if item is not None]
        broad_results = [item for item in broad_results if item is not None]
        if not core_results and not broad_results:
            return {
                "key": "profitability",
                "label": "中",
                "level": "medium",
                "score": 60.0,
                "summary": "上一交易日样本未能形成可验证的 T+1/T+2 结果。",
            }

        core_success_rate = 100.0 * sum(1 for item in core_results if item["success"]) / max(len(core_results), 1)
        broad_success_rate = 100.0 * sum(1 for item in broad_results if item["success"]) / max(len(broad_results), 1)
        core_profit_window = mean(item["profit_window_pct"] for item in core_results) if core_results else 0.0
        broad_profit_window = mean(item["profit_window_pct"] for item in broad_results) if broad_results else 0.0
        avg_profit_window = mean(
            [item["profit_window_pct"] for item in core_results + broad_results]
        ) if (core_results or broad_results) else 0.0
        core_level = self._classify_profitability_level(core_success_rate, core_profit_window)
        broad_level = self._classify_profitability_level(broad_success_rate, broad_profit_window)
        score = (
            core_success_rate * 0.36
            + broad_success_rate * 0.24
            + min(core_profit_window, 4.0) / 4.0 * 24.0
            + min(broad_profit_window, 4.0) / 4.0 * 16.0
        )
        if core_level == "strong" and broad_level in {"strong", "medium"}:
            level = "strong"
        elif core_level == "weak" and broad_level == "weak":
            level = "weak"
        else:
            level = "medium"
        return {
            "key": "profitability",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": round(score, 1),
            "core_level": core_level,
            "broad_level": broad_level,
            "core_success_rate": round(core_success_rate, 1),
            "broad_success_rate": round(broad_success_rate, 1),
            "core_profit_window_pct": round(core_profit_window, 2),
            "broad_profit_window_pct": round(broad_profit_window, 2),
            "summary": (
                f"上一交易日 Top10 成功率 {broad_success_rate:.1f}% ，核心 3 票成功率 {core_success_rate:.1f}% ，"
                f"平均利润窗口 {avg_profit_window:.2f}% 。"
            ),
        }

    def _evaluate_market_environment_sample_item(
        self,
        trade_date: str,
        candidate: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._evaluate_strategy_health_portfolio_item(
            trade_date=trade_date,
            portfolio_item={"ts_code": candidate.get("ts_code")},
            candidate=candidate,
        )

    def _build_market_environment_sentiment(
        self,
        candidates: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fetcher = getattr(self.screener_service, "fetcher", None)
        get_market_stats = getattr(fetcher, "get_market_stats", None)
        if callable(get_market_stats):
            try:
                stats = get_market_stats()
            except Exception:
                logger.debug("Failed to load market stats for sentiment gate", exc_info=True)
                stats = None
            if isinstance(stats, dict) and stats:
                up_count = int(_safe_float(stats.get("up_count")))
                down_count = int(_safe_float(stats.get("down_count")))
                flat_count = int(_safe_float(stats.get("flat_count")))
                limit_up_count = int(_safe_float(stats.get("limit_up_count")))
                limit_down_count = int(_safe_float(stats.get("limit_down_count")))
                total_amount = _safe_float(stats.get("total_amount"))
                total_count = max(up_count + down_count + flat_count, 1)
                up_down_ratio = up_count / max(down_count, 1)
                breadth_ratio = up_count / total_count
                score = _clamp_float(
                    52.0
                    + min(limit_up_count, 120) * 0.22
                    - min(limit_down_count, 40) * 0.9
                    + (up_down_ratio - 1.0) * 16.0
                    + (breadth_ratio - 0.5) * 40.0
                    + (5.0 if total_amount >= 12000 else -5.0 if 0 < total_amount < 7000 else 0.0),
                    18.0,
                    88.0,
                )

                if (
                    limit_up_count >= 55
                    and limit_down_count <= 8
                    and up_down_ratio >= 1.25
                    and breadth_ratio >= 0.52
                ):
                    level = "strong"
                elif (
                    limit_up_count <= 20
                    and limit_down_count >= 12
                    and (up_down_ratio <= 0.95 or breadth_ratio <= 0.47)
                ):
                    level = "weak"
                else:
                    level = "medium"

                return {
                    "key": "sentiment",
                    "label": GATE_LEVEL_LABELS[level],
                    "level": level,
                    "score": round(score, 1),
                    "summary": (
                        f"涨停 {limit_up_count} 家、跌停 {limit_down_count} 家，"
                        f"上涨 {up_count} 家 / 下跌 {down_count} 家，成交额 {total_amount:.0f} 亿元。"
                    ),
                }

        candidate_count = len(candidates)
        clear_count = sum(item.get("_buy_point_status") == "clear" for item in candidates)
        ready_count = sum(item.get("suggested_action") == "ready" for item in portfolio)
        avg_risk = mean(_safe_float(item.get("risk_score")) for item in portfolio) if portfolio else 50.0
        if candidate_count >= 8 and clear_count >= 2 and ready_count >= 1 and avg_risk <= 35:
            level = "strong"
            score = 82.0
        elif candidate_count <= 3 or (clear_count == 0 and avg_risk >= 45):
            level = "weak"
            score = 28.0
        else:
            level = "medium"
            score = 60.0
        return {
            "key": "sentiment",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": f"候选池 {candidate_count} 只，买点清晰 {clear_count} 只，默认组合可执行 {ready_count} 只。",
        }

    @staticmethod
    def _build_market_environment_breadth(themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not themes:
            return {
                "key": "theme_breadth",
                "label": GATE_LEVEL_LABELS["weak"],
                "level": "weak",
                "score": 25.0,
                "summary": "当前没有形成可用主线扩散结构。",
            }

        top_theme = themes[0]
        second_theme = themes[1] if len(themes) > 1 else None
        top_score = _safe_float(top_theme.get("score"))
        second_score = _safe_float(second_theme.get("score")) if second_theme else 0.0
        if top_score >= 75 and (second_theme is None or top_score - second_score >= 6):
            level = "strong"
            score = 80.0
        elif top_score >= 60:
            level = "medium"
            score = 60.0
        else:
            level = "weak"
            score = 30.0
        summary = f"{top_theme.get('name', '主线')} 评分 {top_score:.1f}"
        if second_theme:
            summary = f"{summary}，第二主线 {second_theme.get('name', '次主线')} 评分 {second_score:.1f}"
        return {
            "key": "theme_breadth",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": summary,
        }

    def _build_opportunity_quality(
        self,
        *,
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        theme_clarity = self._build_opportunity_theme_clarity(themes)
        portfolio_quality = self._build_opportunity_portfolio_quality(portfolio)
        buy_point_clarity = self._build_opportunity_buy_point_clarity(portfolio)
        role_structure = self._build_opportunity_role_structure(portfolio)
        risk_control = self._build_opportunity_risk_control(portfolio)
        modules = [buy_point_clarity, portfolio_quality, theme_clarity]
        score = (
            buy_point_clarity["score"] * 0.5
            + portfolio_quality["score"] * 0.3
            + theme_clarity["score"] * 0.2
        )
        main_item = next((item for item in portfolio if item.get("slot") == "main"), None)
        secondary_item = next((item for item in portfolio if item.get("slot") == "secondary"), None)
        main_buy_point_clear = self._has_planned_buy_point(main_item)
        secondary_buy_point_clear = (
            self._has_planned_buy_point(secondary_item)
        )
        core_overextended_count = self._count_core_overextended_items(portfolio)
        portfolio_unresolved = len(portfolio) <= 1
        clear_count = int(buy_point_clarity.get("clear_count", 0))
        main_risk_reward_pass = self._opportunity_main_risk_reward_pass(main_item)
        theme_concentration_pass = self._opportunity_theme_concentration_pass(portfolio, themes)
        if not portfolio or not themes:
            matrix_level = "weak"
        elif clear_count >= 3:
            matrix_level = "strong" if main_risk_reward_pass else "upper_mid"
        elif clear_count == 2:
            matrix_level = (
                "strong"
                if main_risk_reward_pass and theme_concentration_pass
                else "upper_mid"
            )
        elif clear_count == 1:
            matrix_level = "mid" if main_risk_reward_pass else "weak"
        else:
            matrix_level = "weak"

        if matrix_level == "strong":
            level = "strong"
        elif matrix_level in {"upper_mid", "mid"}:
            level = "medium"
        else:
            level = "weak"
        return {
            "level": level,
            "label": GATE_LEVEL_LABELS[level],
            "matrix_level": matrix_level,
            "matrix_label": OPPORTUNITY_MATRIX_LEVEL_LABELS[matrix_level],
            "score": round(score, 1),
            "reason": (
                f"默认组合有 {clear_count} 只明日买点计划清晰，"
                f"主仓盈亏比{'过线' if main_risk_reward_pass else '未过线'}，"
                f"主线集中度{'达标' if theme_concentration_pass else '不足'}，"
                f"机会质量判定为{OPPORTUNITY_MATRIX_LEVEL_LABELS[matrix_level]}。"
            ),
            "modules": modules,
            "clear_count": clear_count,
            "clear_buy_point_count": clear_count,
            "main_risk_reward_pass": main_risk_reward_pass,
            "theme_concentration_pass": theme_concentration_pass,
            "main_buy_point_clear": main_buy_point_clear,
            "secondary_buy_point_clear": secondary_buy_point_clear,
            "core_overextended_count": core_overextended_count,
            "portfolio_unresolved": portfolio_unresolved,
        }

    @staticmethod
    def _build_opportunity_theme_clarity(themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not themes:
            return {"key": "theme_clarity", "label": GATE_LEVEL_LABELS["weak"], "level": "weak", "score": 20.0, "summary": "没有清晰主线。"}
        top_theme = themes[0]
        second_theme = themes[1] if len(themes) > 1 else None
        top_score = _safe_float(top_theme.get("score"))
        second_score = _safe_float(second_theme.get("score")) if second_theme else 0.0
        if top_score >= 75 and (second_theme is None or top_score - second_score >= 6):
            level, score = "strong", 82.0
        elif top_score >= 60:
            level, score = "medium", 60.0
        else:
            level, score = "weak", 28.0
        return {
            "key": "theme_clarity",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": f"主线 {top_theme.get('name', '未分类')} 评分 {top_score:.1f}。",
        }

    @staticmethod
    def _build_opportunity_portfolio_quality(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
        ready_count = sum(item.get("suggested_action") == "ready" for item in portfolio)
        planned_count = sum(MomentumSecondaryDecisionService._has_planned_buy_point(item) for item in portfolio)
        slot_count = len(portfolio)
        main_item = next((item for item in portfolio if item.get("slot") == "main"), None)
        main_clear = MomentumSecondaryDecisionService._has_planned_buy_point(main_item)
        if main_clear and planned_count >= 2 and slot_count >= 2:
            level, score = "strong", 82.0
        elif main_clear or planned_count >= 2 or ready_count >= 1:
            level, score = "medium", 60.0
        else:
            level, score = "weak", 30.0
        return {
            "key": "portfolio_quality",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": (
                f"默认组合共 {slot_count} 只，明日买点计划清晰 {planned_count} 只，"
                f"当前已触发/可执行 {ready_count} 只。"
            ),
        }

    @staticmethod
    def _build_opportunity_buy_point_clarity(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
        clear_count = sum(MomentumSecondaryDecisionService._has_planned_buy_point(item) for item in portfolio)
        main_item = next((item for item in portfolio if item.get("slot") == "main"), None)
        main_clear = MomentumSecondaryDecisionService._has_planned_buy_point(main_item)
        if main_clear and clear_count >= 2:
            level, score = "strong", 84.0
        elif clear_count >= 2:
            level, score = "medium", 60.0
        elif main_clear:
            level, score = "medium", 60.0
        else:
            level, score = "weak", 24.0
        return {
            "key": "buy_point_clarity",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "clear_count": clear_count,
            "summary": (
                f"主仓{'已' if main_clear else '未'}具备明日买点计划，"
                f"组合共 {clear_count} 只买点计划清晰。"
            ),
        }

    @staticmethod
    def _has_planned_buy_point(item: Optional[Dict[str, Any]]) -> bool:
        """Whether a T-day candidate has a clear T+1 execution plan, not necessarily triggered yet."""

        if not isinstance(item, dict):
            return False

        status = _safe_str(item.get("buy_point_status"), item.get("_buy_point_status"))
        if status == "clear":
            return True
        if status != "waiting":
            return False
        if item.get("entry_range_low") is None or item.get("entry_range_high") is None:
            return False
        if MomentumSecondaryDecisionService._is_static_overextended_item(item):
            return False
        return _safe_float(item.get("risk_score"), 100.0) <= 45.0

    @staticmethod
    def _opportunity_main_risk_reward_pass(main_item: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(main_item, dict):
            return False
        if main_item.get("entry_range_low") is None or main_item.get("entry_range_high") is None:
            return False
        if MomentumSecondaryDecisionService._is_static_overextended_item(main_item):
            return False
        return _safe_float(main_item.get("risk_score"), 100.0) <= 35.0

    @staticmethod
    def _portfolio_theme_counts(portfolio: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for item in portfolio:
            theme_name = _safe_str(item.get("theme"), item.get("_theme"))
            if theme_name:
                counts[theme_name] += 1
        return counts

    @staticmethod
    def _opportunity_theme_concentration_pass(
        portfolio: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
    ) -> bool:
        if not portfolio:
            return False
        # Opportunity quality should judge whether the portfolio itself is focused.
        # Whether that focus also aligns with the top V1.3 mainline is tracked
        # separately in the structured diagnostics and backtest attribution.
        dominant_theme_count = max(
            MomentumSecondaryDecisionService._portfolio_theme_counts(portfolio).values(),
            default=0,
        )
        return dominant_theme_count >= 2

    @staticmethod
    def _build_opportunity_role_structure(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
        slots = {item.get("slot") for item in portfolio}
        roles = {item.get("role") for item in portfolio}
        if {"main", "secondary"}.issubset(slots) and len(roles) >= 2:
            level, score = "strong", 75.0
        elif "main" in slots:
            level, score = "medium", 58.0
        else:
            level, score = "weak", 28.0
        return {
            "key": "role_structure",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": f"当前组合覆盖 {len(slots)} 个仓位角色。",
        }

    @staticmethod
    def _build_opportunity_risk_control(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not portfolio:
            return {"key": "risk_control", "label": GATE_LEVEL_LABELS["weak"], "level": "weak", "score": 25.0, "summary": "当前没有可评估组合。"}
        avg_risk = mean(_safe_float(item.get("risk_score")) for item in portfolio)
        entry_ready = sum(
            item.get("entry_range_low") is not None and item.get("entry_range_high") is not None
            for item in portfolio
        )
        overextended_count = sum(
            1
            for item in portfolio
            if MomentumSecondaryDecisionService._is_static_overextended_item(item)
        )
        if avg_risk <= 28 and entry_ready >= 2 and overextended_count == 0:
            level, score = "strong", 80.0
        elif avg_risk <= 40 and entry_ready >= 1 and overextended_count <= 1:
            level, score = "medium", 60.0
        else:
            level, score = "weak", 28.0
        return {
            "key": "risk_control",
            "label": GATE_LEVEL_LABELS[level],
            "level": level,
            "score": score,
            "summary": (
                f"组合平均风险分 {avg_risk:.1f}，具备明确区间的个股 {entry_ready} 只，"
                f"明显偏离过大的对象 {overextended_count} 只。"
            ),
        }

    @staticmethod
    def _is_static_overextended_item(item: Dict[str, Any]) -> bool:
        risk_tags = {str(tag) for tag in (item.get("risk_tags") or [])}
        buy_point_status = _safe_str(item.get("buy_point_status"), item.get("_buy_point_status"))
        risk_score = _safe_float(item.get("risk_score"))
        return "high_acceleration" in risk_tags and (
            buy_point_status != "clear" or risk_score >= 35.0
        )

    def _count_core_overextended_items(self, portfolio: List[Dict[str, Any]]) -> int:
        return sum(
            1
            for item in portfolio
            if _safe_str(item.get("slot")) in {"main", "secondary"}
            and self._is_static_overextended_item(item)
        )

    @staticmethod
    def _build_historical_validity(
        strategy_health: Dict[str, Any],
        *,
        attack_permission: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        attack_status = _safe_str((attack_permission or {}).get("status"))
        if attack_status == "open":
            level = "healthy"
            max_action_level = "strong_go"
            recommendation_cap = "full"
        elif attack_status == "recovering":
            level = "general"
            max_action_level = "normal_go"
            recommendation_cap = "full"
        else:
            level = "weak"
            max_action_level = "cautious_go"
            recommendation_cap = "limited"

        return {
            "level": level,
            "label": HISTORICAL_VALIDITY_LABELS[level],
            "score": round(
                _safe_float((attack_permission or {}).get("score"))
                or (
                    _safe_float(strategy_health.get("short_window", {}).get("score"))
                    + _safe_float(strategy_health.get("long_window", {}).get("score"))
                )
                / 2,
                1,
            ),
            "reason": _safe_str((attack_permission or {}).get("reason"), _safe_str(strategy_health.get("reason"))),
            "max_action_level": max_action_level,
            "recommendation_cap": recommendation_cap,
            "attack_permission_status": attack_status or "paused",
            "attack_permission_label": _safe_str((attack_permission or {}).get("label"), "暂停进攻"),
        }

    def _build_action(
        self,
        profile: str,
        *,
        market_environment: Dict[str, Any],
        opportunity_quality: Dict[str, Any],
        historical_validity: Dict[str, Any],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not portfolio:
            gate_context = {
                "market_level": _safe_str(market_environment.get("level"), "weak"),
                "opportunity_matrix_level": _safe_str(opportunity_quality.get("matrix_level"), "weak"),
                "historical_validity_level": _safe_str(historical_validity.get("level"), "weak"),
                "clear_count": 0,
                "main_risk_reward_pass": False,
                "theme_concentration_pass": False,
                "core_premium_level": "",
                "breadth_premium_level": "",
                "base_level": "stand_aside",
                "resolved_level": "stand_aside",
                "promotion_applied": False,
                "promotion_reason": "",
                "restriction_reason": "当前没有默认组合，基础动作矩阵直接收口为今日不做。",
            }
        else:
            matrix = {
                ("strong", "strong"): "strong_go",
                ("strong", "upper_mid"): "normal_go",
                ("strong", "mid"): "cautious_go",
                ("strong", "weak"): "observe_only",
                ("medium", "strong"): "normal_go",
                ("medium", "upper_mid"): "cautious_go",
                ("medium", "mid"): "observe_only",
                ("medium", "weak"): "stand_aside",
                ("weak", "strong"): "cautious_go",
                ("weak", "upper_mid"): "observe_only",
                ("weak", "mid"): "stand_aside",
                ("weak", "weak"): "stand_aside",
            }
            market_level = _safe_str(market_environment.get("level"))
            opportunity_matrix_level = _safe_str(opportunity_quality.get("matrix_level"))
            clear_count = int(_safe_float(opportunity_quality.get("clear_count"), 0))
            main_risk_reward_pass = bool(opportunity_quality.get("main_risk_reward_pass"))
            theme_concentration_pass = bool(opportunity_quality.get("theme_concentration_pass"))
            if not opportunity_matrix_level:
                opportunity_modules = {
                    _safe_str(module.get("key")): module
                    for module in opportunity_quality.get("modules", [])
                    if isinstance(module, dict)
                }
                clear_count = int(
                    _safe_float(
                        opportunity_quality.get("clear_count"),
                        opportunity_modules.get("buy_point_clarity", {}).get("clear_count", 0),
                    )
                )
                main_item = next((item for item in portfolio if item.get("slot") == "main"), None)
                if "main_risk_reward_pass" not in opportunity_quality:
                    main_risk_reward_pass = self._opportunity_main_risk_reward_pass(main_item)
                if "theme_concentration_pass" not in opportunity_quality:
                    theme_counts = self._portfolio_theme_counts(portfolio)
                    theme_concentration_pass = max(theme_counts.values(), default=0) >= 2
                if clear_count >= 3:
                    opportunity_matrix_level = "strong" if main_risk_reward_pass else "upper_mid"
                elif clear_count == 2:
                    opportunity_matrix_level = (
                        "strong"
                        if main_risk_reward_pass and theme_concentration_pass
                        else "upper_mid"
                    )
                elif clear_count == 1:
                    opportunity_matrix_level = "mid" if main_risk_reward_pass else "weak"
                else:
                    opportunity_matrix_level = "weak"
            market_modules = {
                _safe_str(module.get("key")): _safe_str(module.get("level"))
                for module in market_environment.get("modules", [])
                if isinstance(module, dict)
            }
            core_premium_level = market_modules.get("core_premium", "")
            breadth_premium_level = market_modules.get("breadth_premium", "")
            base_level = matrix.get(
                (market_level, opportunity_matrix_level),
                "observe_only",
            )
            promotion_applied = False
            promotion_reason = ""
            if (
                market_level == "medium"
                and opportunity_matrix_level == "mid"
                and base_level == "observe_only"
                and clear_count >= 1
                and main_risk_reward_pass
                and _safe_str(historical_validity.get("level")) in {"healthy", "general"}
                and "strong" in {core_premium_level, breadth_premium_level}
            ):
                base_labels = (
                    GATE_LEVEL_LABELS.get(market_level, market_level),
                    OPPORTUNITY_MATRIX_LEVEL_LABELS.get(
                        opportunity_matrix_level,
                        opportunity_matrix_level,
                    ),
                )
                promotion_applied = True
                promotion_reason = (
                    f"市场环境虽为{base_labels[0]}，但核心溢价/广度溢价至少一项仍强，"
                    f"且主仓盈亏比过线、组合已有 {clear_count} 只计划买点，"
                    "所以把基础矩阵从“仅观察”上调到“谨慎出手”。"
                )
                resolved_level = "cautious_go"
            else:
                resolved_level = base_level
            restriction_reason = ""
            if resolved_level in {"observe_only", "stand_aside"}:
                restriction_reason = (
                    f"市场环境为{GATE_LEVEL_LABELS.get(market_level, market_level)}、"
                    f"机会质量为{OPPORTUNITY_MATRIX_LEVEL_LABELS.get(opportunity_matrix_level, opportunity_matrix_level)}，"
                    f"基础动作矩阵先收口到“{ACTION_LEVEL_LABELS[resolved_level]}”。"
                )
            gate_context = {
                "market_level": market_level,
                "opportunity_matrix_level": opportunity_matrix_level,
                "historical_validity_level": _safe_str(historical_validity.get("level"), "weak"),
                "clear_count": clear_count,
                "main_risk_reward_pass": bool(main_risk_reward_pass),
                "theme_concentration_pass": bool(theme_concentration_pass),
                "core_premium_level": core_premium_level,
                "breadth_premium_level": breadth_premium_level,
                "base_level": base_level,
                "resolved_level": resolved_level,
                "promotion_applied": promotion_applied,
                "promotion_reason": promotion_reason,
                "restriction_reason": restriction_reason,
            }

        reason = self._build_action_reason(
            gate_context["resolved_level"],
            market_environment=market_environment,
            opportunity_quality=opportunity_quality,
            historical_validity=historical_validity,
        )
        if gate_context.get("promotion_applied") and gate_context.get("promotion_reason"):
            reason = f"{reason} {gate_context['promotion_reason']}"
        elif gate_context.get("restriction_reason"):
            reason = f"{reason} {gate_context['restriction_reason']}"
        return {
            "level": gate_context["resolved_level"],
            "label": ACTION_LEVEL_LABELS[gate_context["resolved_level"]],
            "reason": reason,
            "source_profile": profile,
            "base_level": gate_context["base_level"],
            "base_label": ACTION_LEVEL_LABELS[gate_context["base_level"]],
            "gate_context": gate_context,
        }

    def _build_empty_strategy_health(self) -> Dict[str, Any]:
        return {
            "status": "disabled",
            "label": STRATEGY_HEALTH_LABELS["disabled"],
            "reason": "当前没有形成可验证的候选池，20 日进攻许可直接暂停。",
            "recommendation_cap": "disabled",
            "can_full_recommend": False,
            "short_window": self._build_strategy_health_window(
                "short_20d",
                score=0.0,
                threshold=68.0,
                status="weak",
            ),
            "long_window": self._build_strategy_health_window(
                "long_60d",
                score=0.0,
                threshold=64.0,
                status="weak",
            ),
            "blockers": [
                "20 日窗口当前没有形成可用结论。",
                "60 日窗口当前没有形成可信结构。",
            ],
            "recovery_conditions": [
                "先恢复到能稳定给出 1-2 只可跟踪票。",
                "再恢复到主线、角色与默认组合结构都重新稳定。",
            ],
        }

    def _build_strategy_health(
        self,
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not themes or not portfolio:
            return self._build_empty_strategy_health()

        top_theme_score = _safe_float(themes[0].get("score"))
        secondary_theme_score = _safe_float(themes[1].get("score")) if len(themes) > 1 else 0.0
        ready_count = sum(item.get("suggested_action") == "ready" for item in portfolio)
        clear_count = sum(item.get("buy_point_status") == "clear" for item in portfolio)
        avg_risk = mean(_safe_float(item.get("risk_score")) for item in portfolio)
        avg_rank_score = mean(_official_sort_score(item) for item in portfolio)
        candidate_count = len(candidates)
        top_theme_count = int(themes[0].get("candidate_count", 0))
        dominant_share = top_theme_count / max(candidate_count, 1)
        has_leader = any(item.get("_role_key") == "leader" for item in candidates)
        has_front = any(item.get("_role_key") == "front" for item in candidates)

        short_score = _clamp_float(
            top_theme_score * 0.45
            + ready_count * 12.0
            + clear_count * 8.0
            + avg_rank_score * 0.20
            + dominant_share * 10.0
            - avg_risk * 0.30
        )
        long_score = _clamp_float(
            top_theme_score * 0.35
            + secondary_theme_score * 0.10
            + avg_rank_score * 0.25
            + (10.0 if has_leader else 0.0)
            + (8.0 if has_front else 0.0)
            + min(candidate_count, 5) * 3.0
            + dominant_share * 8.0
            - avg_risk * 0.15
        )

        short_status = self._determine_strategy_window_status(short_score, healthy_threshold=68.0, recovering_threshold=58.0)
        long_status = self._determine_strategy_window_status(long_score, healthy_threshold=64.0, recovering_threshold=54.0)

        if short_status == "healthy" and long_status == "healthy":
            status = "healthy"
        elif short_status == "healthy" and long_status != "healthy":
            status = "recovery_mode"
        elif short_status == "weak" and long_status == "weak":
            status = "disabled"
        else:
            status = "partial_healthy"

        blockers: List[str] = []
        recovery_conditions: List[str] = []

        if short_status == "weak":
            blockers.append("20 日窗口当前可用性不足，今天不应继续给出强执行结论。")
            recovery_conditions.append("20 日窗口需要先恢复到最近结果能稳定输出 1-2 只可执行票。")
        elif short_status == "recovering":
            recovery_conditions.append("20 日窗口仍在恢复中，需要继续观察是否能稳定维持当前可用性。")

        if long_status == "weak":
            blockers.append("60 日窗口结构可信度不足，当前更适合观察或少量推荐。")
            recovery_conditions.append("60 日窗口需要恢复到主线、角色与组合结构重新稳定。")
        elif long_status == "recovering":
            recovery_conditions.append("60 日窗口仍在恢复中，需要继续验证主线与组合结构是否稳定。")

        if avg_risk >= 40:
            blockers.append("当前默认组合平均风险分偏高，20 日进攻许可需要至少降一级理解。")

        if status == "healthy":
            reason = "20 日可用性与 60 日结构可信度同时健康，允许维持完整强推荐。"
            recommendation_cap = "full"
        elif status == "recovery_mode":
            reason = "20 日窗口先恢复，但 60 日结构可信度还没完全修复，先降级到观察 / 少量推荐。"
            recommendation_cap = "limited"
        elif status == "partial_healthy":
            reason = "当前只有一侧窗口健康，系统只保留 1-2 只有限推荐或观察。"
            recommendation_cap = "limited"
        else:
            reason = "20 日与 60 日窗口同时失效，系统今天应明确停用并劝退。"
            recommendation_cap = "disabled"

        return {
            "status": status,
            "label": STRATEGY_HEALTH_LABELS[status],
            "reason": reason,
            "recommendation_cap": recommendation_cap,
            "can_full_recommend": recommendation_cap == "full",
            "short_window": self._build_strategy_health_window(
                "short_20d",
                score=short_score,
                threshold=68.0,
                status=short_status,
            ),
            "long_window": self._build_strategy_health_window(
                "long_60d",
                score=long_score,
                threshold=64.0,
                status=long_status,
            ),
            "blockers": blockers[:3],
            "recovery_conditions": recovery_conditions[:4],
        }

    def _build_strategy_health_window(
        self,
        window: str,
        *,
        score: float,
        threshold: float,
        status: str,
    ) -> Dict[str, Any]:
        if status == "healthy":
            summary = f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}已达健康阈值，可继续支撑当前判断。"
        elif status == "recovering":
            summary = f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}开始修复，但还没恢复到完整强推荐状态。"
        else:
            summary = f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}当前不足，今天需要明确降级。"

        return {
            "window": window,
            "window_label": STRATEGY_HEALTH_WINDOW_LABELS[window],
            "status": status,
            "status_label": STRATEGY_HEALTH_WINDOW_STATUS_LABELS[status],
            "score": round(score, 1),
            "threshold": round(threshold, 1),
            "summary": summary,
        }

    @staticmethod
    def _determine_strategy_window_status(
        score: float,
        *,
        healthy_threshold: float,
        recovering_threshold: float,
    ) -> str:
        if score >= healthy_threshold:
            return "healthy"
        if score >= recovering_threshold:
            return "recovering"
        return "weak"

    def _build_empty_strategy_health(self) -> Dict[str, Any]:
        short_metrics = self._empty_strategy_health_metrics("short_20d")
        long_metrics = self._empty_strategy_health_metrics("long_60d")
        return {
            "status": "disabled",
            "label": STRATEGY_HEALTH_LABELS["disabled"],
            "reason": "当前没有足够的历史验证样本，20 日进攻许可暂时暂停。",
            "recommendation_cap": "disabled",
            "can_full_recommend": False,
            "short_window": self._build_strategy_health_window("short_20d", metrics=short_metrics),
            "long_window": self._build_strategy_health_window("long_60d", metrics=long_metrics),
            "blockers": [
                "20 日窗口当前没有形成可验证样本。",
                "60 日窗口当前没有形成可信结构。",
            ],
            "recovery_conditions": [
                "先恢复到最近窗口能稳定输出可评估样本。",
                "再恢复到主线、角色与默认组合重新稳定。",
            ],
        }

    def _build_strategy_health(
        self,
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
        *,
        trade_date: str,
        request_params: Optional[Dict[str, Any]],
        wait_for_strategy_health: bool = False,
        strategy_health_progress_callback: Optional[StrategyHealthProgressCallback] = None,
        strategy_health_mode: str = STRATEGY_HEALTH_MODE_DEFAULT,
    ) -> Dict[str, Any]:
        historical_health, runtime_metadata = self._build_historical_strategy_health(
            trade_date=trade_date,
            request_params=request_params,
            wait_for_strategy_health=wait_for_strategy_health,
            strategy_health_progress_callback=strategy_health_progress_callback,
            strategy_health_mode=strategy_health_mode,
        )
        if historical_health is not None:
            return self._attach_strategy_health_runtime_metadata(
                historical_health,
                data_source="historical",
                is_warming=bool(runtime_metadata.get("is_warming", False)),
                validation_status=_safe_str(runtime_metadata.get("validation_status"), "final"),
                progress=runtime_metadata.get("progress"),
            )
        if (
            strategy_health_mode == STRATEGY_HEALTH_MODE_STRICT_FINAL
            and _safe_str(runtime_metadata.get("validation_status")) == "failed"
        ):
            return self._attach_strategy_health_runtime_metadata(
                self._build_unavailable_strategy_health(
                    reason=self._format_strategy_health_failure_reason(
                        _safe_str(runtime_metadata.get("failure_reason"))
                    )
                ),
                data_source="historical",
                is_warming=False,
                validation_status="failed",
                progress=runtime_metadata.get("progress"),
            )
        if not themes or not portfolio:
            return self._attach_strategy_health_runtime_metadata(
                self._build_empty_strategy_health(),
                data_source="proxy",
                is_warming=False,
                validation_status="proxy",
                progress=runtime_metadata.get("progress"),
            )
        return self._attach_strategy_health_runtime_metadata(
            self._build_proxy_strategy_health(
                candidates,
                themes,
                portfolio,
                is_warming=bool(runtime_metadata.get("is_warming", False)),
            ),
            data_source="proxy",
            is_warming=bool(runtime_metadata.get("is_warming", False)),
            validation_status="proxy",
            progress=runtime_metadata.get("progress"),
        )

    def _build_historical_strategy_health(
        self,
        *,
        trade_date: str,
        request_params: Optional[Dict[str, Any]],
        wait_for_strategy_health: bool = False,
        strategy_health_progress_callback: Optional[StrategyHealthProgressCallback] = None,
        strategy_health_mode: str = STRATEGY_HEALTH_MODE_DEFAULT,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        normalized_trade_date = self._normalize_trade_date(trade_date)
        if not normalized_trade_date or not request_params or self.screener_service is None:
            return None, self._build_strategy_health_runtime_metadata()

        cache_key = self._build_strategy_health_cache_key(normalized_trade_date, request_params)
        state = self._load_strategy_health_state(cache_key)
        health = self._extract_strategy_health_from_state(state)
        runtime_metadata = self._build_strategy_health_runtime_metadata(state)
        if _safe_str((state or {}).get("status")) == "final" and health is not None:
            return health, runtime_metadata
        if strategy_health_mode == STRATEGY_HEALTH_MODE_CACHED_ONLY:
            return health, runtime_metadata

        if wait_for_strategy_health and strategy_health_mode == STRATEGY_HEALTH_MODE_STRICT_FINAL:
            state = self._compute_strategy_health_to_completion(
                cache_key=cache_key,
                trade_date=normalized_trade_date,
                request_params=request_params,
                progress_callback=strategy_health_progress_callback,
            )
            runtime_metadata = self._build_strategy_health_runtime_metadata(state)
            return self._extract_strategy_health_from_state(state), runtime_metadata

        if wait_for_strategy_health:
            if self.strategy_health_async:
                scheduled = self._schedule_strategy_health_compute(
                    cache_key=cache_key,
                    trade_date=normalized_trade_date,
                    request_params=request_params,
                    force_immediate=True,
                )
                if scheduled:
                    state = self._wait_for_strategy_health_state(
                        cache_key,
                        timeout_seconds=STRATEGY_HEALTH_WAIT_TIMEOUT_SECONDS,
                    )
                    runtime_metadata = self._build_strategy_health_runtime_metadata(state)
                    health = self._extract_strategy_health_from_state(state)
                    if health is not None:
                        return health, runtime_metadata
                    return None, runtime_metadata

            state = self._compute_strategy_health_to_completion(
                cache_key=cache_key,
                trade_date=normalized_trade_date,
                request_params=request_params,
                progress_callback=strategy_health_progress_callback,
            )
            runtime_metadata = self._build_strategy_health_runtime_metadata(state)
            return self._extract_strategy_health_from_state(state), runtime_metadata

        if self.strategy_health_async and self._schedule_strategy_health_compute(
            cache_key=cache_key,
            trade_date=normalized_trade_date,
            request_params=request_params,
        ):
            state = self._load_strategy_health_state(cache_key)
            runtime_metadata = self._build_strategy_health_runtime_metadata(state, fallback_is_warming=True)
            health = self._extract_strategy_health_from_state(state)
            return health, runtime_metadata

        state = self._compute_strategy_health_to_completion(
            cache_key=cache_key,
            trade_date=normalized_trade_date,
            request_params=request_params,
            progress_callback=strategy_health_progress_callback,
        )
        runtime_metadata = self._build_strategy_health_runtime_metadata(state)
        return self._extract_strategy_health_from_state(state), runtime_metadata

    def _build_proxy_strategy_health(
        self,
        candidates: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
        *,
        is_warming: bool = False,
    ) -> Dict[str, Any]:
        top_theme_score = _safe_float(themes[0].get("score"))
        secondary_theme_score = _safe_float(themes[1].get("score")) if len(themes) > 1 else 0.0
        ready_count = sum(item.get("suggested_action") == "ready" for item in portfolio)
        clear_count = sum(item.get("buy_point_status") == "clear" for item in portfolio)
        avg_risk = mean(_safe_float(item.get("risk_score")) for item in portfolio)
        avg_rank_score = mean(_official_sort_score(item) for item in portfolio)
        candidate_count = len(candidates)
        top_theme_count = int(themes[0].get("candidate_count", 0))
        dominant_share = top_theme_count / max(candidate_count, 1)
        has_leader = any(item.get("_role_key") == "leader" for item in candidates)
        has_front = any(item.get("_role_key") == "front" for item in candidates)

        short_score = _clamp_float(
            top_theme_score * 0.45
            + ready_count * 12.0
            + clear_count * 8.0
            + avg_rank_score * 0.20
            + dominant_share * 10.0
            - avg_risk * 0.30
        )
        long_score = _clamp_float(
            top_theme_score * 0.35
            + secondary_theme_score * 0.10
            + avg_rank_score * 0.25
            + (10.0 if has_leader else 0.0)
            + (8.0 if has_front else 0.0)
            + min(candidate_count, 5) * 3.0
            + dominant_share * 8.0
            - avg_risk * 0.15
        )

        short_window = self._proxy_strategy_health_metrics(
            "short_20d",
            score=short_score,
            healthy_threshold=68.0,
            recovering_threshold=58.0,
        )
        long_window = self._proxy_strategy_health_metrics(
            "long_60d",
            score=long_score,
            healthy_threshold=64.0,
            recovering_threshold=54.0,
        )
        health = self._compose_strategy_health(short_window, long_window)
        if is_warming:
            health["reason"] = f"{health['reason']} {STRATEGY_HEALTH_WARMING_REASON}"
        return health

    @staticmethod
    def _attach_strategy_health_runtime_metadata(
        health: Dict[str, Any],
        *,
        data_source: str,
        is_warming: bool,
        validation_status: str,
        progress: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        enriched = deepcopy(health)
        enriched["data_source"] = data_source
        enriched["is_warming"] = is_warming
        enriched["validation_status"] = validation_status
        enriched["progress"] = deepcopy(progress) if isinstance(progress, dict) else {
            "status": "proxy" if data_source == "proxy" else validation_status,
            "processed_trade_date_count": 0,
            "total_trade_date_count": 0,
            "valid_sample_count": 0,
            "target_sample_count": STRATEGY_HEALTH_TARGET_SAMPLE_COUNT,
            "progress_pct": 0.0,
            "last_evaluated_trade_date": None,
            "updated_at": None,
        }
        return enriched

    def _build_strategy_health_runtime_metadata(
        self,
        state: Optional[Dict[str, Any]] = None,
        *,
        fallback_is_warming: bool = False,
    ) -> Dict[str, Any]:
        state = deepcopy(state) if isinstance(state, dict) else {}
        status = _safe_str(state.get("status"))
        has_partial = isinstance(state.get("partial_health"), dict)
        if status == "final":
            validation_status = "final"
            is_warming = False
        elif status == "failed":
            validation_status = "failed"
            is_warming = False
        elif has_partial:
            validation_status = "partial"
            is_warming = True
        else:
            validation_status = "proxy"
            is_warming = fallback_is_warming or status in STRATEGY_HEALTH_IN_PROGRESS_STATUSES
        return {
            "validation_status": validation_status,
            "is_warming": is_warming,
            "failure_reason": _safe_str(state.get("last_error")),
            "progress": self._build_strategy_health_progress(state, validation_status=validation_status),
        }

    def _build_strategy_health_progress(
        self,
        state: Optional[Dict[str, Any]] = None,
        *,
        validation_status: str,
    ) -> Dict[str, Any]:
        state = state or {}
        processed_trade_date_count = int(
            state.get("processed_trade_date_count", state.get("next_trade_date_index", 0)) or 0
        )
        total_trade_date_count = int(state.get("total_trade_date_count", 0) or 0)
        valid_sample_count = len(state.get("validations", [])) if isinstance(state.get("validations"), list) else 0
        progress_pct = (
            round(processed_trade_date_count / max(total_trade_date_count, 1) * 100, 1)
            if total_trade_date_count > 0
            else 0.0
        )
        runtime_status = _safe_str(state.get("status")) or validation_status
        if validation_status == "proxy" and runtime_status == "":
            runtime_status = "proxy"
        return {
            "status": runtime_status,
            "processed_trade_date_count": processed_trade_date_count,
            "total_trade_date_count": total_trade_date_count,
            "valid_sample_count": valid_sample_count,
            "target_sample_count": STRATEGY_HEALTH_TARGET_SAMPLE_COUNT,
            "progress_pct": progress_pct,
            "last_evaluated_trade_date": state.get("last_evaluated_trade_date"),
            "updated_at": state.get("updated_at"),
        }

    @staticmethod
    def _extract_strategy_health_from_state(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(state, dict):
            return None
        final_health = state.get("final_health")
        if isinstance(final_health, dict):
            return deepcopy(final_health)
        partial_health = state.get("partial_health")
        if isinstance(partial_health, dict):
            return deepcopy(partial_health)
        return None

    def _summarize_strategy_health_validations(self, validations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not validations:
            return None
        short_window = self._summarize_strategy_health_window(
            "short_20d",
            validations[: STRATEGY_HEALTH_WINDOW_TARGETS["short_20d"]["lookback"]],
        )
        long_window = self._summarize_strategy_health_window(
            "long_60d",
            validations[: STRATEGY_HEALTH_WINDOW_TARGETS["long_60d"]["lookback"]],
        )
        return self._compose_strategy_health(short_window, long_window)

    def _create_strategy_health_state(
        self,
        *,
        trade_date: str,
        request_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "status": "queued",
            "trade_date": trade_date,
            "request_params": deepcopy(request_params),
            "trade_dates": [],
            "total_trade_date_count": 0,
            "next_trade_date_index": 0,
            "processed_trade_date_count": 0,
            "validations": [],
            "partial_health": None,
            "final_health": None,
            "last_evaluated_trade_date": None,
            "last_error": None,
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
        }

    def _compute_strategy_health_to_completion(
        self,
        *,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
        progress_callback: Optional[StrategyHealthProgressCallback] = None,
    ) -> Optional[Dict[str, Any]]:
        state = self._load_strategy_health_state(cache_key)
        while True:
            state = self._advance_strategy_health_state(
                cache_key=cache_key,
                trade_date=trade_date,
                request_params=request_params,
                state=state,
                progress_callback=progress_callback,
            )
            if not isinstance(state, dict):
                return None
            if _safe_str(state.get("status")) in {"final", "failed"}:
                return state
            if int(state.get("processed_trade_date_count", 0)) >= int(state.get("total_trade_date_count", 0)):
                return state

    def _advance_strategy_health_state(
        self,
        *,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[StrategyHealthProgressCallback] = None,
    ) -> Optional[Dict[str, Any]]:
        working_state = deepcopy(state) if isinstance(state, dict) else self._load_strategy_health_state(cache_key)
        if not isinstance(working_state, dict):
            working_state = self._create_strategy_health_state(
                trade_date=trade_date,
                request_params=request_params,
            )

        if _safe_str(working_state.get("status")) == "final":
            return working_state

        trade_dates = working_state.get("trade_dates")
        if not isinstance(trade_dates, list) or not trade_dates:
            trade_dates = self._load_strategy_health_trade_dates(
                end_trade_date=trade_date,
                limit=STRATEGY_HEALTH_TARGET_SAMPLE_COUNT + 12,
            )
            working_state["trade_dates"] = trade_dates
            working_state["total_trade_date_count"] = len(trade_dates)
            if not trade_dates:
                working_state["status"] = "failed"
                working_state["last_error"] = "no_trade_dates"
                working_state["updated_at"] = datetime.now().isoformat()
                self._store_strategy_health_state(cache_key, working_state)
                self._notify_strategy_health_progress(progress_callback, working_state)
                return working_state

        started_at = time_module.monotonic()
        last_progress_notify_at = started_at
        validations = working_state.get("validations")
        if not isinstance(validations, list):
            validations = []
            working_state["validations"] = validations
        working_state["status"] = "running"
        working_state["last_error"] = None
        working_state["updated_at"] = datetime.now().isoformat()
        self._notify_strategy_health_progress(progress_callback, working_state)

        while int(working_state.get("next_trade_date_index", 0)) < len(trade_dates):
            next_index = int(working_state.get("next_trade_date_index", 0))
            historical_trade_date = _safe_str(trade_dates[next_index])
            working_state["next_trade_date_index"] = next_index + 1
            working_state["processed_trade_date_count"] = next_index + 1
            working_state["last_evaluated_trade_date"] = historical_trade_date

            try:
                validation = self._evaluate_strategy_health_trade_date(
                    historical_trade_date=historical_trade_date,
                    request_params=request_params,
                )
            except Exception:
                logger.exception(
                    "Failed to evaluate momentum strategy health sample: trade_date=%s",
                    historical_trade_date,
                )
                validation = None

            if validation is not None:
                validations.append(validation)
                if len(validations) == 1 or len(validations) % 5 == 0:
                    logger.info(
                        "Momentum strategy health progress: trade_date=%s samples=%d last_sample=%s",
                        trade_date,
                        len(validations),
                        historical_trade_date,
                    )
                if len(validations) >= STRATEGY_HEALTH_TARGET_SAMPLE_COUNT:
                    break

            now_monotonic = time_module.monotonic()
            should_notify_progress = False
            if validation is not None and (len(validations) == 1 or len(validations) % 5 == 0):
                should_notify_progress = True
            elif now_monotonic - last_progress_notify_at >= 5.0:
                should_notify_progress = True

            if should_notify_progress:
                working_state["updated_at"] = datetime.now().isoformat()
                self._notify_strategy_health_progress(progress_callback, working_state)
                last_progress_notify_at = now_monotonic

            if len(validations) >= STRATEGY_HEALTH_MIN_PARTIAL_SAMPLE_COUNT:
                elapsed_seconds = time_module.monotonic() - started_at
                if elapsed_seconds >= STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS:
                    logger.info(
                        "Momentum strategy health compute reached slice budget: trade_date=%s samples=%d elapsed=%.1fs",
                        trade_date,
                        len(validations),
                        elapsed_seconds,
                    )
                    break

        summary = self._summarize_strategy_health_validations(validations)
        if summary is not None:
            working_state["partial_health"] = summary

        working_state["updated_at"] = datetime.now().isoformat()
        if len(validations) >= STRATEGY_HEALTH_TARGET_SAMPLE_COUNT or int(working_state.get("next_trade_date_index", 0)) >= len(trade_dates):
            working_state["status"] = "final"
            working_state["final_health"] = deepcopy(working_state.get("partial_health"))
            working_state["completed_at"] = working_state["updated_at"]
        elif summary is not None:
            working_state["status"] = "partial"

        self._store_strategy_health_state(cache_key, working_state)
        self._notify_strategy_health_progress(progress_callback, working_state)
        return deepcopy(working_state)

    def _notify_strategy_health_progress(
        self,
        progress_callback: Optional[StrategyHealthProgressCallback],
        state: Optional[Dict[str, Any]],
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(
                self._build_strategy_health_runtime_metadata(
                    state,
                    fallback_is_warming=True,
                )
            )
        except Exception:
            logger.exception("Failed to emit momentum strategy health progress callback")

    def _schedule_strategy_health_compute(
        self,
        *,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
        force_immediate: bool = False,
    ) -> bool:
        executor = self._strategy_health_executor
        if executor is None:
            return False

        with self._strategy_health_jobs_lock:
            current = self._strategy_health_jobs.get(cache_key)
            if current is not None:
                if isinstance(current, Future):
                    if current.done():
                        self._strategy_health_jobs.pop(cache_key, None)
                    else:
                        return True
                elif isinstance(current, Timer):
                    if force_immediate and current.is_alive():
                        current.cancel()
                        self._strategy_health_jobs.pop(cache_key, None)
                    elif current.is_alive():
                        return True
                    else:
                        self._strategy_health_jobs.pop(cache_key, None)
                else:
                    return True

            delay_seconds = 0.0 if force_immediate else self.strategy_health_async_delay_seconds
            request_payload = dict(request_params)
            if delay_seconds > 0:
                timer = Timer(
                    delay_seconds,
                    self._start_delayed_strategy_health_compute,
                    kwargs={
                        "cache_key": cache_key,
                        "trade_date": trade_date,
                        "request_params": request_payload,
                    },
                )
                timer.daemon = True
                self._strategy_health_jobs[cache_key] = timer
                timer.start()
                return True

            future = executor.submit(
                self._compute_and_cache_strategy_health,
                cache_key,
                trade_date,
                request_payload,
            )
            self._strategy_health_jobs[cache_key] = future
            future.add_done_callback(
                lambda completed, *, key=cache_key: self._clear_strategy_health_job(key, completed)
            )
            return True

    def _has_active_strategy_health_job(self, cache_key: str) -> bool:
        with self._strategy_health_jobs_lock:
            current = self._strategy_health_jobs.get(cache_key)
            if isinstance(current, Future):
                return not current.done()
            if isinstance(current, Timer):
                return current.is_alive()
            return current is not None

    def _wait_for_strategy_health_state(
        self,
        cache_key: str,
        *,
        timeout_seconds: float,
    ) -> Optional[Dict[str, Any]]:
        deadline = time_module.time() + max(0.0, timeout_seconds)
        while time_module.time() <= deadline:
            state = self._load_strategy_health_state(cache_key)
            if isinstance(state, dict):
                if _safe_str(state.get("status")) == "final":
                    return state
                if self._extract_strategy_health_from_state(state) is not None:
                    return state

            if not self._has_active_strategy_health_job(cache_key):
                break

            time_module.sleep(STRATEGY_HEALTH_WAIT_POLL_INTERVAL_SECONDS)
        return self._load_strategy_health_state(cache_key)

    def _start_delayed_strategy_health_compute(
        self,
        *,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
    ) -> None:
        state = self._load_strategy_health_state(cache_key)
        if _safe_str((state or {}).get("status")) == "final":
            self._clear_strategy_health_job(cache_key, None)
            return

        executor = self._strategy_health_executor
        if executor is None:
            self._clear_strategy_health_job(cache_key, None)
            return

        future = executor.submit(
            self._compute_and_cache_strategy_health,
            cache_key,
            trade_date,
            dict(request_params),
        )
        with self._strategy_health_jobs_lock:
            self._strategy_health_jobs[cache_key] = future
        future.add_done_callback(
            lambda completed, *, key=cache_key: self._clear_strategy_health_job(key, completed)
        )

    def _compute_and_cache_strategy_health(
        self,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
    ) -> None:
        try:
            logger.info(
                "Momentum strategy health warm start: cache_key=%s trade_date=%s profile=%s",
                cache_key,
                trade_date,
                request_params.get("profile"),
            )
            state = self._load_strategy_health_state(cache_key)
            while True:
                state = self._advance_strategy_health_state(
                    cache_key=cache_key,
                    trade_date=trade_date,
                    request_params=request_params,
                    state=state,
                )
                if not isinstance(state, dict):
                    break
                status = _safe_str(state.get("status"))
                health = self._extract_strategy_health_from_state(state)
                if health is not None and status in {"partial", "final"}:
                    logger.info(
                        "Momentum strategy health checkpoint saved: cache_key=%s samples=%s processed=%s/%s status=%s",
                        cache_key,
                        len(state.get("validations", [])) if isinstance(state.get("validations"), list) else 0,
                        state.get("processed_trade_date_count"),
                        state.get("total_trade_date_count"),
                        status,
                    )
                if status in {"final", "failed"}:
                    break
        except Exception:
            logger.exception("Failed to warm momentum strategy health cache for %s", cache_key)

    def _clear_strategy_health_job(self, cache_key: str, future: Optional[Any]) -> None:
        with self._strategy_health_jobs_lock:
            current = self._strategy_health_jobs.get(cache_key)
            if future is None or current is future:
                self._strategy_health_jobs.pop(cache_key, None)

    def _empty_strategy_health_metrics(self, window: str) -> Dict[str, Any]:
        return {
            "window": window,
            "status": "weak",
            "score": 0.0,
            "threshold": STRATEGY_HEALTH_WINDOW_THRESHOLDS[window],
            "sample_count": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "avg_profit_window_pct": 0.0,
            "avg_max_drawdown_pct": 0.0,
            "avg_selected_count": 0.0,
            "summary": f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}当前没有形成可用历史样本。",
        }

    def _proxy_strategy_health_metrics(
        self,
        window: str,
        *,
        score: float,
        healthy_threshold: float,
        recovering_threshold: float,
    ) -> Dict[str, Any]:
        if score >= healthy_threshold:
            status = "healthy"
        elif score >= recovering_threshold:
            status = "recovering"
        else:
            status = "weak"

        sample_count = STRATEGY_HEALTH_WINDOW_TARGETS[window]["lookback"]
        success_rate = round(score, 1)
        return {
            "window": window,
            "status": status,
            "score": round(score, 1),
            "threshold": STRATEGY_HEALTH_WINDOW_THRESHOLDS[window],
            "sample_count": sample_count,
            "success_count": int(round(sample_count * success_rate / 100)),
            "success_rate": success_rate,
            "avg_profit_window_pct": round(max(0.5, score / 30), 2),
            "avg_max_drawdown_pct": round(max(1.0, 6 - score / 18), 2),
            "avg_selected_count": 2.0,
            "summary": f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}暂时仍使用代理结果，等待历史样本补齐。",
        }

    def _compose_strategy_health(
        self,
        short_window: Dict[str, Any],
        long_window: Dict[str, Any],
    ) -> Dict[str, Any]:
        short_status = _safe_str(short_window.get("status"))
        long_status = _safe_str(long_window.get("status"))

        if short_status == "healthy" and long_status == "healthy":
            status = "healthy"
            reason = "20 日可用性与 60 日结构可信度同时健康，允许维持完整强推荐。"
            recommendation_cap = "full"
        elif short_status == "healthy" and long_status != "healthy":
            status = "recovery_mode"
            reason = "20 日窗口先恢复，但 60 日结构可信度还没完全修复，先降级到观察 / 少量推荐。"
            recommendation_cap = "limited"
        elif short_status == "weak" and long_status == "weak":
            status = "disabled"
            reason = "20 日与 60 日窗口同时失效，系统今天应明确停用并劝退。"
            recommendation_cap = "disabled"
        else:
            status = "partial_healthy"
            reason = "当前只有一侧窗口健康，系统只保留 1-2 只有限推荐或观察。"
            recommendation_cap = "limited"

        blockers: List[str] = []
        recovery_conditions: List[str] = []

        if short_status == "weak":
            blockers.append(
                self._format_strategy_health_blocker(
                    short_window,
                    "20 日窗口当前可用性不足，今天不应继续给出强执行结论。",
                )
            )
            recovery_conditions.append("20 日窗口需要先恢复到最近结果能稳定输出 1-2 只可执行票。")
        elif short_status == "recovering":
            recovery_conditions.append("20 日窗口仍在恢复中，需要继续观察是否能稳定维持当前可用性。")

        if long_status == "weak":
            blockers.append(
                self._format_strategy_health_blocker(
                    long_window,
                    "60 日窗口结构可信度不足，当前更适合观察或少量推荐。",
                )
            )
            recovery_conditions.append("60 日窗口需要恢复到主线、角色与组合结构重新稳定。")
        elif long_status == "recovering":
            recovery_conditions.append("60 日窗口仍在恢复中，需要继续验证主线与组合结构是否稳定。")

        return {
            "status": status,
            "label": STRATEGY_HEALTH_LABELS[status],
            "reason": reason,
            "recommendation_cap": recommendation_cap,
            "can_full_recommend": recommendation_cap == "full",
            "short_window": self._build_strategy_health_window("short_20d", metrics=short_window),
            "long_window": self._build_strategy_health_window("long_60d", metrics=long_window),
            "blockers": blockers[:3],
            "recovery_conditions": recovery_conditions[:4],
        }

    @staticmethod
    def _format_strategy_health_blocker(window: Dict[str, Any], prefix: str) -> str:
        sample_count = int(window.get("sample_count", 0))
        success_rate = _safe_float(window.get("success_rate"))
        return f"{prefix} 当前样本 {sample_count} 天，成功率 {success_rate:.1f}% 。"

    def _build_strategy_health_window(
        self,
        window: str,
        *,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "window": window,
            "window_label": STRATEGY_HEALTH_WINDOW_LABELS[window],
            "status": metrics["status"],
            "status_label": STRATEGY_HEALTH_WINDOW_STATUS_LABELS[metrics["status"]],
            "score": round(_safe_float(metrics.get("score")), 1),
            "threshold": round(_safe_float(metrics.get("threshold"), STRATEGY_HEALTH_WINDOW_THRESHOLDS[window]), 1),
            "sample_count": int(metrics.get("sample_count", 0)),
            "success_count": int(metrics.get("success_count", 0)),
            "success_rate": round(_safe_float(metrics.get("success_rate")), 1),
            "avg_profit_window_pct": round(_safe_float(metrics.get("avg_profit_window_pct")), 2),
            "avg_max_drawdown_pct": round(_safe_float(metrics.get("avg_max_drawdown_pct")), 2),
            "avg_selected_count": round(_safe_float(metrics.get("avg_selected_count")), 1),
            "summary": _safe_str(metrics.get("summary")),
        }

    def _normalize_trade_date(self, value: Any) -> str:
        text = _safe_str(value).strip()
        if not text:
            return ""
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""

    @staticmethod
    def _build_strategy_health_request_signature(request_params: Dict[str, Any]) -> str:
        normalized = {
            "min_change_pct": round(_safe_float(request_params.get("min_change_pct"), MOMENTUM_DEFAULT_MIN_CHANGE_PCT), 3),
            "min_amount": round(_safe_float(request_params.get("min_amount"), MOMENTUM_DEFAULT_MIN_AMOUNT), 3),
            "min_turnover": round(_safe_float(request_params.get("min_turnover"), MOMENTUM_DEFAULT_MIN_TURNOVER), 3),
            "exclude_st": bool(request_params.get("exclude_st", True)),
            "main_board_only": bool(request_params.get("main_board_only", False)),
            "profile": _safe_str(request_params.get("profile"), "standard"),
        }
        return "|".join(f"{key}={value}" for key, value in normalized.items())

    def _build_strategy_health_cache_key(self, trade_date: str, request_params: Dict[str, Any]) -> str:
        request_signature = self._build_strategy_health_request_signature(request_params)
        return f"trade_date={trade_date}|{request_signature}"

    def _build_strategy_health_sample_cache_key(self, historical_trade_date: str, request_params: Dict[str, Any]) -> str:
        request_signature = self._build_strategy_health_request_signature(request_params)
        return f"historical_trade_date={historical_trade_date}|{request_signature}"

    def _load_cached_strategy_health(self, cache_key: str) -> Optional[Dict[str, Any]]:
        state = self._load_strategy_health_state(cache_key)
        health = self._extract_strategy_health_from_state(state)
        if health is None:
            return None
        runtime_metadata = self._build_strategy_health_runtime_metadata(state)
        return self._attach_strategy_health_runtime_metadata(
            health,
            data_source="historical",
            is_warming=bool(runtime_metadata.get("is_warming", False)),
            validation_status=_safe_str(runtime_metadata.get("validation_status"), "final"),
            progress=runtime_metadata.get("progress"),
        )

    def _store_cached_strategy_health(self, cache_key: str, value: Dict[str, Any]) -> None:
        now = datetime.now().isoformat()
        self._store_strategy_health_state(
            cache_key,
            {
                "status": "final",
                "trade_date": None,
                "request_params": {},
                "trade_dates": [],
                "total_trade_date_count": 0,
                "next_trade_date_index": 0,
                "processed_trade_date_count": 0,
                "validations": [],
                "partial_health": deepcopy(value),
                "final_health": deepcopy(value),
                "last_evaluated_trade_date": None,
                "last_error": None,
                "started_at": now,
                "updated_at": now,
                "completed_at": now,
            },
        )

    @staticmethod
    def _extract_strategy_health_sample_cache_value(cached: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if not isinstance(cached, dict):
            return False, None
        status = _safe_str(cached.get("status"))
        if status == "miss":
            return True, None
        value = cached.get("value")
        if status == "hit" and isinstance(value, dict):
            return True, deepcopy(value)
        return False, None

    def _load_cached_strategy_health_sample(self, cache_key: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        cached = self._strategy_health_sample_cache.get(cache_key)
        if cached is not None:
            if cached["expires_at"] <= datetime.now():
                self._strategy_health_sample_cache.pop(cache_key, None)
            else:
                return self._extract_strategy_health_sample_cache_value(cached.get("value"))

        disk_cached = self._load_disk_cached_strategy_health_sample(cache_key)
        if disk_cached is not None:
            self._strategy_health_sample_cache[cache_key] = {
                "value": deepcopy(disk_cached),
                "expires_at": datetime.now() + STRATEGY_HEALTH_SAMPLE_CACHE_TTL,
            }
            return self._extract_strategy_health_sample_cache_value(disk_cached)
        return False, None

    def _store_cached_strategy_health_sample(self, cache_key: str, value: Optional[Dict[str, Any]]) -> None:
        cache_value = {
            "status": "hit" if isinstance(value, dict) else "miss",
            "value": deepcopy(value) if isinstance(value, dict) else None,
        }
        self._strategy_health_sample_cache[cache_key] = {
            "value": deepcopy(cache_value),
            "expires_at": datetime.now() + STRATEGY_HEALTH_SAMPLE_CACHE_TTL,
        }
        self._store_disk_cached_strategy_health_sample(cache_key, cache_value)

    def _load_strategy_health_state(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self._strategy_health_cache.get(cache_key)
        if cached is not None:
            if cached["expires_at"] <= datetime.now():
                self._strategy_health_cache.pop(cache_key, None)
            else:
                value = cached.get("value")
                if isinstance(value, dict):
                    return deepcopy(value)

        disk_cached = self._load_disk_cached_strategy_health(cache_key)
        if disk_cached is not None:
            self._strategy_health_cache[cache_key] = {
                "value": deepcopy(disk_cached),
                "expires_at": datetime.now() + STRATEGY_HEALTH_CACHE_TTL,
            }
            return disk_cached
        return None

    def _store_strategy_health_state(self, cache_key: str, value: Dict[str, Any]) -> None:
        cache_value = deepcopy(value)
        self._strategy_health_cache[cache_key] = {
            "value": cache_value,
            "expires_at": datetime.now() + STRATEGY_HEALTH_CACHE_TTL,
        }
        self._store_disk_cached_strategy_health(cache_key, cache_value)

    def _strategy_health_cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(f"{STRATEGY_HEALTH_CACHE_VERSION}|{cache_key}".encode("utf-8")).hexdigest()
        return self._strategy_health_cache_dir / f"{digest}.json"

    def _strategy_health_sample_cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(f"{STRATEGY_HEALTH_SAMPLE_CACHE_VERSION}|{cache_key}".encode("utf-8")).hexdigest()
        return self._strategy_health_sample_cache_dir / f"{digest}.json"

    def _load_disk_cached_strategy_health(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cache_path = self._strategy_health_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read momentum strategy health disk cache: %s", cache_path)
            return None

        expires_at = self._parse_strategy_health_cache_timestamp(payload.get("expires_at"))
        if expires_at is None or expires_at <= datetime.now():
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove expired momentum strategy health cache: %s", cache_path)
            return None

        value = payload.get("value")
        if not isinstance(value, dict):
            return None
        return value

    def _store_disk_cached_strategy_health(self, cache_key: str, value: Dict[str, Any]) -> None:
        cache_path = self._strategy_health_cache_path(cache_key)
        payload = {
            "version": STRATEGY_HEALTH_CACHE_VERSION,
            "expires_at": (datetime.now() + STRATEGY_HEALTH_CACHE_TTL).isoformat(),
            "value": value,
        }
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("Failed to write momentum strategy health disk cache: %s", cache_path)

    def _load_disk_cached_strategy_health_sample(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cache_path = self._strategy_health_sample_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read momentum strategy health sample disk cache: %s", cache_path)
            return None

        expires_at = self._parse_strategy_health_cache_timestamp(payload.get("expires_at"))
        if expires_at is None or expires_at <= datetime.now():
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove expired momentum strategy health sample cache: %s", cache_path)
            return None

        value = payload.get("value")
        if not isinstance(value, dict):
            return None
        return value

    def _store_disk_cached_strategy_health_sample(self, cache_key: str, value: Dict[str, Any]) -> None:
        cache_path = self._strategy_health_sample_cache_path(cache_key)
        payload = {
            "version": STRATEGY_HEALTH_SAMPLE_CACHE_VERSION,
            "expires_at": (datetime.now() + STRATEGY_HEALTH_SAMPLE_CACHE_TTL).isoformat(),
            "value": value,
        }
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("Failed to write momentum strategy health sample disk cache: %s", cache_path)

    @staticmethod
    def _parse_strategy_health_cache_timestamp(value: Any) -> Optional[datetime]:
        text = _safe_str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _load_strategy_health_trade_dates(self, *, end_trade_date: str, limit: int) -> List[str]:
        if self.screener_service is None:
            return []

        list_recent_trade_dates = getattr(self.screener_service, "list_recent_trade_dates", None)
        if callable(list_recent_trade_dates):
            dates = list_recent_trade_dates(end_trade_date=end_trade_date, limit=limit)
            normalized_dates: List[str] = []
            for item in dates:
                normalized = self._normalize_trade_date(item)
                if normalized:
                    normalized_dates.append(normalized)
            return normalized_dates

        fetcher = getattr(self.screener_service, "fetcher", None)
        raw_trade_dates = getattr(fetcher, "trade_dates", None)
        if isinstance(raw_trade_dates, list) and raw_trade_dates:
            normalized_dates = []
            for item in raw_trade_dates:
                normalized = self._normalize_trade_date(item)
                if normalized and normalized < end_trade_date:
                    normalized_dates.append(normalized)
            if normalized_dates:
                return sorted(set(normalized_dates), reverse=True)[:limit]

        raw_trade_snapshots = getattr(fetcher, "trade_snapshots", None)
        if isinstance(raw_trade_snapshots, dict) and raw_trade_snapshots:
            normalized_dates = []
            for item in raw_trade_snapshots.keys():
                normalized = self._normalize_trade_date(item)
                if normalized and normalized < end_trade_date:
                    normalized_dates.append(normalized)
            if normalized_dates:
                return sorted(set(normalized_dates), reverse=True)[:limit]

        call_api = getattr(fetcher, "_call_api_with_rate_limit", None)
        if call_api is None:
            return []

        end_dt = datetime.strptime(end_trade_date, "%Y-%m-%d").date()
        start_dt = end_dt - timedelta(days=max(limit * 4, 240))
        df = call_api(
            "trade_cal",
            exchange="SSE",
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
        )
        if df is None or getattr(df, "empty", True) or "cal_date" not in df.columns:
            return []

        trade_dates = sorted(
            (
                datetime.strptime(str(value), "%Y%m%d").strftime("%Y-%m-%d")
                for value in df[df["is_open"] == 1]["cal_date"].astype(str).tolist()
            ),
            reverse=True,
        )
        return [item for item in trade_dates if item < end_trade_date][:limit]

    def _build_unavailable_strategy_health(self, *, reason: str) -> Dict[str, Any]:
        health = self._build_empty_strategy_health()
        health["reason"] = reason
        health["blockers"] = [reason, *health.get("blockers", [])][:3]
        health["recovery_conditions"] = [
            "先补齐该交易日前的历史样本，再重新评估 20/60 窗口。",
            *health.get("recovery_conditions", []),
        ][:4]
        return health

    @staticmethod
    def _format_strategy_health_failure_reason(last_error: str) -> str:
        if last_error == "no_trade_dates":
            return "严格 20/60 历史验证未拿到该交易日前的有效交易日样本，本日不回退代理健康度。"
        if last_error:
            return f"严格 20/60 历史验证失败（{last_error}），本日不回退代理健康度。"
        return "严格 20/60 历史验证失败，本日不回退代理健康度。"

    def _evaluate_strategy_health_trade_date(
        self,
        *,
        historical_trade_date: str,
        request_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if self.screener_service is None:
            return None

        sample_cache_key = self._build_strategy_health_sample_cache_key(historical_trade_date, request_params)
        cache_hit, cached_sample = self._load_cached_strategy_health_sample(sample_cache_key)
        if cache_hit:
            return cached_sample

        def _store_sample_and_return(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            self._store_cached_strategy_health_sample(sample_cache_key, value)
            return value

        strategy_health_top_n = max(
            int(_safe_float(request_params.get("top_n"), STRATEGY_HEALTH_MAX_SCORED_CANDIDATES)),
            STRATEGY_HEALTH_MAX_SCORED_CANDIDATES,
        )
        screening = self.screener_service.screen(
            top_n=strategy_health_top_n,
            min_change_pct=_safe_float(request_params.get("min_change_pct"), MOMENTUM_DEFAULT_MIN_CHANGE_PCT),
            min_amount=_safe_float(request_params.get("min_amount"), MOMENTUM_DEFAULT_MIN_AMOUNT),
            min_turnover=_safe_float(request_params.get("min_turnover"), MOMENTUM_DEFAULT_MIN_TURNOVER),
            exclude_st=bool(request_params.get("exclude_st", True)),
            main_board_only=bool(request_params.get("main_board_only", False)),
            trade_date=historical_trade_date,
            profile=_safe_str(request_params.get("profile"), "standard"),
            use_sector_context=False,
            max_scored_candidates=STRATEGY_HEALTH_MAX_SCORED_CANDIDATES,
        )
        results = self._extract_decision_source_results(screening)
        if not results:
            return _store_sample_and_return(None)

        candidates = [self._build_candidate_view(item) for item in results]
        themes = self._build_theme_summaries(candidates)
        if not themes:
            return _store_sample_and_return(None)
        theme_score_map = {theme["name"]: theme["score"] for theme in themes}
        portfolio = self._build_portfolio(candidates, themes, theme_score_map)
        actionable_items = [item for item in portfolio if item.get("suggested_action") != "observe_only"]
        if not actionable_items:
            return _store_sample_and_return(None)

        candidate_map = {item["ts_code"]: item for item in candidates}
        item_results: List[Dict[str, Any]] = []
        skipped_item_count = 0
        for item in actionable_items:
            try:
                evaluated = self._evaluate_strategy_health_portfolio_item(
                    trade_date=historical_trade_date,
                    portfolio_item=item,
                    candidate=candidate_map.get(item["ts_code"]),
                )
            except Exception as exc:  # noqa: BLE001
                skipped_item_count += 1
                logger.warning(
                    "跳过历史健康度单股验证失败样本: trade_date=%s ts_code=%s error=%s",
                    historical_trade_date,
                    _safe_str(item.get("ts_code")),
                    exc,
                )
                continue
            if evaluated is not None:
                item_results.append(evaluated)
            else:
                skipped_item_count += 1

        if not item_results:
            return _store_sample_and_return(None)

        success_count = sum(1 for item in item_results if item["success"])
        required_success_count = max(1, ceil(len(item_results) * 2 / 3))
        avg_profit_window_pct = mean(item["profit_window_pct"] for item in item_results)
        avg_max_drawdown_pct = mean(item["max_drawdown_pct"] for item in item_results)
        combo_success = (
            success_count >= required_success_count
            and avg_profit_window_pct >= 2.0
            and avg_max_drawdown_pct <= 3.0
        )
        return _store_sample_and_return(
            {
                "trade_date": historical_trade_date,
                "selected_count": len(item_results),
                "success_count": success_count,
                "required_success_count": required_success_count,
                "success": combo_success,
                "profit_window_pct": avg_profit_window_pct,
                "max_drawdown_pct": avg_max_drawdown_pct,
                "skipped_item_count": skipped_item_count,
            }
        )

    def _evaluate_strategy_health_portfolio_item(
        self,
        *,
        trade_date: str,
        portfolio_item: Dict[str, Any],
        candidate: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        analysis_date: date = datetime.strptime(trade_date, "%Y-%m-%d").date()
        stock_code = _safe_str(portfolio_item.get("ts_code"))
        start_daily = self.stock_repo.get_start_daily(code=stock_code, analysis_date=analysis_date)
        forward_bars = self.stock_repo.get_forward_bars(
            code=stock_code,
            analysis_date=analysis_date,
            eval_window_days=2,
        )
        start_price = _safe_float(getattr(start_daily, "close", None))
        highs = [_safe_float(getattr(bar, "high", None)) for bar in forward_bars if _safe_float(getattr(bar, "high", None)) > 0]
        lows = [_safe_float(getattr(bar, "low", None)) for bar in forward_bars if _safe_float(getattr(bar, "low", None)) > 0]
        if start_price <= 0 or len(forward_bars) < 2 or not highs or not lows:
            fallback_prices = self._load_strategy_health_forward_prices_from_fetcher(
                stock_code=stock_code,
                analysis_date=analysis_date,
            )
            if fallback_prices is None:
                return None
            start_price, highs, lows = fallback_prices

        role_key = candidate.get("_role_key") if candidate else "mid"
        target = ROLE_VALIDATION_TARGETS.get(role_key or "mid", ROLE_VALIDATION_TARGETS["mid"])
        profit_window_pct = (max(highs) - start_price) / start_price * 100
        max_drawdown_pct = max(0.0, (start_price - min(lows)) / start_price * 100)
        success = (
            profit_window_pct >= target["profit_window_pct"]
            and max_drawdown_pct <= target["max_drawdown_pct"]
        )
        return {
            "ts_code": stock_code,
            "success": success,
            "profit_window_pct": profit_window_pct,
            "max_drawdown_pct": max_drawdown_pct,
        }

    def _load_strategy_health_forward_prices_from_fetcher(
        self,
        *,
        stock_code: str,
        analysis_date: date,
    ) -> Optional[Tuple[float, List[float], List[float]]]:
        if self.screener_service is None:
            return None

        fetcher = getattr(self.screener_service, "fetcher", None)
        get_daily_data = getattr(fetcher, "get_daily_data", None)
        if not callable(get_daily_data):
            return None

        start_date = analysis_date.strftime("%Y-%m-%d")
        end_date = (analysis_date + timedelta(days=6)).strftime("%Y-%m-%d")
        try:
            history = get_daily_data(stock_code, start_date=start_date, end_date=end_date, days=6)
            if history is None or getattr(history, "empty", True):
                return None

            working = history.copy()
            date_column = "date" if "date" in working.columns else "trade_date" if "trade_date" in working.columns else None
            if date_column is None:
                return None

            working[date_column] = pd.to_datetime(working[date_column])
            working = working.sort_values(date_column).reset_index(drop=True)
            working["_analysis_date"] = working[date_column].dt.date
            current_rows = working[working["_analysis_date"] == analysis_date]
            if current_rows.empty:
                return None

            start_index = int(current_rows.index[0])
            window = working.iloc[start_index : start_index + 3].copy()
            if len(window) < 3:
                return None

            start_price = _safe_float(window.iloc[0].get("close"))
            highs = [_safe_float(value) for value in window.iloc[1:]["high"].tolist() if _safe_float(value) > 0]
            lows = [_safe_float(value) for value in window.iloc[1:]["low"].tolist() if _safe_float(value) > 0]
            if start_price <= 0 or len(highs) < 2 or len(lows) < 2:
                return None
            return start_price, highs, lows
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "跳过 fetcher forward 数据失败的历史健康度单股样本: stock_code=%s analysis_date=%s error=%s",
                stock_code,
                analysis_date.isoformat(),
                exc,
            )
            return None

    def _summarize_strategy_health_window(
        self,
        window: str,
        validations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not validations:
            return self._empty_strategy_health_metrics(window)

        sample_count = len(validations)
        success_count = sum(1 for item in validations if item["success"])
        success_rate = success_count / sample_count * 100
        avg_profit_window_pct = mean(item["profit_window_pct"] for item in validations)
        avg_max_drawdown_pct = mean(item["max_drawdown_pct"] for item in validations)
        avg_selected_count = mean(item["selected_count"] for item in validations)
        status = self._determine_strategy_window_status(
            window=window,
            sample_count=sample_count,
            success_rate=success_rate,
            avg_profit_window_pct=avg_profit_window_pct,
            avg_max_drawdown_pct=avg_max_drawdown_pct,
        )
        score = self._score_strategy_window(
            window=window,
            sample_count=sample_count,
            success_rate=success_rate,
            avg_profit_window_pct=avg_profit_window_pct,
            avg_max_drawdown_pct=avg_max_drawdown_pct,
        )
        return {
            "window": window,
            "status": status,
            "score": score,
            "threshold": STRATEGY_HEALTH_WINDOW_THRESHOLDS[window],
            "sample_count": sample_count,
            "success_count": success_count,
            "success_rate": success_rate,
            "avg_profit_window_pct": avg_profit_window_pct,
            "avg_max_drawdown_pct": avg_max_drawdown_pct,
            "avg_selected_count": avg_selected_count,
            "summary": self._build_strategy_window_summary(
                window=window,
                status=status,
                sample_count=sample_count,
                success_rate=success_rate,
                avg_profit_window_pct=avg_profit_window_pct,
                avg_max_drawdown_pct=avg_max_drawdown_pct,
            ),
        }

    def _score_strategy_window(
        self,
        *,
        window: str,
        sample_count: int,
        success_rate: float,
        avg_profit_window_pct: float,
        avg_max_drawdown_pct: float,
    ) -> float:
        lookback = STRATEGY_HEALTH_WINDOW_TARGETS[window]["lookback"]
        sample_ratio = min(sample_count / max(lookback, 1), 1.0)
        profit_component = min(avg_profit_window_pct / 2.0, 1.0) * 20.0
        drawdown_component = max(0.0, 1.0 - avg_max_drawdown_pct / 5.0) * 10.0
        score = success_rate * 0.65 + profit_component + drawdown_component + sample_ratio * 5.0
        return round(_clamp_float(score), 1)

    def _build_strategy_window_summary(
        self,
        *,
        window: str,
        status: str,
        sample_count: int,
        success_rate: float,
        avg_profit_window_pct: float,
        avg_max_drawdown_pct: float,
    ) -> str:
        if status == "healthy":
            suffix = "已达健康阈值，可继续支撑当前判断。"
        elif status == "recovering":
            suffix = "开始修复，但还没恢复到完整强推荐状态。"
        else:
            suffix = "当前不足，今天需要明确降级。"
        return (
            f"{STRATEGY_HEALTH_WINDOW_LABELS[window]}近 {sample_count} 个样本成功率 {success_rate:.1f}% ，"
            f"平均利润窗口 {avg_profit_window_pct:.2f}% ，平均回撤 {avg_max_drawdown_pct:.2f}% ，{suffix}"
        )

    def _determine_strategy_window_status(
        self,
        *,
        window: str,
        sample_count: int,
        success_rate: float,
        avg_profit_window_pct: float,
        avg_max_drawdown_pct: float,
    ) -> str:
        targets = STRATEGY_HEALTH_WINDOW_TARGETS[window]
        if (
            sample_count >= targets["min_samples_healthy"]
            and success_rate >= targets["healthy_success_rate"]
            and avg_profit_window_pct >= targets["healthy_profit_window_pct"]
            and avg_max_drawdown_pct <= targets["healthy_drawdown_pct"]
        ):
            return "healthy"
        if (
            sample_count >= targets["min_samples_recovering"]
            and success_rate >= targets["recovering_success_rate"]
            and avg_profit_window_pct >= targets["recovering_profit_window_pct"]
            and avg_max_drawdown_pct <= targets["recovering_drawdown_pct"]
        ):
            return "recovering"
        return "weak"

    def _apply_historical_validity_to_action(
        self,
        action: Dict[str, Any],
        historical_validity: Dict[str, Any],
        *,
        market_environment: Dict[str, Any],
        opportunity_quality: Dict[str, Any],
    ) -> Dict[str, Any]:
        level = _safe_str(action.get("level"), "stand_aside")
        attack_permission_status = _safe_str(historical_validity.get("attack_permission_status"), "paused")
        market_level = _safe_str(market_environment.get("level"))
        opportunity_matrix_level = _safe_str(
            opportunity_quality.get("matrix_level"),
            "strong" if _safe_str(opportunity_quality.get("level")) == "strong" else "weak",
        )
        if attack_permission_status == "open":
            capped_level = level
        elif attack_permission_status == "recovering":
            capped_level = self._limit_action_level(level, "normal_go")
        elif market_level == "strong" and opportunity_matrix_level == "strong":
            capped_level = self._limit_action_level(level, "cautious_go")
        elif market_level == "strong" or opportunity_matrix_level == "strong":
            capped_level = self._limit_action_level(level, "observe_only")
        else:
            capped_level = self._limit_action_level(level, "stand_aside")
        reason = _safe_str(action.get("reason"))
        if capped_level != level:
            reason = (
                f"{reason} 当前 20 日进攻许可为“{_safe_str(historical_validity.get('attack_permission_label'), '暂停进攻')}”，"
                f"所以今日最高只放到“{ACTION_LEVEL_LABELS[capped_level]}”。"
            )
        gate_context = action.get("gate_context") if isinstance(action.get("gate_context"), dict) else {}
        gate_context = dict(gate_context)
        gate_context["historical_cap_applied"] = capped_level != level
        gate_context["final_level"] = capped_level
        gate_context["historical_cap_reason"] = (
            _safe_str(historical_validity.get("reason"))
            if capped_level != level
            else ""
        )
        return {
            "level": capped_level,
            "label": ACTION_LEVEL_LABELS[capped_level],
            "reason": reason,
            "source_profile": _safe_str(action.get("source_profile"), "standard"),
            "base_level": _safe_str(action.get("base_level"), level),
            "base_label": _safe_str(action.get("base_label"), ACTION_LEVEL_LABELS.get(level, level)),
            "gate_context": gate_context,
        }

    def _apply_action_permissions_to_portfolio(
        self,
        portfolio: List[Dict[str, Any]],
        action: Dict[str, Any],
        historical_validity: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not portfolio:
            return []

        action_level = _safe_str(action.get("level"))
        historical_label = _safe_str(historical_validity.get("attack_permission_label"), "恢复中")
        adjusted: List[Dict[str, Any]] = []

        for item in portfolio:
            updated = dict(item)
            slot = _safe_str(updated.get("slot"))
            note = ""

            if action_level == "stand_aside":
                updated["suggested_action"] = "observe_only"
                updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS["observe_only"]
                note = "当前总闸门为“今日不做”，页面只保留观察顺序，不建议执行买入。"
            elif action_level == "observe_only":
                updated["suggested_action"] = "observe_only"
                updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS["observe_only"]
                note = "当前总闸门仅允许观察，先保留跟踪，不输出执行级建议。"
            elif action_level == "cautious_go":
                if slot == "main":
                    updated["suggested_action"] = (
                        "ready" if updated.get("buy_point_status") == "clear" else "wait_for_trigger"
                    )
                    updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS[updated["suggested_action"]]
                    note = f"当前 20 日进攻许可为“{historical_label}”，谨慎出手阶段只允许主仓进入正式执行判断。"
                else:
                    updated["suggested_action"] = "observe_only"
                    updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS["observe_only"]
                    note = "谨慎出手阶段，次仓和观察仓只保留观察价值，不作为正式执行对象。"

            if note:
                execution_plan = _safe_str(updated.get("execution_plan"))
                if note not in execution_plan:
                    updated["execution_plan"] = f"{execution_plan} {note}".strip()

            adjusted.append(updated)

        return adjusted

    @staticmethod
    def _limit_action_level(level: str, cap_level: str) -> str:
        try:
            level_index = ACTION_LEVEL_SEQUENCE.index(level)
            cap_index = ACTION_LEVEL_SEQUENCE.index(cap_level)
        except ValueError:
            return level
        return ACTION_LEVEL_SEQUENCE[max(level_index, cap_index)]

    def _build_evidence(
        self,
        profile: str,
        action: Dict[str, Any],
        strategy_health: Dict[str, Any],
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
        excluded: List[Dict[str, Any]],
        *,
        market_environment: Dict[str, Any],
        opportunity_quality: Dict[str, Any],
        historical_validity: Dict[str, Any],
    ) -> Dict[str, Any]:
        theme_validation = [
            f"{theme['name']} 主线评分 {theme['score']:.1f}，{theme['summary']}"
            for theme in themes
        ]
        if not theme_validation:
            theme_validation = ["当前还没有形成足够清晰的主线结构。"]

        today_reasoning = [
            f"本次官方结论来自 {profile} 候选引擎收口后的二次决策，不直接沿用页面 TopN 排名。",
            f"市场环境当前为“{_safe_str(market_environment.get('label'), '中')}”，{_safe_str(market_environment.get('reason'))}",
            f"当日机会质量为“{_safe_str(opportunity_quality.get('label'), '中')}”，{_safe_str(opportunity_quality.get('reason'))}",
            f"20 日进攻许可为“{_safe_str(historical_validity.get('attack_permission_label'), historical_validity.get('label'))}”，{_safe_str(historical_validity.get('reason'), strategy_health.get('reason'))}",
            _safe_str(action.get("reason")),
        ]
        if portfolio:
            today_reasoning.append("默认组合按主仓 / 次仓 / 观察仓固定顺序输出，不会为了凑满三只强行补票。")
        if excluded:
            today_reasoning.append(f"其余候选股已补充主淘汰原因，当前共标记 {len(excluded)} 只落选对象。")

        return {
            "theme_validation": theme_validation,
            "today_reasoning": today_reasoning,
        }

    def _build_action_checklist(
        self,
        action: Dict[str, Any],
        portfolio: List[Dict[str, Any]],
        historical_validity: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not portfolio:
            return {
                "enabled": False,
                "mode": "disabled",
                "reason": "当前没有形成可执行的默认组合，因此不生成明日行动清单。",
                "steps": [],
            }

        action_level = _safe_str(action.get("level"))
        action_label = _safe_str(action.get("label"), "仅观察")
        if action_level not in ACTION_CHECKLIST_ENABLED_LEVELS:
            return {
                "enabled": False,
                "mode": "disabled",
                "reason": f"当前出手级别为“{action_label}”，页面保留组合与观察信息，但不生成行动清单。",
                "steps": [],
            }

        mode = "simplified" if action_level == "cautious_go" else "full"
        all_focus = self._build_portfolio_focus_items(portfolio)
        core_focus = self._build_portfolio_focus_items(portfolio, slots={"main", "secondary"})
        main_focus = self._build_portfolio_focus_items(portfolio, slots={"main"})
        main_item = next((item for item in portfolio if item.get("slot") == "main"), None)
        secondary_item = next((item for item in portfolio if item.get("slot") == "secondary"), None)

        if mode == "full":
            steps = [
                {
                    "phase": "pre_open",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["pre_open"],
                    "objective": "先确认明天最该盯的 1-3 只对象，以及谁是主仓、谁只是确认票。",
                    "focus_items": all_focus,
                    "tasks": [
                        "开盘前先对照主仓、次仓的预期开盘强弱，优先判断谁最接近昨晚定义的执行结构。",
                        "观察仓只承担主线确认作用，不因为短时冲高就临时改顺序。",
                        "如果核心票普遍高开过度或明显弱于预期，优先准备今天不做。",
                    ],
                    "expected_outcome": "明确开盘后先盯主仓，再看次仓，观察仓只做辅助确认。",
                },
                {
                    "phase": "first_30m",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_30m"],
                    "objective": "先排除不达预期的票，只留下仍值得继续跟踪的核心对象。",
                    "focus_items": core_focus or all_focus,
                    "tasks": [
                        "优先排除承接差、明显走弱或已经偏离买点区间过大的票。",
                        "重点确认主仓和次仓谁更接近昨晚定义的触发条件。",
                        "如果只有观察仓活跃，也只保留观察，不替代昨晚固定顺序。",
                    ],
                    "expected_outcome": "快速筛掉掉队对象，保留 1-2 只真正还值得跟踪的核心票。",
                },
                {
                    "phase": "first_60m",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_60m"],
                    "objective": "到 60 分钟内必须收口成今天最终买不买的明确结论。",
                    "focus_items": all_focus,
                    "tasks": [
                        "只有主仓或次仓触发买点时，才按固定顺序输出信号：先主仓，再次仓，其余继续观察。",
                        "如果核心票都未触发，或已明显偏离过大，就明确保留观察但不建议执行。",
                        "把结论收成一句话，并说明今天优先关注谁、次选谁、其余继续观察。",
                    ],
                    "expected_outcome": "输出今天最终是否建议买入，并保留昨晚固定顺序。",
                },
            ]
            reason = f"当前出手级别为“{action_label}”，系统会生成完整版行动清单，帮助你在次日 60 分钟内完成收口。"
        else:
            secondary_name = _safe_str(secondary_item.get("name")) if secondary_item else "次仓"
            main_name = _safe_str(main_item.get("name")) if main_item else "主仓"
            steps = [
                {
                    "phase": "pre_open",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["pre_open"],
                    "objective": "今天只优先盯主仓，次仓和观察仓默认不主动升级成执行对象。",
                    "focus_items": main_focus or all_focus,
                    "tasks": [
                        f"开盘前先确认 {main_name} 是否仍然是最清晰的执行对象。",
                        f"{secondary_name} 只作为备看对象，不主动抢主仓位置。",
                    ],
                    "expected_outcome": "开盘后只重点跟踪主仓，其他对象默认先观察。",
                },
                {
                    "phase": "first_30m",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_30m"],
                    "objective": "如果主仓走坏，今天就应优先转入观察而不是继续扩大战线。",
                    "focus_items": main_focus or all_focus,
                    "tasks": [
                        "如果主仓承接差、明显不及预期或快速偏离买点区间，今天就优先降级为观察。",
                        "谨慎出手阶段不鼓励多票并行执行。",
                    ],
                    "expected_outcome": "只保留主仓是否继续跟踪这一个核心判断。",
                },
                {
                    "phase": "first_60m",
                    "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_60m"],
                    "objective": "到 60 分钟内只收口成“仅主仓可考虑”或“今天不建议买”。",
                    "focus_items": main_focus or all_focus,
                    "tasks": [
                        "只有主仓触发明确买点时，才允许继续考虑执行。",
                        "如果主仓未触发或位置明显不合理，今天直接收口为不建议买。",
                    ],
                    "expected_outcome": "给出“仅主仓可考虑”或“今天不建议买”的最终结论。",
                },
            ]
            reason = (
                f"当前出手级别为“{action_label}”，20 日进攻许可为“{_safe_str(historical_validity.get('attack_permission_label'), '恢复中')}”，"
                "系统只生成简化版行动清单，重点防止多票并行和盘中乱买。"
            )

        return {
            "enabled": True,
            "mode": mode,
            "reason": reason,
            "steps": steps,
        }

    @staticmethod
    def _build_portfolio_focus_items(
        portfolio: List[Dict[str, Any]],
        *,
        slots: Optional[set[str]] = None,
    ) -> List[str]:
        focus_items: List[str] = []
        for item in portfolio:
            if slots is not None and item.get("slot") not in slots:
                continue
            focus_items.append(f"{item['slot_label']}：{item['name']}（{item['theme']} / {item['role']}）")
        return focus_items

    def _classify_buy_point(self, item: Dict[str, Any], role_key: str) -> Tuple[str, str]:
        buyability = item.get("buyability_score")
        rank_score = _official_sort_score(item)
        continuation_score = _safe_float(item.get("continuation_score"))
        risk_score = _safe_float(item.get("risk_score"))
        severe_t1_risk = self._has_severe_t1_direction_risk(item, buy_point_status="clear")
        has_entry_range = (
            item.get("entry_range_low") is not None
            and item.get("entry_range_high") is not None
        )

        if buyability is not None:
            buyability_score = _safe_float(buyability)
            if (
                buyability_score >= 72
                and risk_score <= 35
                and has_entry_range
                and continuation_score >= 74
                and not severe_t1_risk
            ):
                return self._adjust_buy_point_by_sealing_signal("clear", item)
            if buyability_score >= 60 and rank_score >= 65 and risk_score <= 55:
                return self._adjust_buy_point_by_sealing_signal("waiting", item)
            return self._adjust_buy_point_by_sealing_signal("unclear", item)

        if (
            role_key == "leader"
            and continuation_score >= 82
            and rank_score >= 70
            and risk_score <= 40
            and has_entry_range
            and not severe_t1_risk
        ):
            return self._adjust_buy_point_by_sealing_signal("clear", item)
        if continuation_score >= 72 and rank_score >= 60 and risk_score <= 55:
            return self._adjust_buy_point_by_sealing_signal("waiting", item)
        return self._adjust_buy_point_by_sealing_signal("unclear", item)

    @staticmethod
    def _adjust_buy_point_by_sealing_signal(status: str, item: Dict[str, Any]) -> Tuple[str, str]:
        signal = item.get("_v13_sealing_strength_signal")
        if not isinstance(signal, dict) or not signal.get("available"):
            return status, BUY_POINT_LABELS[status]
        if status == "clear" and signal.get("downgrade_buy_point"):
            return "waiting", BUY_POINT_LABELS["waiting"]
        if (
            status == "waiting"
            and _safe_str(signal.get("execution_bias")) == "caution"
            and _safe_str(signal.get("level")) == "weak"
        ):
            return "unclear", BUY_POINT_LABELS["unclear"]
        return status, BUY_POINT_LABELS[status]

    @staticmethod
    def _extension_signal_score(item: Dict[str, Any]) -> float:
        """Convert raw extension into a continuation-friendly signal.

        Extremely high extension often means the next day's upside has already
        been partially consumed, so this is intentionally not monotonic.
        """

        extension_score = _safe_float(item.get("extension_score"))
        if extension_score <= 0:
            return 0.0
        if extension_score < 70:
            return extension_score
        if extension_score <= 88:
            return min(92.0, extension_score + 4.0)
        if extension_score <= 94:
            return 92.0 - (extension_score - 88.0) * 0.8
        return max(70.0, 87.0 - (extension_score - 94.0) * 3.0)

    @staticmethod
    def _t1_direction_risk_adjustment(item: Dict[str, Any], buy_point_status: str) -> float:
        """T-day visible penalty for weak T+1 open-to-close direction odds."""

        risk_tags = {str(tag) for tag in item.get("risk_tags", []) if tag}
        risk_score = _safe_float(item.get("risk_score"))
        pct_chg = _safe_float(item.get("pct_chg"))
        rank_score = _official_sort_score(item)
        continuation_score = _safe_float(item.get("continuation_score"))
        extension_score = _safe_float(item.get("extension_score"))
        adjustment = 0.0

        tag_penalties = {
            "late_session_weakness": 4.0,
            "price_flow_divergence": 4.0,
            "upper_shadow": 3.5,
            "blowoff_volume": 3.0,
            "high_acceleration": 2.0,
            "top_list_distribution": 2.0,
            "sector_fade": 2.0,
        }
        adjustment -= sum(penalty for tag, penalty in tag_penalties.items() if tag in risk_tags)

        if risk_score >= 70:
            adjustment -= 4.0
        elif risk_score >= 55:
            adjustment -= 2.0

        if pct_chg >= 9.7 and (extension_score > 94 or "high_acceleration" in risk_tags):
            adjustment -= 2.0
        elif extension_score >= 98:
            adjustment -= 5.0
        elif extension_score >= 95:
            adjustment -= 3.0
        elif extension_score >= 92 and risk_score >= 10 and buy_point_status == "clear":
            adjustment -= 1.0

        if continuation_score >= 92 and extension_score >= 95:
            adjustment -= 4.0
        elif continuation_score >= 92 and extension_score >= 92:
            adjustment -= 2.0
        elif continuation_score >= 88 and extension_score >= 95:
            adjustment -= 2.0

        if rank_score >= 82 and extension_score >= 95:
            adjustment -= 3.0

        if buy_point_status == "unclear":
            adjustment -= 2.0

        return round(_clamp_float(adjustment, -12.0, 0.0), 2)

    @staticmethod
    def _has_severe_t1_direction_risk(
        item: Dict[str, Any],
        *,
        buy_point_status: str = "",
    ) -> bool:
        risk_tags = {str(tag) for tag in item.get("risk_tags", []) if tag}
        severe_tags = {
            "late_session_weakness",
            "price_flow_divergence",
            "upper_shadow",
            "blowoff_volume",
        }
        extension_score = _safe_float(item.get("extension_score"))
        pct_chg = _safe_float(item.get("pct_chg"))
        risk_score = _safe_float(item.get("risk_score"))
        precomputed_adjustment = _safe_float(item.get("_t1_direction_risk_adjustment"))

        if precomputed_adjustment <= -6.0:
            return True
        if severe_tags & risk_tags:
            return True
        if extension_score >= 95.0:
            return True
        if pct_chg >= 9.7 and extension_score >= 92.0 and (
            "high_acceleration" in risk_tags or risk_score >= 32.0
        ):
            return True
        if buy_point_status == "clear" and extension_score >= 92.0 and risk_score >= 35.0:
            return True
        return False

    def _has_material_t1_stability_edge(
        self,
        candidate: Dict[str, Any],
        reference: Dict[str, Any],
        *,
        min_gap: float = 2.5,
    ) -> bool:
        candidate_buy_point_status = _safe_str(
            candidate.get("_buy_point_status"),
            candidate.get("buy_point_status"),
        )
        reference_buy_point_status = _safe_str(
            reference.get("_buy_point_status"),
            reference.get("buy_point_status"),
        )
        candidate_adjustment = _safe_float(candidate.get("_t1_direction_risk_adjustment"))
        reference_adjustment = _safe_float(reference.get("_t1_direction_risk_adjustment"))
        candidate_severe = self._has_severe_t1_direction_risk(
            candidate,
            buy_point_status=candidate_buy_point_status,
        )
        reference_severe = self._has_severe_t1_direction_risk(
            reference,
            buy_point_status=reference_buy_point_status,
        )

        if candidate_severe:
            return False
        if reference_severe and self._has_planned_buy_point(candidate):
            return candidate_adjustment >= reference_adjustment + 1.5
        return self._has_planned_buy_point(candidate) and candidate_adjustment >= reference_adjustment + min_gap

    @staticmethod
    def _has_v13_mainline_confirmation(item: Dict[str, Any]) -> bool:
        mainline_count = MomentumSecondaryDecisionService._first_available_int(
            item,
            (
                "_theme_pool_count",
                "_v13_mainline_pool_count",
                "v13_mainline_candidate_count",
                "_official_mainline_intensity_count",
                "mainline_intensity_count",
            ),
        )
        return (
            bool(_safe_str(item.get("_v13_theme_id")))
            or _safe_float(item.get("_v13_mainline_score")) >= 70.0
            or int(mainline_count or 0) >= 2
        )

    @staticmethod
    def _forward_alpha_score(
        item: Dict[str, Any],
        role_key: str,
        buy_point_status: str,
    ) -> float:
        """Transparent prior for T+1/T+2 continuation potential."""

        rank = int(_safe_float(item.get("rank"), 999.0))
        continuation_score = _safe_float(item.get("continuation_score"))
        extension_score = _safe_float(item.get("extension_score"))
        buyability_score = _safe_float(item.get("buyability_score"), 0.0)
        risk_score = _safe_float(item.get("risk_score"))
        score = 50.0

        if rank <= 3:
            score += 8.0
        elif rank <= 5:
            score += 5.0
        elif rank <= 10:
            score += 2.0
        else:
            score -= 2.0

        if continuation_score >= 90:
            score += 12.0
        elif continuation_score >= 82:
            score += 8.0
        elif continuation_score >= 74:
            score += 4.0
        elif continuation_score < 65:
            score -= 8.0

        if 86 <= extension_score <= 94:
            score += 10.0
        elif 78 <= extension_score < 86:
            score += 8.0
        elif 70 <= extension_score < 78:
            score += 4.0
        elif extension_score > 94 and risk_score <= 30:
            score += 4.0
        elif extension_score > 94:
            score -= 2.0
        elif extension_score < 60:
            score -= 6.0

        if buyability_score >= 80:
            score += 5.0
        elif buyability_score >= 70:
            score += 3.0

        if risk_score <= 35:
            score += 5.0
        elif risk_score <= 55:
            score += 1.0
        elif risk_score <= 70:
            score -= 5.0
        else:
            score -= 12.0

        score += {
            "leader": 1.0,
            "front": 4.0,
            "mid": 2.0,
            "back": -3.0,
        }.get(role_key, 0.0)
        score += {
            "clear": 3.0,
            "waiting": 2.0,
            "unclear": -8.0,
        }.get(buy_point_status, 0.0)

        if item.get("opportunity_tag"):
            score += 2.0
        risk_tags = {str(tag) for tag in item.get("risk_tags", []) if tag}
        if "high_acceleration" in risk_tags:
            score += 2.0

        return _clamp_float(score)

    @staticmethod
    def _decision_candidate_sort_key(item: Dict[str, Any]) -> Tuple[float, float, float]:
        return (
            _official_sort_score(item),
            -int(_safe_float(item.get("rank"), 999.0)),
            _safe_float(item.get("_forward_alpha_score"), 50.0),
        )

    def _build_decision_candidate_pool(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(candidates, key=self._decision_candidate_sort_key, reverse=True)[:DECISION_CANDIDATE_POOL_LIMIT]

    @staticmethod
    def _reason_item(
        key: str,
        label: str,
        *,
        delta: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"key": key, "label": label}
        if delta is not None:
            payload["delta"] = round(float(delta), 2)
        if detail:
            payload["detail"] = detail
        return payload

    @staticmethod
    def _reason_label_fallback(key: str) -> Optional[str]:
        return {
            "theme_tailwind": "主线题材加分",
            "theme_drag": "题材偏弱",
            "mainline_confirmed": "主线确认",
            "mainline_questionable": "主线存疑",
            "seal_strength_support": "早封强封",
            "seal_quality_drag": "封板质量偏弱",
            "seal_participation_drag": "强封但难参与",
            "role_leader": "龙头核心优先",
            "role_front": "前排换手优先",
            "role_mid": "观察备选补位",
            "role_back": "后排角色降权",
            "planned_buy_point": "计划回踩低吸",
            "waiting_buy_point": "继续等待触发",
            "unclear_buy_point": "买点不清晰",
            "risk_penalty": "风险偏高",
            "main_role_leader": "龙头核心更适合主仓",
            "main_role_front": "前排换手更适合主仓",
            "main_role_mid": "观察备选不宜主仓",
            "main_role_back": "后排角色不做主仓",
            "main_clear_buy_point": "买点清晰",
            "main_planned_buy_point": "回踩计划明确",
            "main_waiting_buy_point": "买点仍待确认",
            "main_unclear_buy_point": "买点不清晰",
            "mainline_strength": "主线强度",
            "theme_strength_boost": "题材强度加分",
            "fund_support_boost": "资金承接加分",
            "shadow_score_signal": "V1.3 题材观察分",
            "forward_alpha_signal": "次日溢价预期",
            "front_attack_window": "前排进攻窗口",
            "front_continuation_bonus": "前排延续加分",
            "watch_same_theme": "与主仓同主线",
            "watch_front_role": "前排换手更值得观察",
            "watch_leader_role": "龙头核心更值得观察",
            "watch_planned_buy_point": "计划回踩低吸",
            "watch_forward_alpha": "次日溢价预期",
            "low_official_score": "官方总分偏低",
            "weak_mainline": "主线强度不足",
            "back_role_main": "后排角色不做主仓",
            "unclear_buy_point_main": "主仓买点不清晰",
            "high_risk_main": "主仓风险偏高",
            "risk_stack_veto": "风险堆叠 >= 3",
            "adaptive_mainline_threshold": "动态主线阈值不足",
            "weak_secondary_score": "次仓强度不足",
            "high_risk_secondary": "次仓风险过高且买点不清晰",
            "back_role_secondary": "后排角色不做次仓",
            "back_role_watch": "弱后排不留观察位",
            "weak_watch_theme": "观察主题强度不足",
        }.get(_safe_str(key))

    @staticmethod
    def _excluded_reason_detail_fallback(reason_key: str) -> Optional[str]:
        return {
            "non_mainline_weak": "当前题材不在默认主线内，且题材强度偏弱，因此本轮不优先收口。",
            "buy_point_unclear": "当前买点还没有收清晰，先放回观察池，等待更明确的触发。",
            "role_duplicate": "同主题同角色已有更优先候选入选，本票本轮作为重复角色落选。",
            "mainline_rank_not_enough": "虽然属于当日主线，但在主线内部的正式排序还不够靠前，暂未收入口袋组合。",
            "slot_capacity": "当前组合槽位已经被更高优先级候选占用，本票保留观察但暂不入选。",
        }.get(_safe_str(reason_key))

    @classmethod
    def _normalize_reason_items(cls, items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            fallback_label = cls._reason_label_fallback(_safe_str(item.get("key")))
            label = _safe_str(item.get("label"))
            if fallback_label and ("?" in label or not label):
                item["label"] = fallback_label
            normalized.append(item)
        return normalized

    def repair_persisted_decision_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        normalized = deepcopy(payload)
        for item in normalized.get("portfolio", []):
            if isinstance(item, dict):
                self._repair_decision_payload_item(item, include_blockers=False)
        for item in normalized.get("candidate_diagnostics", []):
            if isinstance(item, dict):
                self._repair_decision_payload_item(
                    item,
                    include_blockers=not bool(_safe_str(item.get("selected_slot"))),
                )
        for item in normalized.get("excluded_candidates", []):
            if isinstance(item, dict):
                self._repair_excluded_candidate_payload(item)
        return normalized

    def _repair_decision_payload_item(
        self,
        item: Dict[str, Any],
        *,
        include_blockers: bool,
    ) -> None:
        soft_adjustments = self._normalize_reason_items(item.get("soft_adjustments"))
        hard_blockers = self._normalize_reason_items(item.get("hard_blockers"))
        item["soft_adjustments"] = soft_adjustments
        item["hard_blockers"] = hard_blockers
        item["decision_adjustment_reason"] = self._describe_adjustments(
            soft_adjustments,
            blockers=hard_blockers if include_blockers and hard_blockers else None,
        )

    def _repair_excluded_candidate_payload(self, item: Dict[str, Any]) -> None:
        soft_adjustments = self._normalize_reason_items(item.get("soft_adjustments"))
        hard_blockers = self._normalize_reason_items(item.get("hard_blockers"))
        item["soft_adjustments"] = soft_adjustments
        item["hard_blockers"] = hard_blockers
        reason_key = _safe_str(item.get("reason_key"))
        if reason_key in EXCLUDED_REASON_LABELS:
            item["reason"] = EXCLUDED_REASON_LABELS[reason_key]
        if reason_key == "hard_blocked" and hard_blockers:
            item["reason_detail"] = self._describe_adjustments([], blockers=hard_blockers)
        else:
            fallback_detail = self._excluded_reason_detail_fallback(reason_key)
            if fallback_detail:
                item["reason_detail"] = fallback_detail
        item["decision_adjustment_reason"] = self._describe_adjustments(soft_adjustments)

    @staticmethod
    def _dedupe_reason_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            key = _safe_str(item.get("key"))
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _sum_adjustment_deltas(items: List[Dict[str, Any]]) -> float:
        return float(sum(_safe_float(item.get("delta")) for item in items))

    def _sealing_strength_adjustment_item(
        self,
        item: Dict[str, Any],
        *,
        support_delta: float,
        drag_delta: float,
        participation_delta: float,
    ) -> Optional[Dict[str, Any]]:
        signal = item.get("_v13_sealing_strength_signal")
        if not isinstance(signal, dict) or not signal.get("available"):
            return None

        detail = _safe_str(signal.get("summary")) or _safe_str(signal.get("execution_participation_note"))
        if signal.get("is_one_word_like"):
            return self._reason_item(
                "seal_participation_drag",
                "强封但难参与",
                delta=participation_delta,
                detail=detail,
            )
        if _safe_str(signal.get("execution_bias")) == "caution" or _safe_str(signal.get("level")) == "weak":
            return self._reason_item(
                "seal_quality_drag",
                "封板质量偏弱",
                delta=drag_delta,
                detail=detail,
            )
        if _safe_str(signal.get("level")) == "strong":
            return self._reason_item(
                "seal_strength_support",
                "早封强封",
                delta=support_delta,
                detail=detail,
            )
        return None

    @staticmethod
    def _describe_adjustments(
        adjustments: List[Dict[str, Any]],
        *,
        blockers: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if blockers:
            blocker_labels = [str(item.get("label")) for item in blockers if item.get("label")]
            if blocker_labels:
                return f"命中硬阻断：{'、'.join(blocker_labels[:2])}"

        positive = [str(item.get("label")) for item in adjustments if _safe_float(item.get("delta")) > 0.05]
        negative = [str(item.get("label")) for item in adjustments if _safe_float(item.get("delta")) < -0.05]
        if positive and negative:
            return f"收口加分：{'、'.join(positive[:2])}；收口减分：{'、'.join(negative[:2])}"
        if positive:
            return f"收口加分：{'、'.join(positive[:2])}"
        if negative:
            return f"收口减分：{'、'.join(negative[:2])}"
        return "当前收口与官方排序基本一致"

    @staticmethod
    def _preferred_slot_for_candidate(candidate: Dict[str, Any]) -> str:
        role_key = _safe_str(candidate.get("_role_key"))
        if role_key in {"leader", "front"}:
            return "main"
        if role_key == "mid":
            return "secondary"
        return "watch"

    def _portfolio_adjustment_items(
        self,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        theme_score = _safe_float(theme_score_map.get(item["_theme"]), 50.0)
        v13_mainline_score = _safe_float(item.get("_v13_mainline_score"))
        role_key = _safe_str(item.get("_role_key"))
        buy_point_status = _safe_str(item.get("_buy_point_status"), item.get("buy_point_status"))
        risk_score = _safe_float(item.get("risk_score"))
        t1_direction_risk_adjustment = _safe_float(item.get("_t1_direction_risk_adjustment"))
        severe_t1_risk = self._has_severe_t1_direction_risk(
            item,
            buy_point_status=buy_point_status,
        )
        role_adjustment_label = {
            "leader": "龙头核心优先",
            "front": "前排换手优先",
            "mid": "观察备选补位",
            "back": "后排角色降权",
        }.get(role_key, f"{ROLE_LABELS.get(role_key, role_key)}调整")
        adjustments: List[Dict[str, Any]] = []
        if theme_score >= 80:
            adjustments.append(self._reason_item("theme_tailwind", "主线题材加分", delta=1.0))
        elif theme_score < 60:
            adjustments.append(self._reason_item("theme_drag", "题材偏弱", delta=-1.0))
        if v13_mainline_score >= 85:
            adjustments.append(self._reason_item("mainline_confirmed", "主线确认", delta=0.8))
        elif 0 < v13_mainline_score < 70:
            adjustments.append(self._reason_item("mainline_questionable", "主线存疑", delta=-0.6))
        sealing_adjustment = self._sealing_strength_adjustment_item(
            item,
            support_delta=0.4,
            drag_delta=-0.8,
            participation_delta=-0.6,
        )
        if sealing_adjustment:
            adjustments.append(sealing_adjustment)
        role_delta = {"leader": 0.6, "front": 1.0, "mid": 0.2, "back": -1.4}.get(role_key, 0.0)
        if role_delta != 0:
            adjustments.append(self._reason_item(f"role_{role_key}", role_adjustment_label, delta=role_delta))
        if self._has_planned_buy_point(item):
            adjustments.append(self._reason_item("planned_buy_point", "计划回踩低吸", delta=0.8))
        elif buy_point_status == "waiting":
            adjustments.append(self._reason_item("waiting_buy_point", "继续等待触发", delta=0.2))
        elif buy_point_status == "unclear":
            adjustments.append(self._reason_item("unclear_buy_point", "买点不清晰", delta=-1.8))
        if risk_score >= 70:
            adjustments.append(self._reason_item("risk_penalty", "风险偏高", delta=-1.2))
        if t1_direction_risk_adjustment <= -6.0:
            adjustments.append(self._reason_item("t1_direction_drag", "次日方向承接偏弱", delta=-1.2))
        elif t1_direction_risk_adjustment <= -4.0:
            adjustments.append(self._reason_item("t1_direction_drag", "次日方向承接偏弱", delta=-0.7))
        elif t1_direction_risk_adjustment <= -2.5:
            adjustments.append(self._reason_item("t1_direction_drag", "次日方向承接一般", delta=-0.3))
        elif role_key == "leader" and buy_point_status == "clear":
            adjustments.append(self._reason_item("t1_direction_resilience", "次日承接更稳", delta=0.3))
        if role_key == "front" and severe_t1_risk:
            adjustments.append(self._reason_item("front_t1_risk_drag", "前排次日承接偏激进", delta=-0.8))
        return adjustments

    def _main_slot_adjustment_items(
        self,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        role_key = _safe_str(item.get("_role_key"))
        buy_point_status = _safe_str(item.get("_buy_point_status"), item.get("buy_point_status"))
        forward_alpha_score = _safe_float(item.get("_forward_alpha_score"), 50.0)
        continuation_score = _safe_float(item.get("continuation_score"))
        extension_score = _safe_float(item.get("extension_score"))
        v13_mainline_score = _safe_float(item.get("_v13_mainline_score"))
        v13_theme_strength_score = _safe_float(item.get("_v13_theme_strength_score"))
        v13_fund_support_score = _safe_float(item.get("_v13_fund_support_score"))
        v13_shadow_score = _safe_float(item.get("_v13_shadow_score"))
        t1_direction_risk_adjustment = _safe_float(item.get("_t1_direction_risk_adjustment"))
        severe_t1_risk = self._has_severe_t1_direction_risk(
            item,
            buy_point_status=buy_point_status,
        )
        main_role_adjustment_label = {
            "leader": "龙头核心更适合主仓",
            "front": "前排换手更适合主仓",
            "mid": "观察备选不宜主仓",
            "back": "后排角色不做主仓",
        }.get(role_key, f"{ROLE_LABELS.get(role_key, role_key)}主仓调整")
        adjustments: List[Dict[str, Any]] = []
        role_delta = {"leader": 0.8, "front": 1.4, "mid": -0.6, "back": -2.5}.get(role_key, 0.0)
        if role_delta != 0:
            adjustments.append(self._reason_item(f"main_role_{role_key}", main_role_adjustment_label, delta=role_delta))
        if buy_point_status == "clear":
            adjustments.append(self._reason_item("main_clear_buy_point", "买点清晰", delta=1.4))
        elif self._has_planned_buy_point(item):
            adjustments.append(self._reason_item("main_planned_buy_point", "回踩计划明确", delta=0.8))
        elif buy_point_status == "waiting":
            adjustments.append(self._reason_item("main_waiting_buy_point", "买点仍待确认", delta=-0.4))
        else:
            adjustments.append(self._reason_item("main_unclear_buy_point", "买点不清晰", delta=-2.2))
        if v13_mainline_score > 0:
            adjustments.append(self._reason_item("mainline_strength", "主线强度", delta=_clamp_float((v13_mainline_score - 70.0) * 0.20, -4.5, 4.5)))
        if v13_theme_strength_score >= 82:
            adjustments.append(self._reason_item("theme_strength_boost", "题材强度加分", delta=1.2))
        if v13_fund_support_score >= 82:
            adjustments.append(self._reason_item("fund_support_boost", "资金承接加分", delta=0.8))
        if v13_shadow_score > 0:
            adjustments.append(self._reason_item("shadow_score_signal", "V1.3 题材观察分", delta=_clamp_float((v13_shadow_score - 68.0) * 0.08, -2.5, 2.5)))
        sealing_adjustment = self._sealing_strength_adjustment_item(
            item,
            support_delta=0.7,
            drag_delta=-1.2,
            participation_delta=-0.9,
        )
        if sealing_adjustment:
            adjustments.append(sealing_adjustment)
        adjustments.append(self._reason_item("forward_alpha_signal", "次日溢价预期", delta=_clamp_float((forward_alpha_score - 80.0) * 0.18, -0.5, 2.4)))
        if t1_direction_risk_adjustment <= -6.0:
            adjustments.append(self._reason_item("main_t1_risk_drag", "次日方向承接存疑", delta=-3.8))
        elif t1_direction_risk_adjustment <= -4.0:
            adjustments.append(self._reason_item("main_t1_risk_drag", "次日方向承接偏弱", delta=-1.8))
        elif t1_direction_risk_adjustment <= -2.5:
            adjustments.append(self._reason_item("main_t1_risk_drag", "次日方向承接一般", delta=-0.9))
        elif role_key == "leader" and buy_point_status == "clear":
            adjustments.append(self._reason_item("leader_t1_resilience", "龙头承接更稳", delta=0.2))
        if role_key == "front" and severe_t1_risk:
            adjustments.append(self._reason_item("front_t1_risk_penalty", "前排次日承接偏激进", delta=-2.0))
        if role_key == "front" and forward_alpha_score >= 82 and not severe_t1_risk and t1_direction_risk_adjustment >= -2.5:
            adjustments.append(self._reason_item("front_attack_window", "前排进攻窗口", delta=2.5))
        if (
            role_key == "front"
            and forward_alpha_score >= 82
            and continuation_score >= 90
            and extension_score >= 88
            and not severe_t1_risk
            and t1_direction_risk_adjustment >= -2.5
        ):
            adjustments.append(self._reason_item("front_continuation_bonus", "前排延续加分", delta=1.5))
        return adjustments

    def _watch_slot_adjustment_items(
        self,
        item: Dict[str, Any],
        *,
        main_theme: str,
    ) -> List[Dict[str, Any]]:
        role_key = _safe_str(item.get("_role_key"))
        buy_point_status = _safe_str(item.get("_buy_point_status"), item.get("buy_point_status"))
        v13_mainline_score = _safe_float(item.get("_v13_mainline_score"))
        t1_direction_risk_adjustment = _safe_float(item.get("_t1_direction_risk_adjustment"))
        severe_t1_risk = self._has_severe_t1_direction_risk(
            item,
            buy_point_status=buy_point_status,
        )
        adjustments: List[Dict[str, Any]] = []
        if _safe_str(item.get("_theme")) == main_theme:
            adjustments.append(self._reason_item("watch_same_theme", "与主仓同主线", delta=1.0))
        if v13_mainline_score >= 80:
            adjustments.append(self._reason_item("watch_v13_mainline", "V1.3 主线确认", delta=1.1))
        elif self._has_v13_mainline_confirmation(item):
            adjustments.append(self._reason_item("watch_v13_mainline", "V1.3 主线跟踪", delta=0.6))
        sealing_adjustment = self._sealing_strength_adjustment_item(
            item,
            support_delta=0.4,
            drag_delta=-0.5,
            participation_delta=-0.4,
        )
        if sealing_adjustment:
            adjustments.append(sealing_adjustment)
        if role_key == "front":
            adjustments.append(self._reason_item("watch_front_role", "前排换手更值得观察", delta=1.0))
        elif role_key == "leader":
            adjustments.append(self._reason_item("watch_leader_role", "龙头核心更值得观察", delta=0.6))
        if buy_point_status == "clear":
            adjustments.append(self._reason_item("watch_clear_buy_point", "买点清晰", delta=0.6))
        elif self._has_planned_buy_point(item):
            adjustments.append(self._reason_item("watch_planned_buy_point", "计划回踩低吸", delta=0.8))
        elif buy_point_status == "waiting":
            adjustments.append(self._reason_item("watch_waiting_buy_point", "继续等待确认", delta=0.1))
        else:
            adjustments.append(self._reason_item("watch_unclear_buy_point", "买点偏模糊", delta=-0.8))
        if t1_direction_risk_adjustment <= -6.0:
            adjustments.append(self._reason_item("watch_t1_risk_drag", "次日方向承接偏弱", delta=-1.5))
        elif t1_direction_risk_adjustment <= -4.0:
            adjustments.append(self._reason_item("watch_t1_risk_drag", "次日方向承接偏弱", delta=-0.9))
        elif t1_direction_risk_adjustment <= -2.5:
            adjustments.append(self._reason_item("watch_t1_risk_drag", "次日方向承接一般", delta=-0.4))
        elif role_key == "leader" and buy_point_status == "clear":
            adjustments.append(self._reason_item("watch_t1_resilience", "龙头承接更稳", delta=0.4))
        if role_key == "front" and severe_t1_risk:
            adjustments.append(self._reason_item("watch_front_t1_risk", "前排次日承接偏激进", delta=-1.2))
        adjustments.append(self._reason_item("watch_forward_alpha", "次日溢价预期", delta=_clamp_float((_safe_float(item.get("_forward_alpha_score")) - 82.0) * 0.08, -0.3, 1.4)))
        return adjustments

    def _collect_candidate_hard_blocker_items(
        self,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for slot in ("main", "secondary", "watch"):
            items.extend(self._slot_hard_blocker_items(slot, item, theme_score_map))
        return self._dedupe_reason_items(items)

    @staticmethod
    def _first_available_float(item: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return _safe_float(value, default=None)
        return None

    @staticmethod
    def _first_available_int(item: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
        value = MomentumSecondaryDecisionService._first_available_float(item, keys)
        return int(value) if value is not None else None

    @staticmethod
    def _risk_factor_item(
        *,
        key: str,
        label: str,
        triggered: bool,
        evidence: str,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "triggered": bool(triggered),
            "evidence": evidence,
        }

    def _risk_stack_check(self, item: Dict[str, Any]) -> Dict[str, Any]:
        close_price = self._first_available_float(item, ("close", "close_price", "current_price"))
        ma20 = self._first_available_float(item, ("ma20", "ma_20", "ma20_close", "moving_average_20"))
        position_risk = close_price is not None and ma20 is not None and ma20 > 0 and close_price > ma20 * 1.2

        sealing_signal = item.get("_v13_sealing_strength_signal")
        if not isinstance(sealing_signal, dict):
            sealing_signal = item.get("v13_sealing_strength") if isinstance(item.get("v13_sealing_strength"), dict) else {}
        first_seal_time = (
            _safe_str(sealing_signal.get("first_seal_time"))
            or _safe_str(item.get("first_seal_time"))
            or _safe_str(item.get("first_time"))
        )
        last_seal_time = (
            _safe_str(sealing_signal.get("last_seal_time"))
            or _safe_str(item.get("last_seal_time"))
            or _safe_str(item.get("last_time"))
        )
        first_minutes = self._parse_limit_time_minutes(first_seal_time)
        last_minutes = self._parse_limit_time_minutes(last_seal_time)
        late_seal = first_minutes is not None and first_minutes > 14 * 60
        seal_reopen = first_minutes is not None and last_minutes is not None and first_minutes != last_minutes
        sealing_risk = late_seal or seal_reopen

        buy_elg_amount = self._first_available_float(
            item,
            (
                "v13_stock_buy_elg_amount",
                "_v13_stock_buy_elg_amount",
                "buy_elg_amount",
                "stock_fund_buy_elg_amount",
            ),
        )
        high_20d = self._first_available_float(item, ("high_20d", "prev_20d_high", "highest_20d", "twenty_day_high"))
        price_at_20d_high = close_price is not None and high_20d is not None and high_20d > 0 and close_price >= high_20d
        divergence_risk = buy_elg_amount is not None and buy_elg_amount < 0 and price_at_20d_high

        mainline_count = self._first_available_int(
            item,
            (
                "_theme_pool_count",
                "_v13_mainline_pool_count",
                "v13_mainline_candidate_count",
                "candidate_count",
            ),
        )
        ladder_position = item.get("_v13_ladder_position")
        if not isinstance(ladder_position, dict):
            ladder_position = {}
        is_space_leader = bool(item.get("_v13_space_leader") or ladder_position.get("is_space_leader"))
        mainline_risk = mainline_count is not None and mainline_count < 2 and not is_space_leader
        mainline_evidence = (
            f"space_leader board_count={ladder_position.get('board_count')}, "
            f"market_height={ladder_position.get('market_height')}，R4 豁免"
            if is_space_leader
            else (f"pool_count={mainline_count}" if mainline_count is not None else "缺少主线池计数")
        )
        volume_expand_5 = self._first_available_float(
            item,
            (
                "volume_expand_5",
                "_volume_expand_5",
                "volume_ratio_5d",
                "amount_expand_5",
            ),
        )
        price_gain = self._first_available_float(item, ("pct_chg", "price_gain", "change_pct", "pct_change"))
        turnover_rate_f = self._first_available_float(
            item,
            (
                "turnover_rate_f",
                "free_float_turnover_rate",
                "free_turnover_rate",
                "turnover_rate",
            ),
        )
        high_volume_no_acceleration = (
            volume_expand_5 is not None
            and volume_expand_5 > 2.0
            and price_gain is not None
            and price_gain < 5.0
        )
        extreme_churn = turnover_rate_f is not None and turnover_rate_f > 25.0
        exhaustion_risk = high_volume_no_acceleration or extreme_churn

        factors = [
            self._risk_factor_item(
                key="position_risk",
                label="高位风险",
                triggered=position_risk,
                evidence=(
                    f"close={close_price:.2f}, ma20={ma20:.2f}"
                    if close_price is not None and ma20 is not None
                    else "缺少 close/20MA"
                ),
            ),
            self._risk_factor_item(
                key="sealing_risk",
                label="封板风险",
                triggered=sealing_risk,
                evidence=f"first={first_seal_time or '--'}, last={last_seal_time or '--'}",
            ),
            self._risk_factor_item(
                key="divergence_risk",
                label="量价背离风险",
                triggered=divergence_risk,
                evidence=(
                    f"buy_elg={buy_elg_amount:.2f}, close={close_price:.2f}, high20={high_20d:.2f}"
                    if buy_elg_amount is not None and close_price is not None and high_20d is not None
                    else "缺少超大单/20日高点"
                ),
            ),
            self._risk_factor_item(
                key="mainline_risk",
                label="主线风险",
                triggered=mainline_risk,
                evidence=mainline_evidence,
            ),
            self._risk_factor_item(
                key="exhaustion_risk",
                label="量能竭尽风险",
                triggered=exhaustion_risk,
                evidence=(
                    f"volume_expand_5={volume_expand_5 if volume_expand_5 is not None else '--'}, "
                    f"pct_chg={price_gain if price_gain is not None else '--'}, "
                    f"turnover_rate_f={turnover_rate_f if turnover_rate_f is not None else '--'}"
                ),
            ),
        ]
        triggered_factors = [factor for factor in factors if factor["triggered"]]
        mandatory_veto_keys = [
            factor["key"]
            for factor in triggered_factors
            if factor["key"] == "exhaustion_risk"
        ]
        mandatory_veto = bool(mandatory_veto_keys)
        result = {
            "factor_count": len(triggered_factors),
            "veto": mandatory_veto or len(triggered_factors) >= 3,
            "threshold": 3,
            "mandatory_veto": mandatory_veto,
            "mandatory_veto_keys": mandatory_veto_keys,
            "factors": factors,
            "triggered_keys": [factor["key"] for factor in triggered_factors],
        }
        item["_risk_stack_check"] = result
        item["_risk_stack_count"] = result["factor_count"]
        item["_risk_stack_veto"] = result["veto"]
        return result

    def _slot_hard_blocker_items(
        self,
        slot: str,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        official_score = _official_sort_score(item)
        theme_score = _safe_float(theme_score_map.get(_safe_str(item.get("_theme"))), 50.0)
        v13_mainline_score = _safe_float(item.get("_v13_mainline_score"))
        role_key = _safe_str(item.get("_role_key"))
        buy_point_status = _safe_str(item.get("_buy_point_status"), item.get("buy_point_status"))
        risk_score = _safe_float(item.get("risk_score"))
        blockers: List[Dict[str, Any]] = []
        risk_stack = self._risk_stack_check(item)
        if risk_stack["veto"]:
            mandatory_veto = bool(risk_stack.get("mandatory_veto"))
            blockers.append(
                self._reason_item(
                    "risk_stack_veto",
                    "量能竭尽一票否决" if mandatory_veto else "风险堆叠 >= 3",
                    detail="、".join(str(factor.get("label")) for factor in risk_stack["factors"] if factor.get("triggered")),
                )
            )
        if bool(item.get("_adaptive_gate_enabled")) and not bool(item.get("_adaptive_mainline_pass")):
            blockers.append(
                self._reason_item(
                    "adaptive_mainline_threshold",
                    "动态主线阈值不足",
                    detail=(
                        f"弱市收口要求主线池计数 >= {int(_safe_float(item.get('_adaptive_mainline_min_count'), 1.0))}，"
                        f"当前为 {int(_safe_float(item.get('_adaptive_mainline_count')))}。"
                    ),
                )
            )

        has_mainline_confirmation = self._has_v13_mainline_confirmation(item)
        if slot == "main":
            if official_score < 60:
                blockers.append(self._reason_item("low_official_score", "官方总分偏低"))
            if theme_score < 58 and v13_mainline_score < 75 and not has_mainline_confirmation:
                blockers.append(self._reason_item("weak_mainline", "主线强度不足"))
            if role_key == "back":
                blockers.append(self._reason_item("back_role_main", "后排角色不做主仓"))
            if buy_point_status == "unclear" and not self._has_planned_buy_point(item):
                blockers.append(self._reason_item("unclear_buy_point_main", "主仓买点不清晰"))
            if risk_score >= 78:
                blockers.append(self._reason_item("high_risk_main", "主仓风险偏高"))
        elif slot == "secondary":
            if official_score < 55 and theme_score < 60:
                blockers.append(self._reason_item("weak_secondary_score", "次仓强度不足"))
            if risk_score >= 82 and buy_point_status == "unclear":
                blockers.append(self._reason_item("high_risk_secondary", "次仓风险过高且买点不清晰"))
            if role_key == "back" and theme_score < 62:
                blockers.append(self._reason_item("back_role_secondary", "后排角色不做次仓"))
        else:
            if official_score < 50 and role_key == "back":
                blockers.append(self._reason_item("back_role_watch", "弱后排不留观察位"))
            if theme_score < 55 and role_key not in {"leader", "front"}:
                blockers.append(self._reason_item("weak_watch_theme", "观察主题强度不足"))
        return blockers

    def _slot_hard_blockers(
        self,
        slot: str,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> List[str]:
        return [str(reason.get("label")) for reason in self._slot_hard_blocker_items(slot, item, theme_score_map)]

    def _portfolio_priority(self, item: Dict[str, Any], theme_score_map: Dict[str, float]) -> float:
        official_score = _official_sort_score(item)
        adjustments = self._portfolio_adjustment_items(item, theme_score_map)
        return official_score + _clamp_float(self._sum_adjustment_deltas(adjustments), -3.0, 3.0)

    def _main_slot_priority(self, item: Dict[str, Any], theme_score_map: Dict[str, float]) -> float:
        official_score = _official_sort_score(item)
        adjustments = self._main_slot_adjustment_items(item, theme_score_map)
        return official_score + _clamp_float(self._sum_adjustment_deltas(adjustments), -4.0, 5.5)

    def _watch_slot_priority(
        self,
        item: Dict[str, Any],
        theme_score_map: Dict[str, float],
        *,
        main_theme: str,
    ) -> float:
        official_score = _official_sort_score(item)
        adjustments = self._watch_slot_adjustment_items(item, main_theme=main_theme)
        return official_score + _clamp_float(self._sum_adjustment_deltas(adjustments), -2.0, 3.0)

    def _rebalance_same_theme_main_slot(
        self,
        selected: List[Tuple[str, Dict[str, Any]]],
        theme_score_map: Dict[str, float],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        if len(selected) < 2:
            return selected

        main_slot_index = next((index for index, (slot, _) in enumerate(selected) if slot == "main"), None)
        if main_slot_index is None:
            return selected

        main_slot, main_candidate = selected[main_slot_index]
        same_theme_candidates = [
            (index, slot, candidate)
            for index, (slot, candidate) in enumerate(selected)
            if (
                slot != "main"
                and candidate.get("_theme") == main_candidate.get("_theme")
                and _safe_str(candidate.get("_role_key")) in {"leader", "front"}
                and self._has_planned_buy_point(candidate)
            )
        ]
        if not same_theme_candidates:
            return selected

        main_priority = self._main_slot_priority(main_candidate, theme_score_map)
        best_index, best_slot, best_candidate = max(
            same_theme_candidates,
            key=lambda item: self._main_slot_priority(item[2], theme_score_map),
        )
        best_priority = self._main_slot_priority(best_candidate, theme_score_map)
        main_has_plan = self._has_planned_buy_point(main_candidate)
        main_role_key = _safe_str(main_candidate.get("_role_key"))
        main_buy_point_status = _safe_str(
            main_candidate.get("_buy_point_status"),
            main_candidate.get("buy_point_status"),
        )
        best_role_key = _safe_str(best_candidate.get("_role_key"))
        best_buy_point_status = _safe_str(
            best_candidate.get("_buy_point_status"),
            best_candidate.get("buy_point_status"),
        )
        main_official_score = _official_sort_score(main_candidate)
        best_official_score = _official_sort_score(best_candidate)
        main_forward_alpha_score = _safe_float(main_candidate.get("_forward_alpha_score"), 50.0)
        best_forward_alpha_score = _safe_float(best_candidate.get("_forward_alpha_score"), 50.0)
        main_t1_direction_risk_adjustment = _safe_float(main_candidate.get("_t1_direction_risk_adjustment"))
        best_t1_direction_risk_adjustment = _safe_float(best_candidate.get("_t1_direction_risk_adjustment"))
        should_swap = (
            (
                main_role_key in {"mid", "back"}
                and not main_has_plan
            )
            or
            (not main_has_plan and best_priority >= main_priority + MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE)
            or (
                main_role_key in {"mid", "back"}
                and best_priority >= main_priority - MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
            )
            or (
                main_role_key == "leader"
                and main_buy_point_status != "clear"
                and best_role_key == "front"
                and best_buy_point_status == "clear"
                and best_priority >= main_priority
            )
            or (
                main_role_key in {"front", "mid", "back"}
                and main_buy_point_status != "clear"
                and best_role_key == "leader"
                and best_buy_point_status == "clear"
                and best_priority >= main_priority - MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
                and _safe_float(main_candidate.get("_forward_alpha_score"), 50.0)
                <= _safe_float(best_candidate.get("_forward_alpha_score"), 50.0) + 2.0
            )
            or (
                main_role_key == "front"
                and main_buy_point_status == "waiting"
                and best_role_key == "leader"
                and best_buy_point_status == "clear"
                and best_priority >= main_priority - SAME_THEME_CONFIRMATION_PRIORITY_TOLERANCE
                and 0.0
                <= main_official_score - best_official_score
                <= WAITING_FRONT_CLEAR_LEADER_OFFICIAL_GAP_TOLERANCE
                and main_forward_alpha_score
                <= best_forward_alpha_score + WAITING_FRONT_CLEAR_LEADER_FORWARD_ALPHA_ADVANTAGE_CAP
                and best_t1_direction_risk_adjustment >= main_t1_direction_risk_adjustment
            )
            or (
                main_role_key == "front"
                and main_buy_point_status == "clear"
                and best_role_key == "leader"
                and best_buy_point_status == "clear"
                and best_priority >= main_priority - MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
                and best_t1_direction_risk_adjustment >= main_t1_direction_risk_adjustment + 2.5
            )
        )
        if not should_swap:
            return selected

        rebalanced = list(selected)
        rebalanced[main_slot_index] = (main_slot, best_candidate)
        rebalanced[best_index] = (best_slot, main_candidate)
        return rebalanced

    def _pick_main_candidate(
        self,
        candidates: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        eligible = [
            item
            for item in candidates
            if not self._slot_hard_blockers("main", item, theme_score_map)
        ]
        pool = eligible or [
            item
            for item in candidates
            if not bool(self._risk_stack_check(item).get("veto"))
        ]
        if not pool:
            return None
        return max(pool, key=lambda item: self._main_slot_priority(item, theme_score_map))

    def _pick_secondary_candidate(
        self,
        candidates: List[Dict[str, Any]],
        selected_codes: set[str],
        main_candidate: Dict[str, Any],
        themes: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        remaining = [item for item in candidates if item["ts_code"] not in selected_codes]
        if not remaining:
            return None

        eligible_remaining = [
            item
            for item in remaining
            if not self._slot_hard_blockers("secondary", item, theme_score_map)
        ]
        if not eligible_remaining:
            return None

        best_remaining = max(eligible_remaining, key=lambda item: self._portfolio_priority(item, theme_score_map))
        best_remaining_score = self._portfolio_priority(best_remaining, theme_score_map)
        main_role_key = _safe_str(main_candidate.get("_role_key"))
        main_buy_point_status = _safe_str(
            main_candidate.get("_buy_point_status"),
            main_candidate.get("buy_point_status"),
        )
        same_theme_confirmation = [
            item
            for item in eligible_remaining
            if (
                item["_theme"] == main_candidate["_theme"]
                and _safe_str(item.get("_role_key")) in {"leader", "front"}
                and self._has_planned_buy_point(item)
            )
        ]
        if same_theme_confirmation:
            best_same_theme_confirmation = max(
                same_theme_confirmation,
                key=lambda item: self._portfolio_priority(item, theme_score_map),
            )
            best_same_theme_score = self._portfolio_priority(
                best_same_theme_confirmation,
                theme_score_map,
            )
            if (
                (main_buy_point_status != "clear" or main_role_key in {"mid", "back"})
                and best_same_theme_score
                >= best_remaining_score - SAME_THEME_CONFIRMATION_PRIORITY_TOLERANCE
            ):
                return best_same_theme_confirmation

        safer_remaining = [
            item
            for item in eligible_remaining
            if (
                item["ts_code"] != best_remaining["ts_code"]
                and self._has_material_t1_stability_edge(item, best_remaining)
            )
        ]
        if safer_remaining:
            best_safer_remaining = max(
                safer_remaining,
                key=lambda item: self._portfolio_priority(item, theme_score_map),
            )
            best_safer_score = self._portfolio_priority(best_safer_remaining, theme_score_map)
            safer_tolerance = (
                SAME_THEME_CONFIRMATION_PRIORITY_TOLERANCE
                if best_safer_remaining["_theme"] == best_remaining["_theme"]
                else DIVERSIFICATION_PRIORITY_TOLERANCE
            )
            if best_safer_score >= best_remaining_score - safer_tolerance:
                return best_safer_remaining

        theme_names = [theme["name"] for theme in themes]
        diversify_theme = (
            len(themes) >= 2
            and _safe_float(themes[1]["score"]) >= 60
            and _safe_float(themes[0]["score"]) - _safe_float(themes[1]["score"]) <= 8
        )

        if diversify_theme:
            cross_theme = [
                item
                for item in eligible_remaining
                if item["_theme"] != main_candidate["_theme"] and item["_theme"] in theme_names
            ]
            if cross_theme:
                best_cross_theme = max(
                    cross_theme,
                    key=lambda item: self._portfolio_priority(item, theme_score_map),
                )
                best_cross_theme_score = self._portfolio_priority(best_cross_theme, theme_score_map)
                if best_cross_theme_score >= best_remaining_score - DIVERSIFICATION_PRIORITY_TOLERANCE:
                    return best_cross_theme

        role_diversified = [
            item
            for item in eligible_remaining
            if item["_buy_point_status"] != "unclear" and item["_role_key"] != main_candidate["_role_key"]
        ]
        if role_diversified:
            return max(role_diversified, key=lambda item: self._portfolio_priority(item, theme_score_map))

        if _official_sort_score(best_remaining) < 55:
            return None
        return best_remaining

    def _pick_watch_candidate(
        self,
        candidates: List[Dict[str, Any]],
        selected_codes: set[str],
        selected_themes: List[str],
        theme_score_map: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        remaining = [item for item in candidates if item["ts_code"] not in selected_codes]
        if not remaining:
            return None

        eligible_remaining = [
            item
            for item in remaining
            if not self._slot_hard_blockers("watch", item, theme_score_map)
        ]
        if not eligible_remaining:
            return None

        mainline_watch = [
            item
            for item in eligible_remaining
            if (
                (
                    item["_theme"] in selected_themes
                    and (item["_role_key"] == "leader" or item["_buy_point_status"] != "unclear")
                )
                or self._has_v13_mainline_confirmation(item)
            )
        ]
        pool = mainline_watch or eligible_remaining
        main_theme = selected_themes[0] if selected_themes else ""
        candidate = max(
            pool,
            key=lambda item: self._watch_slot_priority(item, theme_score_map, main_theme=main_theme),
        )
        if main_theme:
            mainline_confirmation_candidates = [
                item
                for item in pool
                if (
                    item["_theme"] == main_theme
                    and _safe_str(item.get("_role_key")) in {"leader", "front"}
                    and self._has_planned_buy_point(item)
                )
            ]
            if mainline_confirmation_candidates:
                best_mainline_confirmation = max(
                    mainline_confirmation_candidates,
                    key=lambda item: self._watch_slot_priority(item, theme_score_map, main_theme=main_theme),
                )
                best_mainline_confirmation_priority = self._watch_slot_priority(
                    best_mainline_confirmation,
                    theme_score_map,
                    main_theme=main_theme,
                )
                candidate_priority = self._watch_slot_priority(
                    candidate,
                    theme_score_map,
                    main_theme=main_theme,
                )
                if (
                    self._has_v13_mainline_confirmation(candidate)
                    and not self._has_v13_mainline_confirmation(best_mainline_confirmation)
                ):
                    if best_mainline_confirmation_priority >= candidate_priority + 0.5:
                        candidate = best_mainline_confirmation
                elif best_mainline_confirmation_priority >= candidate_priority - MAINLINE_CONFIRMATION_PRIORITY_TOLERANCE:
                    candidate = best_mainline_confirmation

        safer_pool = [
            item
            for item in pool
            if item["ts_code"] != candidate["ts_code"] and self._has_material_t1_stability_edge(item, candidate)
        ]
        if safer_pool:
            best_safer_candidate = max(
                safer_pool,
                key=lambda item: self._watch_slot_priority(item, theme_score_map, main_theme=main_theme),
            )
            best_safer_priority = self._watch_slot_priority(
                best_safer_candidate,
                theme_score_map,
                main_theme=main_theme,
            )
            candidate_priority = self._watch_slot_priority(
                candidate,
                theme_score_map,
                main_theme=main_theme,
            )
            safer_tolerance = (
                MAINLINE_CONFIRMATION_PRIORITY_TOLERANCE
                if main_theme and best_safer_candidate["_theme"] == main_theme
                else DIVERSIFICATION_PRIORITY_TOLERANCE
            )
            if best_safer_priority >= candidate_priority - safer_tolerance:
                candidate = best_safer_candidate

        return candidate

    def _rebalance_portfolio_anchor(
        self,
        selected: List[Tuple[str, Dict[str, Any]]],
        theme_score_map: Dict[str, float],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        if len(selected) < 2:
            return selected

        main_slot_index = next((index for index, (slot, _) in enumerate(selected) if slot == "main"), None)
        if main_slot_index is None:
            return selected

        main_slot, main_candidate = selected[main_slot_index]
        anchor_candidates = [
            (index, slot, candidate)
            for index, (slot, candidate) in enumerate(selected)
            if (
                slot != "main"
                and _safe_str(candidate.get("_role_key")) in {"leader", "front"}
                and self._has_planned_buy_point(candidate)
            )
        ]
        if not anchor_candidates:
            return selected

        main_priority = self._main_slot_priority(main_candidate, theme_score_map)
        best_index, best_slot, best_candidate = max(
            anchor_candidates,
            key=lambda item: self._main_slot_priority(item[2], theme_score_map),
        )
        best_priority = self._main_slot_priority(best_candidate, theme_score_map)
        main_buy_point_status = _safe_str(
            main_candidate.get("_buy_point_status"),
            main_candidate.get("buy_point_status"),
        )
        best_buy_point_status = _safe_str(
            best_candidate.get("_buy_point_status"),
            best_candidate.get("buy_point_status"),
        )
        main_forward_alpha_score = _safe_float(main_candidate.get("_forward_alpha_score"), 50.0)
        best_forward_alpha_score = _safe_float(best_candidate.get("_forward_alpha_score"), 50.0)
        main_severe_t1_risk = self._has_severe_t1_direction_risk(
            main_candidate,
            buy_point_status=main_buy_point_status,
        )
        should_swap = (
            best_priority >= main_priority + MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
            or (
                main_buy_point_status != "clear"
                and best_buy_point_status == "clear"
                and best_priority >= main_priority - MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
                and (
                    _safe_str(main_candidate.get("_role_key")) != "front"
                    or main_forward_alpha_score <= best_forward_alpha_score + 2.0
                    or self._has_material_t1_stability_edge(
                        best_candidate,
                        main_candidate,
                        min_gap=1.5,
                    )
                )
            )
            or (
                main_severe_t1_risk
                and self._has_material_t1_stability_edge(
                    best_candidate,
                    main_candidate,
                    min_gap=1.5,
                )
                and best_priority >= main_priority - MAIN_SLOT_REBALANCE_PRIORITY_TOLERANCE
            )
        )
        if not should_swap:
            return selected

        rebalanced = list(selected)
        rebalanced[main_slot_index] = (main_slot, best_candidate)
        rebalanced[best_index] = (best_slot, main_candidate)
        return rebalanced

    def _build_portfolio_slot(
        self,
        slot: str,
        candidate: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> Dict[str, Any]:
        suggested_action = self._suggested_action_for_candidate(slot, candidate)
        official_score = round(_official_sort_score(candidate), 1)
        hard_blockers = self._slot_hard_blocker_items(slot, candidate, theme_score_map)
        if slot == "main":
            soft_adjustments = self._main_slot_adjustment_items(candidate, theme_score_map)
            slot_score = official_score + _clamp_float(self._sum_adjustment_deltas(soft_adjustments), -4.0, 5.5)
        elif slot == "secondary":
            soft_adjustments = self._portfolio_adjustment_items(candidate, theme_score_map)
            slot_score = official_score + _clamp_float(self._sum_adjustment_deltas(soft_adjustments), -3.0, 3.0)
        else:
            soft_adjustments = self._watch_slot_adjustment_items(
                candidate,
                main_theme=_safe_str(candidate.get("_theme")),
            )
            slot_score = official_score + _clamp_float(self._sum_adjustment_deltas(soft_adjustments), -2.0, 3.0)
        decision_adjustment = round(slot_score - official_score, 2)
        return {
            "slot": slot,
            "slot_label": SLOT_LABELS[slot],
            "rank": int(candidate.get("rank", 0)),
            "base_rank": int(candidate.get("rank", 0)),
            "ts_code": candidate["ts_code"],
            "name": candidate["name"],
            "theme": candidate["_theme"],
            "v13_theme_id": candidate.get("_v13_theme_id"),
            "v13_mainline_score": (
                round(_safe_float(candidate.get("_v13_mainline_score")), 1)
                if candidate.get("_v13_mainline_score")
                else None
            ),
            "v13_mainline_level": candidate.get("_v13_mainline_level"),
            "v13_mainline_level_label": candidate.get("_v13_mainline_level_label"),
            "v13_theme_strength_score": (
                round(_safe_float(candidate.get("_v13_theme_strength_score")), 1)
                if candidate.get("_v13_theme_strength_score") is not None
                else None
            ),
            "v13_fund_support_score": (
                round(_safe_float(candidate.get("_v13_fund_support_score")), 1)
                if candidate.get("_v13_fund_support_score") is not None
                else None
            ),
            "v13_limit_structure_score": (
                round(_safe_float(candidate.get("_v13_limit_structure_score")), 1)
                if candidate.get("_v13_limit_structure_score") is not None
                else None
            ),
            "v13_sealing_strength": self._public_v13_sealing_strength_signal(candidate),
            "v13_ladder_position": self._public_v13_ladder_position(candidate),
            "v13_sealing_strength_score": (
                round(_safe_float(candidate.get("_v13_sealing_strength_score")), 1)
                if candidate.get("_v13_sealing_strength_score") is not None
                else None
            ),
            "v13_sealing_strength_level": candidate.get("_v13_sealing_strength_level"),
            "v13_sealing_strength_level_label": candidate.get("_v13_sealing_strength_level_label"),
            "v13_buyability_score": (
                round(_safe_float(candidate.get("_v13_buyability_score")), 1)
                if candidate.get("_v13_buyability_score") is not None
                else None
            ),
            "v13_chip_risk_score": (
                round(_safe_float(candidate.get("_v13_chip_risk_score")), 1)
                if candidate.get("_v13_chip_risk_score") is not None
                else None
            ),
            "risk_stack": candidate.get("_risk_stack_check"),
            "risk_stack_count": candidate.get("_risk_stack_count"),
            "risk_stack_veto": candidate.get("_risk_stack_veto"),
            "mainline_intensity_count": int(_safe_float(candidate.get("_official_mainline_intensity_count"))),
            "mainline_intensity_multiplier": round(
                _safe_float(candidate.get("_official_mainline_intensity_multiplier"), 1.0),
                2,
            ),
            "mainline_intensity_bonus": round(
                _safe_float(candidate.get("_official_mainline_intensity_bonus")),
                2,
            ),
            "adaptive_gate": candidate.get("_adaptive_gate_context"),
            "adaptive_mainline_count": candidate.get("_adaptive_mainline_count"),
            "adaptive_mainline_min_count": candidate.get("_adaptive_mainline_min_count"),
            "adaptive_mainline_pass": candidate.get("_adaptive_mainline_pass"),
            "v13_shadow_score": (
                round(_safe_float(candidate.get("_v13_shadow_score")), 1)
                if candidate.get("_v13_shadow_score") is not None
                else None
            ),
            "v13_shadow_summary": candidate.get("_v13_shadow_summary"),
            "role": candidate["_role_label"],
            "score": round(slot_score, 1),
            "official_score": official_score,
            "base_rank_score": official_score,
            "risk_score": round(_safe_float(candidate.get("risk_score")), 1),
            "rule_base_score": round(_safe_float(candidate.get("_rule_base_score")), 1),
            "decision_adjustment": decision_adjustment,
            "decision_adjustment_reason": self._describe_adjustments(soft_adjustments),
            "hard_blockers": hard_blockers,
            "soft_adjustments": soft_adjustments,
            "forward_alpha_score": round(_safe_float(candidate.get("_forward_alpha_score"), 50.0), 1),
            "t1_direction_risk_adjustment": round(
                _safe_float(candidate.get("_t1_direction_risk_adjustment")),
                1,
            ),
            "buy_point_status": candidate["_buy_point_status"],
            "buy_point_label": candidate["_buy_point_label"],
            "suggested_action": suggested_action,
            "suggested_action_label": SUGGESTED_ACTION_LABELS[suggested_action],
            "primary_reason": candidate["_primary_reason"],
            "role_reason": self._build_role_reason(slot, candidate),
            "execution_plan": self._build_execution_plan(candidate),
            "entry_hint": self._build_entry_hint(candidate),
            "entry_range_low": candidate.get("entry_range_low"),
            "entry_range_high": candidate.get("entry_range_high"),
            "opportunity_tag": candidate.get("opportunity_tag"),
            "risk_tags": list(candidate.get("risk_tags", [])),
        }

    @staticmethod
    def _suggested_action_for_candidate(slot: str, candidate: Dict[str, Any]) -> str:
        if candidate["_buy_point_status"] == "clear":
            return "ready"
        if slot == "watch" or candidate["_role_key"] == "back":
            return "observe_only"
        return "wait_for_trigger"

    @staticmethod
    def _build_role_reason(slot: str, candidate: Dict[str, Any]) -> str:
        theme = candidate["_theme"]
        role = candidate["_role_label"]
        if slot == "main":
            return f"{theme} 当前是最值得优先盯的方向，这只票的 {role} 身位和买点准备度最适合作为主仓观察对象。"
        if slot == "secondary":
            return f"{theme} 里它承担补强与进攻角色，适合作为次仓候选，帮助区分谁更值得先看。"
        return f"{theme} 方向仍有主线确认价值，但买点还未完全收口，因此先放在观察仓持续跟踪。"

    def _build_execution_plan(self, candidate: Dict[str, Any]) -> str:
        entry_hint = self._build_entry_hint(candidate)
        if entry_hint:
            return entry_hint
        if candidate["_role_key"] == "leader":
            return "优先等回踩承接或高开后强度确认，未触发前不建议直接追入。"
        if candidate["_role_key"] == "front":
            return "优先等分歧转一致与放量换手确认，再考虑跟随。"
        return "先观察主线回流、分时承接和板块跟随，待条件清晰后再升级。"

    @staticmethod
    def _build_entry_hint(candidate: Dict[str, Any]) -> Optional[str]:
        low = candidate.get("entry_range_low")
        high = candidate.get("entry_range_high")
        if low is None or high is None:
            return None
        return f"优先关注 {low:.2f} - {high:.2f} 区间确认，不建议明显脱离区间追入。"

    @staticmethod
    def _theme_strength_label(score: float) -> str:
        if score >= 78:
            return "主线极强"
        if score >= 68:
            return "主线清晰"
        if score >= 58:
            return "可跟踪"
        return "偏弱观察"

    @staticmethod
    def _downgrade_action_level(level: str) -> str:
        try:
            index = ACTION_LEVEL_SEQUENCE.index(level)
        except ValueError:
            return level
        return ACTION_LEVEL_SEQUENCE[min(index + 1, len(ACTION_LEVEL_SEQUENCE) - 1)]

    @staticmethod
    def _ordered_intraday_items(portfolio_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        slot_order = {"main": 0, "secondary": 1, "watch": 2}
        return sorted(portfolio_items, key=lambda item: slot_order.get(_safe_str(item.get("slot")), 99))

    def _build_intraday_focus_order(self, portfolio_items: List[Dict[str, Any]]) -> List[str]:
        if not portfolio_items:
            return []

        prefix_map = {
            "main": "优先关注",
            "secondary": "次选关注",
            "watch": "其余继续观察",
        }
        status_hint_map = {
            "triggered": "买点已触发",
            "watching": "继续等待触发",
            "do_not_chase": "不建议追入",
            "observe_only": "仅保留观察",
            "data_unavailable": "盘中数据不足",
        }

        focus_order: List[str] = []
        for item in self._ordered_intraday_items(portfolio_items):
            prefix = prefix_map.get(_safe_str(item.get("slot")), "继续关注")
            status_hint = status_hint_map.get(_safe_str(item.get("status")), _safe_str(item.get("status_label"), "继续跟踪"))
            focus_order.append(f"{prefix}：{item['slot_label']} {item['name']}（{status_hint}）")
        return focus_order

    def _build_intraday_closing_note(
        self,
        final_recommendation: str,
        portfolio_items: List[Dict[str, Any]],
    ) -> str:
        ordered_items = self._ordered_intraday_items(portfolio_items)
        if not ordered_items:
            return "当前没有默认组合，今天不建议买入。"

        sequence = "、".join(f"{item['slot_label']} {item['name']}" for item in ordered_items)
        triggered = [f"{item['slot_label']} {item['name']}" for item in ordered_items if item.get("signal_triggered")]
        watch_item = next((item for item in ordered_items if item.get("slot") == "watch"), None)

        if final_recommendation == "buy":
            if triggered:
                return (
                    f"今天建议买，当前已触发的信号来自 {('、'.join(triggered))}；"
                    f"但固定顺序不变，仍按 {sequence} 跟踪，其余继续观察。"
                )
            return f"今天可以继续按 {sequence} 的固定顺序跟踪，一旦主仓或次仓触发就发出买点信号。"

        if final_recommendation == "main_only_consider":
            return (
                f"今天只允许主仓进入正式执行判断；当前已触发的信号来自 {('、'.join(triggered)) or '主仓'}，"
                f"仍按 {sequence} 的固定顺序跟踪，其余继续观察。"
            )

        if final_recommendation == "do_not_buy":
            observe_note = ""
            if watch_item is not None:
                observe_note = f"{watch_item['slot_label']} {watch_item['name']} 仍可保留主线观察价值，"
            if triggered:
                return (
                    f"虽然 {('、'.join(triggered))} 出现了局部强势，但今天整体仍不建议买入；"
                    f"{observe_note}不建议执行。"
                )
            return f"今天结论是不建议买入；{observe_note}其余只保留观察，不建议执行。"

        return f"固定顺序仍按 {sequence} 跟踪，继续等待更清晰的买点触发后再收口。"

    @staticmethod
    def _parse_trade_date(value: str) -> Optional[datetime]:
        normalized = value.strip()
        for date_format in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(normalized, date_format)
            except ValueError:
                continue
        return None

    def _is_historical_trade_date(self, trade_date: str, current_time: datetime) -> bool:
        parsed = self._parse_trade_date(trade_date)
        if parsed is None:
            return False
        current_day = current_time.date()
        return parsed.date() < current_day - timedelta(days=1) or parsed.date() > current_day

    @staticmethod
    def _resolve_market_phase(current_time: datetime) -> str:
        clock = current_time.time()
        if clock < time(9, 15):
            return "pre_open"
        if clock < time(9, 30):
            return "call_auction"
        if clock < time(10, 0):
            return "first_30m"
        if clock < time(10, 30):
            return "first_60m"
        if clock < time(11, 30):
            return "after_first_hour"
        if clock < time(13, 0):
            return "midday_break"
        if clock < time(15, 0):
            return "afternoon"
        return "closed"

    @staticmethod
    def _build_snapshot_assist_from_intraday_signal(intraday_signal: Dict[str, Any]) -> Dict[str, Any]:
        portfolio_items = list(intraday_signal.get("portfolio_items") or [])
        degraded_codes = [
            _safe_str(item.get("ts_code"))
            for item in portfolio_items
            if item.get("quote_available") is False and item.get("ts_code")
        ]
        assist_items: List[Dict[str, Any]] = []
        for item in portfolio_items:
            status = _safe_str(item.get("status"))
            if status == "do_not_chase":
                assist_status = "overextended"
                assist_label = "偏离过大"
                manual_check = "等待价格回到更合理的确认区间，再结合分时承接人工判断。"
            elif item.get("quote_available") is False:
                assist_status = "quote_missing"
                assist_label = "报价不足"
                manual_check = "先确认实时行情是否更新，不用这条快照做执行依据。"
            elif item.get("signal_triggered"):
                assist_status = "near_watch_zone"
                assist_label = "接近观察条件"
                manual_check = "只代表价格接近昨晚观察条件，仍需人工确认主线同步和分时承接。"
            elif status == "observe_only":
                assist_status = "observe_only"
                assist_label = "仅观察"
                manual_check = "只保留主线观察价值，不输出正式买入触发。"
            else:
                assist_status = "neutral"
                assist_label = "继续观察"
                manual_check = "等待价格、强度和承接进一步明确。"

            assist_items.append(
                {
                    "slot": item.get("slot"),
                    "slot_label": item.get("slot_label"),
                    "ts_code": item.get("ts_code"),
                    "name": item.get("name"),
                    "status": assist_status,
                    "status_label": assist_label,
                    "current_price": item.get("current_price"),
                    "change_percent": item.get("change_percent"),
                    "entry_range_low": item.get("entry_range_low"),
                    "entry_range_high": item.get("entry_range_high"),
                    "price_vs_entry_high_pct": item.get("price_vs_entry_high_pct"),
                    "manual_check": manual_check,
                }
            )

        degraded_reasons = [f"{code}: realtime_quote unavailable" for code in degraded_codes]
        return {
            "label": "盘中快照辅助",
            "confidence": "low",
            "data_as_of": intraday_signal.get("updated_at"),
            "is_degraded": bool(degraded_reasons),
            "degraded_reasons": degraded_reasons,
            "summary": "该模块只用当前快照提示是否接近观察区、是否偏离过大，以及还需要人工确认什么；不输出正式买入指令。",
            "items": assist_items,
        }

    def _build_intraday_item_signal(
        self,
        item: Dict[str, Any],
        quote: Optional[Dict[str, Any]],
        *,
        action_level: Any,
    ) -> Dict[str, Any]:
        quote = quote or {}
        entry_range_low = item.get("entry_range_low")
        entry_range_high = item.get("entry_range_high")
        current_price = _safe_float(quote.get("current_price"), 0.0)
        open_price = _safe_float(quote.get("open"), 0.0)
        change_percent = _safe_float(quote.get("change_percent"), 0.0)
        quote_available = current_price > 0 and open_price > 0
        price_vs_open_pct = None
        price_vs_entry_high_pct = None

        if quote_available:
            price_vs_open_pct = round(((current_price - open_price) / open_price) * 100, 2)
        if quote_available and entry_range_high is not None and _safe_float(entry_range_high) > 0:
            entry_high_value = _safe_float(entry_range_high)
            price_vs_entry_high_pct = round(((current_price - entry_high_value) / entry_high_value) * 100, 2)

        within_entry_range = (
            quote_available
            and entry_range_low is not None
            and entry_range_high is not None
            and _safe_float(entry_range_low) <= current_price <= _safe_float(entry_range_high)
        )
        do_not_chase = self._is_overextended(
            item,
            price_vs_open_pct=price_vs_open_pct,
            price_vs_entry_high_pct=price_vs_entry_high_pct,
            quote_available=quote_available,
        )
        signal_triggered = quote_available and not do_not_chase and (
            within_entry_range
            or (
                item.get("buy_point_status") == "clear"
                and price_vs_open_pct is not None
                and price_vs_open_pct >= -0.3
                and change_percent >= -0.5
            )
        )
        if action_level in {"observe_only", "stand_aside"}:
            signal_triggered = False
        elif action_level == "cautious_go" and item.get("slot") != "main":
            signal_triggered = False
        status = self._determine_intraday_item_status(
            item,
            action_level=action_level,
            quote_available=quote_available,
            signal_triggered=signal_triggered,
            do_not_chase=do_not_chase,
        )
        missing_conditions = self._build_intraday_missing_conditions(
            current_price=current_price,
            change_percent=change_percent,
            entry_range_low=entry_range_low,
            entry_range_high=entry_range_high,
            price_vs_open_pct=price_vs_open_pct,
            quote_available=quote_available,
            signal_triggered=signal_triggered,
            do_not_chase=do_not_chase,
        )

        return {
            "slot": item["slot"],
            "slot_label": item["slot_label"],
            "ts_code": item["ts_code"],
            "name": item["name"],
            "theme": item["theme"],
            "role": item["role"],
            "status": status,
            "status_label": INTRADAY_ITEM_STATUS_LABELS[status],
            "reason": self._build_intraday_item_reason(
                status=status,
                quote_available=quote_available,
                signal_triggered=signal_triggered,
                do_not_chase=do_not_chase,
            ),
            "quote_available": quote_available,
            "signal_triggered": signal_triggered,
            "do_not_chase": do_not_chase,
            "current_price": round(current_price, 2) if quote_available else None,
            "change_percent": round(change_percent, 2) if quote_available else None,
            "open_price": round(open_price, 2) if quote_available else None,
            "entry_range_low": entry_range_low,
            "entry_range_high": entry_range_high,
            "price_vs_open_pct": price_vs_open_pct,
            "price_vs_entry_high_pct": price_vs_entry_high_pct,
            "missing_conditions": missing_conditions,
            "update_time": quote.get("update_time"),
        }

    def _build_intraday_item_without_quote(
        self,
        item: Dict[str, Any],
        *,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "slot": item["slot"],
            "slot_label": item["slot_label"],
            "ts_code": item["ts_code"],
            "name": item["name"],
            "theme": item["theme"],
            "role": item["role"],
            "status": "data_unavailable",
            "status_label": INTRADAY_ITEM_STATUS_LABELS["data_unavailable"],
            "reason": reason,
            "quote_available": False,
            "signal_triggered": False,
            "do_not_chase": False,
            "current_price": None,
            "change_percent": None,
            "open_price": None,
            "entry_range_low": item.get("entry_range_low"),
            "entry_range_high": item.get("entry_range_high"),
            "price_vs_open_pct": None,
            "price_vs_entry_high_pct": None,
            "missing_conditions": ["等待盘中行情更新后再判断。"],
            "update_time": None,
        }

    @staticmethod
    def _determine_intraday_item_status(
        item: Dict[str, Any],
        *,
        action_level: Any,
        quote_available: bool,
        signal_triggered: bool,
        do_not_chase: bool,
    ) -> str:
        if not quote_available:
            return "data_unavailable"
        if action_level in {"observe_only", "stand_aside"}:
            return "observe_only"
        if do_not_chase:
            return "do_not_chase"
        if signal_triggered and item["slot"] in {"main", "secondary"}:
            return "triggered"
        if item["slot"] == "watch" or item.get("suggested_action") == "observe_only":
            return "observe_only"
        return "watching"

    @staticmethod
    def _is_overextended(
        item: Dict[str, Any],
        *,
        price_vs_open_pct: Optional[float],
        price_vs_entry_high_pct: Optional[float],
        quote_available: bool,
    ) -> bool:
        if not quote_available:
            return False

        role = _safe_str(item.get("role"))
        if "前排" in role and price_vs_open_pct is not None and price_vs_open_pct > 3.0:
            return True
        if price_vs_entry_high_pct is None:
            return False
        if "龙头" in role:
            return price_vs_entry_high_pct > 3.0
        return price_vs_entry_high_pct > 2.0

    @staticmethod
    def _build_intraday_missing_conditions(
        *,
        current_price: float,
        change_percent: float,
        entry_range_low: Optional[float],
        entry_range_high: Optional[float],
        price_vs_open_pct: Optional[float],
        quote_available: bool,
        signal_triggered: bool,
        do_not_chase: bool,
    ) -> List[str]:
        if not quote_available:
            return ["等待实时行情更新后再判断。"]
        if signal_triggered:
            return []
        if do_not_chase:
            return ["等待价格回到更合理的确认区间。"]
        if entry_range_low is not None and entry_range_high is not None:
            if current_price < _safe_float(entry_range_low):
                return [f"等待价格回到 {entry_range_low:.2f} - {entry_range_high:.2f} 的确认区间。"]
            if current_price > _safe_float(entry_range_high):
                return ["当前位置已经偏离昨晚建议区间，先等分歧回踩。"]

        conditions: List[str] = []
        if price_vs_open_pct is not None and price_vs_open_pct < 0:
            conditions.append("等待分时重新站回开盘价上方。")
        if change_percent < 0.5:
            conditions.append("等待强度进一步确认。")
        if not conditions:
            conditions.append("等待更清晰的承接或回流信号。")
        return conditions[:3]

    @staticmethod
    def _build_intraday_item_reason(
        *,
        status: str,
        quote_available: bool,
        signal_triggered: bool,
        do_not_chase: bool,
    ) -> str:
        del status
        if not quote_available:
            return "暂时没有可靠盘中报价，当前只保留昨晚的静态排序。"
        if do_not_chase:
            return "当前价格已经明显偏离建议区间，不建议追入。"
        if signal_triggered:
            return "价格与强度已经靠近昨晚预设买点，可重点跟踪执行信号。"
        return "买点尚未完全触发，继续等待更清晰的承接确认。"

    def _evaluate_intraday_confidence(
        self,
        action_level: Any,
        portfolio_items: List[Dict[str, Any]],
    ) -> Tuple[str, str, List[str]]:
        if action_level == "stand_aside":
            return "low", "昨晚结论已明确为今日不做，盘中不再输出买入信号。", []

        main_item = next((item for item in portfolio_items if item["slot"] == "main"), None)
        secondary_item = next((item for item in portfolio_items if item["slot"] == "secondary"), None)
        core_slots = {"main"} if action_level == "cautious_go" else {"main", "secondary"}
        core_items = [item for item in portfolio_items if item["slot"] in core_slots]

        reasons: List[str] = []
        watch_items: List[str] = []

        if any(item["status"] == "data_unavailable" for item in core_items):
            reasons.append("核心观察位缺少可靠盘中报价")

        if (
            main_item is not None
            and main_item["price_vs_open_pct"] is not None
            and main_item["price_vs_open_pct"] < -1.5
            and not main_item["signal_triggered"]
        ):
            reasons.append("主仓开盘后承接明显弱于预期")
            watch_items.append("主仓仍未重新站回开盘价上方。")

        if (
            action_level != "cautious_go"
            and
            main_item is not None
            and secondary_item is not None
            and main_item["change_percent"] is not None
            and secondary_item["change_percent"] is not None
            and secondary_item["change_percent"] - main_item["change_percent"] >= 2.0
            and not main_item["signal_triggered"]
        ):
            reasons.append("次仓盘中强度明显反超主仓，排序需要继续观察")
            watch_items.append("次仓短线强度已经明显反超主仓。")

        if reasons:
            return "low", "；".join(dict.fromkeys(reasons)), watch_items

        if any(item["status"] == "do_not_chase" for item in core_items):
            return "medium", "核心标的存在价格偏离，先等回踩到更合理的位置。", [
                "核心票当前位置不建议追入，等待回到确认区间。",
            ]

        if any(item["signal_triggered"] for item in core_items):
            reason = "主仓已经出现更清晰的买点触发。" if action_level == "cautious_go" else "主仓或次仓已经出现更清晰的买点触发。"
            return "high", reason, []

        return "medium", "盘中信号仍在观察阶段，继续等待更明确的买点触发。", self._collect_watch_items(
            portfolio_items
        )

    @staticmethod
    def _collect_watch_items(portfolio_items: List[Dict[str, Any]]) -> List[str]:
        watch_items: List[str] = []
        for item in portfolio_items:
            missing_conditions = item.get("missing_conditions", [])
            if missing_conditions:
                watch_items.append(f"{item['slot_label']}：{missing_conditions[0]}")
        return watch_items[:3]

    @staticmethod
    def _build_intraday_overall_conclusion(
        action_level: Any,
        action_reason: Any,
        market_phase: str,
        confidence_level: str,
        confidence_reason: str,
        portfolio_items: List[Dict[str, Any]],
    ) -> Tuple[str, str, str]:
        triggered_core = [
            item
            for item in portfolio_items
            if item["slot"] in {"main", "secondary"} and item["signal_triggered"]
        ]
        main_triggered = [item for item in triggered_core if item["slot"] == "main"]
        core_do_not_chase = [
            item
            for item in portfolio_items
            if item["slot"] in {"main", "secondary"} and item["do_not_chase"]
        ]

        if action_level == "stand_aside":
            return "stand_aside", "do_not_buy", _safe_str(action_reason)

        if confidence_level == "low":
            return "low_confidence", "do_not_buy", confidence_reason

        if action_level == "cautious_go" and main_triggered:
            return (
                "buy_ready",
                "main_only_consider",
                "谨慎出手阶段仅主仓允许进入正式执行判断，当前主仓已触发更清晰买点。",
            )

        if triggered_core and action_level in {"strong_go", "normal_go"}:
            slot_labels = "、".join(item["slot_label"] for item in triggered_core)
            return "buy_ready", "buy", f"{slot_labels} 已出现更清晰的买点触发，可继续按昨晚固定顺序跟踪。"

        if action_level == "observe_only":
            if market_phase in {"after_first_hour", "midday_break", "afternoon", "closed"}:
                return "do_not_buy", "do_not_buy", "昨晚结论本就是仅观察，60 分钟内也没有升级成清晰买点，今天继续不建议执行。"
            return "watching", "watch", "昨晚结论是仅观察，盘中只跟踪是否出现更明确的修复信号。"

        if market_phase in {"after_first_hour", "midday_break", "afternoon", "closed"}:
            if core_do_not_chase:
                return "do_not_buy", "do_not_buy", "核心票已经明显偏离买点区间，而且 60 分钟内没有更优触发，今天先不建议追入。"
            return "do_not_buy", "do_not_buy", "开盘后 60 分钟内仍未形成清晰买点，今天先不建议买入。"

        if market_phase in {"pre_open", "call_auction"}:
            return "not_started", "watch", "等待开盘后再确认是否出现更清晰的买点。"

        return "watching", "watch", confidence_reason

    def _build_action_reason(
        self,
        level: str,
        *,
        market_environment: Dict[str, Any],
        opportunity_quality: Dict[str, Any],
        historical_validity: Dict[str, Any],
    ) -> str:
        market_label = _safe_str(market_environment.get("label"), "中")
        opportunity_label = _safe_str(opportunity_quality.get("label"), "中")
        attack_label = _safe_str(historical_validity.get("attack_permission_label"), "恢复中")
        if level == "strong_go":
            return (
                f"当前市场环境{market_label}、当日机会质量{opportunity_label}、20 日进攻许可{attack_label}，"
                "主仓与次仓都具备较清晰买点，今天可以按固定顺序积极跟踪。"
            )
        if level == "normal_go":
            return (
                f"当前市场环境{market_label}、当日机会质量{opportunity_label}，"
                f"20 日进攻许可{attack_label}，今天可按主仓优先、次仓次选的顺序跟踪。"
            )
        if level == "cautious_go":
            return (
                f"当前市场环境{market_label}、当日机会质量{opportunity_label}，"
                f"但 20 日进攻许可为{attack_label}，今天只适合谨慎出手，最多保留 1-2 只重点跟踪对象。"
            )
        if level == "observe_only":
            return (
                f"当前市场环境{market_label}或当日机会质量{opportunity_label}还不足以收口成可执行答案，"
                "页面保留观察顺序，但不建议直接执行买入。"
            )
        return (
            f"当前市场环境{market_label}、当日机会质量{opportunity_label}无法支持执行，"
            "系统今天明确劝退，即使有个别票看起来还行也先不做。"
        )
