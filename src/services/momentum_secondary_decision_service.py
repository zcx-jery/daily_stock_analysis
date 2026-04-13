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
from math import ceil
from pathlib import Path
import pandas as pd
from statistics import mean
from threading import Lock, Timer
import time as time_module
from typing import Any, Dict, List, Optional, Tuple

from src.repositories.stock_repo import StockRepository
from src.services.momentum_screener_service import MomentumScreenerService
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

BUY_SIGNAL_ACTION_LEVELS = {"strong_go", "normal_go", "cautious_go"}
ACTION_CHECKLIST_ENABLED_LEVELS = {"strong_go", "normal_go"}
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
STRATEGY_HEALTH_CACHE_VERSION = "v3"
STRATEGY_HEALTH_DISK_CACHE_DIRNAME = "momentum_strategy_health"
STRATEGY_HEALTH_ASYNC_DEFAULT_DELAY_SECONDS = 20.0
STRATEGY_HEALTH_WAIT_TIMEOUT_SECONDS = 8.0
STRATEGY_HEALTH_WAIT_POLL_INTERVAL_SECONDS = 0.1
STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS = 75.0
STRATEGY_HEALTH_MIN_PARTIAL_SAMPLE_COUNT = 5
STRATEGY_HEALTH_MAX_SCORED_CANDIDATES = 30
STRATEGY_HEALTH_WARMING_REASON = (
    "真实 20/60 日历史验证正在后台计算，本次先展示代理健康度，稍后刷新即可切换为真实结果。"
)

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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
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


