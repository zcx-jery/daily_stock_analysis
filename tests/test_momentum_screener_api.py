# -*- coding: utf-8 -*-
"""API tests for momentum screener endpoint."""

import sys
import types
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.modules.setdefault(
    "fake_useragent",
    types.SimpleNamespace(UserAgent=lambda *args, **kwargs: types.SimpleNamespace(random="pytest-agent")),
)
multipart_module = types.ModuleType("multipart")
multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (value, {})
multipart_module.__version__ = "0.0-test"
sys.modules.setdefault("multipart", multipart_module)
sys.modules.setdefault("multipart.multipart", multipart_submodule)

from api.app import create_app
import src.auth as auth
from src.services.momentum_screener_service import MomentumScreenerService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from tests.test_momentum_screener_service import _FakeFetcher


class _IntegrationMomentumScreenerService(MomentumScreenerService):
    def __init__(self):
        super().__init__(fetcher=_FakeFetcher())


class _IntegrationMomentumSecondaryDecisionService(MomentumSecondaryDecisionService):
    def __init__(self, screener_service=None, stock_service=None, **kwargs):
        super().__init__(
            screener_service or MomentumScreenerService(fetcher=_FakeFetcher()),
            stock_service=stock_service,
            **kwargs,
        )


class _FakeStockService:
    def __init__(self, quotes=None):
        self.quotes = quotes or {
            "600001.SH": {
                "stock_code": "600001.SH",
                "current_price": 10.42,
                "open": 10.30,
                "change_percent": 1.8,
                "prev_close": 10.24,
                "update_time": "2026-04-11T09:45:00",
            },
            "600002.SH": {
                "stock_code": "600002.SH",
                "current_price": 18.66,
                "open": 18.51,
                "change_percent": 2.3,
                "prev_close": 18.24,
                "update_time": "2026-04-11T09:45:00",
            },
        }

    def get_realtime_quote(self, stock_code):
        return self.quotes.get(stock_code)


class _IntegrationMomentumIntradayDecisionService(MomentumSecondaryDecisionService):
    def __init__(self, screener_service=None, stock_service=None, **kwargs):
        super().__init__(
            screener_service or MomentumScreenerService(fetcher=_FakeFetcher()),
            stock_service or _FakeStockService(),
            **kwargs,
        )


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def disable_auth():
    auth._auth_enabled = None
    with patch("api.middlewares.auth.is_auth_enabled", return_value=False), \
         patch("src.auth.is_auth_enabled", return_value=False):
        yield
    auth._auth_enabled = None


