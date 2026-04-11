# -*- coding: utf-8 -*-
"""Tests for MomentumScreenerService."""

from __future__ import annotations

import os
import sys
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
    def __init__(self) -> None:
        self.api_calls: dict[str, int] = {}
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
        return "20260410"

    def _call_api_with_rate_limit(self, method_name: str, **kwargs):
        self.api_calls[method_name] = self.api_calls.get(method_name, 0) + 1
        if method_name == "index_member":
            return self.index_member_by_code.get(kwargs.get("index_code"), pd.DataFrame())
        if method_name == "index_daily":
            return self.index_daily_by_code.get(kwargs.get("ts_code"), pd.DataFrame())
        return self.snapshot.get(method_name, pd.DataFrame())

    def get_daily_data(self, stock_code: str, start_date=None, end_date=None, days: int = 80):
        normalized = str(stock_code).split(".")[0]
        return self.history.get(stock_code, self.history.get(normalized, pd.DataFrame()))


class MomentumScreenerServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Config.reset_instance()
        os.environ.pop("MOMENTUM_SECTOR_CACHE_TTL_SECONDS", None)
        MomentumScreenerService.reset_sector_cache()

    def tearDown(self) -> None:
        os.environ.pop("MOMENTUM_SECTOR_CACHE_TTL_SECONDS", None)
        Config.reset_instance()

    def test_screen_returns_ranked_results(self) -> None:
        service = MomentumScreenerService(fetcher=_FakeFetcher())

        result = service.screen(top_n=2, profile="standard")

        self.assertEqual(result["profile"], "standard")
        self.assertEqual(result["trade_date"], "2026-04-10")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["ts_code"], "600001.SH")
        self.assertEqual(result["results"][0]["themes"][0], "电力设备")
        self.assertIn("continuation_score", result["results"][0])
        self.assertIn("score_breakdown", result["results"][0])
        self.assertGreater(result["results"][0]["rank_score"], result["results"][1]["rank_score"])

    def test_screen_supports_aggressive_profile(self) -> None:
        service = MomentumScreenerService(fetcher=_FakeFetcher())

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

    def test_sector_context_cache_is_shared_across_service_instances(self) -> None:
        fetcher = _FakeFetcher()

        first_service = MomentumScreenerService(fetcher=fetcher)
        first_service.screen(top_n=2, profile="standard")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 1)
        self.assertEqual(fetcher.api_calls.get("index_member"), 1)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 1)
        self.assertEqual(MomentumScreenerService.get_sector_cache_stats()["miss"], 1)

        second_service = MomentumScreenerService(fetcher=fetcher)
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
            service = MomentumScreenerService(fetcher=fetcher)
            service.screen(top_n=2, profile="standard")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 1)
        self.assertEqual(fetcher.api_calls.get("index_member"), 1)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 1)

        ttl = MomentumScreenerService.get_sector_cache_stats()["ttl_seconds"]
        with patch.object(MomentumScreenerService, "_cache_now_ts", return_value=1000.0 + ttl + 1):
            reloaded_service = MomentumScreenerService(fetcher=fetcher)
            reloaded_service.screen(top_n=2, profile="aggressive")

        self.assertEqual(fetcher.api_calls.get("index_classify"), 2)
        self.assertEqual(fetcher.api_calls.get("index_member"), 2)
        self.assertEqual(fetcher.api_calls.get("index_daily"), 2)
        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["miss"], 2)
        self.assertEqual(stats["expired"], 1)

    def test_sector_cache_ttl_reads_runtime_config(self) -> None:
        os.environ["MOMENTUM_SECTOR_CACHE_TTL_SECONDS"] = "900"
        Config.reset_instance()

        service = MomentumScreenerService(fetcher=_FakeFetcher())
        service.screen(top_n=2, profile="standard")

        stats = MomentumScreenerService.get_sector_cache_stats()
        self.assertEqual(stats["ttl_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
