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

    def test_get_ths_index_translates_concept_code(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.ths_index.return_value = pd.DataFrame(
            {
                "ts_code": ["886089.TI"],
                "name": ["回购增持再贷款概念"],
                "count": [477],
                "exchange": ["A"],
                "list_date": ["20241021"],
                "type": ["N"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_ths_index(ts_code="886089.TI")

        fetcher._api.ths_index.assert_called_once_with(
            fields="ts_code,name,count,exchange,list_date,type",
            ts_code="886089.TI",
        )
        row = payload["rows"][0]
        self.assertEqual(row["theme_code"], "886089.TI")
        self.assertEqual(row["theme_name"], "回购增持再贷款概念")
        self.assertEqual(row["member_count"], 477)
        self.assertEqual(row["list_date"], "2024-10-21")

    def test_get_belong_board_uses_ths_member_and_index_name(self) -> None:
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
        fetcher._api.ths_index.return_value = pd.DataFrame(
            {
                "ts_code": ["885800.TI"],
                "name": ["动力电池"],
                "count": [80],
                "exchange": ["A"],
                "list_date": ["20200101"],
                "type": ["概念"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            boards = fetcher.get_belong_board("300750")

        self.assertEqual(boards[0]["name"], "动力电池")
        self.assertEqual(boards[0]["code"], "885800.TI")
        self.assertEqual(boards[0]["source"], "tushare.ths_member")

    def test_get_belong_board_prioritizes_industry_over_generic_indexes(self) -> None:
        fetcher = self._make_fetcher()
        member_payload = {
            "rows": [
                {"theme_code": "881001.TI", "in_date": "2020-01-01"},
                {"theme_code": "881002.TI", "in_date": "2020-01-01"},
                {"theme_code": "885001.TI", "in_date": "2020-01-01"},
            ]
        }
        index_rows = {
            "881001.TI": {
                "theme_name": "\u540c\u82b1\u987a\u5168A(\u52a0\u6743)",
                "type": "S",
            },
            "881002.TI": {
                "theme_name": "\u540c\u82b1\u987a\u6caa\u6df1\u5168A",
                "type": "BB",
            },
            "885001.TI": {
                "theme_name": "\u5316\u5b66\u5236\u54c1(A\u80a1)",
                "type": "I",
            },
        }

        def lookup_index(**kwargs):
            return {"rows": [index_rows[kwargs["ts_code"]]]}

        with (
            patch.object(fetcher, "get_ths_members", return_value=member_payload),
            patch.object(fetcher, "get_ths_index", side_effect=lookup_index),
        ):
            boards = fetcher.get_belong_board("002407")

        self.assertEqual(boards[0]["name"], "\u5316\u5b66\u5236\u54c1(A\u80a1)")
        self.assertEqual(boards[0]["code"], "885001.TI")
        self.assertEqual(boards[-1]["name"], "\u540c\u82b1\u987a\u6caa\u6df1\u5168A")

    def test_get_daily_basic_metrics_normalizes_latest_row(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.daily_basic.return_value = pd.DataFrame(
            {
                "ts_code": ["600519.SH", "600519.SH"],
                "trade_date": ["20260422", "20260424"],
                "close": [1500.0, 1600.0],
                "turnover_rate": [0.7, 0.8],
                "turnover_rate_f": [1.2, 1.3],
                "volume_ratio": [0.9, 1.1],
                "pe": [20.0, 21.0],
                "pe_ttm": [22.0, 23.0],
                "pb": [8.0, 8.5],
                "ps": [10.0, 10.5],
                "ps_ttm": [9.0, 9.5],
                "dv_ratio": [1.1, 1.2],
                "dv_ttm": [1.3, 1.4],
                "total_share": [1000.0, 1000.0],
                "float_share": [900.0, 900.0],
                "free_share": [800.0, 800.0],
                "total_mv": [15000000.0, 16000000.0],
                "circ_mv": [12000000.0, 13000000.0],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_daily_basic_metrics("600519", trade_date="2026-04-24")

        args = fetcher._api.daily_basic.call_args.kwargs
        self.assertEqual(args["ts_code"], "600519.SH")
        self.assertEqual(args["end_date"], "20260424")
        row = payload["rows"][0]
        self.assertEqual(row["trade_date"], "2026-04-24")
        self.assertEqual(row["pe_ratio"], 21.0)
        self.assertEqual(row["pb_ratio"], 8.5)
        self.assertEqual(row["dividend_yield_pct"], 1.4)
        self.assertEqual(row["total_mv_wan"], 16000000.0)

    def test_get_daily_basic_metrics_marks_stale_when_latest_row_lags_requested(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.daily_basic.return_value = pd.DataFrame(
            {
                "ts_code": ["600519.SH"],
                "trade_date": ["20260422"],
                "close": [1500.0],
                "turnover_rate": [0.7],
                "turnover_rate_f": [1.2],
                "volume_ratio": [0.9],
                "pe": [20.0],
                "pe_ttm": [22.0],
                "pb": [8.0],
                "ps": [10.0],
                "ps_ttm": [9.0],
                "dv_ratio": [1.1],
                "dv_ttm": [1.3],
                "total_share": [1000.0],
                "float_share": [900.0],
                "free_share": [800.0],
                "total_mv": [15000000.0],
                "circ_mv": [12000000.0],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_daily_basic_metrics("600519", trade_date="2026-04-24")

        self.assertEqual(payload["status"], "stale")
        self.assertTrue(payload["is_degraded"])
        self.assertEqual(payload["trade_date"], "2026-04-22")
        self.assertIn("stale_result:2026-04-22<expected:2026-04-24", payload["degraded_reasons"])

    def test_v13_api_error_classifies_permission_denied(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.daily_basic.side_effect = Exception("permission denied: need 6000 points")

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_daily_basic_metrics("600519", trade_date="2026-04-24")

        self.assertEqual(payload["status"], "permission_denied")
        self.assertTrue(payload["is_degraded"])
        self.assertIn("permission denied", payload["degraded_reasons"][0])

    def test_get_tushare_fundamental_bundle_maps_homepage_blocks(self) -> None:
        fetcher = self._make_fetcher()
        with patch.object(fetcher, "get_daily_basic_metrics", return_value={
            "source": "tushare.daily_basic",
            "status": "ok",
            "rows": [{
                "trade_date": "2026-04-24",
                "close": 50.0,
                "pe_ratio": 12.0,
                "pe_ttm": 13.0,
                "pb_ratio": 2.1,
                "dividend_yield_pct": 3.0,
                "turnover_rate": 1.2,
            }],
            "degraded_reasons": [],
        }), patch.object(fetcher, "get_financial_indicator_summary", return_value={
            "source": "tushare.fina_indicator",
            "status": "ok",
            "rows": [{
                "ann_date": "2026-04-20",
                "report_period": "2026-03-31",
                "roe": 18.0,
                "gross_margin": 55.0,
                "revenue_yoy": 12.0,
                "net_profit_yoy": 10.0,
                "eps": 2.0,
            }],
            "degraded_reasons": [],
        }), patch.object(fetcher, "get_dividend_summary", return_value={
            "source": "tushare.dividend",
            "status": "ok",
            "rows": [],
            "summary": {"ttm_event_count": 1, "ttm_cash_dividend_per_share": 2.5, "events": []},
            "degraded_reasons": [],
        }), patch.object(fetcher, "get_performance_event_summary", return_value={
            "source": "tushare.performance_events",
            "status": "ok",
            "rows": [],
            "forecast_events": [{"summary": "预增", "ann_date": "2026-04-01"}],
            "express_events": [{"revenue": 100.0, "net_profit_parent": 20.0}],
            "degraded_reasons": [],
        }):
            bundle = fetcher.get_tushare_fundamental_bundle("600519", latest_price=50.0)

        self.assertEqual(bundle["status"], "partial")
        self.assertEqual(bundle["valuation"]["pe_ratio"], 12.0)
        self.assertEqual(bundle["profitability"]["roe"], 18.0)
        self.assertEqual(bundle["growth"]["revenue_yoy"], 12.0)
        self.assertAlmostEqual(bundle["earnings"]["dividend"]["ttm_dividend_yield_pct"], 5.0)
        self.assertEqual(bundle["earnings"]["forecast_summary"], "预增")

    def test_get_tushare_fundamental_bundle_preserves_permission_denied_status(self) -> None:
        fetcher = self._make_fetcher()
        permission_payload = {
            "source": "tushare.mock",
            "status": "permission_denied",
            "rows": [],
            "degraded_reasons": ["permission denied"],
        }
        with patch.object(fetcher, "get_daily_basic_metrics", return_value={**permission_payload, "source": "tushare.daily_basic"}), \
                patch.object(fetcher, "get_financial_indicator_summary", return_value={**permission_payload, "source": "tushare.fina_indicator"}), \
                patch.object(fetcher, "get_dividend_summary", return_value={**permission_payload, "source": "tushare.dividend"}), \
                patch.object(fetcher, "get_performance_event_summary", return_value={**permission_payload, "source": "tushare.performance_events"}):
            bundle = fetcher.get_tushare_fundamental_bundle("600519", latest_price=50.0)

        self.assertEqual(bundle["status"], "permission_denied")
        self.assertEqual(bundle["source_chain"][0]["result"], "permission_denied")
        self.assertTrue(any(error.endswith("permission denied") for error in bundle["errors"]))

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

    def test_get_dc_index_normalizes_board_strength(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.dc_index.return_value = pd.DataFrame(
            {
                "ts_code": ["BK0574.DC"],
                "trade_date": ["20260424"],
                "name": ["锂电池概念"],
                "leading": ["多氟多"],
                "leading_code": ["002407.SZ"],
                "pct_change": [5.2],
                "leading_pct": [10.0],
                "total_mv": [12345678.0],
                "turnover_rate": [3.6],
                "up_num": [58],
                "down_num": [8],
                "idx_type": ["概念板块"],
                "level": [None],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_dc_concepts("2026-04-24")

        fetcher._api.dc_index.assert_called_once()
        args = fetcher._api.dc_index.call_args.kwargs
        self.assertEqual(args["trade_date"], "20260424")
        self.assertEqual(args["idx_type"], "概念板块")
        row = payload["rows"][0]
        self.assertEqual(row["theme_code"], "BK0574.DC")
        self.assertEqual(row["theme_name"], "锂电池概念")
        self.assertEqual(row["leading"], "多氟多")
        self.assertEqual(row["up_num"], 58)

    def test_get_dc_members_normalizes_stock_board_map(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.dc_member.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424"],
                "ts_code": ["BK0574.DC"],
                "con_code": ["002407.SZ"],
                "name": ["多氟多"],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_dc_members("20260424", con_code="002407")

        fetcher._api.dc_member.assert_called_once_with(
            trade_date="20260424",
            fields="trade_date,ts_code,con_code,name",
            con_code="002407.SZ",
        )
        row = payload["rows"][0]
        self.assertEqual(row["theme_code"], "BK0574.DC")
        self.assertEqual(row["con_code"], "002407.SZ")
        self.assertEqual(row["con_name"], "多氟多")

    def test_get_dc_moneyflow_themes_normalizes_net_amount(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.moneyflow_ind_dc.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424"],
                "content_type": ["概念"],
                "ts_code": ["BK0574.DC"],
                "name": ["锂电池概念"],
                "pct_change": [5.2],
                "close": [1234.0],
                "net_amount": [10898035456.0],
                "net_amount_rate": [3.2],
                "buy_elg_amount": [5000000000.0],
                "buy_elg_amount_rate": [1.5],
                "buy_lg_amount": [3000000000.0],
                "buy_lg_amount_rate": [1.1],
                "buy_md_amount": [1000000000.0],
                "buy_md_amount_rate": [0.3],
                "buy_sm_amount": [-500000000.0],
                "buy_sm_amount_rate": [-0.2],
                "buy_sm_amount_stock": ["多氟多"],
                "rank": [1],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_dc_moneyflow_themes("20260424", content_type="概念")

        fetcher._api.moneyflow_ind_dc.assert_called_once()
        args = fetcher._api.moneyflow_ind_dc.call_args.kwargs
        self.assertEqual(args["content_type"], "概念")
        row = payload["rows"][0]
        self.assertEqual(row["theme_name"], "锂电池概念")
        self.assertEqual(row["net_amount"], 10898035456.0)
        self.assertEqual(row["rank"], 1)

    def test_get_stock_moneyflow_ths_converts_wan_amounts_into_yuan(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.moneyflow_ths.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424"],
                "ts_code": ["002407.SZ"],
                "name": ["test-name"],
                "pct_change": [9.9],
                "latest": [16.82],
                "net_amount": [12345.6],
                "net_d5_amount": [34567.8],
                "buy_lg_amount": [9876.5],
                "buy_lg_amount_rate": [2.6],
                "buy_md_amount": [2345.6],
                "buy_md_amount_rate": [0.7],
                "buy_sm_amount": [-1234.5],
                "buy_sm_amount_rate": [-0.3],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_stock_moneyflow_ths("20260424", ts_code="002407")

        fetcher._api.moneyflow_ths.assert_called_once()
        args = fetcher._api.moneyflow_ths.call_args.kwargs
        self.assertEqual(args["trade_date"], "20260424")
        self.assertEqual(args["ts_code"], "002407.SZ")
        row = payload["rows"][0]
        self.assertEqual(row["net_amount"], 123456000.0)
        self.assertEqual(row["net_d5_amount"], 345678000.0)
        self.assertEqual(row["buy_lg_amount"], 98765000.0)

    def test_get_stock_moneyflow_dc_converts_wan_amounts_into_yuan(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.moneyflow_dc.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424"],
                "ts_code": ["002407.SZ"],
                "name": ["test-name"],
                "pct_change": [9.9],
                "close": [16.82],
                "net_amount": [23456.7],
                "net_amount_rate": [3.2],
                "buy_elg_amount": [6789.1],
                "buy_elg_amount_rate": [1.1],
                "buy_lg_amount": [5678.9],
                "buy_lg_amount_rate": [0.9],
                "buy_md_amount": [3456.7],
                "buy_md_amount_rate": [0.5],
                "buy_sm_amount": [-1111.1],
                "buy_sm_amount_rate": [-0.2],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_stock_moneyflow_dc("20260424", ts_code="002407")

        fetcher._api.moneyflow_dc.assert_called_once()
        args = fetcher._api.moneyflow_dc.call_args.kwargs
        self.assertEqual(args["trade_date"], "20260424")
        self.assertEqual(args["ts_code"], "002407.SZ")
        row = payload["rows"][0]
        self.assertEqual(row["net_amount"], 234567000.0)
        self.assertEqual(row["buy_elg_amount"], 67891000.0)
        self.assertEqual(row["buy_lg_amount"], 56789000.0)

    def test_get_cyq_perf_normalizes_winner_rate(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.cyq_perf.return_value = pd.DataFrame(
            {
                "ts_code": ["002407.SZ"],
                "trade_date": ["20260424"],
                "his_low": [9.5],
                "his_high": [17.2],
                "cost_5pct": [10.1],
                "cost_15pct": [11.4],
                "cost_50pct": [13.8],
                "cost_85pct": [15.9],
                "cost_95pct": [16.6],
                "weight_avg": [13.9],
                "winner_rate": [87.5],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_cyq_perf("20260424", ts_code="002407")

        fetcher._api.cyq_perf.assert_called_once()
        row = payload["rows"][0]
        self.assertAlmostEqual(row["winner_rate"], 0.875)
        self.assertEqual(row["cost_85pct"], 15.9)

    def test_get_cyq_chips_builds_snapshot_from_distribution(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.cyq_chips.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424", "20260424", "20260424", "20260424"],
                "ts_code": ["002407.SZ", "002407.SZ", "002407.SZ", "002407.SZ"],
                "price": [10.0, 11.0, 12.0, 13.0],
                "percent": [10.0, 20.0, 30.0, 40.0],
            }
        )
        fetcher._api.daily.return_value = pd.DataFrame(
            {
                "trade_date": ["20260424"],
                "ts_code": ["002407.SZ"],
                "close": [12.0],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_cyq_chips("20260424", ts_code="002407")

        self.assertEqual(fetcher._api.cyq_chips.call_count, 1)
        self.assertEqual(fetcher._api.daily.call_count, 1)
        row = payload["rows"][0]
        self.assertAlmostEqual(row["profit_ratio"], 0.6)
        self.assertAlmostEqual(row["avg_cost"], 12.0)
        self.assertEqual(row["cost_90_low"], 10.0)
        self.assertEqual(row["cost_90_high"], 13.0)
        self.assertAlmostEqual(row["concentration_90"], 0.1304, places=4)
        self.assertEqual(row["distribution_points"], 4)

    def test_get_kpl_list_normalizes_theme_reason(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.kpl_list.return_value = pd.DataFrame(
            {
                "ts_code": ["002407.SZ"],
                "name": ["多氟多"],
                "trade_date": ["20260424"],
                "lu_time": ["093101"],
                "ld_time": [None],
                "open_time": [None],
                "last_time": ["145501"],
                "lu_desc": ["锂电池"],
                "tag": ["涨停"],
                "theme": ["锂电池"],
                "net_change": [100000000.0],
                "bid_amount": [30000000.0],
                "status": ["首板"],
                "bid_change": [5000000.0],
                "bid_turnover": [1.2],
                "lu_bid_vol": [80000000.0],
                "pct_chg": [10.0],
                "bid_pct_chg": [5.0],
                "rt_pct_chg": [10.0],
                "limit_order": [90000000.0],
                "amount": [1200000000.0],
                "turnover_rate": [18.0],
                "free_float": [80.0],
                "lu_limit_order": [100000000.0],
            }
        )

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_kpl_list("20260424", tag="涨停")

        fetcher._api.kpl_list.assert_called_once()
        row = payload["rows"][0]
        self.assertEqual(row["theme"], "锂电池")
        self.assertEqual(row["lu_desc"], "锂电池")
        self.assertEqual(row["limit_order"], 90000000.0)

    def test_empty_result_returns_partial_payload(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.stk_limit.return_value = pd.DataFrame()

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_stock_limit_prices("20260423")

        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["is_degraded"])
        self.assertEqual(payload["degraded_reasons"], ["empty_result"])
        self.assertEqual(payload["rows"], [])

    def test_api_permission_error_returns_permission_denied_payload(self) -> None:
        fetcher = self._make_fetcher()
        fetcher._api.limit_list_d.side_effect = Exception("permission denied")

        with patch.object(fetcher, "_check_rate_limit"), patch.object(fetcher, "_get_china_now", self._fixed_now):
            payload = fetcher.get_limit_list("20260423")

        self.assertEqual(payload["status"], "permission_denied")
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
