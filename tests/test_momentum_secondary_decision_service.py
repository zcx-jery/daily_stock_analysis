# -*- coding: utf-8 -*-
"""Tests for MomentumSecondaryDecisionService."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import pandas as pd

from src.services.momentum_screener_service import MomentumScreenerService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from tests.test_momentum_screener_service import _FakeFetcher


class _FakeStockService:
    def __init__(self, quotes=None):
        self.quotes = quotes or {}

    def get_realtime_quote(self, stock_code):
        return self.quotes.get(stock_code)


class _FakeDailyBar:
    def __init__(self, trading_date: date, close: float, high: float, low: float):
        self.date = trading_date
        self.close = close
        self.high = high
        self.low = low


class _FakeStockRepo:
    def __init__(self, start_bars, forward_bars):
        self.start_bars = start_bars
        self.forward_bars = forward_bars

    def get_start_daily(self, *, code: str, analysis_date: date):
        return self.start_bars.get((code, analysis_date))

    def get_forward_bars(self, *, code: str, analysis_date: date, eval_window_days: int):
        return list(self.forward_bars.get((code, analysis_date), []))[:eval_window_days]


class _FakeIndexApi:
    def __init__(self, frames=None):
        self.frames = frames or {}

    def index_daily(self, ts_code: str, start_date: str | None = None, end_date: str | None = None):
        del start_date, end_date
        frame = self.frames.get(ts_code)
        if frame is None:
            return pd.DataFrame()
        return frame.copy()


class _FakeGateFetcher:
    def __init__(self, *, index_frames=None, index_snapshot=None, market_stats=None):
        self._api = _FakeIndexApi(index_frames) if index_frames is not None else None
        self._index_snapshot = index_snapshot or []
        self._market_stats = market_stats

    def get_main_indices(self, region: str = "cn"):
        del region
        return [dict(item) for item in self._index_snapshot]

    def get_market_stats(self):
        return dict(self._market_stats) if self._market_stats is not None else None


class _FakeGateScreenerService:
    def __init__(self, fetcher):
        self.fetcher = fetcher


class _FakeHistoricalScreenerService:
    def __init__(self, screens_by_date):
        self.screens_by_date = screens_by_date
        self.screen_calls = []

    def screen(
        self,
        *,
        top_n: int = 10,
        trade_date: str | None = None,
        profile: str = "standard",
        **_: object,
    ):
        normalized = trade_date if trade_date and "-" in trade_date else datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d")
        self.screen_calls.append(normalized)
        results = [dict(item) for item in self.screens_by_date.get(normalized, [])]
        return {
            "profile": profile,
            "trade_date": normalized,
            "candidate_count": len(results),
            "results": results[:top_n],
        }

    def list_recent_trade_dates(self, *, end_trade_date: str, limit: int):
        return [item for item in sorted(self.screens_by_date.keys(), reverse=True) if item < end_trade_date][:limit]


class _FullRankedHistoricalScreenerService(_FakeHistoricalScreenerService):
    def screen(
        self,
        *,
        top_n: int = 10,
        trade_date: str | None = None,
        profile: str = "standard",
        **kwargs: object,
    ):
        result = super().screen(top_n=top_n, trade_date=trade_date, profile=profile, **kwargs)
        full_ranked_results = [dict(item) for item in self.screens_by_date.get(result["trade_date"], [])]
        result["ranked_results"] = full_ranked_results
        result["results"] = full_ranked_results[:top_n]
        return result


class _FlakyHistoricalScreenerService(_FakeHistoricalScreenerService):
    def __init__(self, screens_by_date, failing_dates):
        super().__init__(screens_by_date)
        self.failing_dates = set(failing_dates)

    def screen(
        self,
        *,
        top_n: int = 10,
        trade_date: str | None = None,
        profile: str = "standard",
        **kwargs: object,
    ):
        normalized = trade_date if trade_date and "-" in trade_date else datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d")
        if normalized in self.failing_dates:
            self.screen_calls.append(normalized)
            raise RuntimeError(f"screen timeout for {normalized}")
        return super().screen(top_n=top_n, trade_date=trade_date, profile=profile, **kwargs)


class _FallbackForwardFetcher:
    def get_daily_data(self, stock_code: str, start_date=None, end_date=None, days: int = 6):
        analysis_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if stock_code == "600001.SH":
            return pd.DataFrame(
                [
                    {"date": analysis_date.strftime("%Y-%m-%d"), "close": 10.0, "high": 10.1, "low": 9.9},
                    {"date": (analysis_date + timedelta(days=1)).strftime("%Y-%m-%d"), "close": 10.2, "high": 10.35, "low": 9.8},
                    {"date": (analysis_date + timedelta(days=2)).strftime("%Y-%m-%d"), "close": 10.3, "high": 10.45, "low": 10.0},
                ]
            )
        return pd.DataFrame(
            [
                {"date": analysis_date.strftime("%Y-%m-%d"), "close": 20.0, "high": 20.2, "low": 19.8},
                {"date": (analysis_date + timedelta(days=1)).strftime("%Y-%m-%d"), "close": 20.6, "high": 20.9, "low": 19.4},
                {"date": (analysis_date + timedelta(days=2)).strftime("%Y-%m-%d"), "close": 20.8, "high": 21.1, "low": 19.7},
            ]
        )


def _build_historical_strategy_fixture(*, short_successes: int, long_successes: int):
    current_trade_date = "2026-04-10"
    current_screening = {
        "profile": "aggressive",
        "trade_date": current_trade_date,
        "candidate_count": 2,
        "results": [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "历史龙头",
                "pct_chg": 9.9,
                "continuation_score": 89.0,
                "extension_score": 81.0,
                "risk_score": 18.0,
                "buyability_score": 78.0,
                "opportunity_tag": "分歧转一致",
                "entry_range_low": 10.2,
                "entry_range_high": 10.5,
                "final_score": 90.0,
                "rank_score": 83.0,
                "themes": ["机器人"],
                "leader_level": "龙头",
                "top_reasons": ["强势确认", "资金承接"],
                "risk_tags": [],
                "score_breakdown": {},
            },
            {
                "rank": 2,
                "ts_code": "600002.SH",
                "name": "历史前排",
                "pct_chg": 8.5,
                "continuation_score": 82.0,
                "extension_score": 75.0,
                "risk_score": 26.0,
                "buyability_score": 72.0,
                "opportunity_tag": "放量换手",
                "entry_range_low": 18.4,
                "entry_range_high": 18.9,
                "final_score": 84.0,
                "rank_score": 77.0,
                "themes": ["机器人"],
                "leader_level": "前排",
                "top_reasons": ["换手充分", "主线共振"],
                "risk_tags": [],
                "score_breakdown": {},
            },
        ],
    }

    historical_dates = [
        (date(2026, 2, 8) + timedelta(days=index)).strftime("%Y-%m-%d")
        for index in range(60)
    ]
    historical_dates_desc = list(reversed(historical_dates))
    success_dates = set(historical_dates_desc[:short_successes])
    if long_successes > short_successes:
        extra_needed = long_successes - short_successes
        success_dates.update(historical_dates_desc[20 : 20 + extra_needed])

    screens_by_date = {}
    start_bars = {}
    forward_bars = {}
    for trade_date_str in historical_dates:
        screens_by_date[trade_date_str] = [dict(item) for item in current_screening["results"]]
        analysis_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()

        start_bars[("600001.SH", analysis_date)] = _FakeDailyBar(analysis_date, close=10.0, high=10.1, low=9.9)
        start_bars[("600002.SH", analysis_date)] = _FakeDailyBar(analysis_date, close=20.0, high=20.2, low=19.8)

        if trade_date_str in success_dates:
            forward_bars[("600001.SH", analysis_date)] = [
                _FakeDailyBar(analysis_date + timedelta(days=1), close=10.2, high=10.35, low=9.8),
                _FakeDailyBar(analysis_date + timedelta(days=2), close=10.3, high=10.45, low=10.0),
            ]
            forward_bars[("600002.SH", analysis_date)] = [
                _FakeDailyBar(analysis_date + timedelta(days=1), close=20.6, high=20.9, low=19.4),
                _FakeDailyBar(analysis_date + timedelta(days=2), close=20.8, high=21.1, low=19.7),
            ]
        else:
            forward_bars[("600001.SH", analysis_date)] = [
                _FakeDailyBar(analysis_date + timedelta(days=1), close=9.7, high=10.12, low=9.5),
                _FakeDailyBar(analysis_date + timedelta(days=2), close=9.8, high=10.0, low=9.6),
            ]
            forward_bars[("600002.SH", analysis_date)] = [
                _FakeDailyBar(analysis_date + timedelta(days=1), close=19.2, high=20.3, low=18.8),
                _FakeDailyBar(analysis_date + timedelta(days=2), close=19.4, high=20.1, low=19.0),
            ]

    request_params = {
        "top_n": 2,
        "min_change_pct": 7.0,
        "min_amount": 3e8,
        "min_turnover": 3.0,
        "exclude_st": True,
        "main_board_only": True,
        "trade_date": current_trade_date,
        "profile": "aggressive",
    }
    return current_screening, request_params, _FakeHistoricalScreenerService(screens_by_date), _FakeStockRepo(start_bars, forward_bars)


class MomentumSecondaryDecisionServiceTestCase(unittest.TestCase):
    def test_build_from_screening_returns_action_themes_and_portfolio(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        screening = {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 5,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "主线龙头",
                    "pct_chg": 9.9,
                    "continuation_score": 89.0,
                    "extension_score": 81.0,
                    "risk_score": 18.0,
                    "buyability_score": 78.0,
                    "opportunity_tag": "分歧转一致",
                    "entry_range_low": 10.2,
                    "entry_range_high": 10.5,
                    "final_score": 90.0,
                    "rank_score": 83.0,
                    "themes": ["机器人"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认", "资金承接"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 2,
                    "ts_code": "600002.SH",
                    "name": "前排换手",
                    "pct_chg": 8.5,
                    "continuation_score": 82.0,
                    "extension_score": 75.0,
                    "risk_score": 26.0,
                    "buyability_score": 72.0,
                    "opportunity_tag": "放量换手",
                    "entry_range_low": 18.4,
                    "entry_range_high": 18.9,
                    "final_score": 84.0,
                    "rank_score": 77.0,
                    "themes": ["机器人"],
                    "leader_level": "前排",
                    "top_reasons": ["换手充分", "主线共振"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 3,
                    "ts_code": "600003.SH",
                    "name": "观察备选",
                    "pct_chg": 7.8,
                    "continuation_score": 74.0,
                    "extension_score": 68.0,
                    "risk_score": 32.0,
                    "buyability_score": 61.0,
                    "opportunity_tag": "回踩承接",
                    "entry_range_low": 22.1,
                    "entry_range_high": 22.6,
                    "final_score": 78.0,
                    "rank_score": 70.0,
                    "themes": ["机器人"],
                    "leader_level": "中位",
                    "top_reasons": ["跟随回流"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 4,
                    "ts_code": "600004.SH",
                    "name": "次主线龙头",
                    "pct_chg": 8.8,
                    "continuation_score": 80.0,
                    "extension_score": 72.0,
                    "risk_score": 29.0,
                    "buyability_score": 70.0,
                    "opportunity_tag": "板块回流",
                    "entry_range_low": 12.0,
                    "entry_range_high": 12.3,
                    "final_score": 81.0,
                    "rank_score": 75.0,
                    "themes": ["电力设备"],
                    "leader_level": "龙头",
                    "top_reasons": ["板块联动"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 5,
                    "ts_code": "600005.SH",
                    "name": "弱跟风",
                    "pct_chg": 7.1,
                    "continuation_score": 63.0,
                    "extension_score": 60.0,
                    "risk_score": 48.0,
                    "buyability_score": 48.0,
                    "opportunity_tag": None,
                    "entry_range_low": None,
                    "entry_range_high": None,
                    "final_score": 60.0,
                    "rank_score": 58.0,
                    "themes": ["医药"],
                    "leader_level": "后排",
                    "top_reasons": ["低位异动"],
                    "risk_tags": ["risk-alert"],
                    "score_breakdown": {},
                },
            ],
        }

        result = service.build_from_screening(screening)

        self.assertEqual(result["profile"], "aggressive")
        self.assertEqual(result["action"]["level"], "cautious_go")
        self.assertEqual(result["strategy_health"]["status"], "healthy")
        self.assertGreaterEqual(len(result["themes"]), 2)
        self.assertEqual(result["themes"][0]["name"], "机器人")
        self.assertEqual([item["slot"] for item in result["portfolio"]], ["main", "secondary", "watch"])
        self.assertEqual(result["portfolio"][0]["name"], "主线龙头")
        self.assertTrue(result["portfolio"][0]["entry_hint"])
        self.assertTrue(result["action_checklist"]["enabled"])
        self.assertEqual(len(result["action_checklist"]["steps"]), 3)
        self.assertEqual(result["action_checklist"]["steps"][0]["phase"], "pre_open")
        self.assertTrue(result["excluded_candidates"])
        self.assertEqual(result["excluded_candidates"][0]["reason"], "非主线 / 主线过弱")

    def test_build_from_screening_disables_strategy_when_both_windows_are_weak(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        screening = {
            "profile": "standard",
            "trade_date": "2026-04-10",
            "candidate_count": 1,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600010.SH",
                    "name": "弱势观察票",
                    "pct_chg": 4.8,
                    "continuation_score": 58.0,
                    "extension_score": 55.0,
                    "risk_score": 60.0,
                    "buyability_score": 42.0,
                    "opportunity_tag": None,
                    "entry_range_low": None,
                    "entry_range_high": None,
                    "final_score": 56.0,
                    "rank_score": 52.0,
                    "themes": ["其他"],
                    "leader_level": "后排",
                    "top_reasons": ["低位异动"],
                    "risk_tags": ["risk-alert"],
                    "score_breakdown": {},
                }
            ],
        }

        result = service.build_from_screening(screening)

        self.assertEqual(result["strategy_health"]["status"], "disabled")
        self.assertEqual(result["strategy_health"]["recommendation_cap"], "disabled")
        self.assertEqual(result["action"]["level"], "observe_only")
        self.assertFalse(result["action_checklist"]["enabled"])
        self.assertTrue(all(item["suggested_action"] == "observe_only" for item in result["portfolio"]))

    def test_build_from_screening_requires_entry_range_for_clear_buy_point(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        screening = {
            "profile": "standard",
            "trade_date": "2026-04-10",
            "candidate_count": 2,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600011.SH",
                    "name": "标准龙头",
                    "pct_chg": 9.8,
                    "continuation_score": 86.0,
                    "extension_score": 79.0,
                    "risk_score": 18.0,
                    "buyability_score": None,
                    "opportunity_tag": None,
                    "entry_range_low": None,
                    "entry_range_high": None,
                    "final_score": 88.0,
                    "rank_score": 74.0,
                    "themes": ["电力设备"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认", "资金承接"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 2,
                    "ts_code": "600012.SH",
                    "name": "标准前排",
                    "pct_chg": 8.1,
                    "continuation_score": 73.0,
                    "extension_score": 68.0,
                    "risk_score": 28.0,
                    "buyability_score": None,
                    "opportunity_tag": None,
                    "entry_range_low": None,
                    "entry_range_high": None,
                    "final_score": 79.0,
                    "rank_score": 63.0,
                    "themes": ["电力设备"],
                    "leader_level": "前排",
                    "top_reasons": ["量价结构"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
            ],
        }

        result = service.build_from_screening(screening)

        self.assertEqual(result["portfolio"][0]["buy_point_status"], "waiting")
        self.assertEqual(result["portfolio"][0]["suggested_action"], "observe_only")

    def test_build_from_screening_prefers_full_ranked_results_over_display_topn(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        ranked_results = [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "Leader Core",
                "pct_chg": 9.9,
                "continuation_score": 89.0,
                "extension_score": 81.0,
                "risk_score": 18.0,
                "buyability_score": 78.0,
                "opportunity_tag": "breakout_confirmation",
                "entry_range_low": 10.2,
                "entry_range_high": 10.5,
                "final_score": 90.0,
                "rank_score": 83.0,
                "themes": ["AI"],
                "leader_level": "leader",
                "top_reasons": ["strength_confirmed", "capital_support"],
                "risk_tags": [],
                "score_breakdown": {},
            },
            {
                "rank": 2,
                "ts_code": "600002.SH",
                "name": "Front Runner",
                "pct_chg": 8.5,
                "continuation_score": 82.0,
                "extension_score": 75.0,
                "risk_score": 26.0,
                "buyability_score": 72.0,
                "opportunity_tag": "turnover_breakout",
                "entry_range_low": 18.4,
                "entry_range_high": 18.9,
                "final_score": 84.0,
                "rank_score": 77.0,
                "themes": ["AI"],
                "leader_level": "front",
                "top_reasons": ["turnover_ready", "theme_resonance"],
                "risk_tags": [],
                "score_breakdown": {},
            },
            {
                "rank": 3,
                "ts_code": "600003.SH",
                "name": "Watch Backup",
                "pct_chg": 7.8,
                "continuation_score": 74.0,
                "extension_score": 68.0,
                "risk_score": 32.0,
                "buyability_score": 61.0,
                "opportunity_tag": "pullback_support",
                "entry_range_low": 22.1,
                "entry_range_high": 22.6,
                "final_score": 78.0,
                "rank_score": 70.0,
                "themes": ["AI"],
                "leader_level": "mid",
                "top_reasons": ["follow_through"],
                "risk_tags": [],
                "score_breakdown": {},
            },
        ]
        screening = {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 3,
            "results": ranked_results[:1],
            "ranked_results": ranked_results,
        }

        result = service.build_from_screening(screening)

        self.assertEqual([item["ts_code"] for item in result["portfolio"]], ["600001.SH", "600002.SH", "600003.SH"])
        self.assertEqual(result["themes"][0]["candidate_count"], 3)
        self.assertEqual(result["excluded_candidates"], [])

    def test_build_from_screening_allows_forward_alpha_to_challenge_clear_leader(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        screening = {
            "profile": "standard",
            "trade_date": "2026-04-10",
            "candidate_count": 2,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600101.SH",
                    "name": "稳态龙头",
                    "pct_chg": 7.2,
                    "continuation_score": 84.0,
                    "extension_score": 70.0,
                    "risk_score": 18.0,
                    "buyability_score": None,
                    "entry_range_low": 10.1,
                    "entry_range_high": 10.4,
                    "final_score": 84.0,
                    "rank_score": 83.0,
                    "themes": ["机器人"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 8,
                    "ts_code": "600108.SH",
                    "name": "高弹性前排",
                    "pct_chg": 8.6,
                    "continuation_score": 96.0,
                    "extension_score": 90.0,
                    "risk_score": 35.0,
                    "buyability_score": None,
                    "entry_range_low": None,
                    "entry_range_high": None,
                    "final_score": 82.0,
                    "rank_score": 80.0,
                    "themes": ["机器人"],
                    "leader_level": "前排",
                    "top_reasons": ["弹性更强"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
            ],
        }

        result = service.build_from_screening(screening)

        self.assertEqual(result["portfolio"][0]["ts_code"], "600108.SH")
        self.assertEqual(result["portfolio"][0]["buy_point_status"], "waiting")
        self.assertGreater(
            result["portfolio"][0]["forward_alpha_score"],
            result["portfolio"][1]["forward_alpha_score"],
        )
        diagnostic = next(
            item for item in result["candidate_diagnostics"] if item["ts_code"] == "600108.SH"
        )
        self.assertEqual(diagnostic["selected_slot"], "main")

    def test_build_from_screening_keeps_secondary_on_mainline_when_cross_theme_is_too_weak(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)
        screening = {
            "profile": "standard",
            "trade_date": "2026-04-10",
            "candidate_count": 4,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600201.SH",
                    "name": "主线前排",
                    "pct_chg": 7.0,
                    "continuation_score": 92.0,
                    "extension_score": 86.0,
                    "risk_score": 0.0,
                    "buyability_score": None,
                    "final_score": 88.0,
                    "rank_score": 86.0,
                    "themes": ["电力设备"],
                    "leader_level": "front",
                    "top_reasons": ["主线强"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 2,
                    "ts_code": "600202.SH",
                    "name": "主线龙头",
                    "pct_chg": 6.8,
                    "continuation_score": 89.0,
                    "extension_score": 85.0,
                    "risk_score": 0.0,
                    "buyability_score": None,
                    "final_score": 87.0,
                    "rank_score": 85.0,
                    "themes": ["电力设备"],
                    "leader_level": "leader",
                    "top_reasons": ["主线确认"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 3,
                    "ts_code": "600203.SH",
                    "name": "次线前排",
                    "pct_chg": 6.5,
                    "continuation_score": 80.0,
                    "extension_score": 82.0,
                    "risk_score": 0.0,
                    "buyability_score": None,
                    "final_score": 78.0,
                    "rank_score": 76.0,
                    "themes": ["电子"],
                    "leader_level": "front",
                    "top_reasons": ["次线跟随"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 4,
                    "ts_code": "600204.SH",
                    "name": "次线龙头",
                    "pct_chg": 6.3,
                    "continuation_score": 79.0,
                    "extension_score": 80.0,
                    "risk_score": 0.0,
                    "buyability_score": None,
                    "final_score": 77.0,
                    "rank_score": 75.0,
                    "themes": ["电子"],
                    "leader_level": "leader",
                    "top_reasons": ["次线确认"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
            ],
        }

        result = service.build_from_screening(screening)

        self.assertEqual(result["portfolio"][0]["ts_code"], "600201.SH")
        self.assertEqual(result["portfolio"][1]["ts_code"], "600202.SH")

    def test_build_from_screening_uses_real_historical_validation_for_strategy_health(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(result["strategy_health"]["status"], "healthy")
            self.assertEqual(result["strategy_health"]["recommendation_cap"], "full")
            self.assertEqual(result["strategy_health"]["short_window"]["sample_count"], 20)
            self.assertEqual(result["strategy_health"]["long_window"]["sample_count"], 60)
            self.assertGreaterEqual(result["strategy_health"]["short_window"]["success_rate"], 65.0)
            self.assertGreaterEqual(result["strategy_health"]["long_window"]["success_rate"], 60.0)
            self.assertGreater(result["strategy_health"]["short_window"]["avg_profit_window_pct"], 2.0)
            self.assertLessEqual(result["strategy_health"]["short_window"]["avg_max_drawdown_pct"], 3.5)

    def test_strategy_health_trade_date_uses_full_ranked_results_not_display_topn(self) -> None:
        screening, request_params, historical_screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        historical_trade_date = sorted(historical_screener_service.screens_by_date.keys())[0]
        full_ranked_service = _FullRankedHistoricalScreenerService(
            {
                historical_trade_date: [
                    dict(item) for item in historical_screener_service.screens_by_date[historical_trade_date]
                ]
            }
        )
        request_params = {**request_params, "top_n": 1}
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=full_ranked_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            trade_result = service._evaluate_strategy_health_trade_date(
                historical_trade_date=historical_trade_date,
                request_params=request_params,
            )

            self.assertIsNotNone(trade_result)
            self.assertEqual(trade_result["selected_count"], 2)

    def test_strategy_health_trade_date_uses_internal_evaluation_topn_when_results_are_truncated(self) -> None:
        screening, request_params, historical_screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        historical_trade_date = sorted(historical_screener_service.screens_by_date.keys())[0]
        request_params = {**request_params, "top_n": 1}
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=historical_screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            trade_result = service._evaluate_strategy_health_trade_date(
                historical_trade_date=historical_trade_date,
                request_params=request_params,
            )

            self.assertIsNotNone(trade_result)
            self.assertEqual(trade_result["selected_count"], 2)

    def test_build_from_screening_downgrades_action_when_real_historical_validation_is_weak(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=5,
            long_successes=12,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(result["strategy_health"]["status"], "disabled")
            self.assertEqual(result["strategy_health"]["recommendation_cap"], "disabled")
            self.assertEqual(result["action"]["level"], "cautious_go")
            self.assertTrue(result["strategy_health"]["blockers"])
            self.assertIn(result["portfolio"][0]["suggested_action"], {"ready", "wait_for_trigger"})
            self.assertTrue(all(item["suggested_action"] == "observe_only" for item in result["portfolio"][1:]))

    def test_build_from_screening_cached_only_mode_skips_historical_replay(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = service.build_from_screening(
                screening,
                request_params=request_params,
                strategy_health_mode="cached_only",
            )

            self.assertEqual(result["strategy_health"]["data_source"], "proxy")
            self.assertEqual(result["strategy_health"]["validation_status"], "proxy")
            self.assertEqual(len(screener_service.screen_calls), 1)

    def test_build_from_screening_cached_only_mode_reuses_cached_historical_health(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            first_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            first = first_service.build_from_screening(screening, request_params=request_params)
            initial_calls = len(screener_service.screen_calls)

            second_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            second = second_service.build_from_screening(
                screening,
                request_params=request_params,
                strategy_health_mode="cached_only",
            )

            self.assertEqual(second["strategy_health"]["data_source"], "historical")
            self.assertEqual(second["strategy_health"]["validation_status"], "final")
            self.assertEqual(second["strategy_health"]["status"], first["strategy_health"]["status"])
            self.assertEqual(len(screener_service.screen_calls), initial_calls + 1)

    def test_build_from_screening_returns_proxy_health_while_async_validation_warms(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=True,
                strategy_health_cache_dir=Path(temp_dir),
            )
            try:
                first = service.build_from_screening(screening, request_params=request_params)

                self.assertEqual(first["strategy_health"]["data_source"], "proxy")
                self.assertTrue(first["strategy_health"]["is_warming"])
                self.assertIn("后台", first["strategy_health"]["reason"])

                deadline = time.time() + 3.0
                cache_key = service._build_strategy_health_cache_key(screening["trade_date"], request_params)
                cached = None
                while time.time() < deadline:
                    cached = service._load_cached_strategy_health(cache_key)
                    if cached is not None:
                        break
                    time.sleep(0.05)

                self.assertIsNotNone(cached)

                second = service.build_from_screening(screening, request_params=request_params)
                self.assertEqual(second["strategy_health"]["data_source"], "historical")
                self.assertFalse(second["strategy_health"]["is_warming"])
                self.assertEqual(second["strategy_health"]["status"], "healthy")
            finally:
                if service._strategy_health_executor is not None:
                    service._strategy_health_executor.shutdown(wait=True)

    def test_build_from_screening_waits_for_historical_validation_when_requested(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=True,
                strategy_health_async_delay_seconds=20.0,
                strategy_health_cache_dir=Path(temp_dir),
            )
            try:
                result = service.build_from_screening(
                    screening,
                    request_params=request_params,
                    wait_for_strategy_health=True,
                )

                self.assertEqual(result["strategy_health"]["data_source"], "historical")
                self.assertFalse(result["strategy_health"]["is_warming"])
                self.assertEqual(result["strategy_health"]["status"], "healthy")
            finally:
                if service._strategy_health_executor is not None:
                    service._strategy_health_executor.shutdown(wait=True)

    def test_build_from_screening_skips_failed_historical_samples(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        flaky_service = _FlakyHistoricalScreenerService(
            screener_service.screens_by_date,
            failing_dates={"2026-04-08", "2026-04-03"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=flaky_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(result["strategy_health"]["data_source"], "historical")
            self.assertFalse(result["strategy_health"]["is_warming"])
            self.assertEqual(result["strategy_health"]["status"], "healthy")
            self.assertIn("2026-04-08", flaky_service.screen_calls)
            self.assertIn("2026-04-03", flaky_service.screen_calls)

    def test_build_from_screening_reuses_disk_cached_historical_health(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            first_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            first = first_service.build_from_screening(screening, request_params=request_params)
            initial_calls = len(screener_service.screen_calls)

            second_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            second = second_service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(second["strategy_health"]["data_source"], "historical")
            self.assertFalse(second["strategy_health"]["is_warming"])
            self.assertEqual(second["strategy_health"]["status"], first["strategy_health"]["status"])
            self.assertEqual(len(screener_service.screen_calls), initial_calls + 1)

    def test_build_from_screening_reuses_cached_historical_health_across_display_topn(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            first_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            first = first_service.build_from_screening(screening, request_params=request_params)
            initial_calls = len(screener_service.screen_calls)

            second_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            second = second_service.build_from_screening(
                screening,
                request_params={**request_params, "top_n": 1},
            )

            self.assertEqual(second["strategy_health"]["data_source"], "historical")
            self.assertFalse(second["strategy_health"]["is_warming"])
            self.assertEqual(second["strategy_health"]["status"], first["strategy_health"]["status"])
            self.assertEqual(second["action"]["level"], first["action"]["level"])
            self.assertEqual(len(screener_service.screen_calls), initial_calls + 1)

    def test_build_from_screening_surfaces_partial_historical_health_while_background_job_continues(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=True,
                strategy_health_cache_dir=Path(temp_dir),
            )
            original_evaluate = service._evaluate_strategy_health_trade_date

            def slow_evaluate(*, historical_trade_date: str, request_params: dict[str, object]):
                time.sleep(0.01)
                return original_evaluate(
                    historical_trade_date=historical_trade_date,
                    request_params=request_params,
                )

            try:
                with patch(
                    "src.services.momentum_secondary_decision_service.STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS",
                    0.03,
                ), patch.object(service, "_evaluate_strategy_health_trade_date", side_effect=slow_evaluate):
                    first = service.build_from_screening(screening, request_params=request_params)

                    self.assertEqual(first["strategy_health"]["data_source"], "proxy")
                    self.assertEqual(first["strategy_health"]["validation_status"], "proxy")
                    self.assertTrue(first["strategy_health"]["is_warming"])

                    partial = None
                    deadline = time.time() + 3.0
                    while time.time() < deadline:
                        partial = service.build_from_screening(screening, request_params=request_params)
                        if partial["strategy_health"]["validation_status"] == "partial":
                            break
                        time.sleep(0.05)

                    self.assertIsNotNone(partial)
                    self.assertEqual(partial["strategy_health"]["data_source"], "historical")
                    self.assertEqual(partial["strategy_health"]["validation_status"], "partial")
                    self.assertTrue(partial["strategy_health"]["is_warming"])
                    self.assertGreater(partial["strategy_health"]["progress"]["valid_sample_count"], 0)
                    self.assertLess(
                        partial["strategy_health"]["progress"]["processed_trade_date_count"],
                        partial["strategy_health"]["progress"]["total_trade_date_count"],
                    )

                    final = None
                    deadline = time.time() + 4.0
                    while time.time() < deadline:
                        final = service.build_from_screening(screening, request_params=request_params)
                        if final["strategy_health"]["validation_status"] == "final":
                            break
                        time.sleep(0.05)

                    self.assertIsNotNone(final)
                    self.assertEqual(final["strategy_health"]["data_source"], "historical")
                    self.assertEqual(final["strategy_health"]["validation_status"], "final")
                    self.assertFalse(final["strategy_health"]["is_warming"])
                    self.assertEqual(final["strategy_health"]["progress"]["valid_sample_count"], 60)
            finally:
                if service._strategy_health_executor is not None:
                    service._strategy_health_executor.shutdown(wait=True)

    def test_strategy_health_state_resumes_from_partial_checkpoint_across_service_instances(self) -> None:
        screening, request_params, screener_service, stock_repo = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            first_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )
            cache_key = first_service._build_strategy_health_cache_key(screening["trade_date"], request_params)
            original_evaluate = first_service._evaluate_strategy_health_trade_date

            def slow_evaluate(*, historical_trade_date: str, request_params: dict[str, object]):
                time.sleep(0.01)
                return original_evaluate(
                    historical_trade_date=historical_trade_date,
                    request_params=request_params,
                )

            with patch(
                "src.services.momentum_secondary_decision_service.STRATEGY_HEALTH_COMPUTE_TIME_BUDGET_SECONDS",
                0.03,
            ), patch.object(first_service, "_evaluate_strategy_health_trade_date", side_effect=slow_evaluate):
                partial_state = first_service._advance_strategy_health_state(
                    cache_key=cache_key,
                    trade_date=screening["trade_date"],
                    request_params=request_params,
                )

            self.assertIsNotNone(partial_state)
            self.assertEqual(partial_state["status"], "partial")
            self.assertLess(len(screener_service.screen_calls), 60)

            second_service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=stock_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = second_service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(result["strategy_health"]["data_source"], "historical")
            self.assertEqual(result["strategy_health"]["validation_status"], "final")
            self.assertEqual(result["strategy_health"]["progress"]["valid_sample_count"], 60)
            self.assertEqual(len(screener_service.screen_calls), 61)

    def test_build_from_screening_uses_fetcher_fallback_when_repo_lacks_forward_bars(self) -> None:
        screening, request_params, screener_service, _ = _build_historical_strategy_fixture(
            short_successes=14,
            long_successes=38,
        )
        screener_service.fetcher = _FallbackForwardFetcher()
        empty_repo = _FakeStockRepo(start_bars={}, forward_bars={})
        with tempfile.TemporaryDirectory() as temp_dir:
            service = MomentumSecondaryDecisionService(
                screener_service=screener_service,
                stock_repo=empty_repo,
                strategy_health_async=False,
                strategy_health_cache_dir=Path(temp_dir),
            )

            result = service.build_from_screening(screening, request_params=request_params)

            self.assertEqual(result["strategy_health"]["data_source"], "historical")
            self.assertEqual(result["strategy_health"]["status"], "healthy")

    def test_build_runs_with_underlying_screener_service(self) -> None:
        screener_service = MomentumScreenerService(fetcher=_FakeFetcher())
        service = MomentumSecondaryDecisionService(screener_service=screener_service)

        result = service.build(top_n=2, trade_date="2026-04-10", profile="aggressive")

        self.assertEqual(result["screening"]["candidate_count"], 2)
        self.assertEqual(result["decision"]["profile"], "aggressive")
        self.assertEqual(result["decision"]["trade_date"], "2026-04-10")
        self.assertTrue(result["decision"]["themes"])
        self.assertTrue(result["decision"]["portfolio"])
        self.assertIn("action", result["decision"])

    def test_build_intraday_from_decision_marks_overextended_price_as_do_not_chase(self) -> None:
        screening = {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 2,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "主线龙头",
                    "pct_chg": 9.9,
                    "continuation_score": 89.0,
                    "extension_score": 81.0,
                    "risk_score": 18.0,
                    "buyability_score": 78.0,
                    "opportunity_tag": "分歧转一致",
                    "entry_range_low": 10.2,
                    "entry_range_high": 10.5,
                    "final_score": 90.0,
                    "rank_score": 83.0,
                    "themes": ["机器人"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 2,
                    "ts_code": "600002.SH",
                    "name": "前排换手",
                    "pct_chg": 8.5,
                    "continuation_score": 82.0,
                    "extension_score": 75.0,
                    "risk_score": 26.0,
                    "buyability_score": 72.0,
                    "opportunity_tag": "放量换手",
                    "entry_range_low": 18.4,
                    "entry_range_high": 18.9,
                    "final_score": 84.0,
                    "rank_score": 77.0,
                    "themes": ["机器人"],
                    "leader_level": "前排",
                    "top_reasons": ["换手充分"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
            ],
        }
        stock_service = _FakeStockService(
            {
                "600001.SH": {
                    "stock_code": "600001.SH",
                    "current_price": 10.95,
                    "open": 10.55,
                    "change_percent": 4.2,
                    "prev_close": 10.5,
                    "update_time": "2026-04-11T10:05:00",
                },
                "600002.SH": {
                    "stock_code": "600002.SH",
                    "current_price": 18.12,
                    "open": 18.24,
                    "change_percent": -0.4,
                    "prev_close": 18.4,
                    "update_time": "2026-04-11T10:05:00",
                },
            }
        )
        service = MomentumSecondaryDecisionService(stock_service=stock_service)
        decision = service.build_from_screening(screening)

        intraday = service.build_intraday_from_decision(
            decision,
            now=datetime(2026, 4, 11, 10, 5),
        )

        main_item = intraday["portfolio_items"][0]
        self.assertEqual(main_item["status"], "do_not_chase")
        self.assertTrue(main_item["do_not_chase"])
        self.assertEqual(intraday["final_recommendation"], "watch")
        self.assertTrue(intraday["closing_note"])
        self.assertTrue(intraday["focus_order"])
        self.assertIn("主仓", intraday["focus_order"][0])

    def test_build_intraday_from_decision_downgrades_to_low_confidence_when_main_is_weaker(self) -> None:
        screening = {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 2,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "主线龙头",
                    "pct_chg": 9.9,
                    "continuation_score": 89.0,
                    "extension_score": 81.0,
                    "risk_score": 18.0,
                    "buyability_score": 78.0,
                    "opportunity_tag": "分歧转一致",
                    "entry_range_low": 10.2,
                    "entry_range_high": 10.5,
                    "final_score": 90.0,
                    "rank_score": 83.0,
                    "themes": ["机器人"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
                {
                    "rank": 2,
                    "ts_code": "600002.SH",
                    "name": "前排换手",
                    "pct_chg": 8.5,
                    "continuation_score": 82.0,
                    "extension_score": 75.0,
                    "risk_score": 26.0,
                    "buyability_score": 72.0,
                    "opportunity_tag": "放量换手",
                    "entry_range_low": 18.4,
                    "entry_range_high": 18.9,
                    "final_score": 84.0,
                    "rank_score": 77.0,
                    "themes": ["机器人"],
                    "leader_level": "前排",
                    "top_reasons": ["换手充分"],
                    "risk_tags": [],
                    "score_breakdown": {},
                },
            ],
        }
        stock_service = _FakeStockService(
            {
                "600001.SH": {
                    "stock_code": "600001.SH",
                    "current_price": 10.05,
                    "open": 10.36,
                    "change_percent": -1.8,
                    "prev_close": 10.45,
                    "update_time": "2026-04-11T09:50:00",
                },
                "600002.SH": {
                    "stock_code": "600002.SH",
                    "current_price": 18.92,
                    "open": 18.45,
                    "change_percent": 3.9,
                    "prev_close": 18.4,
                    "update_time": "2026-04-11T09:50:00",
                },
            }
        )
        service = MomentumSecondaryDecisionService(stock_service=stock_service)
        decision = service.build_from_screening(screening)

        intraday = service.build_intraday_from_decision(
            decision,
            now=datetime(2026, 4, 11, 9, 50),
        )

        self.assertEqual(intraday["confidence_level"], "low")
        self.assertEqual(intraday["status"], "low_confidence")
        self.assertEqual(intraday["final_recommendation"], "do_not_buy")
        self.assertTrue(intraday["watch_items"])
        self.assertTrue(intraday["closing_note"])
        self.assertEqual(len(intraday["focus_order"]), len(intraday["portfolio_items"]))

    def test_build_market_environment_index_trend_prefers_ma5_and_slope_history(self) -> None:
        index_frames = {
            "000001.SH": pd.DataFrame(
                {
                    "trade_date": ["20260407", "20260408", "20260409", "20260410", "20260411"],
                    "close": [3200.0, 3215.0, 3235.0, 3260.0, 3285.0],
                }
            ),
            "399006.SZ": pd.DataFrame(
                {
                    "trade_date": ["20260407", "20260408", "20260409", "20260410", "20260411"],
                    "close": [1890.0, 1905.0, 1922.0, 1938.0, 1950.0],
                }
            ),
            "399303.SZ": pd.DataFrame(
                {
                    "trade_date": ["20260407", "20260408", "20260409", "20260410", "20260411"],
                    "close": [5100.0, 5115.0, 5130.0, 5148.0, 5165.0],
                }
            ),
        }
        service = MomentumSecondaryDecisionService(
            screener_service=_FakeGateScreenerService(
                _FakeGateFetcher(
                    index_frames=index_frames,
                    index_snapshot=[
                        {"code": "000001", "name": "上证指数", "change_pct": -0.8},
                        {"code": "399006", "name": "创业板指", "change_pct": -0.5},
                    ],
                )
            )
        )

        result = service._build_market_environment_index_trend()

        self.assertEqual(result["level"], "strong")
        self.assertIn("5 日线", result["summary"])
        self.assertIn("上证指数", result["summary"])

    def test_build_market_environment_sentiment_prefers_market_stats_when_available(self) -> None:
        service = MomentumSecondaryDecisionService(
            screener_service=_FakeGateScreenerService(
                _FakeGateFetcher(
                    market_stats={
                        "up_count": 3250,
                        "down_count": 1380,
                        "flat_count": 220,
                        "limit_up_count": 78,
                        "limit_down_count": 5,
                        "total_amount": 13650.0,
                    }
                )
            )
        )

        result = service._build_market_environment_sentiment([], [])

        self.assertEqual(result["level"], "strong")
        self.assertIn("涨停 78 家", result["summary"])
        self.assertIn("成交额 13650 亿元", result["summary"])

    def test_build_intraday_from_decision_returns_main_only_consider_for_cautious_go(self) -> None:
        stock_service = _FakeStockService(
            quotes={
                "600001.SH": {
                    "current_price": 10.3,
                    "open": 10.1,
                    "change_percent": 2.1,
                    "update_time": "2026-04-11T09:50:00",
                }
            }
        )
        service = MomentumSecondaryDecisionService(stock_service=stock_service)
        decision = {
            "trade_date": "2026-04-11",
            "action": {
                "level": "cautious_go",
                "label": "谨慎出手",
                "reason": "今天只能谨慎处理主仓。",
            },
            "portfolio": [
                {
                    "slot": "main",
                    "slot_label": "主仓",
                    "ts_code": "600001.SH",
                    "name": "测试主仓",
                    "theme": "机器人",
                    "role": "龙头核心",
                    "buy_point_status": "clear",
                    "suggested_action": "ready",
                    "entry_range_low": 10.0,
                    "entry_range_high": 10.5,
                },
                {
                    "slot": "secondary",
                    "slot_label": "次仓",
                    "ts_code": "600002.SH",
                    "name": "测试次仓",
                    "theme": "机器人",
                    "role": "前排换手",
                    "buy_point_status": "clear",
                    "suggested_action": "observe_only",
                    "entry_range_low": 18.0,
                    "entry_range_high": 18.5,
                },
            ],
        }

        intraday = service.build_intraday_from_decision(
            decision,
            now=datetime(2026, 4, 11, 9, 50),
        )

        self.assertEqual(intraday["status"], "buy_ready")
        self.assertEqual(intraday["final_recommendation"], "main_only_consider")
        self.assertTrue(intraday["can_emit_buy_signal"])
        self.assertIn("主仓", intraday["closing_note"])

    def test_build_opportunity_buy_point_clarity_relaxes_when_two_slots_are_clear(self) -> None:
        result = MomentumSecondaryDecisionService._build_opportunity_buy_point_clarity(
            [
                {"slot": "main", "buy_point_status": "waiting"},
                {"slot": "secondary", "buy_point_status": "clear"},
                {"slot": "watch", "buy_point_status": "clear"},
            ]
        )

        self.assertEqual(result["level"], "medium")
        self.assertEqual(result["score"], 60.0)

    def test_build_opportunity_quality_stays_medium_when_main_waits_but_two_slots_are_clear(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)

        result = service._build_opportunity_quality(
            candidates=[],
            themes=[
                {"name": "Theme A", "score": 83.0},
                {"name": "Theme B", "score": 79.0},
            ],
            portfolio=[
                {
                    "slot": "main",
                    "buy_point_status": "waiting",
                    "suggested_action": "wait_for_trigger",
                    "risk_score": 18.0,
                    "entry_range_low": 10.0,
                    "entry_range_high": 10.5,
                    "risk_tags": [],
                },
                {
                    "slot": "secondary",
                    "buy_point_status": "clear",
                    "suggested_action": "ready",
                    "risk_score": 22.0,
                    "entry_range_low": 12.0,
                    "entry_range_high": 12.4,
                    "risk_tags": [],
                },
                {
                    "slot": "watch",
                    "buy_point_status": "clear",
                    "suggested_action": "ready",
                    "risk_score": 20.0,
                    "entry_range_low": 8.0,
                    "entry_range_high": 8.3,
                    "risk_tags": [],
                },
            ],
        )

        self.assertEqual(result["level"], "medium")
        buy_point_clarity = next(module for module in result["modules"] if module["key"] == "buy_point_clarity")
        self.assertEqual(buy_point_clarity["level"], "medium")

    def test_build_action_caps_to_cautious_when_main_buy_point_is_not_clear(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)

        result = service._build_action(
            "standard",
            market_environment={
                "level": "strong",
                "modules": [{"key": "profitability", "level": "strong", "core_level": "strong"}],
            },
            opportunity_quality={
                "level": "strong",
                "main_buy_point_clear": False,
                "secondary_buy_point_clear": True,
                "core_overextended_count": 0,
                "portfolio_unresolved": False,
                "modules": [
                    {"key": "theme_clarity", "level": "strong"},
                    {"key": "portfolio_quality", "level": "strong"},
                ],
            },
            historical_validity={"level": "healthy"},
            portfolio=[
                {"slot": "main", "buy_point_status": "waiting", "risk_tags": [], "risk_score": 18.0},
                {"slot": "secondary", "buy_point_status": "clear", "risk_tags": [], "risk_score": 20.0},
            ],
        )

        self.assertEqual(result["level"], "cautious_go")

    def test_build_action_drops_to_observe_when_both_core_items_are_overextended(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)

        result = service._build_action(
            "aggressive",
            market_environment={
                "level": "strong",
                "modules": [{"key": "profitability", "level": "strong", "core_level": "strong"}],
            },
            opportunity_quality={
                "level": "strong",
                "main_buy_point_clear": True,
                "secondary_buy_point_clear": True,
                "core_overextended_count": 2,
                "portfolio_unresolved": False,
                "modules": [
                    {"key": "theme_clarity", "level": "strong"},
                    {"key": "portfolio_quality", "level": "strong"},
                ],
            },
            historical_validity={"level": "healthy"},
            portfolio=[
                {
                    "slot": "main",
                    "buy_point_status": "clear",
                    "risk_tags": ["high_acceleration"],
                    "risk_score": 38.0,
                },
                {
                    "slot": "secondary",
                    "buy_point_status": "clear",
                    "risk_tags": ["high_acceleration"],
                    "risk_score": 36.0,
                },
            ],
        )

        self.assertEqual(result["level"], "observe_only")

    def test_build_action_forces_stand_aside_when_market_and_core_profitability_are_weak(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)

        result = service._build_action(
            "standard",
            market_environment={
                "level": "weak",
                "modules": [{"key": "profitability", "level": "weak", "core_level": "weak"}],
            },
            opportunity_quality={
                "level": "strong",
                "main_buy_point_clear": True,
                "secondary_buy_point_clear": True,
                "core_overextended_count": 0,
                "portfolio_unresolved": False,
                "modules": [
                    {"key": "theme_clarity", "level": "strong"},
                    {"key": "portfolio_quality", "level": "strong"},
                ],
            },
            historical_validity={"level": "healthy"},
            portfolio=[
                {"slot": "main", "buy_point_status": "clear", "risk_tags": [], "risk_score": 18.0},
                {"slot": "secondary", "buy_point_status": "clear", "risk_tags": [], "risk_score": 20.0},
            ],
        )

        self.assertEqual(result["level"], "stand_aside")

    def test_build_action_upgrades_to_strong_go_only_when_core_profitability_is_strong(self) -> None:
        service = MomentumSecondaryDecisionService(screener_service=None)

        result = service._build_action(
            "standard",
            market_environment={
                "level": "strong",
                "modules": [{"key": "profitability", "level": "strong", "core_level": "strong"}],
            },
            opportunity_quality={
                "level": "strong",
                "main_buy_point_clear": True,
                "secondary_buy_point_clear": True,
                "core_overextended_count": 0,
                "portfolio_unresolved": False,
                "modules": [
                    {"key": "theme_clarity", "level": "strong"},
                    {"key": "portfolio_quality", "level": "strong"},
                ],
            },
            historical_validity={"level": "healthy"},
            portfolio=[
                {"slot": "main", "buy_point_status": "clear", "risk_tags": [], "risk_score": 18.0},
                {"slot": "secondary", "buy_point_status": "clear", "risk_tags": [], "risk_score": 20.0},
            ],
        )

        self.assertEqual(result["level"], "strong_go")


if __name__ == "__main__":
    unittest.main()
