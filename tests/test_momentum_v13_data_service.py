# -*- coding: utf-8 -*-
"""Tests for MomentumV13DataService."""

from __future__ import annotations

from dataclasses import dataclass
import unittest
from unittest.mock import MagicMock

from src.services.momentum_v13_data_service import MomentumV13DataService


@dataclass
class _Quote:
    code: str
    price: float
    source: str = "mock"

    def to_dict(self):
        return {"code": self.code, "price": self.price, "source": self.source}


class TestMomentumV13DataService(unittest.TestCase):
    def setUp(self) -> None:
        MomentumV13DataService.reset_cache()

    @staticmethod
    def _payload(source: str, rows, *, status: str = "ok", degraded_reasons=None):
        reasons = degraded_reasons or []
        return {
            "source": source,
            "status": status,
            "trade_date": "2026-04-23",
            "data_as_of": "2026-04-23T15:30:00+08:00",
            "is_degraded": status != "ok" or bool(reasons),
            "degraded_reasons": reasons,
            "rows": rows,
        }

    def _make_fetcher(self):
        fetcher = MagicMock()
        fetcher.get_stock_limit_prices.return_value = self._payload(
            "tushare.stk_limit",
            [
                {"ts_code": "600519.SH", "up_limit": 1760.0, "down_limit": 1440.0},
                {"ts_code": "300750.SZ", "up_limit": 244.0, "down_limit": 200.0},
            ],
        )
        fetcher.get_limit_list.return_value = self._payload(
            "tushare.limit_list_d",
            [{"ts_code": "600519.SH", "limit": "U", "open_times": 1}],
        )
        fetcher.get_ths_members.side_effect = lambda con_code: self._payload(
            "tushare.ths_member",
            [
                {"theme_code": "885800.TI", "con_code": con_code, "con_name": f"name-{con_code}"},
                {"theme_code": "886000.TI", "con_code": con_code, "con_name": f"name-{con_code}"},
            ],
        )
        fetcher.get_ths_hot.return_value = self._payload(
            "tushare.ths_hot",
            [{"ts_code": "600519.SH", "rank": 1, "concepts": ["白酒"]}],
        )
        fetcher.get_realtime_quote.return_value = _Quote(code="600519.SH", price=1688.0)
        return fetcher

    def test_build_context_aggregates_sources_and_theme_map(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        context = service.build_context(trade_date="2026/04/23", ts_codes=["600519", "300750.SZ", "600519.SH"])

        self.assertEqual(context["trade_date"], "2026-04-23")
        self.assertFalse(context["is_degraded"])
        self.assertEqual(context["source_status"]["stk_limit"], "ok")
        self.assertIn("600519.SH", context["limit_prices"])
        self.assertIn("600519.SH", context["limit_events"])
        self.assertEqual(len(context["stock_theme_map"]["600519.SH"]), 2)
        self.assertEqual(context["theme_members"]["885800.TI"], ["600519.SH", "300750.SZ"])
        self.assertEqual(context["hot_items"][0]["rank"], 1)

        fetcher.get_stock_limit_prices.assert_called_once_with("2026/04/23")
        fetcher.get_limit_list.assert_called_once_with("2026/04/23")
        fetcher.get_ths_hot.assert_called_once_with("2026/04/23")
        self.assertEqual(fetcher.get_ths_members.call_count, 2)

    def test_build_context_uses_cache_for_repeated_request(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        first = service.build_context(trade_date="20260423", ts_codes=["600519"])
        second = service.build_context(trade_date="20260423", ts_codes=["600519"])

        self.assertIs(first, second)
        fetcher.get_stock_limit_prices.assert_called_once()
        fetcher.get_limit_list.assert_called_once()
        fetcher.get_ths_hot.assert_called_once()
        fetcher.get_ths_members.assert_called_once()
        self.assertGreaterEqual(MomentumV13DataService.get_cache_stats()["hit"], 1)

    def test_degraded_source_is_visible_in_context(self) -> None:
        fetcher = self._make_fetcher()
        fetcher.get_limit_list.return_value = self._payload(
            "tushare.limit_list_d",
            [],
            status="unavailable",
            degraded_reasons=["permission_denied"],
        )
        service = MomentumV13DataService(fetcher=fetcher)

        context = service.build_context(trade_date="20260423", ts_codes=["600519"])

        self.assertTrue(context["is_degraded"])
        self.assertEqual(context["source_status"]["limit_list_d"], "unavailable")
        self.assertIn("limit_list_d:permission_denied", context["degraded_reasons"])

    def test_build_replay_context_marks_realtime_quote_excluded(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        context = service.build_replay_context(trade_date="20260423", ts_codes=["600519"])

        self.assertTrue(context["is_replay_context"])
        self.assertTrue(any("realtime_quote" in note for note in context["replay_notes"]))
        fetcher.get_realtime_quote.assert_not_called()

    def test_get_intraday_snapshot_uses_short_ttl_quote_cache(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        first = service.get_intraday_snapshot(trade_date="20260423", ts_codes=["600519"])
        second = service.get_intraday_snapshot(trade_date="20260423", ts_codes=["600519"])

        self.assertEqual(first["label"], "盘中快照辅助")
        self.assertEqual(first["confidence"], "low")
        self.assertFalse(first["is_degraded"])
        self.assertEqual(first["rows"][0]["price"], 1688.0)
        self.assertEqual(second["rows"][0]["price"], 1688.0)
        fetcher.get_realtime_quote.assert_called_once_with("600519.SH")

    def test_get_intraday_snapshot_handles_missing_quote(self) -> None:
        fetcher = self._make_fetcher()
        fetcher.get_realtime_quote.return_value = None
        service = MomentumV13DataService(fetcher=fetcher)

        snapshot = service.get_intraday_snapshot(trade_date="20260423", ts_codes=["600519"])

        self.assertTrue(snapshot["is_degraded"])
        self.assertEqual(snapshot["source_status"]["600519.SH"], "unavailable")
        self.assertIn("600519.SH:empty_result", snapshot["degraded_reasons"])
        self.assertEqual(snapshot["rows"], [])

    def test_build_mainline_radar_scores_theme_density_and_limit_strength(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)
        context = {
            "is_degraded": False,
            "degraded_reasons": [],
            "stock_theme_map": {
                "600519.SH": [{"theme_code": "theme_a", "theme_name": "白酒"}],
                "000001.SZ": [{"theme_code": "theme_a", "theme_name": "白酒"}],
                "300750.SZ": [{"theme_code": "theme_b", "theme_name": "电池"}],
            },
            "theme_members": {
                "theme_a": ["600519.SH", "000001.SZ"],
                "theme_b": ["300750.SZ"],
            },
            "limit_events": {
                "600519.SH": [{"limit": "U", "limit_times": 2, "fd_amount": 200000.0, "open_times": 0}],
                "000001.SZ": [{"limit": "U", "limit_times": 1, "fd_amount": 100000.0, "open_times": 0}],
                "300750.SZ": [{"limit": "Z", "limit_times": 0, "open_times": 2}],
            },
            "hot_items": [{"ts_code": "600519.SH", "rank": 1}],
        }
        candidates = [
            {"rank": 1, "ts_code": "600519.SH", "name": "贵州茅台", "rank_score": 88, "leader_level": "leader"},
            {"rank": 4, "ts_code": "000001.SZ", "name": "平安银行", "rank_score": 72, "leader_level": "front"},
            {"rank": 2, "ts_code": "300750.SZ", "name": "宁德时代", "rank_score": 82, "leader_level": "leader"},
        ]

        radar = service.build_mainline_radar(candidates=candidates, context=context, previous_feedback={"success_rate": 70})

        self.assertEqual(radar[0]["theme_id"], "theme_a")
        self.assertEqual(radar[0]["theme_name"], "白酒")
        self.assertEqual(radar[0]["candidate_count"], 2)
        self.assertEqual(radar[0]["limit_up_count"], 2)
        self.assertEqual(radar[0]["hot_rank"], 1)
        self.assertEqual(radar[0]["representatives"][0]["ts_code"], "600519.SH")
        self.assertTrue(any(item["key"] == "density" for item in radar[0]["evidence"]))

    def test_build_mainline_radar_falls_back_to_candidate_themes(self) -> None:
        service = MomentumV13DataService(fetcher=self._make_fetcher())
        radar = service.build_mainline_radar(
            candidates=[
                {"rank": 1, "ts_code": "600519.SH", "name": "贵州茅台", "rank_score": 88, "themes": ["白酒"]},
            ],
            context={"stock_theme_map": {}, "theme_members": {}, "limit_events": {}, "hot_items": []},
        )

        self.assertEqual(radar[0]["theme_id"], "白酒")
        self.assertEqual(radar[0]["theme_name"], "白酒")
        self.assertEqual(radar[0]["candidate_count"], 1)

    def test_build_mainline_radar_propagates_context_degradation(self) -> None:
        service = MomentumV13DataService(fetcher=self._make_fetcher())
        radar = service.build_mainline_radar(
            candidates=[
                {"rank": 1, "ts_code": "600519.SH", "name": "贵州茅台", "rank_score": 88, "themes": ["白酒"]},
            ],
            context={
                "is_degraded": True,
                "degraded_reasons": ["ths_member:permission_denied"],
                "stock_theme_map": {},
                "theme_members": {},
                "limit_events": {},
                "hot_items": [],
            },
        )

        self.assertTrue(radar[0]["is_degraded"])
        self.assertIn("ths_member:permission_denied", radar[0]["degraded_reasons"])

    def test_build_short_term_sentiment_classifies_hot_market(self) -> None:
        service = MomentumV13DataService(fetcher=self._make_fetcher())
        mainline_radar = [
            {
                "theme_id": "theme_a",
                "theme_name": "白酒",
                "score": 88,
                "representatives": [{"ts_code": "600519.SH"}],
            }
        ]
        context = {
            "is_degraded": False,
            "degraded_reasons": [],
            "limit_events": {
                "600519.SH": [{"limit": "U", "limit_times": 3, "open_times": 0}],
                "000001.SZ": [{"limit": "U", "limit_times": 1, "open_times": 0}],
                "300750.SZ": [{"limit": "U", "limit_times": 1, "open_times": 0}],
            },
            "hot_items": [{"ts_code": "600519.SH", "rank": 1}],
        }

        sentiment = service.build_short_term_sentiment(
            mainline_radar=mainline_radar,
            context=context,
            previous_feedback={"success_rate": 75, "avg_profit_window_pct": 3},
        )

        self.assertIn(sentiment["level"], {"hot", "tradable"})
        self.assertIn(sentiment["label"], {"高涨", "可做"})
        self.assertEqual(sentiment["confidence"], "high")
        self.assertTrue(any(item["key"] == "limit_strength" for item in sentiment["modules"]))

    def test_build_short_term_sentiment_classifies_ebb_market(self) -> None:
        service = MomentumV13DataService(fetcher=self._make_fetcher())
        context = {
            "is_degraded": False,
            "degraded_reasons": [],
            "limit_events": {
                "600519.SH": [{"limit": "Z", "limit_times": 0, "open_times": 5}],
                "000001.SZ": [{"limit": "Z", "limit_times": 0, "open_times": 4}],
            },
            "hot_items": [],
        }

        sentiment = service.build_short_term_sentiment(
            mainline_radar=[],
            context=context,
            previous_feedback={"success_rate": 20, "avg_profit_window_pct": 0},
        )

        self.assertEqual(sentiment["level"], "ebb")
        self.assertEqual(sentiment["label"], "退潮")
        self.assertIn("拖累", sentiment["summary"])

    def test_build_short_term_sentiment_marks_low_confidence_when_degraded(self) -> None:
        service = MomentumV13DataService(fetcher=self._make_fetcher())
        sentiment = service.build_short_term_sentiment(
            mainline_radar=[],
            context={
                "is_degraded": True,
                "degraded_reasons": ["limit_list_d:permission_denied"],
                "limit_events": {},
                "hot_items": [],
            },
        )

        self.assertEqual(sentiment["confidence"], "low")
        self.assertTrue(sentiment["is_degraded"])
        self.assertIn("limit_list_d:permission_denied", sentiment["degraded_reasons"])


if __name__ == "__main__":
    unittest.main()