def test_momentum_screener_endpoint_returns_response(client):
    fake_result = {
        "profile": "standard",
        "trade_date": "2026-04-10",
        "candidate_count": 1,
        "results": [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "测试龙头",
                "pct_chg": 9.8,
                "continuation_score": 86.5,
                "extension_score": 78.2,
                "risk_score": 15.0,
                "buyability_score": None,
                "final_score": 84.0,
                "rank_score": 73.4,
                "themes": ["电力设备"],
                "leader_level": "龙头",
                "top_reasons": ["强势确认", "量价结构"],
                "risk_tags": [],
                "score_breakdown": {
                    "strength_confirmation": {
                        "score": 17.0,
                        "max_score": 20.0,
                        "items": {"pct_chg_strength": 6},
                    }
                },
            }
        ],
    }

    with patch("api.deps.MomentumScreenerService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.screen.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "standard", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "standard"
    assert data["candidate_count"] == 1
    assert data["results"][0]["ts_code"] == "600001.SH"


def test_momentum_screener_endpoint_supports_aggressive_profile(client):
    fake_result = {
        "profile": "aggressive",
        "trade_date": "2026-04-10",
        "candidate_count": 1,
        "results": [
            {
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "测试龙头",
                "pct_chg": 9.8,
                "continuation_score": 88.1,
                "extension_score": 81.4,
                "risk_score": 6.7,
                "buyability_score": 72.5,
                "opportunity_tag": "分歧转一致",
                "entry_range_low": 10.34,
                "entry_range_high": 10.66,
                "final_score": 91.0,
                "rank_score": 79.6,
                "themes": ["电力设备"],
                "leader_level": "龙头",
                "top_reasons": ["强势确认", "买入可行性"],
                "risk_tags": ["upper_shadow"],
                "score_breakdown": {
                    "strength_confirmation": {
                        "score": 26.0,
                        "max_score": 30.0,
                        "items": {"limit_strength": 10},
                    },
                    "buyability": {
                        "score": 11.0,
                        "max_score": 15.0,
                        "items": {"amplitude_space": 6},
                    },
                },
            }
        ],
    }

    with patch("api.deps.MomentumScreenerService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.screen.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "aggressive"
    assert data["results"][0]["buyability_score"] == 72.5
    assert data["results"][0]["opportunity_tag"] == "分歧转一致"
    assert data["results"][0]["entry_range_low"] == 10.34
    assert data["results"][0]["entry_range_high"] == 10.66
    assert "buyability" in data["results"][0]["score_breakdown"]


def test_momentum_screener_endpoint_runs_real_standard_service_flow(client):
    with patch("api.deps.MomentumScreenerService", _IntegrationMomentumScreenerService):
        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "standard", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "standard"
    assert data["trade_date"] == "2026-04-10"
    assert data["candidate_count"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["ts_code"] == "600001.SH"
    assert data["results"][0]["themes"][0] == "电力设备"
    assert "strength_confirmation" in data["results"][0]["score_breakdown"]
    assert hasattr(client.app.state, "momentum_screener_service")


def test_momentum_screener_endpoint_runs_real_aggressive_service_flow(client):
    with patch("api.deps.MomentumScreenerService", _IntegrationMomentumScreenerService):
        response = client.post(
            "/api/v1/stocks/screener/momentum",
            json={"profile": "aggressive", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "aggressive"
    assert data["trade_date"] == "2026-04-10"
    assert data["candidate_count"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["buyability_score"] is not None
    assert data["results"][0]["opportunity_tag"] is not None
    assert data["results"][0]["entry_range_low"] is not None
    assert data["results"][0]["entry_range_high"] is not None
    assert "buyability" in data["results"][0]["score_breakdown"]


def test_momentum_secondary_decision_endpoint_returns_response(client):
    fake_result = {
        "screening": {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 2,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "测试龙头",
                    "pct_chg": 9.8,
                    "continuation_score": 88.1,
                    "extension_score": 81.4,
                    "risk_score": 6.7,
                    "buyability_score": 72.5,
                    "opportunity_tag": "分歧转一致",
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "final_score": 91.0,
                    "rank_score": 79.6,
                    "themes": ["电力设备"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认", "买入可行性"],
                    "risk_tags": ["upper_shadow"],
                    "score_breakdown": {},
                }
            ],
        },
        "decision": {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "action": {
                "level": "normal_go",
                "label": "可正常出手",
                "reason": "主线清晰且已有两只票具备可跟踪买点。",
                "source_profile": "aggressive",
            },
            "strategy_health": {
                "status": "healthy",
                "label": "正常",
                "reason": "20 日可用性与 60 日结构可信度同时健康，允许维持完整强推荐。",
                "recommendation_cap": "full",
                "can_full_recommend": True,
                "short_window": {
                    "window": "short_20d",
                    "window_label": "20 日当前可用性",
                    "status": "healthy",
                    "status_label": "健康",
                    "score": 82.0,
                    "threshold": 68.0,
                    "sample_count": 20,
                    "success_count": 14,
                    "success_rate": 70.0,
                    "avg_profit_window_pct": 2.6,
                    "avg_max_drawdown_pct": 2.1,
                    "avg_selected_count": 2.1,
                    "summary": "20 日窗口当前可用性已达健康阈值，可继续支撑当前判断。",
                },
                "long_window": {
                    "window": "long_60d",
                    "window_label": "60 日结构可信度",
                    "status": "healthy",
                    "status_label": "健康",
                    "score": 78.0,
                    "threshold": 64.0,
                    "sample_count": 60,
                    "success_count": 38,
                    "success_rate": 63.3,
                    "avg_profit_window_pct": 2.2,
                    "avg_max_drawdown_pct": 2.8,
                    "avg_selected_count": 2.0,
                    "summary": "60 日窗口结构可信度已达健康阈值，可继续支撑当前判断。",
                },
                "blockers": [],
                "recovery_conditions": [],
            },
            "themes": [
                {
                    "name": "电力设备",
                    "score": 76.2,
                    "strength_label": "主线清晰",
                    "candidate_count": 2,
                    "clear_buy_point_count": 1,
                    "leader_count": 1,
                    "summary": "电力设备当前聚集 2 只强势候选。",
                    "representatives": [
                        {
                            "rank": 1,
                            "ts_code": "600001.SH",
                            "name": "测试龙头",
                            "role": "龙头核心",
                            "buy_point_label": "买点清晰",
                            "rank_score": 79.6,
                        }
                    ],
                }
            ],
            "portfolio": [
                {
                    "slot": "main",
                    "slot_label": "主仓",
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "测试龙头",
                    "theme": "电力设备",
                    "role": "龙头核心",
                    "score": 89.2,
                    "rank_score": 79.6,
                    "risk_score": 6.7,
                    "buy_point_status": "clear",
                    "buy_point_label": "买点清晰",
                    "suggested_action": "ready",
                    "suggested_action_label": "可准备执行",
                    "primary_reason": "强势确认",
                    "role_reason": "它的买点准备度最高。",
                    "execution_plan": "优先关注 10.34 - 10.66 区间确认。",
                    "entry_hint": "优先关注 10.34 - 10.66 区间确认。",
                    "opportunity_tag": "分歧转一致",
                }
            ],
            "excluded_candidates": [],
            "action_checklist": {
                "enabled": True,
                "reason": "当前出手级别为“可正常出手”，系统会补充明日行动清单。",
                "steps": [
                    {
                        "phase": "pre_open",
                        "phase_label": "开盘前",
                        "objective": "先确认默认组合今天是否还值得继续盯。",
                        "focus_items": ["主仓：测试龙头（电力设备 / 龙头核心）"],
                        "tasks": ["先看竞价强弱。"],
                        "expected_outcome": "明确开盘后优先盯主仓。",
                    }
                ],
            },
            "evidence": {
                "theme_validation": ["电力设备主线评分 76.2。"],
                "today_reasoning": ["本次二次决策基于 aggressive 候选引擎重新收口组合。"],
            },
        },
    }

    with patch("api.deps.MomentumSecondaryDecisionService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.build.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum/decision",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screening"]["profile"] == "aggressive"
    assert data["decision"]["action"]["level"] == "normal_go"
    assert data["decision"]["strategy_health"]["status"] == "healthy"
    assert data["decision"]["portfolio"][0]["slot"] == "main"
    assert data["decision"]["themes"][0]["name"] == "电力设备"
    assert data["decision"]["action_checklist"]["enabled"] is True
    assert data["decision"]["action_checklist"]["steps"][0]["phase"] == "pre_open"


def test_momentum_secondary_decision_endpoint_runs_real_service_flow(client):
    with patch("api.deps.MomentumSecondaryDecisionService", _IntegrationMomentumSecondaryDecisionService):
        response = client.post(
            "/api/v1/stocks/screener/momentum/decision",
            json={"profile": "aggressive", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screening"]["profile"] == "aggressive"
    assert data["screening"]["candidate_count"] == 2
    assert data["decision"]["profile"] == "aggressive"
    assert data["decision"]["trade_date"] == "2026-04-10"
    assert data["decision"]["action"]["level"] in {
        "strong_go",
        "normal_go",
        "cautious_go",
        "observe_only",
        "stand_aside",
    }
    assert data["decision"]["themes"]
    assert data["decision"]["portfolio"]
    assert "strategy_health" in data["decision"]
    assert "action_checklist" in data["decision"]


def test_momentum_secondary_decision_endpoint_can_wait_for_strategy_health(client):
    with patch("api.deps.MomentumSecondaryDecisionService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.build.return_value = {
            "screening": {"profile": "aggressive", "trade_date": "2026-04-10", "candidate_count": 0, "results": []},
            "decision": {
                "profile": "aggressive",
                "trade_date": "2026-04-10",
                "action": {
                    "level": "observe_only",
                    "label": "仅观察",
                    "reason": "等待真实历史验证结果。",
                    "source_profile": "aggressive",
                },
                "strategy_health": {
                    "status": "partial_healthy",
                    "label": "谨慎",
                    "reason": "正在等待真实 20/60 结果。",
                    "recommendation_cap": "limited",
                    "can_full_recommend": False,
                    "short_window": {
                        "window": "short_20d",
                        "window_label": "20 日当前可用性",
                        "status": "healthy",
                        "status_label": "健康",
                        "score": 70.0,
                        "threshold": 68.0,
                        "sample_count": 20,
                        "success_count": 14,
                        "success_rate": 70.0,
                        "avg_profit_window_pct": 2.3,
                        "avg_max_drawdown_pct": 2.1,
                        "avg_selected_count": 1.8,
                        "summary": "20 日窗口已健康。",
                    },
                    "long_window": {
                        "window": "long_60d",
                        "window_label": "60 日结构可信度",
                        "status": "recovering",
                        "status_label": "恢复中",
                        "score": 61.0,
                        "threshold": 64.0,
                        "sample_count": 60,
                        "success_count": 34,
                        "success_rate": 56.7,
                        "avg_profit_window_pct": 1.9,
                        "avg_max_drawdown_pct": 2.8,
                        "avg_selected_count": 1.5,
                        "summary": "60 日窗口仍在恢复。",
                    },
                    "blockers": [],
                    "recovery_conditions": [],
                    "data_source": "historical",
                    "is_warming": False,
                },
                "themes": [],
                "portfolio": [],
                "excluded_candidates": [],
                "action_checklist": {"enabled": False, "reason": "仅观察", "steps": []},
                "evidence": {"theme_validation": [], "today_reasoning": []},
            },
        }

        response = client.post(
            "/api/v1/stocks/screener/momentum/decision?wait_for_strategy_health=true",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    assert mock_service.build.call_args.kwargs["wait_for_strategy_health"] is True


def test_momentum_intraday_signal_endpoint_returns_response(client):
    fake_result = {
        "screening": {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "candidate_count": 1,
            "results": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "测试龙头",
                    "pct_chg": 9.8,
                    "continuation_score": 88.1,
                    "extension_score": 81.4,
                    "risk_score": 6.7,
                    "buyability_score": 72.5,
                    "opportunity_tag": "分歧转一致",
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "final_score": 91.0,
                    "rank_score": 79.6,
                    "themes": ["电力设备"],
                    "leader_level": "龙头",
                    "top_reasons": ["强势确认", "买入可行性"],
                    "risk_tags": ["upper_shadow"],
                    "score_breakdown": {},
                }
            ],
        },
        "decision": {
            "profile": "aggressive",
            "trade_date": "2026-04-10",
            "action": {
                "level": "normal_go",
                "label": "可正常出手",
                "reason": "主线清晰且已有两只票具备可跟踪买点。",
                "source_profile": "aggressive",
            },
            "strategy_health": {
                "status": "healthy",
                "label": "正常",
                "reason": "20 日可用性与 60 日结构可信度同时健康，允许维持完整强推荐。",
                "recommendation_cap": "full",
                "can_full_recommend": True,
                "short_window": {
                    "window": "short_20d",
                    "window_label": "20 日当前可用性",
                    "status": "healthy",
                    "status_label": "健康",
                    "score": 82.0,
                    "threshold": 68.0,
                    "sample_count": 20,
                    "success_count": 14,
                    "success_rate": 70.0,
                    "avg_profit_window_pct": 2.6,
                    "avg_max_drawdown_pct": 2.1,
                    "avg_selected_count": 2.1,
                    "summary": "20 日窗口当前可用性已达健康阈值，可继续支撑当前判断。",
                },
                "long_window": {
                    "window": "long_60d",
                    "window_label": "60 日结构可信度",
                    "status": "healthy",
                    "status_label": "健康",
                    "score": 78.0,
                    "threshold": 64.0,
                    "sample_count": 60,
                    "success_count": 38,
                    "success_rate": 63.3,
                    "avg_profit_window_pct": 2.2,
                    "avg_max_drawdown_pct": 2.8,
                    "avg_selected_count": 2.0,
                    "summary": "60 日窗口结构可信度已达健康阈值，可继续支撑当前判断。",
                },
                "blockers": [],
                "recovery_conditions": [],
            },
            "themes": [],
            "portfolio": [
                {
                    "slot": "main",
                    "slot_label": "主仓",
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "测试龙头",
                    "theme": "电力设备",
                    "role": "龙头核心",
                    "score": 89.2,
                    "rank_score": 79.6,
                    "risk_score": 6.7,
                    "buy_point_status": "clear",
                    "buy_point_label": "买点清晰",
                    "suggested_action": "ready",
                    "suggested_action_label": "可准备执行",
                    "primary_reason": "强势确认",
                    "role_reason": "它的买点准备度最高。",
                    "execution_plan": "优先关注 10.34 - 10.66 区间确认。",
                    "entry_hint": "优先关注 10.34 - 10.66 区间确认。",
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "opportunity_tag": "分歧转一致",
                }
            ],
            "excluded_candidates": [],
            "action_checklist": {
                "enabled": True,
                "reason": "当前出手级别为“可正常出手”，系统会补充明日行动清单。",
                "steps": [
                    {
                        "phase": "pre_open",
                        "phase_label": "开盘前",
                        "objective": "先确认默认组合今天是否还值得继续盯。",
                        "focus_items": ["主仓：测试龙头（电力设备 / 龙头核心）"],
                        "tasks": ["先看竞价强弱。"],
                        "expected_outcome": "明确开盘后优先盯主仓。",
                    }
                ],
            },
            "evidence": {
                "theme_validation": ["电力设备主线评分 76.2。"],
                "today_reasoning": ["本次二次决策基于 aggressive 候选引擎重新收口组合。"],
            },
        },
        "intraday_signal": {
            "market_phase": "first_60m",
            "market_phase_label": "开盘后 60 分钟内",
            "confidence_level": "medium",
            "confidence_label": "中等置信度",
            "can_emit_buy_signal": False,
            "status": "watching",
            "status_label": "继续观察",
            "reason": "盘中信号仍在观察阶段，继续等待更明确的买点触发。",
            "watch_items": ["主仓：等待价格回到 10.34 - 10.66 的确认区间。"],
            "final_recommendation": "watch",
            "final_recommendation_label": "继续观察",
            "closing_note": "固定顺序仍按主仓 测试龙头跟踪，继续等待更清晰的买点触发后再收口。",
            "updated_at": "2026-04-11T09:50:00",
            "focus_order": ["优先关注：主仓 测试龙头（继续等待触发）"],
            "portfolio_items": [
                {
                    "slot": "main",
                    "slot_label": "主仓",
                    "ts_code": "600001.SH",
                    "name": "测试龙头",
                    "theme": "电力设备",
                    "role": "龙头核心",
                    "status": "watching",
                    "status_label": "继续等待",
                    "reason": "买点尚未完全触发，继续等待更清晰的承接确认。",
                    "quote_available": True,
                    "signal_triggered": False,
                    "do_not_chase": False,
                    "current_price": 10.18,
                    "change_percent": 1.6,
                    "open_price": 10.1,
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "price_vs_open_pct": 0.79,
                    "price_vs_entry_high_pct": -4.5,
                    "missing_conditions": ["等待价格回到 10.34 - 10.66 的确认区间。"],
                    "update_time": "2026-04-11T09:50:00",
                }
            ],
        },
    }

    with patch("api.deps.MomentumSecondaryDecisionService") as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.build_intraday.return_value = fake_result

        response = client.post(
            "/api/v1/stocks/screener/momentum/decision/intraday",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screening"]["profile"] == "aggressive"
    assert data["intraday_signal"]["status"] == "watching"
    assert data["decision"]["strategy_health"]["status"] == "healthy"
    assert data["intraday_signal"]["closing_note"]
    assert data["intraday_signal"]["focus_order"]
    assert data["intraday_signal"]["portfolio_items"][0]["slot"] == "main"


def test_momentum_intraday_signal_endpoint_runs_real_service_flow(client):
    with patch("api.deps.MomentumSecondaryDecisionService", _IntegrationMomentumIntradayDecisionService):
        response = client.post(
            "/api/v1/stocks/screener/momentum/decision/intraday",
            json={"profile": "aggressive", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screening"]["profile"] == "aggressive"
    assert data["decision"]["portfolio"]
    assert "strategy_health" in data["decision"]
    assert data["intraday_signal"]["market_phase"] in {
        "pre_open",
        "call_auction",
        "first_30m",
        "first_60m",
        "after_first_hour",
        "midday_break",
        "afternoon",
        "closed",
    }
    assert data["intraday_signal"]["portfolio_items"]
    assert "closing_note" in data["intraday_signal"]
    assert "focus_order" in data["intraday_signal"]


def test_health_endpoint_exposes_momentum_sector_cache_stats(client):
    with patch.object(
        MomentumScreenerService,
        "get_sector_cache_stats",
        return_value={"hit": 5, "miss": 2},
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["diagnostics"]["momentum_sector_cache"] == {"hit": 5, "miss": 2}
