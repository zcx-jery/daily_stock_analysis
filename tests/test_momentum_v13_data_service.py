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

        def _ths_members_payload(con_code=None, limit=None, offset=None):
            rows = [
                {"theme_code": "885800.TI", "con_code": "600519.SH", "con_name": "name-600519.SH"},
                {"theme_code": "886000.TI", "con_code": "600519.SH", "con_name": "name-600519.SH"},
                {"theme_code": "885800.TI", "con_code": "300750.SZ", "con_name": "name-300750.SZ"},
                {"theme_code": "886000.TI", "con_code": "300750.SZ", "con_name": "name-300750.SZ"},
            ]
            if con_code:
                rows = [row for row in rows if row["con_code"] == con_code]
            return self._payload("tushare.ths_member", rows)

        def _ths_index_payload(ts_code=None, limit=None, offset=None):
            rows = [
                {"theme_code": "885800.TI", "theme_name": "白酒"},
                {"theme_code": "886000.TI", "theme_name": "机器人"},
            ]
            if ts_code:
                rows = [row for row in rows if row["theme_code"] == ts_code]
            return self._payload("tushare.ths_index", rows)

        def _dc_members_payload(trade_date, con_code=None, limit=None, offset=None):
            rows = [
                {
                    "theme_code": "BK0574.DC",
                    "con_code": "300750.SZ",
                    "con_name": "name-300750.SZ",
                }
            ]
            if con_code:
                rows = [row for row in rows if row["con_code"] == con_code]
            return self._payload("tushare.dc_member", rows)

        def _cyq_perf_payload(trade_date, ts_code=None, limit=None, offset=None):
            rows = [
                {
                    "ts_code": "600519.SH",
                    "winner_rate": 0.91,
                    "weight_avg": 1650.0,
                    "cost_5pct": 1520.0,
                    "cost_15pct": 1580.0,
                    "cost_50pct": 1638.0,
                    "cost_85pct": 1672.0,
                    "cost_95pct": 1704.0,
                    "data_source": "tushare.cyq_perf",
                },
                {
                    "ts_code": "300750.SZ",
                    "winner_rate": 0.58,
                    "weight_avg": 218.3,
                    "cost_5pct": 201.2,
                    "cost_15pct": 206.5,
                    "cost_50pct": 216.8,
                    "cost_85pct": 223.9,
                    "cost_95pct": 228.4,
                    "data_source": "tushare.cyq_perf",
                },
            ]
            if ts_code:
                rows = [row for row in rows if row["ts_code"] == ts_code]
            return self._payload("tushare.cyq_perf", rows)

        fetcher.get_ths_members = MagicMock(side_effect=_ths_members_payload)
        fetcher.get_ths_index = MagicMock(side_effect=_ths_index_payload)
        fetcher.get_ths_hot.return_value = self._payload(
            "tushare.ths_hot",
            [{"ts_code": "600519.SH", "rank": 1, "concepts": ["白酒"]}],
        )
        fetcher.get_dc_concepts.return_value = self._payload(
            "tushare.dc_index",
            [
                {
                    "theme_code": "BK0574.DC",
                    "theme_name": "锂电池概念",
                    "pct_change": 5.2,
                    "up_num": 58,
                    "down_num": 8,
                    "leading": "多氟多",
                }
            ],
        )
        fetcher.get_dc_moneyflow_themes.side_effect = lambda trade_date, content_type=None: self._payload(
            "tushare.moneyflow_ind_dc",
            [
                {
                    "theme_code": "BK0574.DC" if content_type == "概念" else "电池",
                    "theme_name": "锂电池概念" if content_type == "概念" else "电池",
                    "content_type": content_type,
                    "rank": 1,
                    "net_amount": 10898035456.0,
                    "net_amount_rate": 3.2,
                    "pct_change": 5.2,
                }
            ],
        )
        fetcher.get_dc_members = MagicMock(side_effect=_dc_members_payload)
        fetcher.get_kpl_list.return_value = self._payload(
            "tushare.kpl_list",
            [{"ts_code": "300750.SZ", "name": "宁德时代", "theme": "锂电池", "lu_desc": "电池产业链"}],
        )
        fetcher.get_stock_moneyflow_dc = MagicMock(
            return_value=self._payload(
                "tushare.moneyflow_dc",
                [
                    {
                        "ts_code": "600519.SH",
                        "close": 1688.0,
                        "net_amount": 88000000.0,
                        "net_amount_rate": 5.2,
                        "buy_elg_amount": 32000000.0,
                        "buy_elg_amount_rate": 1.8,
                        "buy_lg_amount": 54000000.0,
                        "buy_lg_amount_rate": 3.1,
                        "data_source": "tushare.moneyflow_dc",
                    },
                    {
                        "ts_code": "300750.SZ",
                        "close": 222.5,
                        "net_amount": 56000000.0,
                        "net_amount_rate": 3.8,
                        "buy_elg_amount": 18000000.0,
                        "buy_elg_amount_rate": 1.0,
                        "buy_lg_amount": 26000000.0,
                        "buy_lg_amount_rate": 1.7,
                        "data_source": "tushare.moneyflow_dc",
                    },
                ],
            )
        )
        fetcher.get_stock_moneyflow_ths = MagicMock(
            return_value=self._payload(
                "tushare.moneyflow_ths",
                [
                    {
                        "ts_code": "600519.SH",
                        "close": 1688.0,
                        "net_amount": 76000000.0,
                        "net_d5_amount": 210000000.0,
                        "buy_lg_amount": 50000000.0,
                        "buy_lg_amount_rate": 2.9,
                        "buy_md_amount": 12000000.0,
                        "buy_md_amount_rate": 0.8,
                        "buy_sm_amount": -6000000.0,
                        "buy_sm_amount_rate": -0.4,
                        "data_source": "tushare.moneyflow_ths",
                    },
                    {
                        "ts_code": "300750.SZ",
                        "close": 222.5,
                        "net_amount": 43000000.0,
                        "net_d5_amount": 88000000.0,
                        "buy_lg_amount": 22000000.0,
                        "buy_lg_amount_rate": 1.4,
                        "buy_md_amount": 8000000.0,
                        "buy_md_amount_rate": 0.5,
                        "buy_sm_amount": -5000000.0,
                        "buy_sm_amount_rate": -0.3,
                        "data_source": "tushare.moneyflow_ths",
                    },
                ],
            )
        )
        fetcher.get_cyq_perf = MagicMock(side_effect=_cyq_perf_payload)
        fetcher.get_cyq_chips = MagicMock(
            side_effect=lambda trade_date, ts_code: self._payload(
                "tushare.cyq_chips",
                [
                    {
                        "ts_code": ts_code,
                        "profit_ratio": 0.89 if ts_code == "600519.SH" else 0.61,
                        "avg_cost": 1648.0 if ts_code == "600519.SH" else 217.6,
                        "cost_90_low": 1515.0 if ts_code == "600519.SH" else 202.1,
                        "cost_90_high": 1698.0 if ts_code == "600519.SH" else 226.5,
                        "concentration_90": 0.057,
                        "cost_70_low": 1578.0 if ts_code == "600519.SH" else 207.4,
                        "cost_70_high": 1674.0 if ts_code == "600519.SH" else 222.8,
                        "concentration_70": 0.03 if ts_code == "600519.SH" else 0.036,
                        "distribution_points": 24,
                        "data_source": "tushare.cyq_chips",
                    }
                ],
            )
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
        self.assertEqual(context["source_status"]["dc_concept"], "ok")
        self.assertEqual(context["source_status"]["moneyflow_ind_dc"], "ok")
        self.assertIn("600519.SH", context["limit_prices"])
        self.assertIn("600519.SH", context["limit_events"])
        self.assertEqual(len(context["stock_raw_theme_map"]["600519.SH"]), 2)
        self.assertGreater(len(context["stock_capital_theme_map"]["600519.SH"]), 0)
        self.assertEqual(len(context["stock_theme_map"]["600519.SH"]), 3)
        self.assertEqual(context["stock_dc_theme_map"]["300750.SZ"][0]["theme_name"], "锂电池概念")
        self.assertEqual(context["theme_strength"]["capital_theme:battery"]["theme_name"], "电池")
        self.assertGreater(context["theme_strength"]["capital_theme:battery"]["net_amount"], 0)
        self.assertEqual(context["theme_members"]["885800.TI"], ["600519.SH", "300750.SZ"])
        self.assertEqual(context["theme_name_map"]["885800.TI"], "白酒")
        self.assertEqual(context["source_status"]["ths_index"], "ok")
        self.assertEqual(context["hot_items"][0]["rank"], 1)
        self.assertEqual(
            sorted(context["stock_moneyflow"]["600519.SH"]["sources"]),
            ["tushare.moneyflow_dc", "tushare.moneyflow_ths"],
        )
        self.assertGreater(context["stock_moneyflow"]["600519.SH"]["net_d5_amount"], 0)
        self.assertAlmostEqual(context["chip_snapshots"]["600519.SH"]["winner_rate"], 0.91)
        self.assertEqual(context["chip_snapshots"]["600519.SH"]["distribution_points"], 24)

        fetcher.get_stock_limit_prices.assert_called_once_with("2026/04/23")
        fetcher.get_limit_list.assert_called_once_with("2026/04/23")
        fetcher.get_ths_hot.assert_called_once_with("2026/04/23")
        fetcher.get_dc_concepts.assert_called_once_with("2026/04/23")
        fetcher.get_stock_moneyflow_dc.assert_called_once_with("2026/04/23")
        fetcher.get_stock_moneyflow_ths.assert_called_once_with("2026/04/23")
        self.assertEqual(fetcher.get_dc_moneyflow_themes.call_count, 2)
        self.assertEqual(fetcher.get_dc_members.call_count, 1)
        fetcher.get_kpl_list.assert_called_once_with("2026/04/23", tag="涨停")
        self.assertEqual(fetcher.get_ths_members.call_count, 1)
        self.assertEqual(fetcher.get_ths_index.call_count, 1)
        self.assertEqual(fetcher.get_cyq_perf.call_count, 1)
        self.assertEqual(fetcher.get_cyq_chips.call_count, 2)

    def test_build_screening_context_skips_chip_and_ths_member_queries(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        context = service.build_screening_context(trade_date="2026/04/23", ts_codes=["600519.SH", "300750.SZ"])

        self.assertFalse(context["is_degraded"])
        self.assertEqual(context["source_status"]["cyq_perf"], "skipped")
        self.assertEqual(context["source_status"]["cyq_chips"], "skipped")
        self.assertEqual(context["source_status"]["ths_member"], "skipped")
        self.assertEqual(context["source_status"]["ths_index"], "skipped")
        self.assertEqual(context["chip_snapshots"], {})
        self.assertEqual(len(context["stock_raw_theme_map"]["600519.SH"]), 0)
        self.assertGreater(len(context["stock_dc_theme_map"]["300750.SZ"]), 0)

        fetcher.get_stock_limit_prices.assert_called_once_with("2026/04/23")
        fetcher.get_limit_list.assert_called_once_with("2026/04/23")
        fetcher.get_ths_hot.assert_called_once_with("2026/04/23")
        fetcher.get_dc_concepts.assert_called_once_with("2026/04/23")
        fetcher.get_stock_moneyflow_dc.assert_called_once_with("2026/04/23")
        fetcher.get_stock_moneyflow_ths.assert_called_once_with("2026/04/23")
        self.assertEqual(fetcher.get_dc_moneyflow_themes.call_count, 2)
        self.assertEqual(fetcher.get_dc_members.call_count, 1)
        fetcher.get_kpl_list.assert_called_once_with("2026/04/23", tag="涨停")
        fetcher.get_ths_members.assert_not_called()
        fetcher.get_ths_index.assert_not_called()
        fetcher.get_cyq_perf.assert_not_called()
        fetcher.get_cyq_chips.assert_not_called()

    def test_build_context_uses_cache_for_repeated_request(self) -> None:
        fetcher = self._make_fetcher()
        service = MomentumV13DataService(fetcher=fetcher)

        first = service.build_context(trade_date="20260423", ts_codes=["600519"])
        second = service.build_context(trade_date="20260423", ts_codes=["600519"])

        self.assertIs(first, second)
        fetcher.get_stock_limit_prices.assert_called_once()
        fetcher.get_limit_list.assert_called_once()
        fetcher.get_ths_hot.assert_called_once()
        fetcher.get_dc_concepts.assert_called_once()
        fetcher.get_stock_moneyflow_dc.assert_called_once()
        fetcher.get_stock_moneyflow_ths.assert_called_once()
        self.assertEqual(fetcher.get_dc_moneyflow_themes.call_count, 2)
        fetcher.get_dc_members.assert_called_once()
        fetcher.get_kpl_list.assert_called_once()
        fetcher.get_ths_members.assert_called_once()
        fetcher.get_ths_index.assert_called_once()
        fetcher.get_cyq_perf.assert_called_once()
        fetcher.get_cyq_chips.assert_called_once()
        self.assertGreaterEqual(MomentumV13DataService.get_cache_stats()["hit"], 1)

    def test_build_context_falls_back_to_per_stock_cyq_perf_when_snapshot_missing_code(self) -> None:
        fetcher = self._make_fetcher()

        def _cyq_perf_snapshot_then_fallback(trade_date, ts_code=None, limit=None, offset=None):
            if ts_code:
                return self._payload(
                    "tushare.cyq_perf",
                    [
                        {
                            "ts_code": ts_code,
                            "winner_rate": 0.58,
                            "weight_avg": 218.3,
                            "cost_5pct": 201.2,
                            "cost_15pct": 206.5,
                            "cost_50pct": 216.8,
                            "cost_85pct": 223.9,
                            "cost_95pct": 228.4,
                            "data_source": "tushare.cyq_perf",
                        }
                    ],
                )
            return self._payload(
                "tushare.cyq_perf",
                [
                    {
                        "ts_code": "600519.SH",
                        "winner_rate": 0.91,
                        "weight_avg": 1650.0,
                        "cost_5pct": 1520.0,
                        "cost_15pct": 1580.0,
                        "cost_50pct": 1638.0,
                        "cost_85pct": 1672.0,
                        "cost_95pct": 1704.0,
                        "data_source": "tushare.cyq_perf",
                    }
                ],
            )

        fetcher.get_cyq_perf.side_effect = _cyq_perf_snapshot_then_fallback
        service = MomentumV13DataService(fetcher=fetcher)

        context = service.build_context(trade_date="20260423", ts_codes=["600519.SH", "300750.SZ"])

        self.assertFalse(context["is_degraded"])
        self.assertAlmostEqual(context["chip_snapshots"]["300750.SZ"]["weight_avg"], 218.3)
        self.assertEqual(fetcher.get_cyq_perf.call_count, 2)

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


if __name__ == "__main__":
    unittest.main()
