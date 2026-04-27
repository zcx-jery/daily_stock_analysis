# -*- coding: utf-8 -*-
"""Tests for MomentumScreenerService."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import pandas as pd

sys.modules.setdefault(
    "fake_useragent",
    types.SimpleNamespace(UserAgent=lambda *args, **kwargs: types.SimpleNamespace(random="pytest-agent")),
)

from src.config import Config
from src.services.momentum_screener_service import MomentumScreenerService


class _FakeFetcher:
    def __init__(
        self,
        *,
        current_time: datetime | None = None,
        snapshot_by_trade_date: dict[str, dict[str, pd.DataFrame]] | None = None,
    ) -> None:
        self.api_calls: dict[str, int] = {}
        self.history_calls: dict[str, int] = {}
        self.snapshot = {
            "stock_basic": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "symbol": "600001",
                        "name": "测试龙头",
                        "industry": "旧行业A",
                        "market": "主板",
                        "list_date": "20150101",
                        "list_status": "L",
                    },
                    {
                        "ts_code": "600002.SH",
                        "symbol": "600002",
                        "name": "测试跟风",
                        "industry": "旧行业B",
                        "market": "主板",
                        "list_date": "20160101",
                        "list_status": "L",
                    },
                ]
            ),
            "index_classify": pd.DataFrame(
                [
                    {"index_code": "801730.SI", "industry_name": "电力设备"},
                    {"index_code": "801120.SI", "industry_name": "食品饮料"},
                ]
            ),
            "daily": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "trade_date": "20260410",
                        "open": 10.0,
                        "high": 11.1,
                        "low": 9.95,
                        "close": 11.0,
                        "pct_chg": 9.8,
                        "amount": 800000,
                    },
                    {
                        "ts_code": "600002.SH",
                        "trade_date": "20260410",
                        "open": 8.0,
                        "high": 8.8,
                        "low": 7.9,
                        "close": 8.65,
                        "pct_chg": 8.1,
                        "amount": 500000,
                    },
                ]
            ),
            "daily_basic": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "trade_date": "20260410",
                        "turnover_rate": 8.2,
                        "volume_ratio": 2.0,
                        "circ_mv": 6000000,
                    },
                    {
                        "ts_code": "600002.SH",
                        "trade_date": "20260410",
                        "turnover_rate": 4.2,
                        "volume_ratio": 1.4,
                        "circ_mv": 9000000,
                    },
                ]
            ),
            "moneyflow": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "trade_date": "20260410",
                        "net_mf_amount": 30000,
                    },
                    {
                        "ts_code": "600002.SH",
                        "trade_date": "20260410",
                        "net_mf_amount": 12000,
                    },
                ]
            ),
            "stk_limit": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "trade_date": "20260410",
                        "up_limit": 11.0,
                        "down_limit": 9.0,
                    },
                    {
                        "ts_code": "600002.SH",
                        "trade_date": "20260410",
                        "up_limit": 8.8,
                        "down_limit": 7.2,
                    },
                ]
            ),
            "top_list": pd.DataFrame(
                [
                    {
                        "ts_code": "600001.SH",
                        "trade_date": "20260410",
                        "net_amount": 2000,
                    }
                ]
            ),
        }
        self.trade_snapshots = {
            "20260410": {
                "daily": self.snapshot["daily"].copy(),
                "daily_basic": self.snapshot["daily_basic"].copy(),
                "moneyflow": self.snapshot["moneyflow"].copy(),
                "stk_limit": self.snapshot["stk_limit"].copy(),
                "top_list": self.snapshot["top_list"].copy(),
            }
        }
        if snapshot_by_trade_date:
            for trade_date, tables in snapshot_by_trade_date.items():
                self.trade_snapshots[trade_date] = {
                    name: table.copy()
                    for name, table in tables.items()
                }
        self.trade_dates = sorted(self.trade_snapshots.keys(), reverse=True)
        self.current_time = current_time or datetime(2026, 4, 10, 18, 0, 0)
        self.index_member_by_code = {
            "801730.SI": pd.DataFrame(
                [
                    {
                        "index_code": "801730.SI",
                        "index_name": "电力设备",
                        "con_code": "600001.SH",
                        "in_date": "20100101",
                        "out_date": "",
                        "is_new": "Y",
                    },
                    {
                        "index_code": "801730.SI",
                        "index_name": "电力设备",
                        "con_code": "600002.SH",
                        "in_date": "20100101",
                        "out_date": "",
                        "is_new": "Y",
                    },
                ]
            ),
            "801120.SI": pd.DataFrame(
                [
                    {
                        "index_code": "801120.SI",
                        "index_name": "食品饮料",
                        "con_code": "600099.SH",
                        "in_date": "20100101",
                        "out_date": "",
                        "is_new": "Y",
                    }
                ]
            ),
        }
        self.index_daily_by_code = {
            "801730.SI": pd.DataFrame(
                [
                    {"ts_code": "801730.SI", "trade_date": "20260410", "pct_chg": 5.6},
                ]
            ),
            "801120.SI": pd.DataFrame(
                [
                    {"ts_code": "801120.SI", "trade_date": "20260410", "pct_chg": 1.2},
                ]
            ),
        }
        self.history = {
            "600001": pd.DataFrame(
                [
                    {"date": "2026-04-01", "open": 8.8, "high": 9.1, "low": 8.7, "close": 9.0, "volume": 1, "amount": 2e8, "pct_chg": 1.2},
                    {"date": "2026-04-02", "open": 9.0, "high": 9.3, "low": 8.9, "close": 9.2, "volume": 1, "amount": 2.1e8, "pct_chg": 2.1},
                    {"date": "2026-04-03", "open": 9.2, "high": 9.6, "low": 9.1, "close": 9.5, "volume": 1, "amount": 2.3e8, "pct_chg": 3.2},
                    {"date": "2026-04-07", "open": 9.6, "high": 10.0, "low": 9.5, "close": 9.9, "volume": 1, "amount": 2.5e8, "pct_chg": 4.1},
                    {"date": "2026-04-08", "open": 9.95, "high": 10.3, "low": 9.9, "close": 10.2, "volume": 1, "amount": 2.8e8, "pct_chg": 3.0},
                    {"date": "2026-04-09", "open": 10.25, "high": 10.6, "low": 10.1, "close": 10.5, "volume": 1, "amount": 3.1e8, "pct_chg": 2.9},
                    {"date": "2026-04-10", "open": 10.0, "high": 11.1, "low": 9.95, "close": 11.0, "volume": 1, "amount": 8e8, "pct_chg": 9.8},
                ]
            ),
            "600002": pd.DataFrame(
                [
                    {"date": "2026-04-01", "open": 7.5, "high": 7.7, "low": 7.4, "close": 7.6, "volume": 1, "amount": 1.8e8, "pct_chg": 0.8},
                    {"date": "2026-04-02", "open": 7.6, "high": 7.8, "low": 7.5, "close": 7.7, "volume": 1, "amount": 1.9e8, "pct_chg": 1.1},
                    {"date": "2026-04-03", "open": 7.7, "high": 7.9, "low": 7.6, "close": 7.8, "volume": 1, "amount": 2.0e8, "pct_chg": 1.3},
                    {"date": "2026-04-07", "open": 7.8, "high": 8.1, "low": 7.7, "close": 8.0, "volume": 1, "amount": 2.2e8, "pct_chg": 2.6},
                    {"date": "2026-04-08", "open": 8.0, "high": 8.2, "low": 7.9, "close": 8.1, "volume": 1, "amount": 2.1e8, "pct_chg": 1.2},
                    {"date": "2026-04-09", "open": 8.1, "high": 8.4, "low": 8.0, "close": 8.2, "volume": 1, "amount": 2.3e8, "pct_chg": 1.4},
                    {"date": "2026-04-10", "open": 8.0, "high": 8.8, "low": 7.9, "close": 8.65, "volume": 1, "amount": 5e8, "pct_chg": 8.1},
                ]
            ),
        }

    def is_available(self) -> bool:
        return True

    def get_trade_time(self, early_time: str = "00:00", late_time: str = "17:00") -> str:
        china_date = self.current_time.strftime("%Y%m%d")
        china_clock = self.current_time.strftime("%H:%M")
        if china_date in self.trade_dates:
            use_today = not (early_time < china_clock < late_time)
        else:
            use_today = False
        if use_today or len(self.trade_dates) == 1:
            return self.trade_dates[0]
        return self.trade_dates[1]

    def _get_china_now(self) -> datetime:
        return self.current_time

    def _call_api_with_rate_limit(self, method_name: str, **kwargs):
        self.api_calls[method_name] = self.api_calls.get(method_name, 0) + 1
        trade_date = kwargs.get("trade_date")
        if method_name in {"daily", "daily_basic", "moneyflow", "stk_limit", "top_list"} and trade_date:
            trade_snapshot = self.trade_snapshots.get(str(trade_date))
            if trade_snapshot is None:
                return pd.DataFrame()
            return trade_snapshot.get(method_name, pd.DataFrame()).copy()
        if method_name == "index_member":
            return self.index_member_by_code.get(kwargs.get("index_code"), pd.DataFrame())
        if method_name == "index_daily":
            return self.index_daily_by_code.get(kwargs.get("ts_code"), pd.DataFrame())
        return self.snapshot.get(method_name, pd.DataFrame())

    def build_trade_snapshot(self, trade_date: str, *, ready: bool) -> dict[str, pd.DataFrame]:
        base = self.trade_snapshots["20260410"]
        snapshot = {
            name: table.copy()
            for name, table in base.items()
        }
        for table in snapshot.values():
            if "trade_date" in table.columns:
                table["trade_date"] = trade_date
        if not ready:
            for name in ("daily", "daily_basic", "moneyflow", "top_list"):
                snapshot[name] = snapshot[name].iloc[0:0].copy()
        return snapshot

    def get_daily_data(self, stock_code: str, start_date=None, end_date=None, days: int = 80):
        normalized = str(stock_code).split(".")[0]
        self.history_calls[normalized] = self.history_calls.get(normalized, 0) + 1
        return self.history.get(stock_code, self.history.get(normalized, pd.DataFrame()))


class MomentumScreenerServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Config.reset_instance()
        os.environ.pop("MOMENTUM_SECTOR_CACHE_TTL_SECONDS", None)
        MomentumScreenerService.reset_sector_cache()
        self.cache_root_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        os.environ.pop("MOMENTUM_SECTOR_CACHE_TTL_SECONDS", None)
        self.cache_root_dir.cleanup()
        Config.reset_instance()

    def _build_service(self, fetcher: _FakeFetcher | None = None) -> MomentumScreenerService:
        cache_root = Path(self.cache_root_dir.name)
        return MomentumScreenerService(
            fetcher=fetcher or _FakeFetcher(),
            history_cache_dir=cache_root / "histories",
            trade_snapshot_cache_dir=cache_root / "snapshots",
            candidate_pool_cache_dir=cache_root / "candidate_pools",
            screening_result_cache_dir=cache_root / "screening_results",
        )

    def test_screen_returns_ranked_results(self) -> None:
        service = self._build_service()

        result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["profile"], "standard")
        self.assertEqual(result["trade_date"], "2026-04-10")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["ts_code"], "600001.SH")
        self.assertEqual(result["results"][0]["themes"][0], "电力设备")
        self.assertIn("continuation_score", result["results"][0])
        self.assertIn("score_breakdown", result["results"][0])
        self.assertIsNotNone(result["results"][0]["entry_range_low"])
        self.assertIsNotNone(result["results"][0]["entry_range_high"])
        self.assertIsNotNone(result["results"][1]["entry_range_low"])
        self.assertIsNotNone(result["results"][1]["entry_range_high"])
        self.assertGreater(result["results"][0]["rank_score"], result["results"][1]["rank_score"])
        self.assertEqual(result["results"][0]["entry_range_low"], 10.89)
        self.assertEqual(result["results"][0]["entry_range_high"], 11.11)
        self.assertEqual(result["results"][1]["entry_range_low"], 8.56)
        self.assertEqual(result["results"][1]["entry_range_high"], 8.74)

        leader_width = result["results"][0]["entry_range_high"] - result["results"][0]["entry_range_low"]
        front_width = result["results"][1]["entry_range_high"] - result["results"][1]["entry_range_low"]
        self.assertLessEqual(round(leader_width, 4), round(11.0 * 0.02 + 0.01, 4))
        self.assertLessEqual(round(front_width, 4), round(8.65 * 0.03 + 0.01, 4))

    def test_standard_score_breakdown_uses_v13_weight_structure(self) -> None:
        service = self._build_service()

        result = service.screen(top_n=2, profile="standard")
        breakdown = result["results"][0]["score_breakdown"]

        self.assertEqual(breakdown["volume_price_structure"]["max_score"], 18)
        self.assertEqual(breakdown["trend_position"]["max_score"], 12)
        self.assertEqual(breakdown["sector_resonance"]["max_score"], 25)
        self.assertEqual(breakdown["capital_support"]["max_score"], 17)
        self.assertEqual(breakdown["elasticity_activity"]["max_score"], 8)
        self.assertLessEqual(result["results"][0]["risk_score"], 100.0)

    def test_standard_v13_profile_can_promote_real_theme_leader(self) -> None:
        service = self._build_service()
        v13_profiles = {
            "600001.SH": {
                "theme_name": "弱势题材",
                "theme_fund_strength_score": 38.0,
                "candidate_count": 1,
                "top10_count": 1,
                "board_rank": 42,
                "board_up_num": 12,
                "board_down_num": 20,
                "leader_stock": "别的股票",
                "stock_theme_rank": 6,
                "limit_events": [
                    {
                        "limit": "Z",
                        "open_times": 3,
                    }
                ],
            },
            "600002.SH": {
                "theme_name": "电池",
                "theme_fund_strength_score": 93.0,
                "candidate_count": 5,
                "top10_count": 3,
                "board_rank": 2,
                "board_up_num": 45,
                "board_down_num": 8,
                "leader_stock": "测试跟风",
                "stock_theme_rank": 1,
                "limit_events": [
                    {
                        "limit": "U",
                        "open_times": 0,
                    }
                ],
            },
        }

        with patch.object(service, "_build_standard_v13_profile_map", return_value=v13_profiles):
            result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["results"][0]["ts_code"], "600002.SH")
        self.assertEqual(
            result["results"][0]["score_breakdown"]["sector_resonance"]["items"]["v13_theme_name"],
            "电池",
        )

    def test_standard_v13_profile_context_limits_expensive_enrichment_to_front12(self) -> None:
        service = self._build_service()
        for method_name in (
            "get_stock_limit_prices",
            "get_limit_list",
            "get_dc_concepts",
            "get_dc_members",
            "get_dc_moneyflow_themes",
            "get_kpl_list",
        ):
            setattr(service.fetcher, method_name, lambda *args, **kwargs: {})

        captured: dict[str, list[str]] = {}

        class _FakeV13Service:
            def build_screening_context(self, *, trade_date: str, ts_codes: list[str]) -> dict[str, object]:
                captured["ts_codes"] = list(ts_codes)
                return {
                    "stock_theme_map": {},
                    "theme_strength": {},
                    "theme_members": {},
                    "limit_events": {},
                    "stock_moneyflow": {},
                    "chip_snapshots": {},
                    "kpl_items": [],
                    "is_degraded": False,
                    "degraded_reasons": [],
                }

            def build_mainline_radar(self, *, candidates, context, limit):  # type: ignore[no-untyped-def]
                return []

        service._v13_data_service = _FakeV13Service()  # type: ignore[assignment]

        provisional_results = [
            {
                "ts_code": f"600{i:03d}.SH",
                "name": f"测试{i:03d}",
                "rank_score": float(200 - i),
                "final_score": float(200 - i),
            }
            for i in range(45)
        ]

        result = service._build_standard_v13_profile_map(
            trade_date="2026-04-10",
            provisional_results=provisional_results,
        )

        self.assertEqual(result, {})
        self.assertEqual(len(captured["ts_codes"]), 12)
        self.assertEqual(captured["ts_codes"][0], "600000.SH")
        self.assertEqual(captured["ts_codes"][-1], "600011.SH")

    def test_screen_prefers_current_trade_date_after_close_when_eod_snapshot_ready(self) -> None:
        fetcher = _FakeFetcher(current_time=datetime(2026, 4, 11, 15, 10, 0))
        fetcher.trade_snapshots["20260411"] = fetcher.build_trade_snapshot("20260411", ready=True)
        fetcher.trade_dates = sorted(fetcher.trade_snapshots.keys(), reverse=True)
        service = self._build_service(fetcher)

        result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["trade_date"], "2026-04-11")
        self.assertIsNone(result["trade_date_note"])
        self.assertIsNone(result["requested_trade_date"])

    def test_screen_falls_back_to_previous_trade_date_when_today_snapshot_not_ready(self) -> None:
        fetcher = _FakeFetcher(current_time=datetime(2026, 4, 11, 15, 10, 0))
        fetcher.trade_snapshots["20260411"] = fetcher.build_trade_snapshot("20260411", ready=False)
        fetcher.trade_dates = sorted(fetcher.trade_snapshots.keys(), reverse=True)
        service = self._build_service(fetcher)

        result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["trade_date"], "2026-04-10")
        self.assertIn("2026-04-11", result["trade_date_note"])
        self.assertIn("2026-04-10", result["trade_date_note"])
        self.assertIsNone(result["requested_trade_date"])

    def test_screen_explicit_today_trade_date_falls_back_with_note_when_eod_not_ready(self) -> None:
        fetcher = _FakeFetcher(current_time=datetime(2026, 4, 11, 15, 10, 0))
        fetcher.trade_snapshots["20260411"] = fetcher.build_trade_snapshot("20260411", ready=False)
        fetcher.trade_dates = sorted(fetcher.trade_snapshots.keys(), reverse=True)
        service = self._build_service(fetcher)

        result = service.screen(top_n=2, profile="standard", trade_date="2026-04-11")

        self.assertEqual(result["trade_date"], "2026-04-10")
        self.assertEqual(result["requested_trade_date"], "2026-04-11")
        self.assertIn("你选择了 2026-04-11", result["trade_date_note"])
        self.assertIn("2026-04-10", result["trade_date_note"])

    def test_screen_keeps_full_ranked_results_for_downstream_decision(self) -> None:
        service = self._build_service()

        result = service.screen(top_n=1, profile="standard")

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(len(result["ranked_results"]), 2)
        self.assertEqual(result["ranked_results"][0]["ts_code"], "600001.SH")
        self.assertEqual(result["ranked_results"][1]["ts_code"], "600002.SH")

    def test_screen_supports_aggressive_profile(self) -> None:
        service = self._build_service()

        result = service.screen(top_n=2, profile="aggressive")

        self.assertEqual(result["profile"], "aggressive")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(len(result["results"]), 2)
        self.assertIsNotNone(result["results"][0]["buyability_score"])
        self.assertIsNotNone(result["results"][0]["opportunity_tag"])
        self.assertIsNotNone(result["results"][0]["entry_range_low"])
        self.assertIsNotNone(result["results"][0]["entry_range_high"])
        self.assertIn("buyability", result["results"][0]["score_breakdown"])
        self.assertIn("volume_price_track", result["results"][0]["score_breakdown"])

    def test_aggressive_score_breakdown_uses_v13_weight_structure(self) -> None:
        service = self._build_service()

        result = service.screen(top_n=2, profile="aggressive")
        breakdown = result["results"][0]["score_breakdown"]

        self.assertEqual(breakdown["buyability"]["max_score"], 18)
        self.assertEqual(breakdown["volume_price_track"]["max_score"], 14)
        self.assertEqual(breakdown["sector_resonance"]["max_score"], 10)
        self.assertLessEqual(result["results"][0]["risk_score"], 100.0)

    def test_aggressive_v13_profile_can_promote_better_participation_target(self) -> None:
        service = self._build_service()
        v13_profiles = {
            "600001.SH": {
                "theme_name": "弱势题材",
                "theme_fund_strength_score": 40.0,
                "candidate_count": 1,
                "stock_theme_rank": 5,
                "kpl_status": "一字板",
                "kpl_turnover_rate": 1.2,
                "limit_events": [
                    {
                        "limit": "Z",
                        "open_times": 3,
                        "limit_times": 1,
                    }
                ],
            },
            "600002.SH": {
                "theme_name": "电池",
                "theme_fund_strength_score": 90.0,
                "candidate_count": 4,
                "stock_theme_rank": 1,
                "kpl_status": "换手回封",
                "kpl_turnover_rate": 8.5,
                "limit_events": [
                    {
                        "limit": "U",
                        "open_times": 1,
                        "limit_times": 2,
                    }
                ],
            },
        }

        with patch.object(service, "_build_standard_v13_profile_map", return_value=v13_profiles):
            result = service.screen(top_n=2, profile="aggressive")

        self.assertEqual(result["results"][0]["ts_code"], "600002.SH")
        self.assertEqual(
            result["results"][0]["score_breakdown"]["buyability"]["items"]["v13_is_one_word_like"],
            False,
        )

    def test_standard_v13_chip_risk_penalty_raises_risk_score_for_overheated_candidate(self) -> None:
        service = self._build_service()
        baseline = service.screen(top_n=2, profile="standard")
        baseline_by_code = {item["ts_code"]: item for item in baseline["ranked_results"]}

        v13_profiles = {
            "600001.SH": {
                "theme_name": "鐢垫睜",
                "theme_fund_strength_score": 86.0,
                "candidate_count": 5,
                "stock_theme_rank": 1,
                "limit_events": [{"limit": "U", "open_times": 0}],
                "chip_sources": ["tushare.cyq_perf", "tushare.cyq_chips"],
                "chip_winner_rate": 0.95,
                "chip_cost_50pct": 9.4,
                "chip_cost_85pct": 9.1,
                "chip_concentration_90": 0.25,
            },
            "600002.SH": {
                "theme_name": "鐢垫睜",
                "theme_fund_strength_score": 82.0,
                "candidate_count": 5,
                "stock_theme_rank": 2,
                "limit_events": [{"limit": "U", "open_times": 1}],
                "chip_sources": ["tushare.cyq_perf", "tushare.cyq_chips"],
                "chip_winner_rate": 0.58,
                "chip_cost_50pct": 8.55,
                "chip_cost_85pct": 8.7,
                "chip_concentration_90": 0.08,
            },
        }

        with patch.object(service, "_build_standard_v13_profile_map", return_value=v13_profiles):
            stressed = service.screen(top_n=2, profile="standard")

        stressed_by_code = {item["ts_code"]: item for item in stressed["ranked_results"]}
        self.assertGreater(stressed_by_code["600001.SH"]["risk_score"], baseline_by_code["600001.SH"]["risk_score"])
        self.assertIn("chip_overheat", stressed_by_code["600001.SH"]["risk_tags"])
        self.assertIn("chip_high_profit", stressed_by_code["600001.SH"]["risk_tags"])

    def test_aggressive_v13_chip_signal_changes_buyability_and_ranking(self) -> None:
        service = self._build_service()
        v13_profiles = {
            "600001.SH": {
                "theme_name": "寮卞娍棰樻潗",
                "theme_fund_strength_score": 42.0,
                "candidate_count": 1,
                "stock_theme_rank": 5,
                "kpl_status": "涓€瀛楁澘",
                "kpl_turnover_rate": 1.2,
                "limit_events": [{"limit": "Z", "open_times": 3, "limit_times": 1}],
                "chip_sources": ["tushare.cyq_perf", "tushare.cyq_chips"],
                "chip_winner_rate": 0.95,
                "chip_cost_50pct": 9.4,
                "chip_cost_85pct": 9.1,
                "chip_concentration_90": 0.25,
            },
            "600002.SH": {
                "theme_name": "鐢垫睜",
                "theme_fund_strength_score": 90.0,
                "candidate_count": 4,
                "stock_theme_rank": 1,
                "kpl_status": "鎹㈡墜鍥炲皝",
                "kpl_turnover_rate": 8.5,
                "limit_events": [{"limit": "U", "open_times": 1, "limit_times": 2}],
                "chip_sources": ["tushare.cyq_perf", "tushare.cyq_chips"],
                "chip_winner_rate": 0.58,
                "chip_cost_50pct": 8.55,
                "chip_cost_85pct": 8.7,
                "chip_concentration_90": 0.08,
                "stock_fund_sources": ["tushare.moneyflow_dc", "tushare.moneyflow_ths"],
                "stock_fund_net_amount": 65000000.0,
                "stock_fund_net_amount_rate": 5.1,
                "stock_fund_net_d5_amount": 128000000.0,
                "stock_fund_buy_lg_amount": 42000000.0,
                "stock_fund_buy_lg_amount_rate": 2.4,
            },
        }

        with patch.object(service, "_build_standard_v13_profile_map", return_value=v13_profiles):
            result = service.screen(top_n=2, profile="aggressive")

        by_code = {item["ts_code"]: item for item in result["ranked_results"]}
        self.assertEqual(result["results"][0]["ts_code"], "600002.SH")
        self.assertEqual(by_code["600002.SH"]["score_breakdown"]["buyability"]["items"]["v13_chip_pressure"], 3)
        self.assertEqual(
            by_code["600002.SH"]["score_breakdown"]["capital_support"]["items"]["v13_stock_flow_source_count"],
            2,
        )
        self.assertIn("chip_overheat", by_code["600001.SH"]["risk_tags"])

    def test_sector_context_cache_is_shared_across_service_instances(self) -> None:
        fetcher = _FakeFetcher()

        first_service = self._build_service(fetcher)
        first_service.screen(top_n=2, profile="standard")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 1)
        self.assertEqual(fetcher.api_calls.get("index_member"), 1)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 1)
        self.assertEqual(MomentumScreenerService.get_sector_cache_stats()["miss"], 1)

        second_service = self._build_service(fetcher)
        second_service.screen(top_n=2, profile="aggressive")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 1)
        self.assertEqual(fetcher.api_calls.get("index_member"), 1)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 1)
        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["miss"], 1)
        self.assertEqual(stats["hit"], 1)

    def test_sector_context_cache_expires_and_reloads(self) -> None:
        fetcher = _FakeFetcher()

        with patch.object(MomentumScreenerService, "_cache_now_ts", return_value=1000.0):
            service = self._build_service(fetcher)
            service.screen(top_n=2, profile="standard")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 1)
        self.assertEqual(fetcher.api_calls.get("index_member"), 1)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 1)

        ttl = MomentumScreenerService.get_sector_cache_stats()["ttl_seconds"]
        with patch.object(MomentumScreenerService, "_cache_now_ts", return_value=1000.0 + ttl + 1):
            reloaded_service = self._build_service(fetcher)
            reloaded_service.screen(top_n=2, profile="aggressive")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 2)
        self.assertEqual(fetcher.api_calls.get("index_member"), 2)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 2)
        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["miss"], 2)
        self.assertEqual(stats["expired"], 1)

    def test_sector_context_cache_hits_when_unmapped_codes_are_known(self) -> None:
        fetcher = _FakeFetcher()
        service = self._build_service(fetcher)
        expires_at = MomentumScreenerService._cache_now_ts() + 600
        service._sector_context_cache["20260410"] = {
            "payload": {
                "mapping": {"600001.SH": "鐢靛姏璁惧"},
                "sector_pct_map": {"鐢靛姏璁惧": 5.6},
                "unmapped_codes": ["999999.SH"],
            },
            "expires_at": expires_at,
        }

        result = service._load_sector_context(
            trade_date="20260410",
            ts_codes=["600001.SH", "999999.SH"],
        )

        self.assertEqual(fetcher.api_calls.get("index_classify"), None)
        self.assertIn("999999.SH", result["unmapped_codes"])
        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["hit"], 1)
        self.assertEqual(stats["miss"], 0)

    def test_sector_cache_ttl_reads_runtime_config(self) -> None:
        os.environ["MOMENTUM_SECTOR_CACHE_TTL_SECONDS"] = "900"
        Config.reset_instance()

        service = self._build_service()
        service.screen(top_n=2, profile="standard")

        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["ttl_seconds"], 900)

    def test_screen_falls_back_when_sector_context_load_fails(self) -> None:
        service = self._build_service()

        with patch.object(service, "_load_sector_context", side_effect=RuntimeError("sector timeout")):
            result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["results"][0]["ts_code"], "600001.SH")
        self.assertEqual(result["results"][0]["themes"][0], "旧行业A")


    def test_history_cache_reuses_disk_snapshot_across_service_instances(self) -> None:
        fetcher = _FakeFetcher()

        first_service = self._build_service(fetcher)
        first_service.screen(top_n=2, profile="standard")

        self.assertEqual(fetcher.history_calls.get("600001"), 1)
        self.assertEqual(fetcher.history_calls.get("600002"), 1)

        MomentumScreenerService._shared_history_cache.clear()

        second_service = self._build_service(fetcher)
        second_service.screen(top_n=2, profile="aggressive")

        self.assertEqual(fetcher.history_calls.get("600001"), 1)
        self.assertEqual(fetcher.history_calls.get("600002"), 1)

    def test_trade_snapshot_cache_reuses_disk_snapshot_across_service_instances(self) -> None:
        fetcher = _FakeFetcher()

        first_service = self._build_service(fetcher)
        first_service._load_trade_snapshot("20260410")

        self.assertEqual(fetcher.api_calls.get("stock_basic"), 1)
        self.assertEqual(fetcher.api_calls.get("daily"), 1)
        self.assertEqual(fetcher.api_calls.get("daily_basic"), 1)
        self.assertEqual(fetcher.api_calls.get("moneyflow"), 1)
        self.assertEqual(fetcher.api_calls.get("stk_limit"), 1)
        self.assertEqual(fetcher.api_calls.get("top_list"), 1)

        MomentumScreenerService._shared_trade_snapshot_cache.clear()

        second_service = self._build_service(fetcher)
        second_snapshot = second_service._load_trade_snapshot("20260410")

        self.assertFalse(second_snapshot["daily"].empty)
        self.assertEqual(fetcher.api_calls.get("stock_basic"), 1)
        self.assertEqual(fetcher.api_calls.get("daily"), 1)
        self.assertEqual(fetcher.api_calls.get("daily_basic"), 1)
        self.assertEqual(fetcher.api_calls.get("moneyflow"), 1)
        self.assertEqual(fetcher.api_calls.get("stk_limit"), 1)
        self.assertEqual(fetcher.api_calls.get("top_list"), 1)

    def test_incomplete_trade_snapshot_is_not_cached(self) -> None:
        fetcher = _FakeFetcher(current_time=datetime(2026, 4, 11, 15, 10, 0))
        fetcher.trade_snapshots["20260411"] = fetcher.build_trade_snapshot("20260411", ready=False)
        fetcher.trade_dates = sorted(fetcher.trade_snapshots.keys(), reverse=True)
        service = self._build_service(fetcher)

        first_snapshot = service._load_trade_snapshot("20260411")
        self.assertTrue(first_snapshot["daily"].empty)

        fetcher.trade_snapshots["20260411"] = fetcher.build_trade_snapshot("20260411", ready=True)
        second_snapshot = service._load_trade_snapshot("20260411")

        self.assertFalse(second_snapshot["daily"].empty)
        self.assertEqual(fetcher.api_calls.get("daily"), 2)
        self.assertEqual(fetcher.api_calls.get("daily_basic"), 2)

    def test_candidate_pool_cache_reuses_filtered_pool_across_profiles_and_topn(self) -> None:
        fetcher = _FakeFetcher()
        service = self._build_service(fetcher)

        first = service.screen(top_n=2, profile="standard")
        self.assertEqual(first["candidate_count"], 2)

        with patch.object(service, "_build_candidates", side_effect=AssertionError("candidate pool should come from cache")):
            second = service.screen(top_n=1, profile="aggressive")

        self.assertEqual(second["candidate_count"], 2)
        self.assertEqual(len(second["ranked_results"]), 2)

    def test_candidate_pool_cache_reuses_disk_filtered_pool_across_service_instances(self) -> None:
        fetcher = _FakeFetcher()

        first_service = self._build_service(fetcher)
        first_service.screen(top_n=2, profile="standard")

        MomentumScreenerService._shared_candidate_pool_cache.clear()

        second_service = self._build_service(fetcher)
        with patch.object(
            second_service,
            "_build_candidates",
            side_effect=AssertionError("candidate pool should be loaded from disk cache"),
        ):
            second = second_service.screen(top_n=1, profile="aggressive")

        self.assertEqual(second["candidate_count"], 2)
        self.assertEqual(len(second["ranked_results"]), 2)

    def test_screening_result_cache_shortcuts_historical_replay_before_snapshot_load(self) -> None:
        fetcher = _FakeFetcher(current_time=datetime(2026, 4, 11, 18, 0, 0))

        first_service = self._build_service(fetcher)
        first = first_service.screen(top_n=2, profile="standard", trade_date="2026-04-10")

        self.assertEqual(first["candidate_count"], 2)
        self.assertEqual(fetcher.api_calls.get("daily"), 1)
        self.assertEqual(fetcher.history_calls.get("600001"), 1)

        MomentumScreenerService._shared_sector_context_cache.clear()
        MomentumScreenerService._shared_trade_snapshot_cache.clear()
        MomentumScreenerService._shared_candidate_pool_cache.clear()
        MomentumScreenerService._shared_history_cache.clear()

        second_service = self._build_service(fetcher)
        with patch.object(
            second_service,
            "_load_trade_snapshot",
            side_effect=AssertionError("historical screening should come from ranked-result cache"),
        ):
            second = second_service.screen(top_n=1, profile="standard", trade_date="2026-04-10")

        self.assertEqual(second["candidate_count"], 2)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(len(second["ranked_results"]), 2)
        self.assertEqual(second["results"][0]["ts_code"], first["results"][0]["ts_code"])
        self.assertEqual(fetcher.api_calls.get("daily"), 1)
        self.assertEqual(fetcher.history_calls.get("600001"), 1)


if __name__ == "__main__":
    unittest.main()
