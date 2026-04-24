# -*- coding: utf-8 -*-
"""Unit tests for TushareFetcher V1.3 momentum screener data adapters."""

import importlib.util
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

try:
    json_repair_available = importlib.util.find_spec("json_repair") is not None
except ValueError:
    json_repair_available = "json_repair" in sys.modules

if not json_repair_available and "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

if "fake_useragent" not in sys.modules:
    sys.modules["fake_useragent"] = MagicMock()

from data_provider.tushare_fetcher import TushareFetcher


class TestTushareFetcherV13Adapters(unittest.TestCase):
    @staticmethod
    def _make_fetcher() -> TushareFetcher:
        with patch.object(TushareFetcher, "_init_api", return_value=None):
            fetcher = TushareFetcher()
        fetcher._api = MagicMock()
        fetcher.priority = 2
        return fetcher

    @staticmethod
    def _fixed_now() -> datetime:
        return datetime(2026, 4, 24, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    def test_get_stock_limit_prices_normalizes_rows(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.stk_limit.return_value = pd.DataFrame(
            {
                "trade_date": ["20260423"],
                "ts_code": ["600519.SH"],
                "pre_close": [1600.0],
                "up_limit": [1760.0],
                "down_limit": [1440.0],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_stock_limit_prices("2026/04/23", ts_code="600519")

        fetcher._api.stk_limit.assert_called_once_with(
            trade_date="20260423",
            fields="trade_date,ts_code,pre_close,up_limit,down_limit",
            ts_code="600519.SH",
        )
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["is_degraded"])
        self.assertEqual(payload["trade_date"], "2026-04-23")
        self.assertEqual(payload["rows"][0]["trade_date"], "2026-04-23")
        self.assertEqual(payload["rows"][0]["up_limit"], 1760.0)
        self.assertEqual(payload["rows"][0]["data_source"], "tushare.stk_limit")

    def test_get_limit_list_normalizes_limit_events(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.limit_list_d.return_value = pd.DataFrame(
            {
                "trade_date": ["20260423"],
                "ts_code": ["002240.SZ"],
                "industry": ["有色金属"],
                "name": ["盛新锂能"],
                "close": [47.36],
                "pct_chg": [10.0],
                "amount": [123456.0],
                "limit_amount": [None],
                "float_mv": [3000000.0],
                "total_mv": [3500000.0],
                "turnover_ratio": [18.5],
                "fd_amount": [80000.0],
                "first_time": ["093102"],
                "last_time": ["143011"],
                "open_times": [2],
                "up_stat": ["3/5"],
                "limit_times": [2],
                "limit": ["U"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_limit_list("20260423", limit_type="u")

        args = fetcher._api.limit_list_d.call_args.kwargs
        self.assertEqual(args["trade_date"], "20260423")
        self.assertEqual(args["limit_type"], "U")
        self.assertIn("open_times", args["fields"])
        self.assertEqual(payload["rows"][0]["open_times"], 2)
        self.assertEqual(payload["rows"][0]["limit"], "U")
        self.assertIsNone(payload["rows"][0]["limit_amount"])

    def test_get_ths_members_supports_stock_code_lookup(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.ths_member.return_value = pd.DataFrame(
            {
                "ts_code": ["885800.TI"],
                "con_code": ["300750.SZ"],
                "con_name": ["宁德时代"],
                "weight": [None],
                "in_date": ["20200101"],
                "out_date": [None],
                "is_new": ["Y"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_ths_members(con_code="300750")

        fetcher._api.ths_member.assert_called_once_with(
            fields="ts_code,con_code,con_name,weight,in_date,out_date,is_new",
            con_code="300750.SZ",
        )
        self.assertEqual(payload["rows"][0]["theme_code"], "885800.TI")
        self.assertEqual(payload["rows"][0]["con_code"], "300750.SZ")
        self.assertEqual(payload["rows"][0]["in_date"], "2020-01-01")

    def test_get_ths_hot_parses_concept_list(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.ths_hot.return_value = pd.DataFrame(
            {
                "trade_date": ["20260423"],
                "data_type": ["热股"],
                "ts_code": ["300750.SZ"],
                "ts_name": ["宁德时代"],
                "rank": [1],
                "pct_change": [5.2],
                "current_price": [222.5],
                "concept": ['["钠离子电池", "同花顺漂亮100"]'],
                "rank_reason": ["热度上升"],
                "hot": [214462.0],
                "rank_time": ["15:30:00"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_ths_hot("2026-04-23", market="热股", is_new="Y")

        fetcher._api.ths_hot.assert_called_once()
        row = payload["rows"][0]
        self.assertEqual(row["concepts"], ["钠离子电池", "同花顺漂亮100"])
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["hot"], 214462.0)

    def test_empty_result_returns_partial_payload(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.stk_limit.return_value = pd.DataFrame()

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_stock_limit_prices("20260423")

        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["is_degraded"])
        self.assertEqual(payload["degraded_reasons"], ["empty_result"])
        self.assertEqual(payload["rows"], [])

    def test_api_error_returns_unavailable_payload(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.limit_list_d.side_effect = Exception("permission denied")

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_limit_list("20260423")

        self.assertEqual(payload["status"], "unavailable")
        self.assertTrue(payload["is_degraded"])
        self.assertIn("permission denied", payload["degraded_reasons"][0])

    def test_unconfigured_api_returns_unavailable_payload(self) -> None:
        with patch.object(TushareFetcher, "_init_api", return_value=None):
            fetcher = TushareFetcher()

        with patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_ths_members(theme_code="885800.TI")

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["degraded_reasons"], ["api_not_initialized"])
        self.assertEqual(payload["rows"], [])


if __name__ == "__main__":
    unittest.main()
