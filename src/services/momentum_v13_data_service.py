# -*- coding: utf-8 -*-
"""V1.3 momentum screener data aggregation service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from data_provider.base import normalize_stock_code
from data_provider.tushare_fetcher import TushareFetcher

logger = logging.getLogger(__name__)

ContextProgressCallback = Callable[[Dict[str, Any]], None]

CONTEXT_PROGRESS_STAGE_LABELS = {
    "limit_prices": "加载涨停价快照",
    "limit_events": "加载涨停事件快照",
    "dc_concepts": "加载东财题材快照",
    "dc_moneyflow": "加载板块资金快照",
    "dc_members": "加载东财题材成分",
    "stock_moneyflow_dc": "加载东财个股资金",
    "stock_moneyflow_ths": "加载同花顺个股资金",
    "cyq_perf": "加载获利盘分布快照",
    "cyq_chips": "加载筹码明细快照",
    "kpl_list": "加载开盘啦题材映射",
    "ths_hot": "加载同花顺热度快照",
    "ths_members": "加载同花顺题材成分",
    "ths_index_names": "加载同花顺题材名称",
}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


CAPITAL_THEME_RULES = [
    {
        "theme_id": "capital_theme:battery",
        "theme_name": "电池",
        "keywords": [
            "锂电",
            "锂电池",
            "电池",
            "固态电池",
            "钠电池",
            "动力电池",
            "储能",
            "电解液",
            "隔膜",
            "正极",
            "负极",
            "锂矿",
            "锂盐",
            "碳酸锂",
            "盐湖提锂",
            "六氟磷酸锂",
            "氟化工",
        ],
        "stock_aliases": [
            "多氟多",
            "天华新能",
            "恩捷股份",
            "天赐材料",
            "盛新锂能",
            "天齐锂业",
            "宁德时代",
            "亿纬锂能",
            "赣锋锂业",
        ],
    },
    {
        "theme_id": "capital_theme:ai_compute",
        "theme_name": "AI 算力",
        "keywords": ["算力", "人工智能", "AI", "服务器", "CPO", "液冷", "数据中心", "光模块", "GPU"],
        "stock_aliases": [],
    },
    {
        "theme_id": "capital_theme:robotics",
        "theme_name": "机器人",
        "keywords": ["机器人", "人形机器人", "减速器", "伺服", "执行器", "传感器"],
        "stock_aliases": [],
    },
    {
        "theme_id": "capital_theme:semiconductor",
        "theme_name": "半导体",
        "keywords": ["半导体", "芯片", "存储", "光刻", "封测", "晶圆", "先进封装"],
        "stock_aliases": [],
    },
    {
        "theme_id": "capital_theme:low_altitude",
        "theme_name": "低空经济",
        "keywords": ["低空", "飞行汽车", "eVTOL", "无人机", "通航"],
        "stock_aliases": [],
    },
]


class MomentumV13DataService:
    """Build reusable V1.3 data contexts for secondary decision and backtest."""

    _shared_resource_cache: Dict[str, Dict[str, Any]] = {}
    _shared_cache_stats: Dict[str, int] = {
        "hit": 0,
        "miss": 0,
        "expired": 0,
        "disk_hit": 0,
        "disk_miss": 0,
        "disk_expired": 0,
        "disk_error": 0,
    }
    _SNAPSHOT_PAGE_SIZE = 5000
    _MAX_SNAPSHOT_PAGES = 20
    _DISK_CACHE_VERSION = "v1"
    _DISK_CACHE_DIRNAME = "momentum_v13_resources"
    _HISTORICAL_RESOURCE_TTL_SECONDS = 30 * 24 * 60 * 60

    _DEFAULT_RESOURCE_TTLS = {
        "dc_concept": 30 * 60,
        "dc_moneyflow": 7 * 24 * 60 * 60,
        "dc_member": 7 * 24 * 60 * 60,
        "stock_moneyflow_dc": 7 * 24 * 60 * 60,
        "stock_moneyflow_ths": 7 * 24 * 60 * 60,
        "cyq_perf": 7 * 24 * 60 * 60,
        "cyq_chips": 7 * 24 * 60 * 60,
        "kpl_list": 7 * 24 * 60 * 60,
        "stk_limit": 7 * 24 * 60 * 60,
        "limit_list_d": 7 * 24 * 60 * 60,
        "ths_member": 7 * 24 * 60 * 60,
        "ths_index": 7 * 24 * 60 * 60,
        "ths_hot": 30 * 60,
        "realtime_quote": 60,
        "context": 30 * 60,
    }

    def __init__(
        self,
        fetcher: Optional[TushareFetcher] = None,
        *,
        resource_ttls: Optional[Dict[str, int]] = None,
        disk_cache_dir: Optional[Path] = None,
        enable_disk_cache: Optional[bool] = None,
    ) -> None:
        self.fetcher = fetcher or TushareFetcher(rate_limit_per_minute=200)
        self._resource_cache = self.__class__._shared_resource_cache
        self._resource_ttls = {**self._DEFAULT_RESOURCE_TTLS, **(resource_ttls or {})}
        self._disk_cache_dir = (
            Path(disk_cache_dir)
            if disk_cache_dir is not None
            else Path.cwd() / "data" / "cache" / self.__class__._DISK_CACHE_DIRNAME
        )
        self._enable_disk_cache = (
            isinstance(self.fetcher, TushareFetcher)
            if enable_disk_cache is None
            else bool(enable_disk_cache)
        )

    @classmethod
    def reset_cache(cls) -> None:
        cls._shared_resource_cache.clear()
        cls._shared_cache_stats = {
            "hit": 0,
            "miss": 0,
            "expired": 0,
            "disk_hit": 0,
            "disk_miss": 0,
            "disk_expired": 0,
            "disk_error": 0,
        }

    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        return {**cls._shared_cache_stats, "size": len(cls._shared_resource_cache)}

    @staticmethod
    def _emit_progress(
        progress_callback: Optional[ContextProgressCallback],
        *,
        stage_key: str,
        stage_label: str,
        progress_pct: float,
        trade_date: Optional[str] = None,
        processed_item_count: Optional[int] = None,
        total_item_count: Optional[int] = None,
    ) -> None:
        if not callable(progress_callback):
            return
        payload: Dict[str, Any] = {
            "stage_key": stage_key,
            "stage_label": stage_label,
            "progress_pct": round(max(0.0, min(100.0, float(progress_pct))), 2),
        }
        if trade_date:
            payload["trade_date"] = str(trade_date)
        if processed_item_count is not None:
            payload["processed_item_count"] = max(0, int(processed_item_count))
        if total_item_count is not None:
            payload["total_item_count"] = max(0, int(total_item_count))
        progress_callback(payload)

    def build_context(
        self,
        *,
        trade_date: str,
        ts_codes: List[str],
        progress_callback: Optional[ContextProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Build the full V1.3 EOD context used by replay and secondary decision."""
        return self._build_context(
            trade_date=trade_date,
            ts_codes=ts_codes,
            context_variant="full",
            include_chip_snapshots=True,
            include_ths_members=True,
            progress_callback=progress_callback,
        )

    def build_screening_context(
        self,
        *,
        trade_date: str,
        ts_codes: List[str],
        progress_callback: Optional[ContextProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Build a lighter V1.3 context for synchronous screening requests."""
        return self._build_context(
            trade_date=trade_date,
            ts_codes=ts_codes,
            context_variant="screening_light",
            include_chip_snapshots=False,
            include_ths_members=False,
            progress_callback=progress_callback,
        )

    def _build_context(
        self,
        *,
        trade_date: str,
        ts_codes: List[str],
        context_variant: str,
        include_chip_snapshots: bool,
        include_ths_members: bool,
        progress_callback: Optional[ContextProgressCallback],
    ) -> Dict[str, Any]:
        normalized_codes = self._normalize_ts_codes(ts_codes)
        context_key = self._cache_key("context", context_variant, trade_date, ",".join(normalized_codes))
        cached = self._cache_get(context_key, self._resource_ttls["context"])
        if cached is not None:
            return cached
        total_started_at = time.perf_counter()

        def _log_context_step(step: str, started_at: float, payload: Dict[str, Any]) -> None:
            logger.info(
                "Momentum V1.3 context timing: trade_date=%s variant=%s step=%s elapsed_seconds=%.3f ts_code_count=%s rows=%s status=%s",
                self._display_trade_date(trade_date),
                context_variant,
                step,
                time.perf_counter() - started_at,
                len(normalized_codes),
                len(_safe_list(payload.get("rows"))),
                str(payload.get("status") or "unknown"),
            )

        active_steps = [
            "limit_prices",
            "limit_events",
            "dc_concepts",
            "dc_moneyflow",
            "dc_members",
            "stock_moneyflow_dc",
            "stock_moneyflow_ths",
        ]
        if include_chip_snapshots:
            active_steps.extend(["cyq_perf", "cyq_chips"])
        active_steps.extend(["kpl_list", "ths_hot"])
        if include_ths_members:
            active_steps.extend(["ths_members", "ths_index_names"])

        def _emit_context_step(step: str) -> None:
            if not active_steps:
                progress_pct = 70.0
            else:
                index = active_steps.index(step)
                progress_pct = 66.5 + (index / max(len(active_steps), 1)) * 5.0
            self._emit_progress(
                progress_callback,
                stage_key=step,
                stage_label=CONTEXT_PROGRESS_STAGE_LABELS.get(step, step),
                progress_pct=progress_pct,
                trade_date=self._display_trade_date(trade_date),
                processed_item_count=len(normalized_codes),
                total_item_count=len(normalized_codes),
            )

        started_at = time.perf_counter()
        _emit_context_step("limit_prices")
        limit_prices = self._load_limit_prices(trade_date)
        _log_context_step("limit_prices", started_at, limit_prices)
        started_at = time.perf_counter()
        _emit_context_step("limit_events")
        limit_events = self._load_limit_events(trade_date)
        _log_context_step("limit_events", started_at, limit_events)
        started_at = time.perf_counter()
        _emit_context_step("dc_concepts")
        dc_concepts = self._load_dc_concepts(trade_date)
        _log_context_step("dc_concepts", started_at, dc_concepts)
        started_at = time.perf_counter()
        _emit_context_step("dc_moneyflow")
        dc_moneyflow = self._load_dc_moneyflow(trade_date)
        _log_context_step("dc_moneyflow", started_at, dc_moneyflow)
        started_at = time.perf_counter()
        _emit_context_step("dc_members")
        dc_members = self._load_dc_members(trade_date, normalized_codes)
        _log_context_step("dc_members", started_at, dc_members)
        started_at = time.perf_counter()
        _emit_context_step("stock_moneyflow_dc")
        stock_moneyflow_dc = self._load_stock_moneyflow_dc(trade_date, normalized_codes)
        _log_context_step("stock_moneyflow_dc", started_at, stock_moneyflow_dc)
        started_at = time.perf_counter()
        _emit_context_step("stock_moneyflow_ths")
        stock_moneyflow_ths = self._load_stock_moneyflow_ths(trade_date, normalized_codes)
        _log_context_step("stock_moneyflow_ths", started_at, stock_moneyflow_ths)
        started_at = time.perf_counter()
        if include_chip_snapshots:
            _emit_context_step("cyq_perf")
        cyq_perf = (
            self._load_cyq_perf(trade_date, normalized_codes)
            if include_chip_snapshots
            else self._payload(
                source="tushare.cyq_perf",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
            )
        )
        if include_chip_snapshots:
            _log_context_step("cyq_perf", started_at, cyq_perf)
        started_at = time.perf_counter()
        if include_chip_snapshots:
            _emit_context_step("cyq_chips")
        cyq_chips = (
            self._load_cyq_chips(trade_date, normalized_codes)
            if include_chip_snapshots
            else self._payload(
                source="tushare.cyq_chips",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
            )
        )
        if include_chip_snapshots:
            _log_context_step("cyq_chips", started_at, cyq_chips)
        started_at = time.perf_counter()
        _emit_context_step("kpl_list")
        kpl_list = self._load_kpl_list(trade_date)
        _log_context_step("kpl_list", started_at, kpl_list)
        started_at = time.perf_counter()
        _emit_context_step("ths_hot")
        ths_hot = self._load_ths_hot(trade_date)
        _log_context_step("ths_hot", started_at, ths_hot)
        started_at = time.perf_counter()
        if include_ths_members:
            _emit_context_step("ths_members")
        ths_members = (
            self._load_ths_members(normalized_codes)
            if include_ths_members
            else self._payload(
                source="tushare.ths_member",
                trade_date=None,
                rows=[],
            )
        )
        if include_ths_members:
            _log_context_step("ths_members", started_at, ths_members)
        started_at = time.perf_counter()
        if include_ths_members:
            _emit_context_step("ths_index_names")
        theme_name_map = self._load_ths_index_names(ths_members) if include_ths_members else {}
        if include_ths_members:
            _log_context_step("ths_index_names", started_at, theme_name_map.get("_payload") or {})

        payloads = {
            "dc_concept": dc_concepts,
            "moneyflow_ind_dc": dc_moneyflow,
            "dc_member": dc_members,
            "moneyflow_dc": stock_moneyflow_dc,
            "moneyflow_ths": stock_moneyflow_ths,
            "cyq_perf": cyq_perf,
            "cyq_chips": cyq_chips,
            "kpl_list": kpl_list,
            "stk_limit": limit_prices,
            "limit_list_d": limit_events,
            "ths_member": ths_members,
            "ths_hot": ths_hot,
        }
        source_status = self._build_source_status(payloads)
        if not include_chip_snapshots:
            source_status["cyq_perf"] = "skipped"
            source_status["cyq_chips"] = "skipped"
        if not include_ths_members:
            source_status["ths_member"] = "skipped"
        ths_index_payload = theme_name_map.get("_payload") or {}
        if ths_index_payload:
            source_status["ths_index"] = str(ths_index_payload.get("status") or "unknown")
        elif not include_ths_members:
            source_status["ths_index"] = "skipped"
        hot_items = _safe_list(ths_hot.get("rows"))
        dc_theme_name_map = self._build_dc_theme_name_map(dc_concepts, dc_moneyflow)
        theme_strength = self._build_theme_strength_map(dc_concepts, dc_moneyflow)
        dc_stock_theme_map = self._build_stock_dc_theme_map(dc_members, normalized_codes, dc_theme_name_map)
        kpl_stock_theme_map = self._build_stock_kpl_theme_map(kpl_list, normalized_codes)
        raw_stock_theme_map = self._build_stock_theme_map(ths_members, normalized_codes)
        source_stock_theme_map = self._merge_stock_theme_maps(
            self._merge_stock_theme_maps(dc_stock_theme_map, kpl_stock_theme_map),
            raw_stock_theme_map,
        )
        stock_capital_theme_map = self._build_stock_capital_theme_map(
            source_stock_theme_map,
            hot_items=hot_items,
            theme_name_map={
                **dc_theme_name_map,
                **{key: value for key, value in theme_name_map.items() if key != "_payload"},
            },
        )
        stock_moneyflow = self._merge_stock_moneyflow_snapshots(
            stock_moneyflow_dc,
            stock_moneyflow_ths,
            normalized_codes,
        )
        chip_snapshots = self._merge_chip_snapshots(cyq_perf, cyq_chips, normalized_codes)
        combined_theme_members = self._merge_theme_members(
            self._merge_theme_members(self._build_theme_members(dc_members), self._build_theme_members(ths_members)),
            self._build_kpl_theme_members(kpl_list),
        )
        context = {
            "trade_date": self._display_trade_date(trade_date),
            "data_as_of": self._now_iso(),
            "is_degraded": self._is_any_degraded(payloads.values()),
            "degraded_reasons": self._collect_degraded_reasons(payloads),
            "source_status": source_status,
            "stock_theme_map": self._merge_stock_theme_maps(source_stock_theme_map, stock_capital_theme_map),
            "stock_raw_theme_map": raw_stock_theme_map,
            "stock_dc_theme_map": dc_stock_theme_map,
            "stock_kpl_theme_map": kpl_stock_theme_map,
            "stock_capital_theme_map": stock_capital_theme_map,
            "stock_moneyflow": stock_moneyflow,
            "chip_snapshots": chip_snapshots,
            "theme_members": combined_theme_members,
            "theme_name_map": {
                **dc_theme_name_map,
                **{key: value for key, value in theme_name_map.items() if key != "_payload"},
            },
            "theme_strength": theme_strength,
            "limit_events": self._index_rows_by_ts_code(limit_events),
            "limit_prices": self._index_rows_by_ts_code(limit_prices),
            "hot_items": hot_items,
            "kpl_items": _safe_list(kpl_list.get("rows")),
            "raw_sources": {**payloads, "ths_index": ths_index_payload},
        }
        logger.info(
            "Momentum V1.3 context timing: trade_date=%s variant=%s step=build_context_total elapsed_seconds=%.3f ts_code_count=%s degraded=%s",
            self._display_trade_date(trade_date),
            context_variant,
            time.perf_counter() - total_started_at,
            len(normalized_codes),
            bool(context.get("is_degraded")),
        )
        self._cache_set(context_key, context)
        return context

    def build_replay_context(
        self,
        *,
        trade_date: str,
        ts_codes: List[str],
        progress_callback: Optional[ContextProgressCallback] = None,
    ) -> Dict[str, Any]:
        """Build a replay-safe V1.3 context without using realtime quote data."""
        context = self.build_context(
            trade_date=trade_date,
            ts_codes=ts_codes,
            progress_callback=progress_callback,
        )
        replay_context = dict(context)
        replay_context["is_replay_context"] = True
        replay_context["replay_notes"] = [
            "realtime_quote is intentionally excluded from historical replay context.",
            "ths_member may use current membership if historical membership is unavailable.",
        ]
        return replay_context

    def get_intraday_snapshot(self, *, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        """Build a low-confidence quote snapshot for V1.3 intraday assist."""
        normalized_codes = self._normalize_ts_codes(ts_codes)
        rows: List[Dict[str, Any]] = []
        degraded_reasons: List[str] = []
        source_status: Dict[str, str] = {}

        for ts_code in normalized_codes:
            payload = self._load_realtime_quote(trade_date, ts_code)
            source_status[ts_code] = str(payload.get("status") or "unknown")
            if payload.get("is_degraded"):
                degraded_reasons.extend(
                    f"{ts_code}:{reason}" for reason in _safe_list(payload.get("degraded_reasons"))
                )
            rows.extend(_safe_list(payload.get("rows")))

        return {
            "label": "盘中快照辅助",
            "trade_date": self._display_trade_date(trade_date),
            "data_as_of": self._now_iso(),
            "confidence": "low",
            "is_degraded": bool(degraded_reasons),
            "degraded_reasons": degraded_reasons,
            "source_status": source_status,
            "rows": rows,
        }

    def build_mainline_radar(
        self,
        *,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any],
        previous_feedback: Optional[Dict[str, Any]] = None,
        limit: int = 2,
    ) -> List[Dict[str, Any]]:
        """Build V1.3 mainline radar items from candidates and enhanced context."""
        if not candidates:
            return []

        normalized_candidates = [self._normalize_candidate(item) for item in candidates]
        candidate_by_code = {
            item["ts_code"]: item
            for item in normalized_candidates
            if item.get("ts_code")
        }
        theme_groups = self._group_candidates_by_theme(normalized_candidates, context)
        limit_events = context.get("limit_events") or {}
        hot_by_code = self._index_hot_items_by_code(context.get("hot_items") or [])
        feedback = previous_feedback or {}

        radar_items: List[Dict[str, Any]] = []
        for theme_id, theme_payload in theme_groups.items():
            theme_candidates = theme_payload["candidates"]
            theme_member_codes = set(theme_payload["member_codes"])
            theme_candidate_codes = {item["ts_code"] for item in theme_candidates}
            theme_strength = theme_payload.get("theme_strength") or {}
            evidence = self._score_mainline_evidence(
                theme_candidates=theme_candidates,
                theme_member_codes=theme_member_codes,
                theme_candidate_codes=theme_candidate_codes,
                theme_strength=theme_strength,
                limit_events=limit_events,
                hot_by_code=hot_by_code,
                previous_feedback=feedback.get(theme_id) or feedback,
            )
            score = round(sum(item["weighted_score"] for item in evidence), 1)
            level, level_label = self._mainline_level(score)
            limit_up_count = int(next(item for item in evidence if item["key"] == "limit_strength")["raw"].get("limit_up_count", 0))
            broken_limit_count = int(next(item for item in evidence if item["key"] == "break_risk")["raw"].get("broken_limit_count", 0))
            hot_rank = self._best_hot_rank(theme_candidate_codes | theme_member_codes, hot_by_code)
            representatives = self._build_mainline_representatives(theme_candidates, candidate_by_code)
            radar_items.append(
                {
                    "theme_id": theme_id,
                    "theme_name": theme_payload["theme_name"],
                    "score": score,
                    "level": level,
                    "level_label": level_label,
                    "candidate_count": len(theme_candidates),
                    "top10_count": sum(int(item.get("rank") or 999) <= 10 for item in theme_candidates),
                    "limit_up_count": limit_up_count,
                    "broken_limit_count": broken_limit_count,
                    "hot_rank": hot_rank,
                    "net_amount": theme_strength.get("net_amount"),
                    "net_amount_rate": theme_strength.get("net_amount_rate"),
                    "board_rank": theme_strength.get("rank"),
                    "pct_change": theme_strength.get("pct_change"),
                    "up_num": theme_strength.get("up_num"),
                    "down_num": theme_strength.get("down_num"),
                    "leader_stock": theme_strength.get("leading"),
                    "data_sources": theme_strength.get("sources") or [],
                    "representatives": representatives,
                    "source_theme_names": sorted(
                        set(theme_payload.get("source_theme_names") or [])
                        | set(theme_strength.get("source_theme_names") or [])
                    )[:8],
                    "evidence": [
                        {
                            "key": item["key"],
                            "label": item["label"],
                            "level": item["level"],
                            "score": round(item["weighted_score"], 1),
                            "raw_score": round(item["raw_score"], 1),
                            "summary": item["summary"],
                            "raw": item["raw"],
                        }
                        for item in evidence
                    ],
                    "is_degraded": bool(context.get("is_degraded")),
                    "degraded_reasons": list(context.get("degraded_reasons") or []),
                    "summary": (
                        f"{theme_payload['theme_name']} 聚集 {len(theme_candidates)} 只候选，"
                        f"Top10 有 {sum(int(item.get('rank') or 999) <= 10 for item in theme_candidates)} 只，"
                        f"主线强度为{level_label}。"
                    ),
                }
            )

        radar_items.sort(
            key=lambda item: (
                item["score"],
                item["candidate_count"],
                item["top10_count"],
                -int(item.get("hot_rank") or 9999),
            ),
            reverse=True,
        )
        return radar_items[: max(1, limit)]

    def build_short_term_sentiment(
        self,
        *,
        mainline_radar: List[Dict[str, Any]],
        context: Dict[str, Any],
        previous_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the V1.3 short-term sentiment module used by the gate layer."""
        limit_events = context.get("limit_events") or {}
        hot_items = context.get("hot_items") or []
        feedback = previous_feedback or {}

        limit_module = self._sentiment_limit_strength(limit_events)
        break_module = self._sentiment_break_risk(limit_events)
        mainline_module = self._sentiment_mainline_clarity(mainline_radar)
        hot_module = self._sentiment_hot_concentration(hot_items, mainline_radar)
        feedback_module = self._sentiment_previous_feedback(feedback)
        modules = [limit_module, break_module, mainline_module, hot_module, feedback_module]
        score = round(
            limit_module["score"] * 0.30
            + break_module["score"] * 0.20
            + mainline_module["score"] * 0.25
            + hot_module["score"] * 0.15
            + feedback_module["score"] * 0.10,
            1,
        )
        level, label = self._sentiment_level(score)
        confidence = "low" if context.get("is_degraded") else "medium"
        if not context.get("is_degraded") and len(hot_items) > 0 and bool(limit_events):
            confidence = "high"
        return {
            "level": level,
            "label": label,
            "score": score,
            "summary": self._sentiment_summary(label, modules),
            "modules": modules,
            "confidence": confidence,
            "is_degraded": bool(context.get("is_degraded")),
            "degraded_reasons": list(context.get("degraded_reasons") or []),
        }

    def _load_limit_prices(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("stk_limit", trade_date)
        cached = self._cache_get(key, self._resource_ttls["stk_limit"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("stk_limit", lambda: self.fetcher.get_stock_limit_prices(trade_date))
        self._cache_set(key, payload)
        return payload

    def _load_limit_events(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("limit_list_d", trade_date)
        cached = self._cache_get(key, self._resource_ttls["limit_list_d"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("limit_list_d", lambda: self.fetcher.get_limit_list(trade_date))
        self._cache_set(key, payload)
        return payload

    def _load_dc_concepts(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("dc_concept", trade_date)
        cached = self._cache_get(key, self._resource_ttls["dc_concept"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("dc_concept", lambda: self.fetcher.get_dc_concepts(trade_date))
        self._cache_set(key, payload)
        return payload

    def _load_dc_moneyflow(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("dc_moneyflow", trade_date)
        cached = self._cache_get(key, self._resource_ttls["dc_moneyflow"])
        if cached is not None:
            return cached

        rows: List[Dict[str, Any]] = []
        source_status: Dict[str, str] = {}
        degraded_reasons: List[str] = []
        for content_type in ("概念", "行业"):
            payload = self._safe_fetch(
                f"moneyflow_ind_dc:{content_type}",
                lambda value=content_type: self.fetcher.get_dc_moneyflow_themes(
                    trade_date,
                    content_type=value,
                ),
            )
            source_status[content_type] = str(payload.get("status") or "unknown")
            rows.extend(_safe_list(payload.get("rows")))
            if payload.get("is_degraded"):
                degraded_reasons.extend(
                    f"{content_type}:{reason}" for reason in _safe_list(payload.get("degraded_reasons"))
                )

        status = "ok"
        if degraded_reasons:
            status = "partial" if rows else "unavailable"
        result = self._payload(
            source="tushare.moneyflow_ind_dc",
            trade_date=self._display_trade_date(trade_date),
            rows=rows,
            status=status,
            degraded_reasons=degraded_reasons,
            extra={"source_status": source_status},
        )
        self._cache_set(key, result)
        return result

    def _load_dc_members(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        fetch_method = self._resolve_fetcher_method("get_dc_members")
        if fetch_method is None:
            return self._payload(
                source="tushare.dc_member",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
                status="unavailable",
                degraded_reasons=["method_not_supported"],
            )
        snapshot = self._load_paginated_resource(
            resource="dc_member",
            trade_date=trade_date,
            cache_parts=[trade_date, "snapshot"],
            ttl_seconds=self._resource_ttls["dc_member"],
            fetch_page_fn=lambda limit, offset: fetch_method(trade_date, limit=limit, offset=offset),
        )
        filtered = self._filter_rows_by_codes(snapshot, ts_codes, field_names=("con_code",))
        filtered["source_status"] = {ts_code: str(snapshot.get("status") or "unknown") for ts_code in ts_codes}
        return filtered

    def _load_stock_moneyflow_dc(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        key = self._cache_key("stock_moneyflow_dc", trade_date)
        cached = self._cache_get(key, self._resource_ttls["stock_moneyflow_dc"])
        if cached is None:
            fetch_method = self._resolve_fetcher_method("get_stock_moneyflow_dc")
            if fetch_method is None:
                cached = self._payload(
                    source="tushare.moneyflow_dc",
                    trade_date=self._display_trade_date(trade_date),
                    rows=[],
                    status="unavailable",
                    degraded_reasons=["method_not_supported"],
                )
            else:
                cached = self._safe_fetch("moneyflow_dc", lambda: fetch_method(trade_date))
            self._cache_set(key, cached)
        return self._filter_rows_by_ts_codes(cached, ts_codes)

    def _load_stock_moneyflow_ths(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        key = self._cache_key("stock_moneyflow_ths", trade_date)
        cached = self._cache_get(key, self._resource_ttls["stock_moneyflow_ths"])
        if cached is None:
            fetch_method = self._resolve_fetcher_method("get_stock_moneyflow_ths")
            if fetch_method is None:
                cached = self._payload(
                    source="tushare.moneyflow_ths",
                    trade_date=self._display_trade_date(trade_date),
                    rows=[],
                    status="unavailable",
                    degraded_reasons=["method_not_supported"],
                )
            else:
                cached = self._safe_fetch("moneyflow_ths", lambda: fetch_method(trade_date))
            self._cache_set(key, cached)
        return self._filter_rows_by_ts_codes(cached, ts_codes)

    def _load_cyq_perf(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        fetch_method = self._resolve_fetcher_method("get_cyq_perf")
        if fetch_method is None:
            return self._payload(
                source="tushare.cyq_perf",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
                status="unavailable",
                degraded_reasons=["method_not_supported"],
            )
        snapshot = self._load_paginated_resource(
            resource="cyq_perf",
            trade_date=trade_date,
            cache_parts=[trade_date, "snapshot"],
            ttl_seconds=self._resource_ttls["cyq_perf"],
            fetch_page_fn=lambda limit, offset: fetch_method(trade_date, limit=limit, offset=offset),
        )
        filtered_snapshot = self._filter_rows_by_codes(snapshot, ts_codes, field_names=("ts_code",))
        grouped_snapshot = self._group_rows_by_fields(filtered_snapshot, ("ts_code",))
        rows: List[Dict[str, Any]] = list(_safe_list(filtered_snapshot.get("rows")))
        source_status: Dict[str, str] = {}
        degraded_reasons: List[str] = []
        for ts_code in ts_codes:
            if grouped_snapshot.get(ts_code):
                source_status[ts_code] = "ok"
                continue
            key = self._cache_key("cyq_perf", trade_date, ts_code)
            cached = self._cache_get(key, self._resource_ttls["cyq_perf"])
            if cached is None:
                cached = self._safe_fetch("cyq_perf", lambda code=ts_code: fetch_method(trade_date, ts_code=code))
                self._cache_set(key, cached)
            source_status[ts_code] = str(cached.get("status") or "unknown")
            rows.extend(_safe_list(cached.get("rows")))
            if cached.get("is_degraded"):
                degraded_reasons.extend(f"{ts_code}:{reason}" for reason in _safe_list(cached.get("degraded_reasons")))
        status = "ok"
        if degraded_reasons:
            status = "partial" if rows else "unavailable"
        return self._payload(
            source="tushare.cyq_perf",
            trade_date=self._display_trade_date(trade_date),
            rows=rows,
            status=status,
            degraded_reasons=degraded_reasons,
            extra={"source_status": source_status},
        )

    def _load_cyq_chips(self, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        source_status: Dict[str, str] = {}
        degraded_reasons: List[str] = []
        fetch_method = self._resolve_fetcher_method("get_cyq_chips")
        if fetch_method is None:
            return self._payload(
                source="tushare.cyq_chips",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
                status="unavailable",
                degraded_reasons=["method_not_supported"],
            )
        for ts_code in ts_codes:
            key = self._cache_key("cyq_chips", trade_date, ts_code)
            cached = self._cache_get(key, self._resource_ttls["cyq_chips"])
            if cached is None:
                cached = self._safe_fetch("cyq_chips", lambda code=ts_code: fetch_method(trade_date, ts_code=code))
                self._cache_set(key, cached)
            source_status[ts_code] = str(cached.get("status") or "unknown")
            rows.extend(_safe_list(cached.get("rows")))
            if cached.get("is_degraded"):
                degraded_reasons.extend(f"{ts_code}:{reason}" for reason in _safe_list(cached.get("degraded_reasons")))

        status = "ok"
        if degraded_reasons:
            status = "partial" if rows else "unavailable"
        return self._payload(
            source="tushare.cyq_chips",
            trade_date=self._display_trade_date(trade_date),
            rows=rows,
            status=status,
            degraded_reasons=degraded_reasons,
            extra={"source_status": source_status},
        )

    def _load_kpl_list(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("kpl_list", trade_date)
        cached = self._cache_get(key, self._resource_ttls["kpl_list"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("kpl_list", lambda: self.fetcher.get_kpl_list(trade_date, tag="涨停"))
        self._cache_set(key, payload)
        return payload

    def _load_ths_hot(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("ths_hot", trade_date)
        cached = self._cache_get(key, self._resource_ttls["ths_hot"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("ths_hot", lambda: self.fetcher.get_ths_hot(trade_date))
        self._cache_set(key, payload)
        return payload

    def _load_ths_members(self, ts_codes: List[str]) -> Dict[str, Any]:
        fetch_method = self._resolve_fetcher_method("get_ths_members")
        if fetch_method is None:
            return self._payload(
                source="tushare.ths_member",
                trade_date=None,
                rows=[],
                status="unavailable",
                degraded_reasons=["method_not_supported"],
            )
        snapshot = self._load_paginated_resource(
            resource="ths_member",
            trade_date=None,
            cache_parts=["snapshot"],
            ttl_seconds=self._resource_ttls["ths_member"],
            fetch_page_fn=lambda limit, offset: fetch_method(limit=limit, offset=offset),
        )
        filtered = self._filter_rows_by_codes(snapshot, ts_codes, field_names=("con_code",))
        filtered["source_status"] = {ts_code: str(snapshot.get("status") or "unknown") for ts_code in ts_codes}
        return filtered

    def _load_ths_index_names(self, ths_members: Dict[str, Any]) -> Dict[str, Any]:
        theme_codes = sorted(
            {
                str(row.get("theme_code") or row.get("ths_code") or "").strip().upper()
                for row in _safe_list(ths_members.get("rows"))
                if self._is_ths_theme_code(row.get("theme_code") or row.get("ths_code"))
            }
        )
        result: Dict[str, Any] = {}
        if not theme_codes:
            result["_payload"] = self._payload(
                source="tushare.ths_index",
                trade_date=None,
                rows=[],
                status="ok",
                degraded_reasons=[],
                extra={"source_status": {}},
            )
            return result
        fetch_method = self._resolve_fetcher_method("get_ths_index")
        if fetch_method is None:
            result["_payload"] = self._payload(
                source="tushare.ths_index",
                trade_date=None,
                rows=[],
                status="unavailable",
                degraded_reasons=["method_not_supported"],
                extra={"source_status": {theme_code: "unavailable" for theme_code in theme_codes}},
            )
            return result
        snapshot = self._load_paginated_resource(
            resource="ths_index",
            trade_date=None,
            cache_parts=["snapshot"],
            ttl_seconds=self._resource_ttls["ths_index"],
            fetch_page_fn=lambda limit, offset: fetch_method(limit=limit, offset=offset),
        )
        filtered_snapshot = self._filter_rows_by_codes(snapshot, theme_codes, field_names=("theme_code",))
        rows = _safe_list(filtered_snapshot.get("rows"))
        for row in rows:
            code = str(row.get("theme_code") or "").strip().upper()
            name = str(row.get("theme_name") or "").strip()
            if code and name:
                result[code] = name
        result["_payload"] = self._payload(
            source="tushare.ths_index",
            trade_date=None,
            rows=rows,
            status=str(snapshot.get("status") or "unknown"),
            degraded_reasons=list(_safe_list(snapshot.get("degraded_reasons"))),
            extra={"source_status": {theme_code: str(snapshot.get("status") or "unknown") for theme_code in theme_codes}},
        )
        return result

    def _load_realtime_quote(self, trade_date: str, ts_code: str) -> Dict[str, Any]:
        key = self._cache_key("realtime_quote", trade_date, ts_code)
        cached = self._cache_get(key, self._resource_ttls["realtime_quote"])
        if cached is not None:
            return cached
        try:
            quote = self.fetcher.get_realtime_quote(ts_code)
        except Exception as exc:
            payload = self._payload(
                source="realtime_quote",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
                status="unavailable",
                degraded_reasons=[str(exc)],
            )
            self._cache_set(key, payload)
            return payload

        if quote is None:
            payload = self._payload(
                source="realtime_quote",
                trade_date=self._display_trade_date(trade_date),
                rows=[],
                status="unavailable",
                degraded_reasons=["empty_result"],
            )
            self._cache_set(key, payload)
            return payload

        if hasattr(quote, "to_dict"):
            row = quote.to_dict()
        else:
            row = dict(quote)
        row.setdefault("ts_code", ts_code)
        row.setdefault("data_source", row.get("source") or "realtime_quote")
        row["data_as_of"] = self._now_iso()
        payload = self._payload(
            source="realtime_quote",
            trade_date=self._display_trade_date(trade_date),
            rows=[row],
        )
        self._cache_set(key, payload)
        return payload

    @staticmethod
    def _normalize_ts_code(ts_code: str) -> str:
        text = str(ts_code or "").strip().upper()
        if not text:
            return ""
        if "." in text:
            return text.replace(".SS", ".SH")
        code = normalize_stock_code(text)
        if code.startswith(("600", "601", "603", "605", "688", "510", "511", "512", "513", "515", "516", "517", "518", "588")):
            return f"{code}.SH"
        if code.startswith(("000", "001", "002", "003", "300", "159")):
            return f"{code}.SZ"
        if code.startswith(("4", "8", "920")):
            return f"{code}.BJ"
        return code

    @classmethod
    def _normalize_ts_codes(cls, ts_codes: Iterable[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for ts_code in ts_codes:
            value = cls._normalize_ts_code(ts_code)
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        return normalized

    @staticmethod
    def _display_trade_date(value: str) -> str:
        text = str(value or "").strip()
        compact = text.replace("-", "").replace("/", "")
        if len(compact) == 8 and compact.isdigit():
            return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        return text

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _cache_get(self, key: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
        effective_ttl = self._effective_cache_ttl(key, ttl_seconds)
        entry = self._resource_cache.get(key)
        if entry is not None:
            age = time.time() - float(entry.get("stored_at", 0))
            if effective_ttl >= 0 and age > effective_ttl:
                self.__class__._shared_cache_stats["expired"] += 1
                self._resource_cache.pop(key, None)
            else:
                self.__class__._shared_cache_stats["hit"] += 1
                return entry.get("value")

        disk_entry = self._read_disk_cache_entry(key, effective_ttl)
        if disk_entry is not None:
            self._resource_cache[key] = disk_entry
            self.__class__._shared_cache_stats["hit"] += 1
            self.__class__._shared_cache_stats["disk_hit"] += 1
            return disk_entry.get("value")

        self.__class__._shared_cache_stats["miss"] += 1
        if self._should_use_disk_cache(key):
            self.__class__._shared_cache_stats["disk_miss"] += 1
        return None

    def _cache_set(self, key: str, value: Dict[str, Any]) -> None:
        entry = {"stored_at": time.time(), "value": value}
        self._resource_cache[key] = entry
        self._write_disk_cache_entry(key, entry)

    @staticmethod
    def _cache_key(resource: str, *parts: str) -> str:
        normalized_parts = [str(part or "").replace("/", "-") for part in parts]
        return ":".join(["momentum", "v13", resource, *normalized_parts])

    def _effective_cache_ttl(self, key: str, ttl_seconds: int) -> int:
        if self._cache_resource_name(key) == "realtime_quote":
            return ttl_seconds
        if self._cache_key_has_historical_trade_date(key):
            return max(ttl_seconds, self.__class__._HISTORICAL_RESOURCE_TTL_SECONDS)
        return ttl_seconds

    @staticmethod
    def _cache_resource_name(key: str) -> str:
        parts = str(key or "").split(":")
        return parts[2] if len(parts) >= 3 else ""

    def _cache_key_has_historical_trade_date(self, key: str) -> bool:
        for part in str(key or "").split(":")[3:]:
            compact = part.replace("-", "").replace("/", "")
            if len(compact) != 8 or not compact.isdigit():
                continue
            try:
                trade_day = datetime.strptime(compact, "%Y%m%d").date()
            except ValueError:
                continue
            return trade_day < datetime.now().date()
        return False

    def _should_use_disk_cache(self, key: str) -> bool:
        if not self._enable_disk_cache:
            return False
        if self._cache_resource_name(key) == "realtime_quote":
            return False
        return True

    def _disk_cache_path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self._disk_cache_dir / digest[:2] / f"{digest}.json"

    def _read_disk_cache_entry(self, key: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
        if not self._should_use_disk_cache(key):
            return None
        path = self._disk_cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:  # pragma: no cover - corrupted cache should never block screening
            logger.debug("Momentum V1.3 disk cache read failed for %s: %s", key, exc)
            self.__class__._shared_cache_stats["disk_error"] += 1
            return None
        if payload.get("version") != self.__class__._DISK_CACHE_VERSION or payload.get("key") != key:
            self.__class__._shared_cache_stats["disk_error"] += 1
            return None
        stored_at = float(payload.get("stored_at", 0) or 0)
        if ttl_seconds >= 0 and time.time() - stored_at > ttl_seconds:
            self.__class__._shared_cache_stats["disk_expired"] += 1
            try:
                path.unlink()
            except OSError:
                pass
            return None
        value = payload.get("value")
        if not isinstance(value, dict):
            self.__class__._shared_cache_stats["disk_error"] += 1
            return None
        return {"stored_at": stored_at, "value": value}

    def _write_disk_cache_entry(self, key: str, entry: Dict[str, Any]) -> None:
        if not self._should_use_disk_cache(key):
            return
        path = self._disk_cache_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name(f"{path.name}.{time.time_ns()}.tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": self.__class__._DISK_CACHE_VERSION,
                        "key": key,
                        "stored_at": entry.get("stored_at", time.time()),
                        "value": entry.get("value"),
                    },
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            tmp_path.replace(path)
        except Exception as exc:  # pragma: no cover - cache writes are best-effort
            logger.debug("Momentum V1.3 disk cache write failed for %s: %s", key, exc)
            self.__class__._shared_cache_stats["disk_error"] += 1

    def _load_paginated_resource(
        self,
        *,
        resource: str,
        trade_date: Optional[str],
        cache_parts: List[str],
        ttl_seconds: int,
        fetch_page_fn,
    ) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        source_status: Dict[str, str] = {}
        degraded_reasons: List[str] = []
        status = "ok"
        page_count = 0

        for page_index in range(self._MAX_SNAPSHOT_PAGES):
            offset = page_index * self._SNAPSHOT_PAGE_SIZE
            page_key = self._cache_key(resource, *cache_parts, f"offset-{offset}")
            cached = self._cache_get(page_key, ttl_seconds)
            if cached is None:
                cached = self._safe_fetch(
                    resource,
                    lambda current_offset=offset: fetch_page_fn(limit=self._SNAPSHOT_PAGE_SIZE, offset=current_offset),
                )
                self._cache_set(page_key, cached)
            source_status[f"page_{page_index}"] = str(cached.get("status") or "unknown")
            payload_rows = _safe_list(cached.get("rows"))
            if not payload_rows:
                if page_index > 0 and self._is_pagination_terminator(cached):
                    break
                if cached.get("is_degraded"):
                    status = "partial" if rows else str(cached.get("status") or "partial")
                    degraded_reasons.extend(
                        f"page_{page_index}:{reason}" for reason in _safe_list(cached.get("degraded_reasons"))
                    )
                elif not rows:
                    status = str(cached.get("status") or "partial")
                break

            rows.extend(payload_rows)
            page_count = page_index + 1
            if cached.get("is_degraded"):
                degraded_reasons.extend(
                    f"page_{page_index}:{reason}" for reason in _safe_list(cached.get("degraded_reasons"))
                )
            if len(payload_rows) < self._SNAPSHOT_PAGE_SIZE:
                break
        else:
            degraded_reasons.append("pagination_limit_reached")
            status = "partial" if rows else "unavailable"

        if degraded_reasons and status == "ok":
            status = "partial" if rows else "unavailable"
        return self._payload(
            source=f"tushare.{resource}",
            trade_date=self._display_trade_date(trade_date) if trade_date else None,
            rows=rows,
            status=status,
            degraded_reasons=degraded_reasons,
            extra={"source_status": source_status, "page_count": page_count},
        )

    @staticmethod
    def _is_pagination_terminator(payload: Dict[str, Any]) -> bool:
        if _safe_list(payload.get("rows")):
            return False
        if str(payload.get("status") or "").strip().lower() != "partial":
            return False
        reasons = [str(reason).strip() for reason in _safe_list(payload.get("degraded_reasons")) if str(reason).strip()]
        return reasons == ["empty_result"]

    def _safe_fetch(self, source: str, fetch_fn) -> Dict[str, Any]:
        try:
            payload = fetch_fn()
        except Exception as exc:
            logger.warning("V1.3 data fetch failed for %s: %s", source, exc)
            return self._payload(
                source=source,
                trade_date=None,
                rows=[],
                status="unavailable",
                degraded_reasons=[str(exc)],
            )
        if isinstance(payload, dict):
            return payload
        return self._payload(
            source=source,
            trade_date=None,
            rows=[],
            status="unavailable",
            degraded_reasons=["invalid_payload"],
        )

    def _payload(
        self,
        *,
        source: str,
        trade_date: Optional[str],
        rows: List[Dict[str, Any]],
        status: str = "ok",
        degraded_reasons: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        reasons = degraded_reasons or []
        payload = {
            "source": source,
            "status": status,
            "trade_date": trade_date,
            "data_as_of": self._now_iso(),
            "is_degraded": status != "ok" or bool(reasons),
            "degraded_reasons": reasons,
            "rows": rows,
        }
        if extra:
            payload.update(extra)
        return payload

    @staticmethod
    def _is_any_degraded(payloads: Iterable[Dict[str, Any]]) -> bool:
        return any(bool(payload.get("is_degraded")) for payload in payloads)

    @staticmethod
    def _collect_degraded_reasons(payloads: Dict[str, Dict[str, Any]]) -> List[str]:
        reasons: List[str] = []
        for key, payload in payloads.items():
            for reason in _safe_list(payload.get("degraded_reasons")):
                reasons.append(f"{key}:{reason}")
        return reasons

    @staticmethod
    def _build_source_status(payloads: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        return {key: str(payload.get("status") or "unknown") for key, payload in payloads.items()}

    @staticmethod
    def _index_rows_by_ts_code(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        return MomentumV13DataService._group_rows_by_fields(payload, ("ts_code",))

    @staticmethod
    def _group_rows_by_fields(
        payload: Dict[str, Any],
        field_names: Iterable[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in _safe_list(payload.get("rows")):
            for field_name in field_names:
                code = str(row.get(field_name) or "").strip().upper()
                if not code:
                    continue
                grouped.setdefault(code, []).append(row)
                break
        return grouped

    def _filter_rows_by_ts_codes(self, payload: Dict[str, Any], ts_codes: List[str]) -> Dict[str, Any]:
        return self._filter_rows_by_codes(payload, ts_codes, field_names=("ts_code", "con_code"))

    def _filter_rows_by_codes(
        self,
        payload: Dict[str, Any],
        codes: List[str],
        *,
        field_names: Iterable[str],
    ) -> Dict[str, Any]:
        normalized_codes = {str(code).strip().upper() for code in codes if str(code).strip()}
        rows = []
        for row in _safe_list(payload.get("rows")):
            for field_name in field_names:
                value = str(row.get(field_name) or "").strip().upper()
                if not value:
                    continue
                if value in normalized_codes:
                    rows.append(row)
                    break
        filtered = dict(payload)
        filtered["rows"] = rows
        return filtered

    def _resolve_fetcher_method(self, name: str):
        fetcher_dict = getattr(self.fetcher, "__dict__", {})
        if isinstance(fetcher_dict, dict) and name in fetcher_dict:
            method = getattr(self.fetcher, name, None)
            if callable(method):
                return method
        if hasattr(type(self.fetcher), name):
            method = getattr(self.fetcher, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _build_stock_theme_map(ths_members: Dict[str, Any], ts_codes: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {ts_code: [] for ts_code in ts_codes}
        for row in _safe_list(ths_members.get("rows")):
            con_code = str(row.get("con_code") or "")
            if not con_code:
                continue
            result.setdefault(con_code, []).append(row)
        return result

    @staticmethod
    def _build_theme_members(ths_members: Dict[str, Any]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for row in _safe_list(ths_members.get("rows")):
            theme_code = str(row.get("theme_code") or "")
            con_code = str(row.get("con_code") or "")
            if not theme_code or not con_code:
                continue
            members = result.setdefault(theme_code, [])
            if con_code not in members:
                members.append(con_code)
        return result

    @staticmethod
    def _merge_theme_members(
        primary: Dict[str, List[str]],
        secondary: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        merged = {key: list(values) for key, values in primary.items()}
        for theme_code, values in secondary.items():
            members = merged.setdefault(theme_code, [])
            for value in values:
                if value not in members:
                    members.append(value)
        return merged

    @staticmethod
    def _build_dc_theme_name_map(dc_concepts: Dict[str, Any], dc_moneyflow: Dict[str, Any]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for payload in (dc_concepts, dc_moneyflow):
            for row in _safe_list(payload.get("rows")):
                theme_code = str(row.get("theme_code") or row.get("ts_code") or "").strip().upper()
                theme_name = str(row.get("theme_name") or row.get("name") or "").strip()
                if theme_code and theme_name:
                    result[theme_code] = theme_name
        return result

    @classmethod
    def _build_stock_dc_theme_map(
        cls,
        dc_members: Dict[str, Any],
        ts_codes: List[str],
        dc_theme_name_map: Dict[str, str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {ts_code: [] for ts_code in ts_codes}
        for row in _safe_list(dc_members.get("rows")):
            con_code = str(row.get("con_code") or "").strip().upper()
            theme_code = str(row.get("theme_code") or row.get("ts_code") or "").strip().upper()
            if not con_code or not theme_code:
                continue
            theme_name = str(dc_theme_name_map.get(theme_code) or row.get("theme_name") or theme_code).strip()
            child_theme_names = [theme_name] if theme_name and theme_name != theme_code else []
            result.setdefault(con_code, []).append(
                {
                    "theme_code": theme_code,
                    "theme_name": theme_name,
                    "source": "dc_member",
                    "con_code": con_code,
                    "con_name": row.get("con_name") or row.get("name"),
                    "child_theme_names": child_theme_names,
                }
            )
            for theme_id, parent_name in cls._capital_theme_refs_from_texts([theme_name, row.get("con_name") or row.get("name")]):
                result[con_code].append(
                    {
                        "theme_code": theme_id,
                        "theme_name": parent_name,
                        "source": "capital_theme",
                        "con_code": con_code,
                        "child_theme_names": child_theme_names,
                    }
                )
        return result

    @classmethod
    def _build_stock_kpl_theme_map(
        cls,
        kpl_list: Dict[str, Any],
        ts_codes: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {ts_code: [] for ts_code in ts_codes}
        for row in _safe_list(kpl_list.get("rows")):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if not ts_code:
                continue
            theme_texts = cls._split_theme_text(row.get("theme"))
            if not theme_texts and row.get("lu_desc"):
                theme_texts = cls._split_theme_text(row.get("lu_desc"))
            for theme_name in theme_texts:
                theme_code = f"kpl:{theme_name}"
                result.setdefault(ts_code, []).append(
                    {
                        "theme_code": theme_code,
                        "theme_name": theme_name,
                        "source": "kpl_list",
                        "con_code": ts_code,
                        "con_name": row.get("name"),
                        "lu_desc": row.get("lu_desc"),
                        "child_theme_names": [theme_name],
                    }
                )
            for theme_id, parent_name in cls._capital_theme_refs_from_texts([*theme_texts, row.get("name"), row.get("lu_desc")]):
                result.setdefault(ts_code, []).append(
                    {
                        "theme_code": theme_id,
                        "theme_name": parent_name,
                        "source": "capital_theme",
                        "con_code": ts_code,
                        "con_name": row.get("name"),
                        "child_theme_names": theme_texts,
                    }
                )
        return result

    @classmethod
    def _build_kpl_theme_members(cls, kpl_list: Dict[str, Any]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for row in _safe_list(kpl_list.get("rows")):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if not ts_code:
                continue
            for theme_name in cls._split_theme_text(row.get("theme")):
                theme_code = f"kpl:{theme_name}"
                result.setdefault(theme_code, [])
                if ts_code not in result[theme_code]:
                    result[theme_code].append(ts_code)
        return result

    @classmethod
    def _build_theme_strength_map(
        cls,
        dc_concepts: Dict[str, Any],
        dc_moneyflow: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}

        def ensure_entry(theme_code: str, theme_name: str, source: str) -> Dict[str, Any]:
            entry = result.setdefault(
                theme_code,
                {
                    "theme_code": theme_code,
                    "theme_name": theme_name or theme_code,
                    "source": source,
                    "sources": set(),
                    "source_theme_names": set(),
                    "net_amount": 0.0,
                    "net_amount_rate": None,
                    "rank": None,
                    "pct_change": None,
                    "up_num": None,
                    "down_num": None,
                    "turnover_rate": None,
                    "leading": "",
                    "leading_code": "",
                },
            )
            entry["sources"].add(source)
            if theme_name:
                entry["source_theme_names"].add(theme_name)
            return entry

        for row in _safe_list(dc_concepts.get("rows")):
            theme_code = str(row.get("theme_code") or row.get("ts_code") or "").strip().upper()
            theme_name = str(row.get("theme_name") or row.get("name") or theme_code).strip()
            if not theme_code:
                continue
            entry = ensure_entry(theme_code, theme_name, "dc_concept")
            entry["pct_change"] = cls._prefer_float(entry.get("pct_change"), row.get("pct_change"))
            entry["up_num"] = row.get("up_num")
            entry["down_num"] = row.get("down_num")
            entry["turnover_rate"] = cls._prefer_float(entry.get("turnover_rate"), row.get("turnover_rate"))
            entry["leading"] = row.get("leading") or entry.get("leading") or ""
            entry["leading_code"] = row.get("leading_code") or entry.get("leading_code") or ""

        for row in _safe_list(dc_moneyflow.get("rows")):
            theme_code = str(row.get("theme_code") or row.get("ts_code") or row.get("name") or "").strip().upper()
            theme_name = str(row.get("theme_name") or row.get("name") or theme_code).strip()
            if not theme_code:
                continue
            entry = ensure_entry(theme_code, theme_name, "moneyflow_ind_dc")
            entry["net_amount"] = float(entry.get("net_amount") or 0.0) + cls._safe_float_like(row.get("net_amount"))
            entry["net_amount_rate"] = cls._prefer_float(entry.get("net_amount_rate"), row.get("net_amount_rate"))
            entry["rank"] = cls._min_rank(entry.get("rank"), row.get("rank"))
            entry["pct_change"] = cls._prefer_float(entry.get("pct_change"), row.get("pct_change"))

        parent_accumulator: Dict[str, Dict[str, Any]] = {}
        for entry in list(result.values()):
            parent_refs = cls._capital_theme_refs_from_texts([entry.get("theme_name")])
            for parent_id, parent_name in parent_refs:
                parent = parent_accumulator.setdefault(
                    parent_id,
                    {
                        "theme_code": parent_id,
                        "theme_name": parent_name,
                        "source": "theme_strength_provider",
                        "sources": set(),
                        "source_theme_names": set(),
                        "net_amount": 0.0,
                        "net_amount_rate": None,
                        "rank": None,
                        "pct_change": None,
                        "up_num": 0,
                        "down_num": 0,
                        "turnover_rate": None,
                        "leading": "",
                        "leading_code": "",
                    },
                )
                parent["sources"].update(entry.get("sources") or [])
                parent["source_theme_names"].update(entry.get("source_theme_names") or [])
                parent["net_amount"] = float(parent.get("net_amount") or 0.0) + float(entry.get("net_amount") or 0.0)
                parent["net_amount_rate"] = cls._prefer_float(parent.get("net_amount_rate"), entry.get("net_amount_rate"))
                parent["rank"] = cls._min_rank(parent.get("rank"), entry.get("rank"))
                parent["pct_change"] = cls._prefer_float(parent.get("pct_change"), entry.get("pct_change"))
                parent["turnover_rate"] = cls._prefer_float(parent.get("turnover_rate"), entry.get("turnover_rate"))
                parent["up_num"] = int(parent.get("up_num") or 0) + int(entry.get("up_num") or 0)
                parent["down_num"] = int(parent.get("down_num") or 0) + int(entry.get("down_num") or 0)
                if not parent.get("leading") and entry.get("leading"):
                    parent["leading"] = entry.get("leading")
                    parent["leading_code"] = entry.get("leading_code")

        result.update(parent_accumulator)
        for entry in result.values():
            entry["sources"] = sorted(str(item) for item in entry.get("sources") or [])
            entry["source_theme_names"] = sorted(str(item) for item in entry.get("source_theme_names") or [])[:12]
            entry["fund_strength_score"] = cls._theme_fund_strength_score(entry)
        return result

    @classmethod
    def _build_stock_capital_theme_map(
        cls,
        stock_theme_map: Dict[str, List[Dict[str, Any]]],
        *,
        hot_items: List[Dict[str, Any]],
        theme_name_map: Dict[str, str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        hot_concepts_by_code: Dict[str, List[str]] = {}
        for row in hot_items:
            ts_code = str(row.get("ts_code") or "").strip()
            if not ts_code:
                continue
            hot_concepts_by_code.setdefault(ts_code, []).extend(
                str(concept).strip()
                for concept in _safe_list(row.get("concepts"))
                if str(concept).strip()
            )

        result: Dict[str, List[Dict[str, Any]]] = {}
        for ts_code, rows in stock_theme_map.items():
            texts: List[str] = []
            child_theme_names: List[str] = []
            for row in rows:
                theme_code = str(row.get("theme_code") or row.get("ths_code") or "").strip().upper()
                raw_name = str(row.get("theme_name") or row.get("ths_name") or "").strip()
                mapped_name = str(theme_name_map.get(theme_code) or "").strip()
                for text in (mapped_name, raw_name, theme_code):
                    if text:
                        texts.append(text)
                display_name = mapped_name or raw_name
                if display_name and display_name not in child_theme_names:
                    child_theme_names.append(display_name)
            texts.extend(hot_concepts_by_code.get(ts_code) or [])

            capital_refs = cls._capital_theme_refs_from_texts(texts)
            if not capital_refs:
                continue
            result[ts_code] = [
                {
                    "theme_code": theme_id,
                    "theme_name": theme_name,
                    "source": "capital_theme",
                    "child_theme_names": child_theme_names,
                }
                for theme_id, theme_name in capital_refs
            ]
        return result

    @staticmethod
    def _merge_stock_theme_maps(
        primary: Dict[str, List[Dict[str, Any]]],
        secondary: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        merged = {key: list(rows) for key, rows in primary.items()}
        for ts_code, rows in secondary.items():
            merged.setdefault(ts_code, []).extend(rows)
        return merged

    @classmethod
    def _merge_stock_moneyflow_snapshots(
        cls,
        dc_payload: Dict[str, Any],
        ths_payload: Dict[str, Any],
        ts_codes: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        dc_rows = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in _safe_list(dc_payload.get("rows"))
            if str(row.get("ts_code") or "").strip()
        }
        ths_rows = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in _safe_list(ths_payload.get("rows"))
            if str(row.get("ts_code") or "").strip()
        }
        merged: Dict[str, Dict[str, Any]] = {}
        for ts_code in ts_codes:
            normalized_code = str(ts_code).strip().upper()
            dc_row = dc_rows.get(normalized_code) or {}
            ths_row = ths_rows.get(normalized_code) or {}
            if not dc_row and not ths_row:
                continue
            net_amount = cls._prefer_float(dc_row.get("net_amount"), ths_row.get("net_amount"))
            net_amount_rate = cls._prefer_float(
                dc_row.get("net_amount_rate"),
                ths_row.get("buy_lg_amount_rate"),
            )
            merged[normalized_code] = {
                "ts_code": normalized_code,
                "close": cls._prefer_float(dc_row.get("close"), ths_row.get("close")),
                "pct_change": cls._prefer_float(dc_row.get("pct_change"), ths_row.get("pct_change")),
                "net_amount": net_amount,
                "net_amount_rate": net_amount_rate,
                "net_d5_amount": cls._prefer_float(None, ths_row.get("net_d5_amount")),
                "buy_elg_amount": cls._prefer_float(None, dc_row.get("buy_elg_amount")),
                "buy_elg_amount_rate": cls._prefer_float(None, dc_row.get("buy_elg_amount_rate")),
                "buy_lg_amount": cls._prefer_float(dc_row.get("buy_lg_amount"), ths_row.get("buy_lg_amount")),
                "buy_lg_amount_rate": cls._prefer_float(dc_row.get("buy_lg_amount_rate"), ths_row.get("buy_lg_amount_rate")),
                "buy_md_amount": cls._prefer_float(dc_row.get("buy_md_amount"), ths_row.get("buy_md_amount")),
                "buy_md_amount_rate": cls._prefer_float(dc_row.get("buy_md_amount_rate"), ths_row.get("buy_md_amount_rate")),
                "buy_sm_amount": cls._prefer_float(dc_row.get("buy_sm_amount"), ths_row.get("buy_sm_amount")),
                "buy_sm_amount_rate": cls._prefer_float(dc_row.get("buy_sm_amount_rate"), ths_row.get("buy_sm_amount_rate")),
                "sources": sorted(
                    {
                        str(item)
                        for item in (
                            dc_row.get("data_source"),
                            ths_row.get("data_source"),
                        )
                        if item
                    }
                ),
            }
        return merged

    @classmethod
    def _merge_chip_snapshots(
        cls,
        cyq_perf: Dict[str, Any],
        cyq_chips: Dict[str, Any],
        ts_codes: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        perf_rows = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in _safe_list(cyq_perf.get("rows"))
            if str(row.get("ts_code") or "").strip()
        }
        chip_rows = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in _safe_list(cyq_chips.get("rows"))
            if str(row.get("ts_code") or "").strip()
        }
        merged: Dict[str, Dict[str, Any]] = {}
        for ts_code in ts_codes:
            normalized_code = str(ts_code).strip().upper()
            perf_row = perf_rows.get(normalized_code) or {}
            chip_row = chip_rows.get(normalized_code) or {}
            if not perf_row and not chip_row:
                continue
            merged[normalized_code] = {
                "ts_code": normalized_code,
                "winner_rate": cls._prefer_float(perf_row.get("winner_rate"), chip_row.get("profit_ratio")),
                "weight_avg": cls._prefer_float(perf_row.get("weight_avg"), chip_row.get("avg_cost")),
                "avg_cost": cls._prefer_float(chip_row.get("avg_cost"), perf_row.get("weight_avg")),
                "cost_5pct": cls._prefer_float(None, perf_row.get("cost_5pct")),
                "cost_15pct": cls._prefer_float(None, perf_row.get("cost_15pct")),
                "cost_50pct": cls._prefer_float(None, perf_row.get("cost_50pct")),
                "cost_85pct": cls._prefer_float(None, perf_row.get("cost_85pct")),
                "cost_95pct": cls._prefer_float(None, perf_row.get("cost_95pct")),
                "cost_90_low": cls._prefer_float(None, chip_row.get("cost_90_low")),
                "cost_90_high": cls._prefer_float(None, chip_row.get("cost_90_high")),
                "concentration_90": cls._prefer_float(None, chip_row.get("concentration_90")),
                "cost_70_low": cls._prefer_float(None, chip_row.get("cost_70_low")),
                "cost_70_high": cls._prefer_float(None, chip_row.get("cost_70_high")),
                "concentration_70": cls._prefer_float(None, chip_row.get("concentration_70")),
                "distribution_points": int(float(chip_row.get("distribution_points") or 0)),
                "sources": sorted(
                    {
                        str(item)
                        for item in (
                            perf_row.get("data_source"),
                            chip_row.get("data_source"),
                        )
                        if item
                    }
                ),
            }
        return merged

    @classmethod
    def _normalize_candidate(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["ts_code"] = cls._normalize_ts_code(str(item.get("ts_code") or item.get("code") or ""))
        try:
            normalized["rank"] = int(float(item.get("rank") or 999))
        except (TypeError, ValueError):
            normalized["rank"] = 999
        try:
            normalized["rank_score"] = float(item.get("rank_score") or item.get("score") or 0)
        except (TypeError, ValueError):
            normalized["rank_score"] = 0.0
        return normalized

    def _group_candidates_by_theme(
        self,
        candidates: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        stock_theme_map = context.get("stock_theme_map") or {}
        theme_members = context.get("theme_members") or {}
        theme_name_map = context.get("theme_name_map") or {}
        theme_strength_map = context.get("theme_strength") or {}
        groups: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            ts_code = candidate.get("ts_code")
            if not ts_code:
                continue
            theme_rows = stock_theme_map.get(ts_code) or []
            theme_refs = self._candidate_theme_refs(candidate, theme_rows)
            seen_theme_ids: set[str] = set()
            for theme_id, theme_name in theme_refs:
                if theme_id in seen_theme_ids:
                    continue
                seen_theme_ids.add(theme_id)
                theme_name = self._display_theme_name(theme_id, theme_name, theme_name_map)
                payload = groups.setdefault(
                    theme_id,
                    {
                        "theme_id": theme_id,
                        "theme_name": theme_name,
                        "candidates": [],
                        "member_codes": set(theme_members.get(theme_id) or []),
                        "source_theme_names": set(),
                        "theme_strength": theme_strength_map.get(theme_id) or theme_strength_map.get(theme_name) or {},
                    },
                )
                payload["candidates"].append(candidate)
                payload["member_codes"].add(ts_code)
                if not payload.get("theme_strength") and theme_strength_map.get(theme_id):
                    payload["theme_strength"] = theme_strength_map[theme_id]
                if not theme_id.startswith("capital_theme:") and theme_name:
                    payload["source_theme_names"].add(theme_name)
                if theme_id.startswith("capital_theme:"):
                    for row in theme_rows:
                        child_theme_name = str(row.get("theme_name") or row.get("ths_name") or "").strip()
                        if child_theme_name:
                            payload["source_theme_names"].add(child_theme_name)
                        for child_name in _safe_list(row.get("child_theme_names")):
                            if child_name:
                                payload["source_theme_names"].add(str(child_name))
                for row in theme_rows:
                    if str(row.get("theme_code") or row.get("ths_code") or "").strip() == theme_id:
                        for child_name in _safe_list(row.get("child_theme_names")):
                            if child_name:
                                payload["source_theme_names"].add(str(child_name))
        return groups

    @staticmethod
    def _is_ths_theme_code(value: Any) -> bool:
        text = str(value or "").strip().upper()
        return len(text) == 9 and text.endswith(".TI") and text[:6].isdigit()

    @classmethod
    def _display_theme_name(cls, theme_id: str, theme_name: str, theme_name_map: Dict[str, str]) -> str:
        normalized_id = str(theme_id or "").strip().upper()
        normalized_name = str(theme_name or "").strip()
        mapped_name = str(theme_name_map.get(normalized_id) or "").strip()
        if mapped_name:
            return mapped_name
        if normalized_name and not cls._is_ths_theme_code(normalized_name):
            return normalized_name
        return normalized_name or normalized_id or "未分类"

    @classmethod
    def _candidate_theme_refs(cls, candidate: Dict[str, Any], theme_rows: List[Dict[str, Any]]) -> List[tuple[str, str]]:
        refs: List[tuple[str, str]] = []
        text_candidates: List[str] = []
        candidate_name = str(candidate.get("name") or "").strip()
        if candidate_name:
            text_candidates.append(candidate_name)
        for theme in candidate.get("themes") or []:
            theme_text = str(theme).strip()
            if theme_text:
                text_candidates.append(theme_text)
        for row in theme_rows:
            theme_id = str(row.get("theme_code") or row.get("ths_code") or "").strip()
            if not theme_id:
                continue
            theme_name = str(row.get("theme_name") or row.get("ths_name") or theme_id).strip()
            refs.append((theme_id, theme_name))
            text_candidates.extend([theme_id, theme_name])
            text_candidates.extend(str(item) for item in _safe_list(row.get("child_theme_names")) if item)
        if refs:
            refs.extend(cls._capital_theme_refs_from_texts(text_candidates))
            return refs
        for theme in candidate.get("themes") or []:
            text = str(theme).strip()
            if text:
                refs.append((text, text))
        refs.extend(cls._capital_theme_refs_from_texts(text_candidates))
        return refs or [("未分类", "未分类")]

    @staticmethod
    def _split_theme_text(value: Any) -> List[str]:
        text = str(value or "").strip()
        if not text:
            return []
        separators = [",", "，", "、", "/", "|", ";", "；", "+"]
        parts = [text]
        for separator in separators:
            next_parts: List[str] = []
            for part in parts:
                next_parts.extend(part.split(separator))
            parts = next_parts
        return [part.strip() for part in parts if part.strip()]

    @staticmethod
    def _safe_float_like(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _prefer_float(cls, current: Any, incoming: Any) -> Optional[float]:
        if incoming is None:
            try:
                return float(current) if current is not None else None
            except (TypeError, ValueError):
                return None
        try:
            incoming_value = float(incoming)
        except (TypeError, ValueError):
            try:
                return float(current) if current is not None else None
            except (TypeError, ValueError):
                return None
        if current is None:
            return incoming_value
        try:
            current_value = float(current)
        except (TypeError, ValueError):
            return incoming_value
        return incoming_value if abs(incoming_value) > abs(current_value) else current_value

    @staticmethod
    def _min_rank(current: Any, incoming: Any) -> Optional[int]:
        ranks: List[int] = []
        for value in (current, incoming):
            try:
                parsed = int(float(value))
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                ranks.append(parsed)
        return min(ranks) if ranks else None

    @classmethod
    def _theme_fund_strength_score(cls, entry: Dict[str, Any]) -> float:
        score = 50.0
        rank = entry.get("rank")
        if rank is not None:
            try:
                score += max(0.0, 38.0 - float(rank) * 1.2)
            except (TypeError, ValueError):
                pass
        net_amount = cls._safe_float_like(entry.get("net_amount"))
        if net_amount > 0:
            score += min(28.0, net_amount / 500000000.0 * 6.0)
        elif net_amount < 0:
            score -= min(22.0, abs(net_amount) / 500000000.0 * 6.0)
        pct_change = cls._safe_float_like(entry.get("pct_change"))
        if pct_change > 0:
            score += min(16.0, pct_change * 2.0)
        elif pct_change < 0:
            score += max(-12.0, pct_change * 2.0)
        up_num = int(entry.get("up_num") or 0)
        down_num = int(entry.get("down_num") or 0)
        if up_num + down_num > 0:
            score += (up_num / max(1, up_num + down_num) - 0.5) * 18.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _capital_theme_refs_from_texts(texts: Iterable[Any]) -> List[tuple[str, str]]:
        refs: List[tuple[str, str]] = []
        normalized_texts = [str(text or "").strip() for text in texts if str(text or "").strip()]
        for rule in CAPITAL_THEME_RULES:
            keywords = [str(item) for item in rule.get("keywords", [])]
            aliases = [str(item) for item in rule.get("stock_aliases", [])]
            matched = False
            for text in normalized_texts:
                upper_text = text.upper()
                if any(keyword and keyword in text for keyword in keywords):
                    matched = True
                    break
                if any(alias and alias in text for alias in aliases):
                    matched = True
                    break
                if "AI" in keywords and "AI" in upper_text:
                    matched = True
                    break
            if matched:
                refs.append((str(rule["theme_id"]), str(rule["theme_name"])))
        return refs

    @staticmethod
    def _index_hot_items_by_code(hot_items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in hot_items:
            ts_code = str(row.get("ts_code") or "").strip()
            if not ts_code:
                continue
            result.setdefault(ts_code, []).append(row)
        return result

    def _score_mainline_evidence(
        self,
        *,
        theme_candidates: List[Dict[str, Any]],
        theme_member_codes: set[str],
        theme_candidate_codes: set[str],
        theme_strength: Dict[str, Any],
        limit_events: Dict[str, List[Dict[str, Any]]],
        hot_by_code: Dict[str, List[Dict[str, Any]]],
        previous_feedback: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        fund_raw = self._score_fund_strength(theme_strength)
        density_raw = self._score_density(theme_candidates)
        limit_raw = self._score_limit_strength(theme_member_codes | theme_candidate_codes, limit_events)
        break_raw = self._score_break_risk(theme_member_codes | theme_candidate_codes, limit_events)
        hot_raw = self._score_hot_concentration(theme_member_codes | theme_candidate_codes, hot_by_code)
        feedback_raw = self._score_previous_feedback(previous_feedback)
        return [
            self._evidence_item("fund_strength", "板块资金强度", fund_raw["score"], 30.0, fund_raw),
            self._evidence_item("density", "候选池密度", density_raw["score"], 20.0, density_raw),
            self._evidence_item("limit_strength", "涨停强度", limit_raw["score"], 20.0, limit_raw),
            self._evidence_item("break_risk", "炸板风险", break_raw["score"], -10.0, break_raw),
            self._evidence_item("hot_concentration", "热榜集中度", hot_raw["score"], 10.0, hot_raw),
            self._evidence_item("previous_feedback", "昨日强势反馈", feedback_raw["score"], 15.0, feedback_raw),
        ]

    @staticmethod
    def _score_fund_strength(theme_strength: Dict[str, Any]) -> Dict[str, Any]:
        if not theme_strength:
            return {"score": 50.0, "net_amount": None, "rank": None, "source_count": 0}
        score = float(theme_strength.get("fund_strength_score") or 50.0)
        return {
            "score": max(0.0, min(100.0, score)),
            "net_amount": theme_strength.get("net_amount"),
            "net_amount_rate": theme_strength.get("net_amount_rate"),
            "rank": theme_strength.get("rank"),
            "pct_change": theme_strength.get("pct_change"),
            "up_num": theme_strength.get("up_num"),
            "down_num": theme_strength.get("down_num"),
            "sources": theme_strength.get("sources") or [],
            "source_count": len(theme_strength.get("sources") or []),
        }

    @staticmethod
    def _score_density(theme_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidate_count = len(theme_candidates)
        top10_count = sum(int(item.get("rank") or 999) <= 10 for item in theme_candidates)
        avg_rank_score = sum(float(item.get("rank_score") or 0) for item in theme_candidates) / max(1, candidate_count)
        score = min(100.0, candidate_count * 18.0 + top10_count * 10.0 + avg_rank_score * 0.25)
        return {
            "score": score,
            "candidate_count": candidate_count,
            "top10_count": top10_count,
            "avg_rank_score": avg_rank_score,
        }

    @staticmethod
    def _score_limit_strength(codes: set[str], limit_events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        events = [event for code in codes for event in _safe_list(limit_events.get(code))]
        limit_up_count = sum(str(event.get("limit") or "").upper() == "U" for event in events)
        max_limit_times = max([int(event.get("limit_times") or 0) for event in events] or [0])
        fd_amount_score = min(20.0, sum(float(event.get("fd_amount") or 0) for event in events) / 100000.0)
        score = min(100.0, limit_up_count * 28.0 + max_limit_times * 10.0 + fd_amount_score)
        return {
            "score": score,
            "limit_up_count": limit_up_count,
            "max_limit_times": max_limit_times,
            "event_count": len(events),
        }

    @staticmethod
    def _score_break_risk(codes: set[str], limit_events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        events = [event for code in codes for event in _safe_list(limit_events.get(code))]
        broken_limit_count = sum(str(event.get("limit") or "").upper() == "Z" for event in events)
        open_times_total = sum(int(event.get("open_times") or 0) for event in events)
        score = min(100.0, broken_limit_count * 35.0 + open_times_total * 8.0)
        return {
            "score": score,
            "broken_limit_count": broken_limit_count,
            "open_times_total": open_times_total,
            "event_count": len(events),
        }

    @staticmethod
    def _score_hot_concentration(codes: set[str], hot_by_code: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        hot_rows = [row for code in codes for row in _safe_list(hot_by_code.get(code))]
        if not hot_rows:
            return {"score": 50.0, "hot_count": 0, "best_rank": None}
        best_rank = min(int(row.get("rank") or 999) for row in hot_rows)
        hot_count = len(hot_rows)
        score = min(100.0, max(0.0, 100.0 - best_rank * 1.5) + min(hot_count, 5) * 4.0)
        return {"score": score, "hot_count": hot_count, "best_rank": best_rank}

    @staticmethod
    def _score_previous_feedback(previous_feedback: Dict[str, Any]) -> Dict[str, Any]:
        if not previous_feedback:
            return {"score": 50.0, "sample_count": 0, "success_rate": None}
        success_rate = previous_feedback.get("success_rate")
        avg_profit = previous_feedback.get("avg_profit_window_pct")
        try:
            success_rate_value = float(success_rate)
        except (TypeError, ValueError):
            success_rate_value = 50.0
        try:
            avg_profit_value = float(avg_profit or 0)
        except (TypeError, ValueError):
            avg_profit_value = 0.0
        score = max(0.0, min(100.0, success_rate_value + avg_profit_value * 4.0))
        return {
            "score": score,
            "sample_count": previous_feedback.get("sample_count", 0),
            "success_rate": success_rate,
            "avg_profit_window_pct": avg_profit,
        }

    @staticmethod
    def _evidence_item(key: str, label: str, raw_score: float, weight: float, raw: Dict[str, Any]) -> Dict[str, Any]:
        weighted_score = raw_score * weight / 100.0
        if weight < 0:
            summary = f"{label}扣分 {abs(weighted_score):.1f}。"
        else:
            summary = f"{label}贡献 {weighted_score:.1f}。"
        return {
            "key": key,
            "label": label,
            "raw_score": raw_score,
            "weight": weight,
            "weighted_score": weighted_score,
            "level": MomentumV13DataService._evidence_level(raw_score),
            "summary": summary,
            "raw": raw,
        }

    @staticmethod
    def _evidence_level(score: float) -> str:
        if score >= 75:
            return "strong"
        if score >= 55:
            return "medium"
        return "weak"

    @staticmethod
    def _mainline_level(score: float) -> tuple[str, str]:
        if score >= 80:
            return "extreme", "主线极强"
        if score >= 65:
            return "confirmed", "主线成立"
        if score >= 50:
            return "uncertain", "主线存疑"
        return "weak", "主线过弱"

    @staticmethod
    def _best_hot_rank(codes: set[str], hot_by_code: Dict[str, List[Dict[str, Any]]]) -> Optional[int]:
        ranks = [
            int(row.get("rank") or 999)
            for code in codes
            for row in _safe_list(hot_by_code.get(code))
            if row.get("rank") is not None
        ]
        return min(ranks) if ranks else None

    @staticmethod
    def _build_mainline_representatives(
        theme_candidates: List[Dict[str, Any]],
        candidate_by_code: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        sorted_items = sorted(
            theme_candidates,
            key=lambda item: (float(item.get("rank_score") or 0), -int(item.get("rank") or 999)),
            reverse=True,
        )
        representatives: List[Dict[str, Any]] = []
        for item in sorted_items[:3]:
            ts_code = item.get("ts_code")
            source = candidate_by_code.get(ts_code, item)
            representatives.append(
                {
                    "rank": int(source.get("rank") or 0),
                    "ts_code": ts_code,
                    "name": str(source.get("name") or ""),
                    "role": str(source.get("leader_level") or source.get("role") or ""),
                    "rank_score": round(float(source.get("rank_score") or 0), 1),
                }
            )
        return representatives

    @staticmethod
    def _sentiment_limit_strength(limit_events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        events = [event for rows in limit_events.values() for event in _safe_list(rows)]
        limit_up_count = sum(str(event.get("limit") or "").upper() == "U" for event in events)
        max_limit_times = max([int(event.get("limit_times") or 0) for event in events] or [0])
        score = min(100.0, limit_up_count * 10.0 + max_limit_times * 12.0)
        return {
            "key": "limit_strength",
            "label": "涨停强度",
            "level": MomentumV13DataService._evidence_level(score),
            "score": round(score, 1),
            "summary": f"涨停 {limit_up_count} 只，最高连板 {max_limit_times}。",
            "raw": {"limit_up_count": limit_up_count, "max_limit_times": max_limit_times},
        }

    @staticmethod
    def _sentiment_break_risk(limit_events: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        events = [event for rows in limit_events.values() for event in _safe_list(rows)]
        broken_limit_count = sum(str(event.get("limit") or "").upper() == "Z" for event in events)
        open_times_total = sum(int(event.get("open_times") or 0) for event in events)
        risk_score = min(100.0, broken_limit_count * 20.0 + open_times_total * 5.0)
        score = max(0.0, 100.0 - risk_score)
        return {
            "key": "break_risk",
            "label": "炸板风险",
            "level": MomentumV13DataService._evidence_level(score),
            "score": round(score, 1),
            "summary": f"炸板 {broken_limit_count} 只，开板次数合计 {open_times_total}。",
            "raw": {"broken_limit_count": broken_limit_count, "open_times_total": open_times_total},
        }

    @staticmethod
    def _sentiment_mainline_clarity(mainline_radar: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not mainline_radar:
            score = 35.0
            summary = "暂未识别到稳定主线。"
        else:
            top = mainline_radar[0]
            score = float(top.get("score") or 0)
            summary = f"最强主线为 {top.get('theme_name') or top.get('theme_id')}，强度 {score:.1f}。"
        return {
            "key": "mainline_clarity",
            "label": "主线清晰度",
            "level": MomentumV13DataService._evidence_level(score),
            "score": round(score, 1),
            "summary": summary,
            "raw": {"mainline_count": len(mainline_radar)},
        }

    @staticmethod
    def _sentiment_hot_concentration(hot_items: List[Dict[str, Any]], mainline_radar: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not hot_items:
            score = 50.0
            best_rank = None
        else:
            best_rank = min(int(item.get("rank") or 999) for item in hot_items)
            top_mainline_codes = {
                rep.get("ts_code")
                for radar in mainline_radar[:2]
                for rep in _safe_list(radar.get("representatives"))
            }
            hot_mainline_count = sum(item.get("ts_code") in top_mainline_codes for item in hot_items)
            score = min(100.0, max(0.0, 100.0 - best_rank * 1.5) + hot_mainline_count * 6.0)
        return {
            "key": "hot_concentration",
            "label": "热榜集中度",
            "level": MomentumV13DataService._evidence_level(score),
            "score": round(score, 1),
            "summary": "热榜能与主线代表股形成呼应。" if score >= 65 else "热榜对主线支撑一般。",
            "raw": {"hot_count": len(hot_items), "best_rank": best_rank},
        }

    @staticmethod
    def _sentiment_previous_feedback(previous_feedback: Dict[str, Any]) -> Dict[str, Any]:
        raw = MomentumV13DataService._score_previous_feedback(previous_feedback)
        score = float(raw["score"])
        return {
            "key": "previous_feedback",
            "label": "昨日强势反馈",
            "level": MomentumV13DataService._evidence_level(score),
            "score": round(score, 1),
            "summary": "昨日强势股反馈偏强。" if score >= 65 else "昨日强势股反馈一般或样本不足。",
            "raw": raw,
        }

    @staticmethod
    def _sentiment_level(score: float) -> tuple[str, str]:
        if score >= 80:
            return "hot", "高涨"
        if score >= 65:
            return "tradable", "可做"
        if score >= 50:
            return "divergent", "分歧"
        return "ebb", "退潮"

    @staticmethod
    def _sentiment_summary(label: str, modules: List[Dict[str, Any]]) -> str:
        weak_modules = [item["label"] for item in modules if item.get("level") == "weak"]
        if weak_modules:
            return f"短线情绪为{label}，主要拖累来自{'、'.join(weak_modules)}。"
        return f"短线情绪为{label}，涨停、主线和热度证据整体可用。"
