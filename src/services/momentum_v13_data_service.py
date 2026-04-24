# -*- coding: utf-8 -*-
"""V1.3 momentum screener data aggregation service."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from data_provider.base import normalize_stock_code
from data_provider.tushare_fetcher import TushareFetcher

logger = logging.getLogger(__name__)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


class MomentumV13DataService:
    """Build reusable V1.3 data contexts for secondary decision and backtest."""

    _shared_resource_cache: Dict[str, Dict[str, Any]] = {}
    _shared_cache_stats: Dict[str, int] = {"hit": 0, "miss": 0, "expired": 0}

    _DEFAULT_RESOURCE_TTLS = {
        "stk_limit": 7 * 24 * 60 * 60,
        "limit_list_d": 7 * 24 * 60 * 60,
        "ths_member": 7 * 24 * 60 * 60,
        "ths_hot": 30 * 60,
        "realtime_quote": 60,
        "context": 30 * 60,
    }

    def __init__(
        self,
        fetcher: Optional[TushareFetcher] = None,
        *,
        resource_ttls: Optional[Dict[str, int]] = None,
    ) -> None:
        self.fetcher = fetcher or TushareFetcher(rate_limit_per_minute=200)
        self._resource_cache = self.__class__._shared_resource_cache
        self._resource_ttls = {**self._DEFAULT_RESOURCE_TTLS, **(resource_ttls or {})}

    @classmethod
    def reset_cache(cls) -> None:
        cls._shared_resource_cache.clear()
        cls._shared_cache_stats = {"hit": 0, "miss": 0, "expired": 0}

    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        return {**cls._shared_cache_stats, "size": len(cls._shared_resource_cache)}

    def build_context(self, *, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        """Build the V1.3 EOD context used by the production secondary decision."""
        normalized_codes = self._normalize_ts_codes(ts_codes)
        context_key = self._cache_key("context", trade_date, ",".join(normalized_codes))
        cached = self._cache_get(context_key, self._resource_ttls["context"])
        if cached is not None:
            return cached

        limit_prices = self._load_limit_prices(trade_date)
        limit_events = self._load_limit_events(trade_date)
        ths_hot = self._load_ths_hot(trade_date)
        ths_members = self._load_ths_members(normalized_codes)

        payloads = {
            "stk_limit": limit_prices,
            "limit_list_d": limit_events,
            "ths_member": ths_members,
            "ths_hot": ths_hot,
        }
        context = {
            "trade_date": self._display_trade_date(trade_date),
            "data_as_of": self._now_iso(),
            "is_degraded": self._is_any_degraded(payloads.values()),
            "degraded_reasons": self._collect_degraded_reasons(payloads),
            "source_status": self._build_source_status(payloads),
            "stock_theme_map": self._build_stock_theme_map(ths_members, normalized_codes),
            "theme_members": self._build_theme_members(ths_members),
            "limit_events": self._index_rows_by_ts_code(limit_events),
            "limit_prices": self._index_rows_by_ts_code(limit_prices),
            "hot_items": _safe_list(ths_hot.get("rows")),
            "raw_sources": payloads,
        }
        self._cache_set(context_key, context)
        return context

    def build_replay_context(self, *, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        """Build a replay-safe V1.3 context without using realtime quote data."""
        context = self.build_context(trade_date=trade_date, ts_codes=ts_codes)
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
            evidence = self._score_mainline_evidence(
                theme_candidates=theme_candidates,
                theme_member_codes=theme_member_codes,
                theme_candidate_codes=theme_candidate_codes,
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
                    "representatives": representatives,
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

    def _load_ths_hot(self, trade_date: str) -> Dict[str, Any]:
        key = self._cache_key("ths_hot", trade_date)
        cached = self._cache_get(key, self._resource_ttls["ths_hot"])
        if cached is not None:
            return cached
        payload = self._safe_fetch("ths_hot", lambda: self.fetcher.get_ths_hot(trade_date))
        self._cache_set(key, payload)
        return payload

    def _load_ths_members(self, ts_codes: List[str]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        source_status: Dict[str, str] = {}
        degraded_reasons: List[str] = []
        for ts_code in ts_codes:
            key = self._cache_key("ths_member", ts_code)
            cached = self._cache_get(key, self._resource_ttls["ths_member"])
            if cached is None:
                cached = self._safe_fetch("ths_member", lambda code=ts_code: self.fetcher.get_ths_members(con_code=code))
                self._cache_set(key, cached)
            source_status[ts_code] = str(cached.get("status") or "unknown")
            rows.extend(_safe_list(cached.get("rows")))
            if cached.get("is_degraded"):
                degraded_reasons.extend(
                    f"{ts_code}:{reason}" for reason in _safe_list(cached.get("degraded_reasons"))
                )
        status = "ok"
        if degraded_reasons:
            status = "partial" if rows else "unavailable"
        return self._payload(
            source="tushare.ths_member",
            trade_date=None,
            rows=rows,
            status=status,
            degraded_reasons=degraded_reasons,
            extra={"source_status": source_status},
        )

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
        entry = self._resource_cache.get(key)
        if entry is None:
            self.__class__._shared_cache_stats["miss"] += 1
            return None
        age = time.time() - float(entry.get("stored_at", 0))
        if ttl_seconds >= 0 and age > ttl_seconds:
            self.__class__._shared_cache_stats["expired"] += 1
            self._resource_cache.pop(key, None)
            return None
        self.__class__._shared_cache_stats["hit"] += 1
        return entry.get("value")

    def _cache_set(self, key: str, value: Dict[str, Any]) -> None:
        self._resource_cache[key] = {"stored_at": time.time(), "value": value}

    @staticmethod
    def _cache_key(resource: str, *parts: str) -> str:
        normalized_parts = [str(part or "").replace("/", "-") for part in parts]
        return ":".join(["momentum", "v13", resource, *normalized_parts])

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
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in _safe_list(payload.get("rows")):
            ts_code = row.get("ts_code") or row.get("con_code")
            if not ts_code:
                continue
            grouped.setdefault(str(ts_code), []).append(row)
        return grouped

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
        groups: Dict[str, Dict[str, Any]] = {}
        for candidate in candidates:
            ts_code = candidate.get("ts_code")
            if not ts_code:
                continue
            theme_rows = stock_theme_map.get(ts_code) or []
            theme_refs = self._candidate_theme_refs(candidate, theme_rows)
            for theme_id, theme_name in theme_refs:
                payload = groups.setdefault(
                    theme_id,
                    {
                        "theme_id": theme_id,
                        "theme_name": theme_name,
                        "candidates": [],
                        "member_codes": set(theme_members.get(theme_id) or []),
                    },
                )
                payload["candidates"].append(candidate)
                payload["member_codes"].add(ts_code)
        return groups

    @staticmethod
    def _candidate_theme_refs(candidate: Dict[str, Any], theme_rows: List[Dict[str, Any]]) -> List[tuple[str, str]]:
        refs: List[tuple[str, str]] = []
        for row in theme_rows:
            theme_id = str(row.get("theme_code") or row.get("ths_code") or "").strip()
            if not theme_id:
                continue
            theme_name = str(row.get("theme_name") or row.get("ths_name") or theme_id).strip()
            refs.append((theme_id, theme_name))
        if refs:
            return refs
        themes = candidate.get("themes") or []
        for theme in themes:
            text = str(theme).strip()
            if text:
                refs.append((text, text))
        return refs or [("未分类", "未分类")]

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
        limit_events: Dict[str, List[Dict[str, Any]]],
        hot_by_code: Dict[str, List[Dict[str, Any]]],
        previous_feedback: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        density_raw = self._score_density(theme_candidates)
        limit_raw = self._score_limit_strength(theme_member_codes | theme_candidate_codes, limit_events)
        break_raw = self._score_break_risk(theme_member_codes | theme_candidate_codes, limit_events)
        hot_raw = self._score_hot_concentration(theme_member_codes | theme_candidate_codes, hot_by_code)
        feedback_raw = self._score_previous_feedback(previous_feedback)
        return [
            self._evidence_item("density", "候选池密度", density_raw["score"], 30.0, density_raw),
            self._evidence_item("limit_strength", "涨停强度", limit_raw["score"], 25.0, limit_raw),
            self._evidence_item("break_risk", "炸板风险", break_raw["score"], -15.0, break_raw),
            self._evidence_item("hot_concentration", "热榜集中度", hot_raw["score"], 15.0, hot_raw),
            self._evidence_item("previous_feedback", "昨日强势反馈", feedback_raw["score"], 25.0, feedback_raw),
        ]

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
