# -*- coding: utf-8 -*-
"""
次日强势股筛选服务（Standard 版）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from data_provider.base import is_st_stock
from data_provider.tushare_fetcher import TushareFetcher
from src.config import get_config

logger = logging.getLogger(__name__)

MOMENTUM_EOD_READY_COVERAGE_RATIO = 0.6
MOMENTUM_MARKET_CLOSE_CUTOFF = "15:00"


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


class MomentumScreenerService:
    """收盘后次日强势股筛选服务。"""

    _shared_sector_context_cache: Dict[str, Dict[str, Any]] = {}
    _shared_sector_cache_stats: Dict[str, int] = {"hit": 0, "miss": 0, "expired": 0}
    _sector_cache_ttl_seconds: int = 6 * 60 * 60
    _shared_trade_snapshot_cache: Dict[str, Dict[str, Any]] = {}
    _trade_snapshot_cache_ttl_seconds: int = 7 * 24 * 60 * 60
    _trade_snapshot_cache_dirname: str = "momentum_trade_snapshots"
    _shared_candidate_pool_cache: Dict[str, Dict[str, Any]] = {}
    _candidate_pool_cache_ttl_seconds: int = 7 * 24 * 60 * 60
    _candidate_pool_cache_dirname: str = "momentum_candidate_pools"
    _shared_history_cache: Dict[str, Dict[str, Any]] = {}
    _history_cache_ttl_seconds: int = 12 * 60 * 60
    _history_cache_dirname: str = "momentum_histories"

    def __init__(
        self,
        fetcher: Optional[TushareFetcher] = None,
        history_cache_dir: Optional[Path] = None,
        trade_snapshot_cache_dir: Optional[Path] = None,
        candidate_pool_cache_dir: Optional[Path] = None,
    ) -> None:
        self.fetcher = fetcher or TushareFetcher(rate_limit_per_minute=200)
        self._sector_context_cache = self.__class__._shared_sector_context_cache
        self._trade_snapshot_cache = self.__class__._shared_trade_snapshot_cache
        self._candidate_pool_cache = self.__class__._shared_candidate_pool_cache
        self._history_cache = self.__class__._shared_history_cache
        self.__class__._refresh_sector_cache_ttl_from_config()
        self._trade_snapshot_cache_dir = (
            Path(trade_snapshot_cache_dir)
            if trade_snapshot_cache_dir is not None
            else Path.cwd() / "data" / "cache" / self.__class__._trade_snapshot_cache_dirname
        )
        self._candidate_pool_cache_dir = (
            Path(candidate_pool_cache_dir)
            if candidate_pool_cache_dir is not None
            else Path.cwd() / "data" / "cache" / self.__class__._candidate_pool_cache_dirname
        )
        self._history_cache_dir = (
            Path(history_cache_dir)
            if history_cache_dir is not None
            else Path.cwd() / "data" / "cache" / self.__class__._history_cache_dirname
        )
        if not self.fetcher.is_available():
            raise RuntimeError("Tushare 数据源不可用，请检查 TUSHARE_TOKEN 配置")

    @classmethod
    def reset_sector_cache(cls) -> None:
        cls._shared_sector_context_cache.clear()
        cls._shared_sector_cache_stats = {"hit": 0, "miss": 0, "expired": 0}
        cls._shared_trade_snapshot_cache.clear()
        cls._shared_candidate_pool_cache.clear()
        cls._shared_history_cache.clear()

    @classmethod
    def get_sector_cache_stats(cls) -> Dict[str, int]:
        cls._refresh_sector_cache_ttl_from_config()
        return {
            **cls._shared_sector_cache_stats,
            "size": len(cls._shared_sector_context_cache),
            "ttl_seconds": cls._sector_cache_ttl_seconds,
        }

    @classmethod
    def _cache_now_ts(cls) -> float:
        return datetime.now(timezone.utc).timestamp()

    @classmethod
    def _refresh_sector_cache_ttl_from_config(cls) -> None:
        try:
            ttl = int(getattr(get_config(), "momentum_sector_cache_ttl_seconds", cls._sector_cache_ttl_seconds))
        except Exception:
            ttl = cls._sector_cache_ttl_seconds
        cls._sector_cache_ttl_seconds = max(0, ttl)

    def screen(
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
        use_sector_context: bool = True,
        max_scored_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:
        if profile not in {"standard", "aggressive"}:
            raise ValueError("仅支持 profile=standard 或 profile=aggressive")

        trade_date_resolution = self._resolve_trade_date_and_snapshot(trade_date)
        resolved_trade_date = trade_date_resolution["trade_date"]
        snapshot = trade_date_resolution["snapshot"]
        candidates = self._load_candidate_pool(
            trade_date=resolved_trade_date,
            snapshot=snapshot,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
        )

        if candidates.empty:
            return {
                "profile": profile,
                "trade_date": self._format_trade_date(resolved_trade_date),
                "requested_trade_date": trade_date_resolution.get("requested_trade_date"),
                "trade_date_note": trade_date_resolution.get("trade_date_note"),
                "candidate_count": 0,
                "ranked_results": [],
                "results": [],
            }

        scoring_candidates = self._preselect_candidates_for_scoring(
            candidates,
            limit=max_scored_candidates,
        )

        sector_context = {"mapping": {}, "sector_pct_map": {}}
        if use_sector_context:
            try:
                sector_context = self._load_sector_context(
                    trade_date=resolved_trade_date,
                    ts_codes=scoring_candidates["ts_code"].dropna().astype(str).tolist(),
                )
            except Exception:
                logger.exception(
                    "Momentum sector context load failed for filtered candidates trade_date=%s; fallback to stock_basic.industry",
                    resolved_trade_date,
                )
                sector_context = {"mapping": {}, "sector_pct_map": {}}
        else:
            logger.debug(
                "Momentum screener skipped sector context for trade_date=%s to use local industry fallback",
                resolved_trade_date,
            )

        scoring_candidates = self._apply_sector_context(scoring_candidates, sector_context)
        results = self._score_candidates(candidates=scoring_candidates, trade_date=resolved_trade_date, profile=profile)
        results = sorted(results, key=lambda item: item["rank_score"], reverse=True)
        for index, item in enumerate(results, start=1):
            item["rank"] = index

        return {
            "profile": profile,
            "trade_date": self._format_trade_date(resolved_trade_date),
            "requested_trade_date": trade_date_resolution.get("requested_trade_date"),
            "trade_date_note": trade_date_resolution.get("trade_date_note"),
            "candidate_count": len(candidates),
            "ranked_results": results,
            "results": results[:top_n],
        }

    @staticmethod
    def _preselect_candidates_for_scoring(candidates: pd.DataFrame, limit: Optional[int]) -> pd.DataFrame:
        if limit is None or limit <= 0 or len(candidates) <= limit:
            return candidates.reset_index(drop=True)

        working = candidates.copy()
        amount_rank = working["amount"].rank(pct=True, method="average")
        turnover_rank = working["turnover_rate"].rank(pct=True, method="average")
        main_inflow_rank = working["main_net_inflow"].fillna(0).rank(pct=True, method="average")
        top_list_bonus = working["top_list_flag"].fillna(False).astype(int) * 0.2
        working["_prefilter_score"] = (
            working["pct_chg"].fillna(0) * 0.45
            + amount_rank * 20
            + turnover_rank * 12
            + main_inflow_rank * 18
            + top_list_bonus
        )
        return (
            working.sort_values(["_prefilter_score", "pct_chg", "amount"], ascending=[False, False, False])
            .head(limit)
            .drop(columns=["_prefilter_score"])
            .reset_index(drop=True)
        )

    def _resolve_trade_date_and_snapshot(self, trade_date: Optional[str]) -> Dict[str, Any]:
        requested_trade_date = trade_date.replace("-", "") if trade_date else None
        current_time = self._get_china_now()
        current_date = current_time.strftime("%Y%m%d")
        current_clock = current_time.strftime("%H:%M")
        market_closed = current_clock >= MOMENTUM_MARKET_CLOSE_CUTOFF
        today_trade_date = self._pick_latest_trade_date_candidate(use_today=True)
        previous_trade_date = self._pick_latest_trade_date_candidate(use_today=False)
        current_trade_date = today_trade_date if today_trade_date == current_date else None

        if requested_trade_date and requested_trade_date != current_trade_date:
            return {
                "trade_date": requested_trade_date,
                "snapshot": self._load_trade_snapshot(requested_trade_date),
                "requested_trade_date": self._format_trade_date(requested_trade_date),
                "trade_date_note": None,
            }

        if current_trade_date is None:
            resolved_trade_date = requested_trade_date or previous_trade_date or today_trade_date
            if not resolved_trade_date:
                raise RuntimeError("无法解析有效交易日")
            return {
                "trade_date": resolved_trade_date,
                "snapshot": self._load_trade_snapshot(resolved_trade_date),
                "requested_trade_date": self._format_trade_date(requested_trade_date) if requested_trade_date else None,
                "trade_date_note": None,
            }

        fallback_trade_date = previous_trade_date or current_trade_date
        requested_trade_date_formatted = (
            self._format_trade_date(requested_trade_date)
            if requested_trade_date
            else None
        )

        if not market_closed and fallback_trade_date != current_trade_date:
            note = (
                f"当前时间 {current_clock} 尚未到收盘后批量筛选时段，"
                f"系统自动使用上一交易日 {self._format_trade_date(fallback_trade_date)}。"
            )
            if requested_trade_date == current_trade_date:
                note = (
                    f"你选择了 {self._format_trade_date(current_trade_date)}，"
                    f"但当前时间 {current_clock} 尚未收盘，系统暂时回退到上一交易日 "
                    f"{self._format_trade_date(fallback_trade_date)}。"
                )
            return {
                "trade_date": fallback_trade_date,
                "snapshot": self._load_trade_snapshot(fallback_trade_date),
                "requested_trade_date": requested_trade_date_formatted,
                "trade_date_note": note,
            }

        today_snapshot = self._load_trade_snapshot(current_trade_date)
        if self._is_trade_snapshot_ready(today_snapshot):
            return {
                "trade_date": current_trade_date,
                "snapshot": today_snapshot,
                "requested_trade_date": requested_trade_date_formatted,
                "trade_date_note": None,
            }

        if fallback_trade_date == current_trade_date:
            return {
                "trade_date": current_trade_date,
                "snapshot": today_snapshot,
                "requested_trade_date": requested_trade_date_formatted,
                "trade_date_note": None,
            }

        if requested_trade_date == current_trade_date:
            note = (
                f"你选择了 {self._format_trade_date(current_trade_date)}，"
                f"但当天收盘数据尚未同步完成，系统暂时回退到上一交易日 "
                f"{self._format_trade_date(fallback_trade_date)}。"
            )
        else:
            note = (
                f"{self._format_trade_date(current_trade_date)} 收盘数据尚未同步完成，"
                f"当前自动使用上一交易日 {self._format_trade_date(fallback_trade_date)}。"
            )
        return {
            "trade_date": fallback_trade_date,
            "snapshot": self._load_trade_snapshot(fallback_trade_date),
            "requested_trade_date": requested_trade_date_formatted,
            "trade_date_note": note,
        }

    def _pick_latest_trade_date_candidate(self, *, use_today: bool) -> Optional[str]:
        try:
            if use_today:
                return self.fetcher.get_trade_time(early_time="00:00", late_time="00:00")
            return self.fetcher.get_trade_time(early_time="00:00", late_time="23:59")
        except Exception:
            logger.debug("Momentum screener failed to resolve trade-date candidate", exc_info=True)
            return None

    def _get_china_now(self) -> datetime:
        fetcher_now = getattr(self.fetcher, "_get_china_now", None)
        if callable(fetcher_now):
            try:
                current_time = fetcher_now()
                if isinstance(current_time, datetime):
                    return current_time
            except Exception:
                logger.debug("Momentum screener failed to fetch China clock from data source", exc_info=True)
        return datetime.now(timezone(timedelta(hours=8)))

    @staticmethod
    def _format_trade_date(trade_date: str) -> str:
        return datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d")

    def _call_tushare(self, method_name: str, **kwargs) -> pd.DataFrame:
        df = self.fetcher._call_api_with_rate_limit(method_name, **kwargs)  # noqa: SLF001
        if df is None:
            return pd.DataFrame()
        return df.copy()

    def _load_trade_snapshot(self, trade_date: str) -> Dict[str, pd.DataFrame]:
        cached = self._load_cached_trade_snapshot(trade_date)
        if cached is not None:
            return cached

        basic = self._call_tushare(
            "stock_basic",
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,industry,market,list_date,list_status",
        )
        daily = self._call_tushare(
            "daily",
            trade_date=trade_date,
            fields="ts_code,trade_date,open,high,low,close,pct_chg,amount",
        )
        daily_basic = self._call_tushare(
            "daily_basic",
            trade_date=trade_date,
            fields="ts_code,trade_date,turnover_rate,volume_ratio,circ_mv",
        )
        moneyflow = self._call_tushare("moneyflow", trade_date=trade_date)
        stk_limit = self._call_tushare(
            "stk_limit",
            trade_date=trade_date,
            fields="ts_code,trade_date,up_limit,down_limit",
        )
        top_list = self._call_tushare("top_list", trade_date=trade_date)

        if "amount" in daily.columns:
            daily["amount"] = pd.to_numeric(daily["amount"], errors="coerce") * 1000
        if "circ_mv" in daily_basic.columns:
            daily_basic["circ_mv"] = pd.to_numeric(daily_basic["circ_mv"], errors="coerce") * 10000

        snapshot = {
            "basic": basic,
            "daily": daily,
            "daily_basic": daily_basic,
            "moneyflow": moneyflow,
            "stk_limit": stk_limit,
            "top_list": top_list,
        }
        if self._is_trade_snapshot_ready(snapshot):
            self._store_cached_trade_snapshot(trade_date, snapshot)
        return self._copy_snapshot(snapshot)

    @staticmethod
    def _pick_first_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        for column in candidates:
            if column in df.columns:
                return column
        return None

    def _load_sector_context(self, *, trade_date: str, ts_codes: List[str]) -> Dict[str, Any]:
        ts_code_set = {code for code in ts_codes if code}
        if not ts_code_set:
            return {"mapping": {}, "sector_pct_map": {}}

        cached = self._sector_context_cache.get(trade_date)
        if cached is not None:
            expires_at = _safe_float(cached.get("expires_at"))
            if expires_at > self.__class__._cache_now_ts():
                payload = cached.get("payload", {})
                cached_mapping = payload.get("mapping", {}) if isinstance(payload, dict) else {}
                cached_unmapped = set(payload.get("unmapped_codes", [])) if isinstance(payload, dict) else set()
                cached_resolved = set(cached_mapping) | cached_unmapped
                if ts_code_set.issubset(cached_resolved):
                    self.__class__._shared_sector_cache_stats["hit"] += 1
                    logger.debug(
                        "Momentum sector context cache hit: trade_date=%s expires_at=%s requested=%d",
                        trade_date,
                        expires_at,
                        len(ts_code_set),
                    )
                    return payload

                logger.debug(
                    "Momentum sector context cache partial hit: trade_date=%s requested=%d cached=%d",
                    trade_date,
                    len(ts_code_set),
                    len(cached_resolved),
                )
                mapping: Dict[str, str] = dict(cached_mapping)
                sector_pct_map: Dict[str, float] = dict(payload.get("sector_pct_map", {}))
                unresolved_codes = set(cached_unmapped)
            else:
                self.__class__._shared_sector_cache_stats["expired"] += 1
                logger.info("Momentum sector context cache expired: trade_date=%s expires_at=%s", trade_date, expires_at)
                self._sector_context_cache.pop(trade_date, None)
                mapping = {}
                sector_pct_map = {}
                unresolved_codes = set()
        else:
            mapping = {}
            sector_pct_map = {}
            unresolved_codes = set()

        self.__class__._shared_sector_cache_stats["miss"] += 1
        logger.debug("Momentum sector context cache miss: trade_date=%s requested=%d", trade_date, len(ts_code_set))
        pending_codes = set(ts_code_set) - set(mapping) - unresolved_codes
        if not pending_codes:
            result = {
                "mapping": mapping,
                "sector_pct_map": sector_pct_map,
                "unmapped_codes": sorted(unresolved_codes),
            }
            self._sector_context_cache[trade_date] = {
                "payload": result,
                "expires_at": self.__class__._cache_now_ts() + self.__class__._sector_cache_ttl_seconds,
            }
            return result

        classify = self._call_tushare(
            "index_classify",
            src="SW2021",
            level="L1",
            fields="index_code,industry_name,index_name,level,src",
        )
        if classify.empty:
            classify = self._call_tushare(
                "index_classify",
                src="SW",
                level="L1",
                fields="index_code,industry_name,index_name,level,src",
            )

        code_col = self._pick_first_column(classify, ["index_code", "industry_code", "ts_code", "code"])
        name_col = self._pick_first_column(classify, ["industry_name", "index_name", "name"])
        if classify.empty or not code_col or not name_col:
            result = {
                "mapping": mapping,
                "sector_pct_map": sector_pct_map,
                "unmapped_codes": sorted(unresolved_codes | pending_codes),
            }
            self._sector_context_cache[trade_date] = {
                "payload": result,
                "expires_at": self.__class__._cache_now_ts() + self.__class__._sector_cache_ttl_seconds,
            }
            return result

        classify = classify[[code_col, name_col]].dropna().drop_duplicates()

        for _, sector_row in classify.iterrows():
            sector_code = _safe_str(sector_row.get(code_col))
            sector_name = _safe_str(sector_row.get(name_col))
            if not sector_code or not sector_name:
                continue

            member = self._call_tushare(
                "index_member",
                index_code=sector_code,
                fields="index_code,index_name,con_code,con_name,in_date,out_date,is_new",
            )
            if member.empty:
                continue

            member_code_col = self._pick_first_column(member, ["con_code", "ts_code"])
            if not member_code_col:
                continue

            active_member = member.copy()
            if "in_date" in active_member.columns:
                active_member["in_date"] = active_member["in_date"].fillna("").astype(str)
            if "out_date" in active_member.columns:
                active_member["out_date"] = active_member["out_date"].fillna("").astype(str)
            if "is_new" in active_member.columns:
                active_member["is_new"] = active_member["is_new"].fillna("").astype(str)

            if "in_date" in active_member.columns:
                active_member = active_member[
                    (active_member["in_date"] == "") | (active_member["in_date"] <= trade_date)
                ]
            if "out_date" in active_member.columns:
                active_member = active_member[
                    (active_member["out_date"] == "") | (active_member["out_date"] > trade_date)
                ]

            matched_codes = [
                member_code
                for member_code in active_member[member_code_col].astype(str).tolist()
                if member_code in pending_codes and member_code not in mapping
            ]
            if not matched_codes:
                continue

            for member_code in matched_codes:
                mapping[member_code] = sector_name
                pending_codes.discard(member_code)

            if sector_name not in sector_pct_map:
                index_daily = self._call_tushare(
                    "index_daily",
                    ts_code=sector_code,
                    trade_date=trade_date,
                    fields="ts_code,trade_date,pct_chg",
                )
                if not index_daily.empty and "pct_chg" in index_daily.columns:
                    sector_pct_map[sector_name] = _safe_float(index_daily.iloc[0].get("pct_chg"))

            if not pending_codes:
                break

        unresolved_codes.update(pending_codes)
        result = {
            "mapping": mapping,
            "sector_pct_map": sector_pct_map,
            "unmapped_codes": sorted(unresolved_codes),
        }
        self._sector_context_cache[trade_date] = {
            "payload": result,
            "expires_at": self.__class__._cache_now_ts() + self.__class__._sector_cache_ttl_seconds,
        }
        logger.info(
            "Momentum sector context loaded: trade_date=%s sectors=%d mapped_stocks=%d cache_stats=%s",
            trade_date,
            len(sector_pct_map),
            len(mapping),
            self.__class__._shared_sector_cache_stats,
        )
        return result

    def _build_candidates(
        self,
        *,
        snapshot: Dict[str, pd.DataFrame],
        min_change_pct: float,
        min_amount: float,
        min_turnover: float,
        exclude_st: bool,
        main_board_only: bool,
    ) -> pd.DataFrame:
        merged = snapshot["daily"].merge(snapshot["basic"], on="ts_code", how="left")
        merged = merged.merge(snapshot["daily_basic"], on=["ts_code", "trade_date"], how="left")
        merged = merged.merge(snapshot["stk_limit"], on=["ts_code", "trade_date"], how="left")
        merged = merged.merge(self._prepare_moneyflow(snapshot["moneyflow"]), on=["ts_code", "trade_date"], how="left")
        merged = merged.merge(self._prepare_top_list(snapshot["top_list"]), on=["ts_code", "trade_date"], how="left")

        if merged.empty:
            return merged

        for column in [
            "pct_chg",
            "amount",
            "turnover_rate",
            "volume_ratio",
            "open",
            "high",
            "low",
            "close",
            "up_limit",
            "circ_mv",
        ]:
            if column in merged.columns:
                merged[column] = pd.to_numeric(merged[column], errors="coerce")

        merged["name"] = merged["name"].fillna("")
        merged["symbol"] = merged["symbol"].fillna(merged["ts_code"].str.split(".").str[0])
        merged["industry"] = merged["industry"].fillna("未分类")
        merged["sector_name"] = merged["industry"]
        merged["is_st"] = merged["name"].map(is_st_stock)
        merged["is_main_board"] = merged["symbol"].map(self._is_main_board_symbol)

        filtered = merged[
            (merged["pct_chg"] >= min_change_pct)
            & (merged["amount"] >= min_amount)
            & (merged["turnover_rate"] >= min_turnover)
        ].copy()

        if exclude_st:
            filtered = filtered[~filtered["is_st"]]
        if main_board_only:
            filtered = filtered[filtered["is_main_board"]]

        return filtered.reset_index(drop=True)

    def _load_candidate_pool(
        self,
        *,
        trade_date: str,
        snapshot: Dict[str, pd.DataFrame],
        min_change_pct: float,
        min_amount: float,
        min_turnover: float,
        exclude_st: bool,
        main_board_only: bool,
    ) -> pd.DataFrame:
        cache_key = self._build_candidate_pool_cache_key(
            trade_date=trade_date,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
        )
        cached = self._load_cached_candidate_pool(cache_key)
        if cached is not None:
            return cached

        candidates = self._build_candidates(
            snapshot=snapshot,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
        )
        if not candidates.empty:
            self._store_cached_candidate_pool(cache_key, candidates)
        return candidates.copy()

    @staticmethod
    def _apply_sector_context(candidates: pd.DataFrame, sector_context: Optional[Dict[str, Any]]) -> pd.DataFrame:
        if candidates.empty:
            return candidates

        mapping = sector_context.get("mapping", {}) if isinstance(sector_context, dict) else {}
        if not mapping:
            return candidates

        result = candidates.copy()
        result["sector_name"] = result["ts_code"].map(mapping).fillna(result["sector_name"])
        return result

    @staticmethod
    def _is_main_board_symbol(symbol: str) -> bool:
        code = _safe_str(symbol)
        return code.startswith(("600", "601", "603", "605", "000", "001", "002", "003"))

    def _prepare_moneyflow(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["ts_code", "trade_date", "main_net_inflow"])

        result = df.copy()
        numeric_columns = [
            "buy_lg_amount",
            "sell_lg_amount",
            "buy_elg_amount",
            "sell_elg_amount",
            "net_mf_amount",
        ]
        for column in numeric_columns:
            if column in result.columns:
                result[column] = pd.to_numeric(result[column], errors="coerce")

        if "net_mf_amount" in result.columns:
            result["main_net_inflow"] = result["net_mf_amount"] * 10000
        else:
            buy_lg = result["buy_lg_amount"] if "buy_lg_amount" in result.columns else 0
            sell_lg = result["sell_lg_amount"] if "sell_lg_amount" in result.columns else 0
            buy_elg = result["buy_elg_amount"] if "buy_elg_amount" in result.columns else 0
            sell_elg = result["sell_elg_amount"] if "sell_elg_amount" in result.columns else 0
            result["main_net_inflow"] = (buy_lg - sell_lg + buy_elg - sell_elg) * 10000

        return result[["ts_code", "trade_date", "main_net_inflow"]]

    def _prepare_top_list(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["ts_code", "trade_date", "top_list_flag", "top_list_net_amount"])

        result = df.copy()
        if "net_amount" in result.columns:
            result["top_list_net_amount"] = pd.to_numeric(result["net_amount"], errors="coerce") * 10000
        else:
            result["top_list_net_amount"] = 0.0
        result["top_list_flag"] = True
        return (
            result.groupby(["ts_code", "trade_date"], as_index=False)
            .agg(
                top_list_flag=("top_list_flag", "max"),
                top_list_net_amount=("top_list_net_amount", "sum"),
            )
        )

    def _score_candidates(self, *, candidates: pd.DataFrame, trade_date: str, profile: str) -> List[Dict[str, Any]]:
        amount_rank = candidates["amount"].rank(pct=True, method="average")
        main_inflow_rank = candidates["main_net_inflow"].fillna(0).rank(pct=True, method="average")
        cached_sector_entry = self._sector_context_cache.get(trade_date, {})
        sector_context = cached_sector_entry.get("payload", {}) if isinstance(cached_sector_entry, dict) else {}
        sector_stats = self._build_sector_stats(candidates, sector_context)

        results: List[Dict[str, Any]] = []
        for index, row in candidates.iterrows():
            history = self._load_history(_safe_str(row.get("ts_code") or row.get("symbol")), trade_date)
            if history.empty:
                logger.debug("跳过缺少历史数据的候选股: %s", row["ts_code"])
                continue

            features = self._build_features(
                row,
                history,
                {
                    "amount_rank_pct": _safe_float(amount_rank.iloc[index]),
                    "main_inflow_rank_pct": _safe_float(main_inflow_rank.iloc[index]),
                    "sector": _safe_str(row.get("sector_name"), _safe_str(row.get("industry"), "未分类")),
                    "sector_stats": sector_stats.get(
                        _safe_str(row.get("sector_name"), _safe_str(row.get("industry"), "未分类")),
                        {},
                    ),
                },
            )
            if profile == "aggressive":
                results.append(self._score_aggressive(row, features))
            else:
                results.append(self._score_standard(row, features))

        return results

    def _build_sector_stats(self, candidates: pd.DataFrame, sector_context: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        sector_stats: Dict[str, Dict[str, Any]] = {}
        sector_context = sector_context or {}
        sector_pct_map = sector_context.get("sector_pct_map", {}) if isinstance(sector_context, dict) else {}

        if sector_pct_map:
            sector_change = (
                pd.DataFrame(
                    [{"sector_name": name, "pct_chg": pct} for name, pct in sector_pct_map.items()]
                )
                .sort_values("pct_chg", ascending=False)
                .reset_index(drop=True)
            )
        else:
            sector_change = (
                candidates.groupby("sector_name", as_index=False)["pct_chg"]
                .mean()
                .sort_values("pct_chg", ascending=False)
                .reset_index(drop=True)
            )

        sector_rank_map = {row["sector_name"]: idx + 1 for idx, row in sector_change.iterrows()}
        sector_total = max(len(sector_rank_map), 1)

        for sector, group in candidates.groupby("sector_name"):
            working = group.copy()
            working["close_position_proxy"] = working.apply(
                lambda r: self._compute_close_position(
                    _safe_float(r.get("open")),
                    _safe_float(r.get("high")),
                    _safe_float(r.get("low")),
                    _safe_float(r.get("close")),
                ),
                axis=1,
            )
            working["leader_metric"] = (
                working["pct_chg"].fillna(0) * 0.5
                + working["amount"].rank(pct=True, method="average") * 5
                + working["close_position_proxy"].fillna(0) * 5
            )
            working = working.sort_values("leader_metric", ascending=False).reset_index(drop=True)
            leader_map = {item["ts_code"]: idx + 1 for idx, (_, item) in enumerate(working.iterrows())}

            sector_stats[sector] = {
                "sector_rank": sector_rank_map.get(sector, sector_total),
                "sector_total": sector_total,
                "sector_pct_chg": _safe_float(sector_pct_map.get(sector), group["pct_chg"].mean()),
                "strong_count": int((group["pct_chg"] >= 5).sum()),
                "limit_count": int((group["pct_chg"] >= 9.7).sum()),
                "size": len(group),
                "leader_map": leader_map,
            }

        return sector_stats

    def _load_history(self, stock_code: str, trade_date: str, days: int = 80) -> pd.DataFrame:
        end_dt = datetime.strptime(trade_date, "%Y%m%d")
        start_date = (end_dt - timedelta(days=days * 2)).strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")
        cache_key = self._build_history_cache_key(stock_code, start_date, end_date, days)
        cached = self._load_cached_history(cache_key)
        if cached is not None:
            return cached

        history = self.fetcher.get_daily_data(stock_code, start_date=start_date, end_date=end_date, days=days)
        if history is None or history.empty:
            return pd.DataFrame()
        result = history.copy()
        result["date"] = pd.to_datetime(result["date"])
        result = result.sort_values("date").reset_index(drop=True)
        self._store_cached_history(cache_key, result)
        return result.copy()

    def _build_history_cache_key(self, stock_code: str, start_date: str, end_date: str, days: int) -> str:
        normalized = _safe_str(stock_code).strip().upper()
        return f"{normalized}|{start_date}|{end_date}|{days}"

    def _build_candidate_pool_cache_key(
        self,
        *,
        trade_date: str,
        min_change_pct: float,
        min_amount: float,
        min_turnover: float,
        exclude_st: bool,
        main_board_only: bool,
    ) -> str:
        normalized = {
            "trade_date": trade_date,
            "min_change_pct": round(_safe_float(min_change_pct), 3),
            "min_amount": round(_safe_float(min_amount), 3),
            "min_turnover": round(_safe_float(min_turnover), 3),
            "exclude_st": bool(exclude_st),
            "main_board_only": bool(main_board_only),
        }
        return "|".join(f"{key}={value}" for key, value in normalized.items())

    @staticmethod
    def _copy_snapshot(snapshot: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        return {name: frame.copy() for name, frame in snapshot.items()}

    @staticmethod
    def _serialize_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        serializable = df.copy()
        datetime_columns = [
            column
            for column in serializable.columns
            if pd.api.types.is_datetime64_any_dtype(serializable[column])
        ]
        for column in datetime_columns:
            serializable[column] = pd.to_datetime(serializable[column]).dt.strftime("%Y-%m-%dT%H:%M:%S")
        return {
            "columns": serializable.columns.tolist(),
            "records": serializable.to_dict(orient="records"),
        }

    @staticmethod
    def _deserialize_dataframe(payload: Dict[str, Any]) -> pd.DataFrame:
        columns = payload.get("columns") if isinstance(payload, dict) else None
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(columns, list):
            return pd.DataFrame()
        if not isinstance(records, list):
            records = []
        return pd.DataFrame.from_records(records, columns=columns)

    def _load_cached_trade_snapshot(self, trade_date: str) -> Optional[Dict[str, pd.DataFrame]]:
        cached = self._trade_snapshot_cache.get(trade_date)
        if cached is not None:
            expires_at = _safe_float(cached.get("expires_at"))
            if expires_at > self.__class__._cache_now_ts():
                payload = cached.get("payload")
                if isinstance(payload, dict):
                    snapshot = self._copy_snapshot(payload)
                    if self._is_trade_snapshot_ready(snapshot):
                        return snapshot
                    self._trade_snapshot_cache.pop(trade_date, None)
            else:
                self._trade_snapshot_cache.pop(trade_date, None)

        return self._load_disk_cached_trade_snapshot(trade_date)

    def _store_cached_trade_snapshot(self, trade_date: str, snapshot: Dict[str, pd.DataFrame]) -> None:
        payload = self._copy_snapshot(snapshot)
        expires_at = self.__class__._cache_now_ts() + self.__class__._trade_snapshot_cache_ttl_seconds
        self._trade_snapshot_cache[trade_date] = {"payload": payload, "expires_at": expires_at}
        self._store_disk_cached_trade_snapshot(trade_date, payload, expires_at)

    def _trade_snapshot_cache_path(self, trade_date: str) -> Path:
        digest = hashlib.sha1(f"snapshot|{trade_date}".encode("utf-8")).hexdigest()
        return self._trade_snapshot_cache_dir / f"{digest}.json"

    def _load_disk_cached_trade_snapshot(self, trade_date: str) -> Optional[Dict[str, pd.DataFrame]]:
        cache_path = self._trade_snapshot_cache_path(trade_date)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            expires_at = _safe_float(payload.get("expires_at"))
            if expires_at <= self.__class__._cache_now_ts():
                return None

            tables = payload.get("tables")
            if not isinstance(tables, dict):
                return None

            snapshot = {
                name: self._deserialize_dataframe(table_payload)
                for name, table_payload in tables.items()
                if isinstance(table_payload, dict)
            }
            if not snapshot or not self._is_trade_snapshot_ready(snapshot):
                try:
                    cache_path.unlink(missing_ok=True)
                except Exception:
                    logger.debug("Momentum trade snapshot disk cache cleanup failed: trade_date=%s", trade_date, exc_info=True)
                return None

            self._trade_snapshot_cache[trade_date] = {
                "payload": self._copy_snapshot(snapshot),
                "expires_at": expires_at,
            }
            return snapshot
        except Exception:
            logger.debug(
                "Momentum trade snapshot disk cache read failed: trade_date=%s path=%s",
                trade_date,
                cache_path,
                exc_info=True,
            )
            return None

    def _store_disk_cached_trade_snapshot(
        self,
        trade_date: str,
        snapshot: Dict[str, pd.DataFrame],
        expires_at: float,
    ) -> None:
        try:
            self._trade_snapshot_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self._trade_snapshot_cache_path(trade_date)
            cache_path.write_text(
                json.dumps(
                    {
                        "expires_at": expires_at,
                        "tables": {
                            name: self._serialize_dataframe(frame)
                            for name, frame in snapshot.items()
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Momentum trade snapshot disk cache write failed: trade_date=%s", trade_date, exc_info=True)

    def _load_cached_candidate_pool(self, cache_key: str) -> Optional[pd.DataFrame]:
        cached = self._candidate_pool_cache.get(cache_key)
        if cached is not None:
            expires_at = _safe_float(cached.get("expires_at"))
            if expires_at > self.__class__._cache_now_ts():
                payload = cached.get("payload")
                if isinstance(payload, pd.DataFrame):
                    if not payload.empty:
                        return payload.copy()
                    self._candidate_pool_cache.pop(cache_key, None)
            else:
                self._candidate_pool_cache.pop(cache_key, None)

        return self._load_disk_cached_candidate_pool(cache_key)

    def _store_cached_candidate_pool(self, cache_key: str, candidates: pd.DataFrame) -> None:
        payload = candidates.copy()
        expires_at = self.__class__._cache_now_ts() + self.__class__._candidate_pool_cache_ttl_seconds
        self._candidate_pool_cache[cache_key] = {"payload": payload, "expires_at": expires_at}
        self._store_disk_cached_candidate_pool(cache_key, payload, expires_at)

    def _candidate_pool_cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(f"candidate|{cache_key}".encode("utf-8")).hexdigest()
        return self._candidate_pool_cache_dir / f"{digest}.json"

    def _load_disk_cached_candidate_pool(self, cache_key: str) -> Optional[pd.DataFrame]:
        cache_path = self._candidate_pool_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            expires_at = _safe_float(payload.get("expires_at"))
            if expires_at <= self.__class__._cache_now_ts():
                return None

            table_payload = payload.get("table")
            if not isinstance(table_payload, dict):
                return None

            candidates = self._deserialize_dataframe(table_payload)
            if candidates.empty:
                try:
                    cache_path.unlink(missing_ok=True)
                except Exception:
                    logger.debug("Momentum candidate pool disk cache cleanup failed: key=%s", cache_key, exc_info=True)
                return None
            self._candidate_pool_cache[cache_key] = {
                "payload": candidates.copy(),
                "expires_at": expires_at,
            }
            return candidates
        except Exception:
            logger.debug("Momentum candidate pool disk cache read failed: key=%s", cache_key, exc_info=True)
            return None

    def _store_disk_cached_candidate_pool(self, cache_key: str, candidates: pd.DataFrame, expires_at: float) -> None:
        try:
            self._candidate_pool_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self._candidate_pool_cache_path(cache_key)
            cache_path.write_text(
                json.dumps(
                    {
                        "expires_at": expires_at,
                        "table": self._serialize_dataframe(candidates),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Momentum candidate pool disk cache write failed: key=%s", cache_key, exc_info=True)

    @staticmethod
    def _is_trade_snapshot_ready(snapshot: Dict[str, pd.DataFrame]) -> bool:
        if not isinstance(snapshot, dict):
            return False

        daily = snapshot.get("daily")
        daily_basic = snapshot.get("daily_basic")
        if not isinstance(daily, pd.DataFrame) or not isinstance(daily_basic, pd.DataFrame):
            return False
        if daily.empty or daily_basic.empty:
            return False

        basic = snapshot.get("basic")
        expected_count = 0
        if isinstance(basic, pd.DataFrame) and not basic.empty:
            expected_count = len(basic)
        else:
            expected_count = max(len(daily), len(daily_basic))

        if expected_count <= 0:
            return False

        daily_coverage = len(daily) / expected_count
        daily_basic_coverage = len(daily_basic) / expected_count
        return (
            daily_coverage >= MOMENTUM_EOD_READY_COVERAGE_RATIO
            and daily_basic_coverage >= MOMENTUM_EOD_READY_COVERAGE_RATIO
        )

    def _load_cached_history(self, cache_key: str) -> Optional[pd.DataFrame]:
        cached = self._history_cache.get(cache_key)
        if cached is not None:
            expires_at = _safe_float(cached.get("expires_at"))
            if expires_at > self.__class__._cache_now_ts():
                payload = cached.get("payload")
                if isinstance(payload, pd.DataFrame):
                    return payload.copy()
            else:
                self._history_cache.pop(cache_key, None)

        return self._load_disk_cached_history(cache_key)

    def _store_cached_history(self, cache_key: str, history: pd.DataFrame) -> None:
        payload = history.copy()
        expires_at = self.__class__._cache_now_ts() + self.__class__._history_cache_ttl_seconds
        self._history_cache[cache_key] = {"payload": payload, "expires_at": expires_at}
        self._store_disk_cached_history(cache_key, payload, expires_at)

    def _history_cache_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return self._history_cache_dir / f"{digest}.json"

    def _load_disk_cached_history(self, cache_key: str) -> Optional[pd.DataFrame]:
        cache_path = self._history_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            expires_at = _safe_float(payload.get("expires_at"))
            if expires_at <= self.__class__._cache_now_ts():
                return None

            records = payload.get("records")
            if not isinstance(records, list) or not records:
                return None

            history = pd.DataFrame(records)
            if "date" in history.columns:
                history["date"] = pd.to_datetime(history["date"])
            history = history.sort_values("date").reset_index(drop=True)
            self._history_cache[cache_key] = {"payload": history.copy(), "expires_at": expires_at}
            return history
        except Exception:
            logger.debug("Momentum history disk cache read failed: key=%s path=%s", cache_key, cache_path, exc_info=True)
            return None

    def _store_disk_cached_history(self, cache_key: str, history: pd.DataFrame, expires_at: float) -> None:
        try:
            self._history_cache_dir.mkdir(parents=True, exist_ok=True)
            serializable = history.copy()
            if "date" in serializable.columns:
                serializable["date"] = pd.to_datetime(serializable["date"]).dt.strftime("%Y-%m-%d")
            cache_path = self._history_cache_path(cache_key)
            cache_path.write_text(
                json.dumps(
                    {
                        "expires_at": expires_at,
                        "records": serializable.to_dict(orient="records"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Momentum history disk cache write failed: key=%s", cache_key, exc_info=True)

    def _build_features(self, row: pd.Series, history: pd.DataFrame, ctx: Dict[str, Any]) -> Dict[str, Any]:
        current = history.iloc[-1]
        prev = history.iloc[-2] if len(history) >= 2 else current
        close_series = history["close"].astype(float)
        amount_series = history["amount"].astype(float).fillna(0)
        pct_series = history["pct_chg"].astype(float).fillna(0)
        close_price = _safe_float(current.get("close"))

        prev_slice_20 = close_series.tail(21).iloc[:-1] if len(close_series) >= 2 else close_series
        prev_slice_60 = close_series.tail(61).iloc[:-1] if len(close_series) >= 2 else close_series
        prev_amount_slice = amount_series.tail(6).iloc[:-1] if len(amount_series) >= 2 else amount_series

        return {
            "prev_open": _safe_float(prev.get("open")),
            "prev_close": _safe_float(prev.get("close")),
            "close_position": self._compute_close_position(
                _safe_float(current.get("open")),
                _safe_float(current.get("high")),
                _safe_float(current.get("low")),
                close_price,
            ),
            "body_ratio": self._compute_body_ratio(
                _safe_float(current.get("open")),
                _safe_float(current.get("high")),
                _safe_float(current.get("low")),
                close_price,
            ),
            "upper_shadow_ratio": self._compute_upper_shadow_ratio(
                _safe_float(current.get("open")),
                _safe_float(current.get("high")),
                _safe_float(current.get("low")),
                close_price,
            ),
            "gap_open_ratio": (_safe_float(current.get("open")) - _safe_float(prev.get("close"))) / max(_safe_float(prev.get("close")), 1.0),
            "amplitude_ratio": (_safe_float(current.get("high")) - _safe_float(current.get("low"))) / max(close_price, 1.0),
            "ma5": close_series.tail(5).mean() if len(close_series) >= 5 else close_series.mean(),
            "ma10": close_series.tail(10).mean() if len(close_series) >= 10 else close_series.mean(),
            "ma20": close_series.tail(20).mean() if len(close_series) >= 20 else close_series.mean(),
            "prev_20d_high": prev_slice_20.max() if not prev_slice_20.empty else close_price,
            "prev_60d_high": prev_slice_60.max() if not prev_slice_60.empty else close_price,
            "cum_ret_3d": pct_series.tail(3).sum(),
            "cum_ret_5d": pct_series.tail(5).sum(),
            "up_days_5d": int((pct_series.tail(5) > 0).sum()),
            "strong_days_60d": int((pct_series.tail(60) >= 7).sum()),
            "limit_up_days_60d": int((pct_series.tail(60) >= 9.7).sum()),
            "volume_expand_5": _safe_float(row.get("amount")) / max(prev_amount_slice.mean(), 1.0) if not prev_amount_slice.empty else 1.0,
            "amount_rank_pct": ctx["amount_rank_pct"],
            "main_inflow_rank_pct": ctx["main_inflow_rank_pct"],
            "sector": ctx["sector"],
            "sector_stats": ctx["sector_stats"],
        }

    @staticmethod
    def _compute_close_position(open_price: float, high: float, low: float, close: float) -> float:
        if high <= low:
            return 1.0 if close >= open_price else 0.5
        return max(0.0, min(1.0, (close - low) / (high - low)))

    @staticmethod
    def _compute_body_ratio(open_price: float, high: float, low: float, close: float) -> float:
        if high <= low:
            return 1.0 if close > open_price else 0.0
        return max(0.0, min(1.0, abs(close - open_price) / (high - low)))

    @staticmethod
    def _compute_upper_shadow_ratio(open_price: float, high: float, low: float, close: float) -> float:
        if high <= low:
            return 0.0
        return max(0.0, min(1.0, (high - max(open_price, close)) / (high - low)))

    def _score_standard(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        breakdown = {
            "strength_confirmation": self._score_strength_confirmation(row, features),
            "volume_price_structure": self._score_volume_price(row, features),
            "trend_position": self._score_trend_position(row, features),
            "sector_resonance": self._score_sector_resonance(row, features),
            "capital_support": self._score_capital_support(row, features),
            "elasticity_activity": self._score_elasticity(row, features),
        }
        risk_penalty, risk_tags = self._score_risk_penalty(row, features)

        base_score = sum(item["score"] for item in breakdown.values())
        final_score = max(0.0, base_score - risk_penalty)
        continuation_score = (
            (breakdown["strength_confirmation"]["score"] / 20.0) * 0.30
            + (breakdown["volume_price_structure"]["score"] / 20.0) * 0.30
            + (breakdown["sector_resonance"]["score"] / 20.0) * 0.25
            + (breakdown["capital_support"]["score"] / 15.0) * 0.15
        ) * 100
        extension_score = (
            (breakdown["trend_position"]["score"] / 15.0) * 0.40
            + (breakdown["sector_resonance"]["score"] / 20.0) * 0.30
            + (breakdown["elasticity_activity"]["score"] / 10.0) * 0.30
        ) * 100
        risk_score = (risk_penalty / 20.0) * 100
        rank_score = continuation_score * 0.65 + extension_score * 0.25 - risk_score * 0.10

        sector_stats = features["sector_stats"]
        leader_rank = sector_stats.get("leader_map", {}).get(row["ts_code"], 999)
        leader_level = self._classify_leader_level(leader_rank)
        entry_range_low, entry_range_high = self._build_standard_entry_range(
            row,
            features,
            leader_rank=leader_rank,
        )

        return {
            "ts_code": row["ts_code"],
            "name": row["name"],
            "pct_chg": round(_safe_float(row.get("pct_chg")), 2),
            "continuation_score": round(continuation_score, 1),
            "extension_score": round(extension_score, 1),
            "risk_score": round(risk_score, 1),
            "buyability_score": None,
            "final_score": round(final_score, 1),
            "rank_score": round(rank_score, 1),
            "themes": [features["sector"]],
            "leader_level": leader_level,
            "top_reasons": self._build_top_reasons(breakdown),
            "risk_tags": risk_tags,
            "score_breakdown": {
                key: {
                    "score": round(value["score"], 1),
                    "max_score": value["max_score"],
                    "items": value["items"],
                }
                for key, value in breakdown.items()
            },
            "opportunity_tag": None,
            "entry_range_low": entry_range_low,
            "entry_range_high": entry_range_high,
        }

    def _build_standard_entry_range(
        self,
        row: pd.Series,
        features: Dict[str, Any],
        *,
        leader_rank: int,
    ) -> tuple[Optional[float], Optional[float]]:
        close_price = _safe_float(row.get("close"))
        if close_price <= 0:
            return None, None

        open_price = _safe_float(row.get("open"))
        ma5 = _safe_float(features.get("ma5"))
        prev_20d_high = _safe_float(features.get("prev_20d_high"))

        is_leader_like = int(leader_rank) <= 2
        total_width_ratio = 0.02 if is_leader_like else 0.03
        half_width_ratio = total_width_ratio / 2

        support_floor = close_price * (1 - half_width_ratio)
        if open_price > 0:
            support_floor = max(support_floor, min(open_price, close_price))
        if ma5 > 0:
            support_floor = max(support_floor, ma5 * (0.997 if is_leader_like else 0.995))

        confirm_ceiling = close_price * (1 + half_width_ratio)
        if prev_20d_high > 0 and close_price >= prev_20d_high * 0.97:
            breakout_confirmation = prev_20d_high * (1.005 if is_leader_like else 1.01)
            if breakout_confirmation >= support_floor:
                confirm_ceiling = min(confirm_ceiling, breakout_confirmation)

        entry_low = support_floor
        entry_high = max(entry_low, confirm_ceiling)
        max_width_value = close_price * total_width_ratio
        if entry_high - entry_low > max_width_value:
            entry_high = entry_low + max_width_value

        return round(entry_low, 2), round(max(entry_low, entry_high), 2)

    def _score_aggressive(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        breakdown = {
            "strength_confirmation": self._score_aggressive_strength_confirmation(row, features),
            "capital_support": self._score_aggressive_capital_support(row, features),
            "buyability": self._score_aggressive_buyability(row, features),
            "volume_price_track": self._score_aggressive_volume_track(row, features),
            "sector_resonance": self._score_aggressive_sector_resonance(row, features),
            "trend_elasticity": self._score_aggressive_trend_elasticity(row, features),
        }
        risk_penalty, risk_tags = self._score_aggressive_risk_penalty(row, features)

        base_score = sum(item["score"] for item in breakdown.values())
        final_score = max(0.0, base_score - risk_penalty)
        continuation_score = (
            (breakdown["strength_confirmation"]["score"] / 30.0) * 0.35
            + (breakdown["capital_support"]["score"] / 20.0) * 0.25
            + (breakdown["volume_price_track"]["score"] / 15.0) * 0.20
            + (breakdown["sector_resonance"]["score"] / 12.0) * 0.10
            + (breakdown["trend_elasticity"]["score"] / 8.0) * 0.10
        ) * 100
        extension_score = (
            (breakdown["strength_confirmation"]["score"] / 30.0) * 0.25
            + (breakdown["sector_resonance"]["score"] / 12.0) * 0.20
            + (breakdown["trend_elasticity"]["score"] / 8.0) * 0.30
            + (breakdown["buyability"]["score"] / 15.0) * 0.25
        ) * 100
        buyability_score = (
            (breakdown["buyability"]["score"] / 15.0) * 0.50
            + (breakdown["volume_price_track"]["score"] / 15.0) * 0.30
            + (breakdown["capital_support"]["score"] / 20.0) * 0.20
        ) * 100
        risk_score = (risk_penalty / 15.0) * 100
        rank_score = continuation_score * 0.55 + buyability_score * 0.25 + extension_score * 0.20 - risk_score * 0.12

        sector_stats = features["sector_stats"]
        leader_rank = sector_stats.get("leader_map", {}).get(row["ts_code"], 999)
        entry_range_low, entry_range_high = self._build_aggressive_entry_range(row, features)
        opportunity_tag = self._build_aggressive_opportunity_tag(row, features)

        return {
            "ts_code": row["ts_code"],
            "name": row["name"],
            "pct_chg": round(_safe_float(row.get("pct_chg")), 2),
            "continuation_score": round(continuation_score, 1),
            "extension_score": round(extension_score, 1),
            "risk_score": round(risk_score, 1),
            "buyability_score": round(buyability_score, 1),
            "final_score": round(final_score, 1),
            "rank_score": round(rank_score, 1),
            "themes": [features["sector"]],
            "leader_level": self._classify_leader_level(leader_rank),
            "top_reasons": self._build_top_reasons(breakdown),
            "risk_tags": risk_tags,
            "score_breakdown": {
                key: {
                    "score": round(value["score"], 1),
                    "max_score": value["max_score"],
                    "items": value["items"],
                }
                for key, value in breakdown.items()
            },
            "opportunity_tag": opportunity_tag,
            "entry_range_low": entry_range_low,
            "entry_range_high": entry_range_high,
        }

    def _score_aggressive_strength_confirmation(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        gap_open_ratio = _safe_float(features["gap_open_ratio"])
        close_position = _safe_float(features["close_position"])
        cum_ret_3d = _safe_float(features["cum_ret_3d"])

        limit_score = 10 if limit_proximity >= 0.997 else 8 if limit_proximity >= 0.99 else 6 if limit_proximity >= 0.98 else 4 if limit_proximity >= 0.97 else 0
        if 0.03 <= gap_open_ratio <= 0.07:
            gap_score = 8
        elif 0.015 <= gap_open_ratio < 0.03:
            gap_score = 6
        elif 0.07 < gap_open_ratio <= 0.095:
            gap_score = 5
        elif gap_open_ratio > 0.095 and limit_proximity >= 0.997:
            gap_score = 5
        elif 0 <= gap_open_ratio < 0.015:
            gap_score = 3
        else:
            gap_score = 0
        close_score = 6 if close_position >= 0.92 else 5 if close_position >= 0.82 else 3 if close_position >= 0.70 else 1 if close_position >= 0.55 else 0
        accel_score = 6 if cum_ret_3d >= 20 and limit_proximity >= 0.99 else 4 if cum_ret_3d >= 15 and close_position >= 0.82 else 2 if cum_ret_3d >= 10 else 0

        return {
            "score": float(limit_score + gap_score + close_score + accel_score),
            "max_score": 30,
            "items": {
                "limit_strength": limit_score,
                "gap_open_strength": gap_score,
                "close_status": close_score,
                "acceleration_confirmation": accel_score,
            },
        }

    def _score_aggressive_capital_support(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        main_net_inflow = _safe_float(row.get("main_net_inflow"))
        inflow_rank_pct = _safe_float(features["main_inflow_rank_pct"])
        main_inflow_ratio = main_net_inflow / max(_safe_float(row.get("amount")), 1.0)
        top_list_flag = bool(row.get("top_list_flag", False))
        top_list_net_amount = _safe_float(row.get("top_list_net_amount"))
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        pct_chg = _safe_float(row.get("pct_chg"))

        absolute_score = 0 if main_net_inflow <= 0 else 8 if inflow_rank_pct >= 0.90 else 6 if inflow_rank_pct >= 0.75 else 4 if inflow_rank_pct >= 0.50 else 2
        ratio_score = 6 if main_inflow_ratio >= 0.06 else 5 if main_inflow_ratio >= 0.04 else 3 if main_inflow_ratio >= 0.02 else 1 if main_inflow_ratio >= 0 else 0
        consistency_score = 4 if limit_proximity >= 0.99 and main_net_inflow > 0 else 3 if pct_chg >= 7 and main_net_inflow > 0 else 1 if pct_chg >= 7 and main_inflow_ratio >= 0 else 0
        top_list_score = 2 if top_list_flag and top_list_net_amount > 0 else 1 if (not top_list_flag) or top_list_net_amount == 0 else 0

        return {
            "score": float(absolute_score + ratio_score + consistency_score + top_list_score),
            "max_score": 20,
            "items": {
                "main_inflow_abs": absolute_score,
                "main_inflow_ratio": ratio_score,
                "price_flow_alignment": consistency_score,
                "top_list": top_list_score,
            },
        }

    def _score_aggressive_buyability(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        amplitude_ratio = _safe_float(features["amplitude_ratio"])
        amount = _safe_float(row.get("amount"))
        turnover_rate = _safe_float(row.get("turnover_rate"))

        amplitude_score = 6 if 0.025 <= amplitude_ratio <= 0.06 else 4 if 0.015 <= amplitude_ratio < 0.025 else 3 if 0.06 < amplitude_ratio <= 0.08 else 1 if 0.008 <= amplitude_ratio < 0.015 else 0
        amount_score = 5 if 5e8 <= amount <= 1.8e9 else 4 if 3e8 <= amount < 5e8 or 1.8e9 < amount <= 2.5e9 else 2 if 2.5e9 < amount <= 4e9 else 0
        turnover_score = 4 if 5 <= turnover_rate <= 15 else 3 if 3 <= turnover_rate < 5 or 15 < turnover_rate <= 20 else 1 if 20 < turnover_rate <= 25 else 0

        return {
            "score": float(amplitude_score + amount_score + turnover_score),
            "max_score": 15,
            "items": {
                "amplitude_space": amplitude_score,
                "amount_golden_zone": amount_score,
                "turnover_golden_zone": turnover_score,
            },
        }

    def _build_aggressive_entry_range(self, row: pd.Series, features: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        close_price = _safe_float(row.get("close"))
        open_price = _safe_float(row.get("open"))
        if close_price <= 0:
            return None, None

        body_low = min(open_price, close_price) if open_price > 0 else close_price
        entry_low = max(close_price * 0.985, body_low)
        entry_high = close_price * 1.015
        return round(entry_low, 2), round(entry_high, 2)

    def _build_aggressive_opportunity_tag(self, row: pd.Series, features: Dict[str, Any]) -> Optional[str]:
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        volume_ratio = _safe_float(row.get("volume_ratio"))
        close_position = _safe_float(features.get("close_position"))
        amplitude_ratio = _safe_float(features.get("amplitude_ratio"))
        turnover_rate = _safe_float(row.get("turnover_rate"))

        if limit_proximity >= 0.997 and volume_ratio < 1.0:
            return "一致再加速"
        if limit_proximity >= 0.99 and close_position >= 0.82 and amplitude_ratio >= 0.025 and turnover_rate >= 5:
            return "分歧转一致"
        if close_position >= 0.82 and turnover_rate >= 3:
            return "强势跟踪"
        return None

    def _score_aggressive_volume_track(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        volume_ratio = _safe_float(row.get("volume_ratio"), 1.0)
        turnover_rate = _safe_float(row.get("turnover_rate"))
        amplitude_ratio = _safe_float(features["amplitude_ratio"])

        if limit_proximity >= 0.997:
            shrink_score = 8 if volume_ratio < 1.0 else 6 if volume_ratio < 1.5 else 3 if volume_ratio <= 2.5 else 0
        else:
            shrink_score = 0

        if limit_proximity < 0.997 or amplitude_ratio >= 0.015:
            if 1.5 <= volume_ratio <= 3.5 and 5 <= turnover_rate <= 15:
                turnover_score = 7
            elif 1.2 <= volume_ratio < 1.5 or 3.5 < volume_ratio <= 4.0:
                turnover_score = 5
            elif 1.0 <= volume_ratio < 1.2 or 3 <= turnover_rate < 5:
                turnover_score = 3
            elif volume_ratio > 5.0 or turnover_rate > 25:
                turnover_score = 0
            else:
                turnover_score = 1
        else:
            turnover_score = 0

        return {
            "score": float(min(shrink_score + turnover_score, 15)),
            "max_score": 15,
            "items": {
                "consensus_limit": shrink_score,
                "healthy_turnover": turnover_score,
            },
        }

    def _score_aggressive_sector_resonance(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        sector_stats = features["sector_stats"]
        sector_rank = int(sector_stats.get("sector_rank", 999))
        sector_total = max(int(sector_stats.get("sector_total", 1)), 1)
        rank_pct = sector_rank / sector_total
        strong_count = int(sector_stats.get("strong_count", 0))
        limit_count = int(sector_stats.get("limit_count", 0))
        leader_rank = int(sector_stats.get("leader_map", {}).get(row["ts_code"], 999))

        rank_score = 5 if rank_pct <= 0.10 else 4 if rank_pct <= 0.20 else 3 if rank_pct <= 0.35 else 2 if rank_pct <= 0.50 else 0
        breadth_score = 4 if limit_count >= 3 or strong_count >= 6 else 3 if limit_count == 2 or 4 <= strong_count <= 5 else 2 if limit_count == 1 or 2 <= strong_count <= 3 else 0
        leader_score = 3 if leader_rank <= 2 else 2 if leader_rank <= 5 else 0

        return {
            "score": float(rank_score + breadth_score + leader_score),
            "max_score": 12,
            "items": {
                "sector_rank": rank_score,
                "sector_breadth": breadth_score,
                "sector_leader": leader_score,
            },
        }

    def _score_aggressive_trend_elasticity(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        close_price = _safe_float(row.get("close"))
        prev_20d_high = _safe_float(features["prev_20d_high"], close_price)
        prev_60d_high = _safe_float(features["prev_60d_high"], close_price)
        circ_mv = _safe_float(row.get("circ_mv"))
        strong_days_60d = int(features["strong_days_60d"])
        limit_up_days_60d = int(features["limit_up_days_60d"])

        breakout_score = 4 if close_price > prev_20d_high or _safe_float(row.get("high")) > prev_60d_high else 3 if prev_20d_high > 0 and abs(close_price - prev_20d_high) / prev_20d_high <= 0.01 else 2 if prev_20d_high > 0 and abs(close_price - prev_20d_high) / prev_20d_high <= 0.03 else 0
        mv_score = 2 if 3e10 <= circ_mv <= 1.5e11 else 1 if 1.5e10 <= circ_mv < 3e10 or 1.5e11 < circ_mv <= 3e11 else 0
        history_score = 2 if limit_up_days_60d >= 1 or strong_days_60d >= 3 else 1 if strong_days_60d >= 1 else 0

        return {
            "score": float(breakout_score + mv_score + history_score),
            "max_score": 8,
            "items": {
                "breakout": breakout_score,
                "circ_mv": mv_score,
                "historical_activity": history_score,
            },
        }

    def _score_aggressive_risk_penalty(self, row: pd.Series, features: Dict[str, Any]) -> tuple[float, List[str]]:
        penalties: List[tuple[str, int]] = []
        pct_chg = _safe_float(row.get("pct_chg"))
        main_net_inflow = _safe_float(row.get("main_net_inflow"))
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        volume_expand_5 = _safe_float(features["volume_expand_5"], 1.0)
        close_position = _safe_float(features["close_position"])
        upper_shadow_ratio = _safe_float(features["upper_shadow_ratio"])
        sector_stats = features["sector_stats"]
        strong_count = int(sector_stats.get("strong_count", 0))
        limit_count = int(sector_stats.get("limit_count", 0))

        if pct_chg >= 7 and main_net_inflow < 0:
            if limit_proximity >= 0.99 and main_net_inflow < -1e6:
                penalties.append(("price_flow_divergence", 8))
            elif main_net_inflow < -1e6:
                penalties.append(("price_flow_divergence", 6))
            else:
                penalties.append(("price_flow_divergence", 3))

        if volume_expand_5 >= 3 and close_position < 0.55:
            penalties.append(("blowoff_volume", 5))
        elif 2.5 <= volume_expand_5 < 3 and close_position < 0.65:
            penalties.append(("blowoff_volume", 3))
        elif volume_expand_5 >= 3 and close_position >= 0.65:
            penalties.append(("blowoff_volume", 1))

        if upper_shadow_ratio >= 0.35:
            penalties.append(("upper_shadow", 4))
        elif upper_shadow_ratio >= 0.25:
            penalties.append(("upper_shadow", 2))

        if strong_count <= 1 and limit_count == 0:
            penalties.append(("sector_fade", 4))
        elif strong_count <= 2:
            penalties.append(("sector_fade", 2))

        total_penalty = min(sum(score for _, score in penalties), 15)
        return float(total_penalty), [name for name, _ in penalties]

    def _score_strength_confirmation(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        pct_chg = _safe_float(row.get("pct_chg"))
        close_position = _safe_float(features["close_position"])
        limit_proximity = _safe_float(row.get("close")) / max(_safe_float(row.get("up_limit")), 1.0)
        body_ratio = _safe_float(features["body_ratio"])

        change_score = 6 if pct_chg >= 9.7 else 5 if pct_chg >= 9.0 else 4 if pct_chg >= 8.0 else 3 if pct_chg >= 7.0 else 0
        close_score = 5 if close_position >= 0.90 else 4 if close_position >= 0.80 else 3 if close_position >= 0.65 else 2 if close_position >= 0.50 else 0
        limit_score = 4 if limit_proximity >= 0.995 else 3 if limit_proximity >= 0.985 else 2 if limit_proximity >= 0.97 else 1 if limit_proximity >= 0.95 else 0
        body_score = 5 if body_ratio >= 0.70 else 4 if body_ratio >= 0.55 else 3 if body_ratio >= 0.40 else 2 if body_ratio >= 0.25 else 0

        return {
            "score": float(change_score + close_score + limit_score + body_score),
            "max_score": 20,
            "items": {
                "pct_chg_strength": change_score,
                "close_position": close_score,
                "limit_proximity": limit_score,
                "body_ratio": body_score,
            },
        }

    def _score_volume_price(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        volume_ratio = _safe_float(row.get("volume_ratio"), 1.0)
        turnover_rate = _safe_float(row.get("turnover_rate"))
        amount_rank_pct = _safe_float(features["amount_rank_pct"])
        volume_expand_5 = _safe_float(features["volume_expand_5"], 1.0)

        volume_score = 6 if 1.5 <= volume_ratio <= 3.0 else 5 if 1.2 <= volume_ratio < 1.5 else 4 if 3.0 < volume_ratio <= 4.0 else 3 if 1.0 <= volume_ratio < 1.2 else 2 if 4.0 < volume_ratio <= 5.0 else 0
        turnover_score = 6 if 3 <= turnover_rate <= 15 else 5 if 2 <= turnover_rate < 3 else 4 if 15 < turnover_rate <= 20 else 3 if 1 <= turnover_rate < 2 else 2 if 20 < turnover_rate <= 25 else 0
        amount_score = 4 if amount_rank_pct >= 0.80 else 3 if amount_rank_pct >= 0.60 else 2 if amount_rank_pct >= 0.30 else 0
        expand_score = 4 if 1.5 <= volume_expand_5 <= 3.0 else 3 if 1.2 <= volume_expand_5 < 1.5 else 2 if 3.0 < volume_expand_5 <= 4.0 else 1 if 1.0 <= volume_expand_5 < 1.2 else 0

        return {
            "score": float(volume_score + turnover_score + amount_score + expand_score),
            "max_score": 20,
            "items": {
                "volume_ratio": volume_score,
                "turnover_rate": turnover_score,
                "amount_rank": amount_score,
                "volume_expand_5": expand_score,
            },
        }

    def _score_trend_position(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        close_price = _safe_float(row.get("close"))
        ma5 = _safe_float(features["ma5"])
        ma10 = _safe_float(features["ma10"])
        ma20 = _safe_float(features["ma20"])
        prev_20d_high = _safe_float(features["prev_20d_high"], close_price)
        prev_60d_high = _safe_float(features["prev_60d_high"], close_price)
        cum_ret_5d = _safe_float(features["cum_ret_5d"])
        up_days_5d = int(features["up_days_5d"])

        ma_score = 5 if ma5 > ma10 > ma20 and close_price > ma5 else 4 if ma5 > ma10 and close_price > ma10 else 3 if close_price > ma5 else 2 if close_price > ma20 else 0
        break_score = 5 if close_price > prev_20d_high or _safe_float(row.get("high")) > prev_60d_high else 4 if prev_20d_high > 0 and abs(close_price - prev_20d_high) / prev_20d_high <= 0.01 else 3 if prev_20d_high > 0 and abs(close_price - prev_20d_high) / prev_20d_high <= 0.03 else 1 if close_price >= ma10 else 0
        strong_score = 5 if cum_ret_5d >= 15 and up_days_5d >= 3 else 4 if cum_ret_5d >= 10 and up_days_5d >= 3 else 3 if cum_ret_5d >= 5 else 1 if _safe_float(row.get("pct_chg")) >= 7 else 0

        return {
            "score": float(ma_score + break_score + strong_score),
            "max_score": 15,
            "items": {
                "ma_structure": ma_score,
                "breakout": break_score,
                "strong_trend_5d": strong_score,
            },
        }

    def _score_sector_resonance(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        sector_stats = features["sector_stats"]
        sector_rank = int(sector_stats.get("sector_rank", 999))
        sector_total = max(int(sector_stats.get("sector_total", 1)), 1)
        rank_pct = sector_rank / sector_total
        strong_count = int(sector_stats.get("strong_count", 0))
        limit_count = int(sector_stats.get("limit_count", 0))
        leader_rank = int(sector_stats.get("leader_map", {}).get(row["ts_code"], 999))
        sector_size = max(int(sector_stats.get("size", 1)), 1)

        rank_score = 5 if rank_pct <= 0.10 else 4 if rank_pct <= 0.20 else 3 if rank_pct <= 0.35 else 2 if rank_pct <= 0.50 else 0
        breadth_score = 6 if limit_count >= 3 or strong_count >= 6 else 5 if limit_count == 2 or 4 <= strong_count <= 5 else 3 if limit_count == 1 or 2 <= strong_count <= 3 else 1 if strong_count == 1 else 0
        ladder_score = 4 if leader_rank <= 2 and strong_count >= 3 else 3 if strong_count >= 2 else 2 if strong_count >= 1 else 0
        leader_score = 5 if leader_rank <= 2 else 4 if leader_rank <= 5 else 2 if leader_rank <= max(int(sector_size / 2), 1) else 0

        return {
            "score": float(rank_score + breadth_score + ladder_score + leader_score),
            "max_score": 20,
            "items": {
                "sector_rank": rank_score,
                "sector_breadth": breadth_score,
                "sector_ladder": ladder_score,
                "sector_leader": leader_score,
            },
        }

    def _score_capital_support(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        main_net_inflow = _safe_float(row.get("main_net_inflow"))
        inflow_rank_pct = _safe_float(features["main_inflow_rank_pct"])
        main_inflow_ratio = main_net_inflow / max(_safe_float(row.get("amount")), 1.0)
        top_list_flag = bool(row.get("top_list_flag", False))
        top_list_net_amount = _safe_float(row.get("top_list_net_amount"))
        pct_chg = _safe_float(row.get("pct_chg"))

        absolute_score = 0 if main_net_inflow <= 0 else 6 if inflow_rank_pct >= 0.90 else 5 if inflow_rank_pct >= 0.75 else 3 if inflow_rank_pct >= 0.50 else 1
        ratio_score = 4 if main_inflow_ratio >= 0.05 else 3 if main_inflow_ratio >= 0.03 else 2 if main_inflow_ratio >= 0.01 else 1 if main_inflow_ratio >= 0 else 0
        top_list_score = 3 if top_list_flag and top_list_net_amount > 0 else 2 if top_list_flag and top_list_net_amount == 0 else 1 if not top_list_flag else 0
        consistency_score = 2 if pct_chg >= 9 and main_net_inflow > 0 else 1 if pct_chg >= 7 and main_net_inflow > 0 else 0

        return {
            "score": float(absolute_score + ratio_score + top_list_score + consistency_score),
            "max_score": 15,
            "items": {
                "main_inflow_abs": absolute_score,
                "main_inflow_ratio": ratio_score,
                "top_list": top_list_score,
                "price_flow_alignment": consistency_score,
            },
        }

    def _score_elasticity(self, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
        circ_mv = _safe_float(row.get("circ_mv"))
        strong_days_60d = int(features["strong_days_60d"])
        limit_up_days_60d = int(features["limit_up_days_60d"])
        pct_chg = _safe_float(row.get("pct_chg"))
        top_list_flag = bool(row.get("top_list_flag", False))

        mv_score = 4 if 3e10 <= circ_mv <= 1.5e11 else 3 if 1.5e10 <= circ_mv < 3e10 or 1.5e11 < circ_mv <= 3e11 else 2 if 3e11 < circ_mv <= 5e11 else 0
        history_score = 4 if limit_up_days_60d >= 1 or strong_days_60d >= 3 else 3 if strong_days_60d == 2 else 2 if strong_days_60d == 1 else 0
        activity_score = 2 if strong_days_60d >= 2 or top_list_flag or pct_chg >= 9.0 else 1 if strong_days_60d >= 1 else 0

        return {
            "score": float(mv_score + history_score + activity_score),
            "max_score": 10,
            "items": {
                "circ_mv": mv_score,
                "historical_activity": history_score,
                "recognition": activity_score,
            },
        }

    def _score_risk_penalty(self, row: pd.Series, features: Dict[str, Any]) -> tuple[float, List[str]]:
        penalties: List[tuple[str, int]] = []
        upper_shadow_ratio = _safe_float(features["upper_shadow_ratio"])
        volume_expand_5 = _safe_float(features["volume_expand_5"], 1.0)
        close_position = _safe_float(features["close_position"])
        cum_ret_3d = _safe_float(features["cum_ret_3d"])
        cum_ret_5d = _safe_float(features["cum_ret_5d"])
        main_net_inflow = _safe_float(row.get("main_net_inflow"))
        pct_chg = _safe_float(row.get("pct_chg"))
        sector_stats = features["sector_stats"]
        strong_count = int(sector_stats.get("strong_count", 0))
        limit_count = int(sector_stats.get("limit_count", 0))
        top_list_flag = bool(row.get("top_list_flag", False))
        top_list_net_amount = _safe_float(row.get("top_list_net_amount"))

        if upper_shadow_ratio >= 0.40:
            penalties.append(("长上影/冲高回落", 5))
        elif upper_shadow_ratio >= 0.30:
            penalties.append(("上影偏长", 4))
        elif upper_shadow_ratio >= 0.20:
            penalties.append(("冲高回落", 2))

        if volume_expand_5 > 4 and close_position < 0.55:
            penalties.append(("爆量滞涨", 4))
        elif 3 <= volume_expand_5 <= 4 and close_position < 0.65:
            penalties.append(("放量分歧", 3))
        elif volume_expand_5 > 3 and close_position >= 0.65:
            penalties.append(("高量透支", 1))

        if close_position < 0.50:
            penalties.append(("尾盘走弱", 4))
        elif close_position < 0.65:
            penalties.append(("尾盘承接一般", 2))

        if cum_ret_3d >= 20 or cum_ret_5d >= 30:
            penalties.append(("高位连续加速", 5))
        elif 15 <= cum_ret_3d < 20:
            penalties.append(("短期加速明显", 3))
        elif 20 <= cum_ret_5d < 30:
            penalties.append(("连续走强后分歧风险", 2))

        if pct_chg >= 7 and main_net_inflow < 0:
            penalties.append(("价资背离", 4 if main_net_inflow < -1e6 else 2))

        if strong_count <= 1 and limit_count == 0:
            penalties.append(("板块退潮", 5))
        elif strong_count <= 2:
            penalties.append(("板块跟随偏弱", 3))
        elif strong_count <= 3:
            penalties.append(("板块联动一般", 1))

        if top_list_flag and top_list_net_amount < 0:
            penalties.append(("龙虎榜偏兑现", 3 if top_list_net_amount < -1e6 else 1))

        total_penalty = min(sum(score for _, score in penalties), 20)
        risk_tags = [name for name, _ in penalties]
        return float(total_penalty), risk_tags

    def _score_risk_penalty(self, row: pd.Series, features: Dict[str, Any]) -> tuple[float, List[str]]:
        penalties: List[tuple[str, int]] = []
        upper_shadow_ratio = _safe_float(features["upper_shadow_ratio"])
        volume_expand_5 = _safe_float(features["volume_expand_5"], 1.0)
        close_position = _safe_float(features["close_position"])
        cum_ret_3d = _safe_float(features["cum_ret_3d"])
        cum_ret_5d = _safe_float(features["cum_ret_5d"])
        main_net_inflow = _safe_float(row.get("main_net_inflow"))
        pct_chg = _safe_float(row.get("pct_chg"))
        sector_stats = features["sector_stats"]
        strong_count = int(sector_stats.get("strong_count", 0))
        limit_count = int(sector_stats.get("limit_count", 0))
        top_list_flag = bool(row.get("top_list_flag", False))
        top_list_net_amount = _safe_float(row.get("top_list_net_amount"))

        if upper_shadow_ratio >= 0.40:
            penalties.append(("upper_shadow", 5))
        elif upper_shadow_ratio >= 0.30:
            penalties.append(("upper_shadow", 4))
        elif upper_shadow_ratio >= 0.20:
            penalties.append(("upper_shadow", 2))

        if volume_expand_5 > 4 and close_position < 0.55:
            penalties.append(("blowoff_volume", 4))
        elif 3 <= volume_expand_5 <= 4 and close_position < 0.65:
            penalties.append(("blowoff_volume", 3))
        elif volume_expand_5 > 3 and close_position >= 0.65:
            penalties.append(("blowoff_volume", 1))

        if close_position < 0.50:
            penalties.append(("late_session_weakness", 4))
        elif close_position < 0.65:
            penalties.append(("late_session_weakness", 2))

        if cum_ret_3d >= 20 or cum_ret_5d >= 30:
            penalties.append(("high_acceleration", 5))
        elif 15 <= cum_ret_3d < 20:
            penalties.append(("high_acceleration", 3))
        elif 20 <= cum_ret_5d < 30:
            penalties.append(("high_acceleration", 2))

        if pct_chg >= 7 and main_net_inflow < 0:
            penalties.append(("price_flow_divergence", 4 if main_net_inflow < -1e6 else 2))

        if strong_count <= 1 and limit_count == 0:
            penalties.append(("sector_fade", 5))
        elif strong_count <= 2:
            penalties.append(("sector_fade", 3))
        elif strong_count <= 3:
            penalties.append(("sector_fade", 1))

        if top_list_flag and top_list_net_amount < 0:
            penalties.append(("top_list_distribution", 3 if top_list_net_amount < -1e6 else 1))

        total_penalty = min(sum(score for _, score in penalties), 15)
        return float(total_penalty), [name for name, _ in penalties]

    @staticmethod
    def _build_top_reasons(breakdown: Dict[str, Dict[str, Any]]) -> List[str]:
        label_map = {
            "strength_confirmation": "强势确认",
            "volume_price_structure": "量价结构",
            "trend_position": "趋势位置",
            "sector_resonance": "板块共振",
            "capital_support": "资金承接",
            "elasticity_activity": "弹性与股性",
            "buyability": "买入可行性",
            "volume_price_track": "量价双轨",
            "trend_elasticity": "趋势位置与弹性",
        }
        reasons: List[tuple[str, float]] = []
        for key, value in breakdown.items():
            max_score = max(value["max_score"], 1)
            ratio = value["score"] / max_score
            if ratio >= 0.70:
                reasons.append((label_map.get(key, key), value["score"]))

        reasons.sort(key=lambda item: item[1], reverse=True)
        return [name for name, _ in reasons[:3]]

    @staticmethod
    def _classify_leader_level(rank: int) -> str:
        if rank <= 2:
            return "龙头"
        if rank <= 5:
            return "前排"
        if rank <= 10:
            return "中位"
        return "后排"