class MomentumSecondaryDecisionService:
    """Aggregate raw screener output into a static decision view."""

    def __init__(
        self,
        screener_service: Optional[MomentumScreenerService] = None,
        stock_service: Optional[StockService] = None,
        stock_repo: Optional[StockRepository] = None,
        strategy_health_async: bool = False,
        strategy_health_async_delay_seconds: float = 0.0,
        strategy_health_cache_dir: Optional[Path] = None,
    ) -> None:
        self.screener_service = screener_service
        self.stock_service = stock_service
        self.stock_repo = stock_repo or getattr(stock_service, "repo", None) or StockRepository()
        self.strategy_health_async = strategy_health_async
        self.strategy_health_async_delay_seconds = max(0.0, float(strategy_health_async_delay_seconds))
        self._strategy_health_cache: Dict[str, Dict[str, Any]] = {}
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

    def build(
        self,
        *,
        top_n: int = 10,
        min_change_pct: float = 7.0,
        min_amount: float = 3e8,
        min_turnover: float = 3.0,
        exclude_st: bool = True,
        main_board_only: bool = True,
        trade_date: Optional[str] = None,
        profile: str = "standard",
        wait_for_strategy_health: bool = False,
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
            ),
        }

    def build_intraday(
        self,
        *,
        top_n: int = 10,
        min_change_pct: float = 7.0,
        min_amount: float = 3e8,
        min_turnover: float = 3.0,
        exclude_st: bool = True,
        main_board_only: bool = True,
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
        return result

    def build_from_screening(
        self,
        screening: Dict[str, Any],
        *,
        request_params: Optional[Dict[str, Any]] = None,
        wait_for_strategy_health: bool = False,
    ) -> Dict[str, Any]:
        results = self._extract_decision_source_results(screening)
        profile = _safe_str(screening.get("profile"), "standard")
        trade_date = _safe_str(screening.get("trade_date"))
        request_params = dict(screening.get("_request_params") or request_params or self._build_request_params(profile=profile))

        if not results:
            strategy_health = self._build_strategy_health(
                [],
                [],
                [],
                trade_date=trade_date,
                request_params=request_params,
                wait_for_strategy_health=wait_for_strategy_health,
            )
            action_reason = "当前没有形成足够强的候选池，系统不建议今天给出强推荐。"
            return {
                "profile": profile,
                "trade_date": trade_date,
                "action": {
                    "level": "stand_aside",
                    "label": ACTION_LEVEL_LABELS["stand_aside"],
                    "reason": action_reason,
                    "source_profile": profile,
                },
                "strategy_health": strategy_health,
                "themes": [],
                "portfolio": [],
                "excluded_candidates": [],
                "action_checklist": {
                    "enabled": False,
                    "reason": "当前没有可执行的默认组合，因此不生成明日行动清单。",
                    "steps": [],
                },
                "evidence": {
                    "theme_validation": ["暂无可用主线，等待候选池重新形成集中强势方向。"],
                    "today_reasoning": [action_reason],
                },
            }

        enriched_candidates = [self._build_candidate_view(item) for item in results]
        themes = self._build_theme_summaries(enriched_candidates)
        theme_score_map = {theme["name"]: theme["score"] for theme in themes}
        portfolio = self._build_portfolio(enriched_candidates, themes, theme_score_map)
        excluded = self._build_excluded_candidates(enriched_candidates, portfolio, themes, theme_score_map)
        raw_action = self._build_action(profile, themes, portfolio)
        strategy_health = self._build_strategy_health(
            enriched_candidates,
            themes,
            portfolio,
            trade_date=trade_date,
            request_params=request_params,
            wait_for_strategy_health=wait_for_strategy_health,
        )
        portfolio = self._apply_strategy_health_to_portfolio(portfolio, strategy_health)
        action = self._apply_strategy_health_to_action(raw_action, strategy_health)
        action_checklist = self._build_action_checklist(action, portfolio, strategy_health)
        evidence = self._build_evidence(profile, action, strategy_health, themes, portfolio, excluded)

        return {
            "profile": profile,
            "trade_date": trade_date,
            "action": action,
            "strategy_health": strategy_health,
            "themes": themes,
            "portfolio": portfolio,
            "excluded_candidates": excluded,
            "action_checklist": action_checklist,
            "evidence": evidence,
        }

    @staticmethod
    def _build_request_params(
        *,
        top_n: int = 10,
        min_change_pct: float = 7.0,
        min_amount: float = 3e8,
        min_turnover: float = 3.0,
        exclude_st: bool = True,
        main_board_only: bool = True,
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
            "can_emit_buy_signal": can_emit_buy_signal and final_recommendation == "buy",
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
        buy_point_status, buy_point_label = self._classify_buy_point(item, role_key)
        primary_reason = next(iter(item.get("top_reasons", [])), "综合强度更优")
        decision_score = (
            _safe_float(item.get("rank_score")) * 0.55
            + _safe_float(item.get("continuation_score")) * 0.20
            + _safe_float(item.get("buyability_score"), _safe_float(item.get("extension_score"))) * 0.15
            + ROLE_PRIORITY[role_key]
            + BUY_POINT_PRIORITY[buy_point_status]
            - _safe_float(item.get("risk_score")) * 0.10
        )

        enriched = dict(item)
        enriched.update(
            {
                "_theme": theme,
                "_role_key": role_key,
                "_role_label": role_label,
                "_buy_point_status": buy_point_status,
                "_buy_point_label": buy_point_label,
                "_decision_score": round(decision_score, 2),
                "_primary_reason": primary_reason,
            }
        )
        return enriched

    def _build_theme_summaries(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate["_theme"]].append(candidate)

        summaries: List[Dict[str, Any]] = []
        for theme, items in grouped.items():
            sorted_items = sorted(items, key=lambda item: item["_decision_score"], reverse=True)
            clear_count = sum(item["_buy_point_status"] == "clear" for item in sorted_items)
            leader_count = sum(item["_role_key"] == "leader" for item in sorted_items)
            front_count = sum(item["_role_key"] == "front" for item in sorted_items)
            avg_rank_score = mean(_safe_float(item.get("rank_score")) for item in sorted_items)
            theme_score = min(
                100.0,
                avg_rank_score * 0.60
                + min(len(sorted_items), 3) * 7.0
                + leader_count * 6.0
                + front_count * 3.0
                + clear_count * 4.0,
            )
            strength_label = self._theme_strength_label(theme_score)
            summaries.append(
                {
                    "name": theme,
                    "score": round(theme_score, 1),
                    "strength_label": strength_label,
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
                            "rank_score": round(_safe_float(item.get("rank_score")), 1),
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

        sorted_candidates = sorted(
            candidates,
            key=lambda item: self._portfolio_priority(item, theme_score_map),
            reverse=True,
        )
        selected: List[Tuple[str, Dict[str, Any]]] = []
        selected_codes: set[str] = set()
        selected_themes: List[str] = []

        main_candidate = self._pick_main_candidate(sorted_candidates, theme_score_map)
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
            if theme_name not in selected_theme_names and theme_score_map.get(theme_name, 0.0) < 60:
                reason = "非主线 / 主线过弱"
            elif candidate["_buy_point_status"] == "unclear":
                reason = "买点不清晰"
            elif (theme_name, role_label) in selected_roles:
                reason = "角色重复"
            elif theme_name == top_theme_name:
                reason = "主线内名次不够"
            else:
                reason = "近期验证偏弱"

            excluded.append(
                {
                    "rank": int(candidate.get("rank", 0)),
                    "ts_code": candidate["ts_code"],
                    "name": candidate["name"],
                    "theme": theme_name,
                    "role": role_label,
                    "reason": reason,
                    "rank_score": round(_safe_float(candidate.get("rank_score")), 1),
                }
            )

        return excluded[:8]

    def _build_action(
        self,
        profile: str,
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not themes or not portfolio:
            level = "stand_aside"
        else:
            top_theme_score = _safe_float(themes[0]["score"])
            ready_count = sum(item["suggested_action"] == "ready" for item in portfolio)
            avg_risk = mean(_safe_float(item["risk_score"]) for item in portfolio)

            if ready_count >= 3 and top_theme_score >= 78:
                level = "strong_go"
            elif ready_count >= 2 and top_theme_score >= 68:
                level = "normal_go"
            elif ready_count >= 1 and top_theme_score >= 58:
                level = "cautious_go"
            elif top_theme_score >= 55:
                level = "observe_only"
            else:
                level = "stand_aside"

            if avg_risk >= 45 and level in {"strong_go", "normal_go"}:
                level = self._downgrade_action_level(level)
            if ready_count == 0 and level == "cautious_go":
                level = "observe_only"

        reason = self._build_action_reason(level, themes, portfolio)
        return {
            "level": level,
            "label": ACTION_LEVEL_LABELS[level],
            "reason": reason,
            "source_profile": profile,
        }

    def _build_empty_strategy_health(self) -> Dict[str, Any]:
        return {
            "status": "disabled",
            "label": STRATEGY_HEALTH_LABELS["disabled"],
            "reason": "当前没有形成可验证的候选池，策略健康度直接落入停用状态。",
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
        avg_rank_score = mean(_safe_float(item.get("rank_score")) for item in portfolio)
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
            blockers.append("当前默认组合平均风险分偏高，策略健康度需要至少降一级理解。")

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
            "reason": "当前没有足够的历史验证样本，策略健康度暂时落入停用状态。",
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
    ) -> Dict[str, Any]:
        historical_health, is_warming = self._build_historical_strategy_health(
            trade_date=trade_date,
            request_params=request_params,
            wait_for_strategy_health=wait_for_strategy_health,
        )
        if historical_health is not None:
            return self._attach_strategy_health_runtime_metadata(
                historical_health,
                data_source="historical",
                is_warming=False,
            )
        if not themes or not portfolio:
            return self._attach_strategy_health_runtime_metadata(
                self._build_empty_strategy_health(),
                data_source="proxy",
                is_warming=False,
            )
        return self._attach_strategy_health_runtime_metadata(
            self._build_proxy_strategy_health(candidates, themes, portfolio, is_warming=is_warming),
            data_source="proxy",
            is_warming=is_warming,
        )

    def _build_historical_strategy_health(
        self,
        *,
        trade_date: str,
        request_params: Optional[Dict[str, Any]],
        wait_for_strategy_health: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        normalized_trade_date = self._normalize_trade_date(trade_date)
        if not normalized_trade_date or not request_params or self.screener_service is None:
            return None, False

        cache_key = self._build_strategy_health_cache_key(normalized_trade_date, request_params)
        cached = self._load_cached_strategy_health(cache_key)
        if cached is not None:
            return cached, False

        if wait_for_strategy_health:
            if self.strategy_health_async:
                scheduled = self._schedule_strategy_health_compute(
                    cache_key=cache_key,
                    trade_date=normalized_trade_date,
                    request_params=request_params,
                    force_immediate=True,
                )
                if scheduled:
                    cached = self._wait_for_cached_strategy_health(
                        cache_key,
                        timeout_seconds=STRATEGY_HEALTH_WAIT_TIMEOUT_SECONDS,
                    )
                    if cached is not None:
                        return cached, False
                    return None, self._has_active_strategy_health_job(cache_key)

            health = self._compute_historical_strategy_health(
                trade_date=normalized_trade_date,
                request_params=request_params,
            )
            if health is None:
                return None, False

            self._store_cached_strategy_health(cache_key, health)
            return health, False

        if self.strategy_health_async and self._schedule_strategy_health_compute(
            cache_key=cache_key,
            trade_date=normalized_trade_date,
            request_params=request_params,
        ):
            return None, True

        health = self._compute_historical_strategy_health(
            trade_date=normalized_trade_date,
            request_params=request_params,
        )
        if health is None:
            return None, False

        self._store_cached_strategy_health(cache_key, health)
        return health, False

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
        avg_rank_score = mean(_safe_float(item.get("rank_score")) for item in portfolio)
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
    ) -> Dict[str, Any]:
        enriched = deepcopy(health)
        enriched["data_source"] = data_source
        enriched["is_warming"] = is_warming
        return enriched

    def _compute_historical_strategy_health(
        self,
        *,
        trade_date: str,
        request_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        started_at = time_module.monotonic()
        trade_dates = self._load_strategy_health_trade_dates(
            end_trade_date=trade_date,
            limit=STRATEGY_HEALTH_WINDOW_TARGETS["long_60d"]["lookback"] + 12,
        )
        if not trade_dates:
            return None

        validations: List[Dict[str, Any]] = []
        for historical_trade_date in trade_dates:
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
                continue
            if validation is None:
                should_stop_early = False
            else:
                validations.append(validation)
                if len(validations) == 1 or len(validations) % 5 == 0:
                    logger.info(
                        "Momentum strategy health progress: trade_date=%s samples=%d last_sample=%s",
                        trade_date,
                        len(validations),
                        historical_trade_date,
                    )
                should_stop_early = len(validations) >= STRATEGY_HEALTH_WINDOW_TARGETS["long_60d"]["lookback"]

            if not should_stop_early and len(validations) >= STRATEGY_HEALTH_MIN_PARTIAL_SAMPLE_COUNT:
                elapsed_seconds = time_module.monotonic() - started_at
                if elapsed_seconds >= STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS:
                    logger.info(
                        "Momentum strategy health compute reached time budget: trade_date=%s samples=%d elapsed=%.1fs",
                        trade_date,
                        len(validations),
                        elapsed_seconds,
                    )
                    should_stop_early = True

            if should_stop_early:
                break

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

    def _wait_for_cached_strategy_health(
        self,
        cache_key: str,
        *,
        timeout_seconds: float,
    ) -> Optional[Dict[str, Any]]:
        deadline = time_module.time() + max(0.0, timeout_seconds)
        while time_module.time() <= deadline:
            cached = self._load_cached_strategy_health(cache_key)
            if cached is not None:
                return cached

            if not self._has_active_strategy_health_job(cache_key):
                break

            time_module.sleep(STRATEGY_HEALTH_WAIT_POLL_INTERVAL_SECONDS)
        return self._load_cached_strategy_health(cache_key)

    def _start_delayed_strategy_health_compute(
        self,
        *,
        cache_key: str,
        trade_date: str,
        request_params: Dict[str, Any],
    ) -> None:
        if self._load_cached_strategy_health(cache_key) is not None:
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
            health = self._compute_historical_strategy_health(
                trade_date=trade_date,
                request_params=request_params,
            )
            if health is not None:
                self._store_cached_strategy_health(cache_key, health)
                logger.info(
                    "Momentum strategy health cache warmed: cache_key=%s short_samples=%s long_samples=%s status=%s",
                    cache_key,
                    health.get("short_window", {}).get("sample_count"),
                    health.get("long_window", {}).get("sample_count"),
                    health.get("status"),
                )
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

    def _build_strategy_health_cache_key(self, trade_date: str, request_params: Dict[str, Any]) -> str:
        normalized = {
            "trade_date": trade_date,
            "min_change_pct": round(_safe_float(request_params.get("min_change_pct"), 7.0), 3),
            "min_amount": round(_safe_float(request_params.get("min_amount"), 3e8), 3),
            "min_turnover": round(_safe_float(request_params.get("min_turnover"), 3.0), 3),
            "exclude_st": bool(request_params.get("exclude_st", True)),
            "main_board_only": bool(request_params.get("main_board_only", True)),
            "profile": _safe_str(request_params.get("profile"), "standard"),
        }
        return "|".join(f"{key}={value}" for key, value in normalized.items())

    def _load_cached_strategy_health(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self._strategy_health_cache.get(cache_key)
        if cached is not None:
            if cached["expires_at"] <= datetime.now():
                self._strategy_health_cache.pop(cache_key, None)
            else:
                return deepcopy(cached["value"])

        disk_cached = self._load_disk_cached_strategy_health(cache_key)
        if disk_cached is not None:
            self._strategy_health_cache[cache_key] = {
                "value": deepcopy(disk_cached),
                "expires_at": datetime.now() + STRATEGY_HEALTH_CACHE_TTL,
            }
            return disk_cached
        return None

    def _store_cached_strategy_health(self, cache_key: str, value: Dict[str, Any]) -> None:
        cache_value = deepcopy(value)
        self._strategy_health_cache[cache_key] = {
            "value": cache_value,
            "expires_at": datetime.now() + STRATEGY_HEALTH_CACHE_TTL,
        }
        self._store_disk_cached_strategy_health(cache_key, cache_value)

    def _strategy_health_cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(f"{STRATEGY_HEALTH_CACHE_VERSION}|{cache_key}".encode("utf-8")).hexdigest()
        return self._strategy_health_cache_dir / f"{digest}.json"

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
        return self._attach_strategy_health_runtime_metadata(
            value,
            data_source=_safe_str(value.get("data_source"), "historical"),
            is_warming=bool(value.get("is_warming", False)),
        )

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

    def _evaluate_strategy_health_trade_date(
        self,
        *,
        historical_trade_date: str,
        request_params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if self.screener_service is None:
            return None

        strategy_health_top_n = max(
            int(_safe_float(request_params.get("top_n"), STRATEGY_HEALTH_MAX_SCORED_CANDIDATES)),
            STRATEGY_HEALTH_MAX_SCORED_CANDIDATES,
        )
        screening = self.screener_service.screen(
            top_n=strategy_health_top_n,
            min_change_pct=_safe_float(request_params.get("min_change_pct"), 7.0),
            min_amount=_safe_float(request_params.get("min_amount"), 3e8),
            min_turnover=_safe_float(request_params.get("min_turnover"), 3.0),
            exclude_st=bool(request_params.get("exclude_st", True)),
            main_board_only=bool(request_params.get("main_board_only", True)),
            trade_date=historical_trade_date,
            profile=_safe_str(request_params.get("profile"), "standard"),
            use_sector_context=False,
            max_scored_candidates=STRATEGY_HEALTH_MAX_SCORED_CANDIDATES,
        )
        results = self._extract_decision_source_results(screening)
        if not results:
            return None

        candidates = [self._build_candidate_view(item) for item in results]
        themes = self._build_theme_summaries(candidates)
        if not themes:
            return None
        theme_score_map = {theme["name"]: theme["score"] for theme in themes}
        portfolio = self._build_portfolio(candidates, themes, theme_score_map)
        actionable_items = [item for item in portfolio if item.get("suggested_action") != "observe_only"]
        if not actionable_items:
            return None

        candidate_map = {item["ts_code"]: item for item in candidates}
        item_results: List[Dict[str, Any]] = []
        for item in actionable_items:
            evaluated = self._evaluate_strategy_health_portfolio_item(
                trade_date=historical_trade_date,
                portfolio_item=item,
                candidate=candidate_map.get(item["ts_code"]),
            )
            if evaluated is not None:
                item_results.append(evaluated)

        if not item_results:
            return None

        success_count = sum(1 for item in item_results if item["success"])
        required_success_count = max(1, ceil(len(item_results) * 2 / 3))
        avg_profit_window_pct = mean(item["profit_window_pct"] for item in item_results)
        avg_max_drawdown_pct = mean(item["max_drawdown_pct"] for item in item_results)
        combo_success = (
            success_count >= required_success_count
            and avg_profit_window_pct >= 2.0
            and avg_max_drawdown_pct <= 3.0
        )
        return {
            "trade_date": historical_trade_date,
            "selected_count": len(item_results),
            "success_count": success_count,
            "required_success_count": required_success_count,
            "success": combo_success,
            "profit_window_pct": avg_profit_window_pct,
            "max_drawdown_pct": avg_max_drawdown_pct,
        }

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

    def _apply_strategy_health_to_action(
        self,
        action: Dict[str, Any],
        strategy_health: Dict[str, Any],
    ) -> Dict[str, Any]:
        status = _safe_str(strategy_health.get("status"))
        if status == "healthy":
            return action

        if status == "disabled":
            level = "stand_aside"
        else:
            level = self._limit_action_level(_safe_str(action.get("level")), "cautious_go")

        return {
            "level": level,
            "label": ACTION_LEVEL_LABELS[level],
            "reason": _safe_str(strategy_health.get("reason"), _safe_str(action.get("reason"))),
            "source_profile": _safe_str(action.get("source_profile"), "standard"),
        }

    def _apply_strategy_health_to_portfolio(
        self,
        portfolio: List[Dict[str, Any]],
        strategy_health: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not portfolio:
            return []

        cap = _safe_str(strategy_health.get("recommendation_cap"))
        status = _safe_str(strategy_health.get("status"))
        limited_ready_limit = 1 if status == "recovery_mode" else 2
        ready_seen = 0
        adjusted: List[Dict[str, Any]] = []

        for item in portfolio:
            updated = dict(item)
            note = ""

            if cap == "disabled":
                updated["suggested_action"] = "observe_only"
                updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS["observe_only"]
                note = "当前策略停用，保留观察但不建议执行。"
            elif cap == "limited":
                if updated.get("suggested_action") == "ready":
                    ready_seen += 1
                    if ready_seen > limited_ready_limit or updated.get("slot") == "watch":
                        downgraded_action = "wait_for_trigger" if updated.get("slot") in {"main", "secondary"} else "observe_only"
                        updated["suggested_action"] = downgraded_action
                        updated["suggested_action_label"] = SUGGESTED_ACTION_LABELS[downgraded_action]
                if status == "recovery_mode":
                    note = "当前策略处于恢复中，只保留少量推荐，优先按固定顺序跟踪。"
                else:
                    note = "当前策略仅部分健康，先等更清晰触发后再考虑执行。"

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
    ) -> Dict[str, Any]:
        theme_validation = [
            f"{theme['name']} 主线评分 {theme['score']:.1f}，{theme['summary']}"
            for theme in themes
        ]
        if not theme_validation:
            theme_validation = ["当前未形成满足条件的主线。"]

        today_reasoning = [
            f"本次二次决策基于 {profile} 候选引擎重新收口组合，不直接沿用 TopN 排名。",
            f"策略健康状态为 {strategy_health['label']}：{strategy_health['reason']}",
            action["reason"],
        ]
        if portfolio:
            today_reasoning.append(
                "默认组合按主仓 / 次仓 / 观察仓给出，但系统不会强行凑满三只。"
            )
        if excluded:
            today_reasoning.append(
                f"其余未入选股票已补充主淘汰原因，当前共标记 {len(excluded)} 只。"
            )

        return {
            "theme_validation": theme_validation,
            "today_reasoning": today_reasoning,
        }

    def _build_action_checklist(
        self,
        action: Dict[str, Any],
        portfolio: List[Dict[str, Any]],
        strategy_health: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not portfolio:
            return {
                "enabled": False,
                "reason": "当前没有可执行的默认组合，因此不生成明日行动清单。",
                "steps": [],
            }

        action_level = _safe_str(action.get("level"))
        action_label = _safe_str(action.get("label"), "仅观察")
        if action_level not in ACTION_CHECKLIST_ENABLED_LEVELS:
            health_reason = _safe_str(strategy_health.get("reason"))
            return {
                "enabled": False,
                "reason": (
                    f"当前出手级别为“{action_label}”，{health_reason} 页面保留默认组合和观察信息，"
                    "但不生成明日行动清单。"
                ),
                "steps": [],
            }

        all_focus = self._build_portfolio_focus_items(portfolio)
        core_focus = self._build_portfolio_focus_items(portfolio, slots={"main", "secondary"})
        watch_focus = self._build_portfolio_focus_items(portfolio, slots={"watch"})

        steps = [
            {
                "phase": "pre_open",
                "phase_label": ACTION_CHECKLIST_PHASE_LABELS["pre_open"],
                "objective": "先确认昨晚这套 1-3 票组合，今天是否还值得继续盯。",
                "focus_items": all_focus,
                "tasks": [
                    "先看主仓、次仓的竞价强弱，判断是否明显低于昨晚预期。",
                    "观察仓只保留主线确认价值，不因为单票冲高就临时改顺序。",
                    "如果三只票普遍高开过度或明显不及预期，优先准备今天不做。",
                ],
                "expected_outcome": "明确开盘后先盯主仓、次仓，观察仓只保留辅助确认作用。",
            },
            {
                "phase": "first_30m",
                "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_30m"],
                "objective": "识别谁掉队、谁还保留买点资格，不让弱票继续占注意力。",
                "focus_items": core_focus or all_focus,
                "tasks": [
                    "先排除明显不及预期的票：承接差、快速走弱、明显偏离买点区的先降级观察。",
                    "重点确认主仓与次仓谁更接近昨晚定义的买点区和触发条件。",
                    "如果只有观察仓活跃，也只保留观察，不替代昨晚顺序。",
                ],
                "expected_outcome": "排除明显掉队的对象，只留下仍值得继续跟踪的 1-2 只核心票。",
            },
            {
                "phase": "first_60m",
                "phase_label": ACTION_CHECKLIST_PHASE_LABELS["first_60m"],
                "objective": "到 60 分钟内必须收口成“建议买 / 不建议买”的明确结论。",
                "focus_items": all_focus,
                "tasks": [
                    "若主仓或次仓触发买点，就按固定顺序发出信号：先主仓、再次仓，其余继续观察。",
                    "若核心票都未触发，或已经偏离过大，则明确保留观察但不建议执行买入。",
                    "把结论收口成一句话，并说明今天优先关注谁、次选谁、其余继续观察。",
                ],
                "expected_outcome": (
                    "输出今天最终该不该买的结论，并保留固定顺序："
                    "优先关注主仓、次选次仓，其余继续观察。"
                ),
            },
        ]
        if watch_focus:
            steps[-1]["tasks"].append("观察仓只承担主线确认作用，不作为临时顶替的执行位。")

        return {
            "enabled": True,
            "reason": (
                f"当前出手级别为“{action_label}”，系统会补充明日行动清单，"
                "帮助你在次日 60 分钟内完成收口。"
            ),
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
        rank_score = _safe_float(item.get("rank_score"))
        continuation_score = _safe_float(item.get("continuation_score"))
        risk_score = _safe_float(item.get("risk_score"))

        if buyability is not None:
            buyability_score = _safe_float(buyability)
            if buyability_score >= 72 and risk_score <= 35:
                return "clear", BUY_POINT_LABELS["clear"]
            if buyability_score >= 60 and rank_score >= 65 and risk_score <= 55:
                return "waiting", BUY_POINT_LABELS["waiting"]
            return "unclear", BUY_POINT_LABELS["unclear"]

        if role_key == "leader" and continuation_score >= 82 and rank_score >= 70 and risk_score <= 40:
            return "clear", BUY_POINT_LABELS["clear"]
        if continuation_score >= 72 and rank_score >= 60 and risk_score <= 55:
            return "waiting", BUY_POINT_LABELS["waiting"]
        return "unclear", BUY_POINT_LABELS["unclear"]

    def _portfolio_priority(self, item: Dict[str, Any], theme_score_map: Dict[str, float]) -> float:
        return (
            _safe_float(item["_decision_score"])
            + _safe_float(theme_score_map.get(item["_theme"]), 50.0) * 0.18
            + ROLE_PRIORITY[item["_role_key"]]
            + BUY_POINT_PRIORITY[item["_buy_point_status"]]
            - _safe_float(item.get("risk_score")) * 0.08
        )

    def _pick_main_candidate(
        self,
        candidates: List[Dict[str, Any]],
        theme_score_map: Dict[str, float],
    ) -> Dict[str, Any]:
        clear_candidates = [item for item in candidates if item["_buy_point_status"] == "clear"]
        pool = clear_candidates or candidates
        return max(pool, key=lambda item: self._portfolio_priority(item, theme_score_map))

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

        theme_names = [theme["name"] for theme in themes]
        diversify_theme = (
            len(themes) >= 2
            and _safe_float(themes[1]["score"]) >= 60
            and _safe_float(themes[0]["score"]) - _safe_float(themes[1]["score"]) <= 8
        )

        if diversify_theme:
            cross_theme = [
                item
                for item in remaining
                if item["_theme"] != main_candidate["_theme"] and item["_theme"] in theme_names
            ]
            if cross_theme:
                return max(cross_theme, key=lambda item: self._portfolio_priority(item, theme_score_map))

        role_diversified = [
            item
            for item in remaining
            if item["_buy_point_status"] != "unclear" and item["_role_key"] != main_candidate["_role_key"]
        ]
        if role_diversified:
            return max(role_diversified, key=lambda item: self._portfolio_priority(item, theme_score_map))

        best_remaining = max(remaining, key=lambda item: self._portfolio_priority(item, theme_score_map))
        if self._portfolio_priority(best_remaining, theme_score_map) < 55:
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

        mainline_watch = [
            item
            for item in remaining
            if item["_theme"] in selected_themes
            and (item["_role_key"] == "leader" or item["_buy_point_status"] != "unclear")
        ]
        pool = mainline_watch or remaining
        candidate = max(pool, key=lambda item: self._portfolio_priority(item, theme_score_map))

        theme_score = _safe_float(theme_score_map.get(candidate["_theme"]), 0.0)
        if theme_score < 55 and candidate["_role_key"] not in {"leader", "front"}:
            return None
        return candidate

    def _build_portfolio_slot(
        self,
        slot: str,
        candidate: Dict[str, Any],
        theme_score_map: Dict[str, float],
    ) -> Dict[str, Any]:
        suggested_action = self._suggested_action_for_candidate(slot, candidate)
        return {
            "slot": slot,
            "slot_label": SLOT_LABELS[slot],
            "rank": int(candidate.get("rank", 0)),
            "ts_code": candidate["ts_code"],
            "name": candidate["name"],
            "theme": candidate["_theme"],
            "role": candidate["_role_label"],
            "score": round(self._portfolio_priority(candidate, theme_score_map), 1),
            "rank_score": round(_safe_float(candidate.get("rank_score")), 1),
            "risk_score": round(_safe_float(candidate.get("risk_score")), 1),
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

    def _build_intraday_item_signal(
        self,
        item: Dict[str, Any],
        quote: Optional[Dict[str, Any]],
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
        status = self._determine_intraday_item_status(
            item,
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
        quote_available: bool,
        signal_triggered: bool,
        do_not_chase: bool,
    ) -> str:
        if not quote_available:
            return "data_unavailable"
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
        core_items = [item for item in portfolio_items if item["slot"] in {"main", "secondary"}]

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
            return "high", "主仓或次仓已经出现更清晰的买点触发。", []

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
        core_triggered = [
            item
            for item in portfolio_items
            if item["slot"] in {"main", "secondary"} and item["signal_triggered"]
        ]
        core_do_not_chase = [
            item
            for item in portfolio_items
            if item["slot"] in {"main", "secondary"} and item["do_not_chase"]
        ]

        if action_level == "stand_aside":
            return "stand_aside", "do_not_buy", _safe_str(action_reason)

        if confidence_level == "low":
            return "low_confidence", "do_not_buy", confidence_reason

        if core_triggered and action_level in BUY_SIGNAL_ACTION_LEVELS:
            slot_labels = "、".join(item["slot_label"] for item in core_triggered)
            return "buy_ready", "buy", f"{slot_labels} 已出现更清晰的买点触发，可继续按昨晚顺序跟踪。"

        if action_level == "observe_only":
            if market_phase in {"after_first_hour", "midday_break", "afternoon", "closed"}:
                return "do_not_buy", "do_not_buy", "昨晚结论本就是仅观察，60 分钟内也没有升级为清晰买点，今天继续不建议执行。"
            return "watching", "watch", "昨晚结论是仅观察，盘中只跟踪是否出现更明确的修复信号。"

        if market_phase in {"after_first_hour", "midday_break", "afternoon", "closed"}:
            if core_do_not_chase:
                return "do_not_buy", "do_not_buy", "核心票已经明显偏离买点区，且 60 分钟内没有更优触发，今天先不建议追入。"
            return "do_not_buy", "do_not_buy", "开盘后 60 分钟内仍未形成清晰买点，今天先不建议买入。"

        if market_phase in {"pre_open", "call_auction"}:
            return "not_started", "watch", "等待开盘后再确认是否出现更清晰的买点。"

        return "watching", "watch", confidence_reason

    def _build_action_reason(
        self,
        level: str,
        themes: List[Dict[str, Any]],
        portfolio: List[Dict[str, Any]],
    ) -> str:
        if not themes or not portfolio:
            return "当前没有形成可执行的主线和默认组合，系统建议今天先不做。"

        top_theme = themes[0]["name"]
        ready_count = sum(item["suggested_action"] == "ready" for item in portfolio)
        if level == "strong_go":
            return f"{top_theme} 主线强度高，默认组合里已有 {ready_count} 只票买点清晰，今天可积极准备次日执行。"
        if level == "normal_go":
            return f"{top_theme} 主线已经比较清晰，默认组合里至少有 2 只票具备可跟踪买点，可正常出手。"
        if level == "cautious_go":
            return f"{top_theme} 方向仍在，但当前只有少数票买点足够清晰，更适合谨慎出手。"
        if level == "observe_only":
            return f"{top_theme} 方向还在，不过买点仍需等待触发，今天保留观察比直接执行更稳妥。"
        return f"{top_theme} 方向还没有收口成可执行组合，即使个别票看起来不错，系统也建议今天先不做。"
