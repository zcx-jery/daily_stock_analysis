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
from api.deps import get_momentum_backtest_service, get_momentum_secondary_decision_service
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



class _FakeMomentumScreenerAICommentaryService:
    def __init__(self):
        pass

    def load_session(self, request):
        return {
            "session_id": "screener_ai:candidate:test-session",
            "review_type": request.review_type,
            "review_type_label": "Candidate AI Review",
            "session_title": "Candidate AI Review - Test Leader",
            "messages": [
                {
                    "id": "1",
                    "role": "assistant",
                    "content": "## Rule Conclusion\n- Current candidate stays in watch mode.",
                    "created_at": "2026-04-15T09:31:00",
                    "context_meta": {
                        "review_type": request.review_type,
                        "review_type_label": "Candidate AI Review",
                        "review_target": "Test Leader (600001.SH)",
                        "trade_date": request.screening.trade_date,
                        "profile": request.screening.profile,
                        "rule_conclusion": "Main slot / buy point clear / keep watching",
                        "rule_guardrail": "Observe only / do not chase",
                        "market_data_as_of": request.screening.trade_date,
                        "tools_used": [],
                    },
                    "suggested_questions": ["What is the biggest risk for this name?"],
                }
            ],
        }

    def stream_review(self, request, progress_callback=None):
        if progress_callback:
            progress_callback({"type": "stage", "stage": "context", "message": "Loaded screener context"})
            progress_callback({"type": "tool_start", "tool": "search_stock_news", "display_name": "Stock News"})
            progress_callback({"type": "tool_done", "tool": "search_stock_news", "display_name": "Stock News", "success": True, "duration": 0.12})
        return {
            "session_id": "screener_ai:candidate:test-session",
            "success": True,
            "content": "## Rule Conclusion\n- Continue to observe this setup.",
            "context_meta": {
                "review_type": request.review_type,
                "review_type_label": "Candidate AI Review",
                "review_target": "Test Leader (600001.SH)",
                "trade_date": request.screening.trade_date,
                "profile": request.screening.profile,
                "rule_conclusion": "Main slot / buy point clear / keep watching",
                "rule_guardrail": "Observe only / do not chase",
                "market_data_as_of": request.screening.trade_date,
                "tools_used": ["Stock News"],
            },
            "suggested_questions": ["When should I fully give up tomorrow?"],
        }




class _FakeMomentumBacktestService:
    def __init__(self):
        self.run = {
            "run_id": "momentum_bt_test_001",
            "status": "completed",
            "profile": "standard",
            "engine_version": "v1",
            "entry_baseline_version": "v1_4_2_2",
            "market_scope_version": "v1_a_share_main_chinext_star",
            "top_n": 30,
            "start_trade_date": "2026-04-08",
            "end_trade_date": "2026-04-10",
            "total_trade_dates": 3,
            "processed_trade_dates": 3,
            "failed_trade_dates": 0,
            "current_trade_date": "2026-04-10",
            "current_stage_key": "completed",
            "current_stage_label": "任务已完成",
            "heartbeat_at": "2026-04-17T10:01:00",
            "started_at": "2026-04-17T10:00:00",
            "finished_at": "2026-04-17T10:01:00",
            "cancel_requested": False,
            "summary": {
                "completed_trade_dates": 3,
                "action_breakdown": {"normal_go": 2, "cautious_go": 1},
                "market_environment_breakdown": {"strong": 2, "general": 1},
                "opportunity_quality_breakdown": {"strong": 2, "general": 1},
                "historical_validity_breakdown": {"healthy": 2, "general": 1},
                "avg_candidate_count": 12.0,
                "avg_selected_count": 2.0,
                "avg_buy_ready_count": 1.0,
                "candidate_top10_buy_trigger_rate": 75.0,
                "candidate_top10_positive_t2_rate": 70.0,
                "candidate_top10_avg_t2_profit_window_pct": 4.1,
                "candidate_top10_avg_t2_max_drawdown_pct": 2.4,
                "decision_top3_buy_trigger_rate": 66.67,
                "decision_top3_positive_t1_rate": 66.67,
                "decision_top3_positive_t2_rate": 66.67,
                "decision_top3_avg_t1_profit_window_pct": 2.3,
                "decision_top3_avg_t2_profit_window_pct": 3.8,
                "decision_top3_avg_t2_max_drawdown_pct": 1.9,
                "benchmark_comparison": [
                    {
                        "key": "official_top3",
                        "label": "官方 Top3",
                        "sample_count": 3,
                        "trigger_rate_pct": 66.67,
                        "positive_t2_rate_pct": 66.67,
                        "avg_t2_profit_window_pct": 3.8,
                        "avg_t2_max_drawdown_pct": 1.9,
                        "alpha_vs_official_top3_pct": 0.0,
                        "alpha_vs_candidate_top10_pct": -0.3,
                    }
                ],
                "layer_diagnostics": [
                    {
                        "key": "candidate_pool",
                        "label": "候选池",
                        "level": "general",
                        "score": 62.0,
                        "summary": "候选池整体质量中等偏上。",
                        "metrics": {"positive_t2_rate_pct": 70.0},
                    }
                ],
                "gate_module_breakdown": [
                    {
                        "key": "buy_point_clarity",
                        "label": "买点清晰度",
                        "group_key": "opportunity_quality",
                        "group_label": "机会质量",
                        "sample_days": 3,
                        "strong_days": 0,
                        "medium_days": 1,
                        "weak_days": 2,
                        "blocker_days": 2,
                        "restricted_days": 1,
                        "avg_score": 38.0,
                        "weak_day_candidate_positive_t2_rate_pct": 66.67,
                        "weak_day_decision_positive_t2_rate_pct": 50.0,
                        "weak_day_candidate_avg_t2_profit_window_pct": 3.9,
                        "weak_day_decision_avg_t2_profit_window_pct": 2.6,
                        "strong_day_decision_avg_t2_profit_window_pct": None,
                        "summary": "弱项 2 天，其中限制出手 1 天；弱项日默认组合 T+2 利润窗口均值 2.60%。",
                    }
                ],
                "regime_breakdown": [
                    {
                        "level": "strong",
                        "label": "强市",
                        "trade_days": 2,
                        "decision_positive_t2_rate_pct": 75.0,
                        "decision_avg_t2_profit_window_pct": 4.2,
                        "decision_avg_t2_max_drawdown_pct": 1.6,
                        "missed_opportunity_rate_pct": 0.0,
                        "allowed_trade_precision_pct": 100.0,
                        "stand_aside_rate_pct": 0.0,
                    }
                ],
            },
            "error_message": None,
            "created_at": "2026-04-17T10:00:00",
            "updated_at": "2026-04-17T10:01:00",
        }
        self.running_run = {
            **self.run,
            "run_id": "momentum_bt_running",
            "status": "running",
            "processed_trade_dates": 1,
            "summary": None,
            "current_trade_date": "2026-04-08",
            "current_stage_key": "candidate_pool",
            "current_stage_label": "候选池计算中",
            "heartbeat_at": "2026-04-17T09:05:00",
            "started_at": "2026-04-17T09:00:00",
            "finished_at": None,
            "created_at": "2026-04-17T09:00:00",
            "updated_at": "2026-04-17T09:05:00",
        }
        self.queued_run = {
            **self.run,
            "run_id": "momentum_bt_queued",
            "status": "queued",
            "processed_trade_dates": 0,
            "summary": None,
            "current_trade_date": None,
            "current_stage_key": "queued",
            "current_stage_label": "等待后台调度",
            "heartbeat_at": "2026-04-17T09:06:00",
            "started_at": None,
            "finished_at": None,
            "created_at": "2026-04-17T09:06:00",
            "updated_at": "2026-04-17T09:06:00",
        }
        self.cancelled_run = {
            **self.run,
            "run_id": "momentum_bt_cancelled",
            "status": "cancelled",
            "processed_trade_dates": 1,
            "summary": self.run["summary"],
            "current_trade_date": "2026-04-09",
            "current_stage_key": "cancelled",
            "current_stage_label": "任务已取消",
            "heartbeat_at": "2026-04-17T08:05:00",
            "started_at": "2026-04-17T08:00:00",
            "finished_at": "2026-04-17T08:05:00",
            "created_at": "2026-04-17T08:00:00",
            "updated_at": "2026-04-17T08:05:00",
        }

    def create_run_async(self, **kwargs):
        return {
            "created_new": True,
            "message": "已创建回测任务，正在后台计算",
            "run": self.running_run,
        }

    def list_runs(self, *, limit=10, profile=None):
        return {
            "current_running": self.running_run,
            "queued": {
                "total": 1,
                "items": [self.queued_run],
            },
            "history": {
                "total": 2,
                "limit": limit,
                "items": [self.run, self.cancelled_run][:limit],
            },
            "refreshed_at": "2026-04-17T10:02:00",
        }

    def get_run(self, run_id):
        if run_id == self.run["run_id"]:
            return self.run
        if run_id == self.running_run["run_id"]:
            return self.running_run
        if run_id == self.queued_run["run_id"]:
            return self.queued_run
        if run_id == self.cancelled_run["run_id"]:
            return self.cancelled_run
        raise ValueError(f"Backtest run not found: {run_id}")

    def cancel_run(self, run_id):
        if run_id != self.running_run["run_id"]:
            raise ValueError("Only running tasks can be cancelled")
        self.running_run = {
            **self.running_run,
            "status": "cancelled",
            "current_stage_key": "cancelled",
            "current_stage_label": "任务已取消",
            "cancel_requested": False,
        }
        return self.running_run

    def delete_run(self, run_id):
        if run_id == self.running_run["run_id"]:
            raise ValueError("Running tasks must be cancelled before deletion")
        return {
            "run_id": run_id,
            "deleted": True,
            "message": "任务已删除",
        }

    def get_summary(self, run_id):
        if run_id != self.run["run_id"]:
            raise ValueError(f"Backtest run not found: {run_id}")
        return {
            "run_id": run_id,
            "profile": self.run["profile"],
            "engine_version": self.run["engine_version"],
            "summary": self.run["summary"],
        }

    def list_daily(self, run_id, **kwargs):
        if run_id != self.run["run_id"]:
            raise ValueError(f"Backtest run not found: {run_id}")
        return {
            "run_id": run_id,
            "total": 1,
            "page": kwargs.get("page", 1),
            "page_size": kwargs.get("page_size", 20),
            "has_more": False,
            "items": [
                {
                    "trade_date": "2026-04-10",
                    "action_level": "normal_go",
                    "action_label": "Normal Go",
                    "recommendation_cap": "full",
                    "action_checklist_mode": "full",
                    "market_environment_level": "strong",
                    "opportunity_quality_level": "strong",
                    "historical_validity_level": "healthy",
                    "candidate_count": 12,
                    "result_count": 12,
                    "selected_count": 2,
                    "buy_ready_count": 1,
                    "main_ts_code": "600001.SH",
                    "secondary_ts_code": "600002.SH",
                    "watch_ts_code": None,
                }
            ],
        }

    def get_daily_detail(self, run_id, trade_date):
        if run_id != self.run["run_id"] or trade_date != "2026-04-10":
            raise ValueError(f"Backtest trade date not found: {trade_date}")
        return {
            "run_id": run_id,
            "trade_date": "2026-04-10",
            "daily_context": self.list_daily(run_id)["items"][0],
            "candidate_top10": [
                {
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "Test Leader",
                    "theme": "Power Equipment",
                    "role": "leader",
                    "market_segment": "main_board",
                    "rank_score": 73.4,
                    "final_score": 84.0,
                    "continuation_score": 86.5,
                    "extension_score": 78.2,
                    "risk_score": 15.0,
                    "buyability_score": None,
                    "outcome": {
                        "view_scope": "candidate_top10",
                        "slot": None,
                        "ts_code": "600001.SH",
                        "name": "Test Leader",
                        "buy_triggered": True,
                        "reference_entry_price": 10.2,
                        "trigger_price": 10.34,
                        "trigger_trade_date": "2026-04-11",
                        "t1_trade_date": "2026-04-11",
                        "t1_close_return_pct": 3.4,
                        "t1_profit_window_pct": 5.7,
                        "t1_max_drawdown_pct": 1.2,
                        "t2_trade_date": "2026-04-14",
                        "t2_close_return_pct": 4.8,
                        "t2_profit_window_pct": 7.3,
                        "t2_max_drawdown_pct": 1.5,
                        "real_strength_label": "strong",
                    },
                }
            ],
            "decision_top3": [
                {
                    "slot": "main",
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "Test Leader",
                    "theme": "Power Equipment",
                    "role": "Leader Core",
                    "decision_score": 89.2,
                    "rank_score": 73.4,
                    "risk_score": 15.0,
                    "buy_point_status": "clear",
                    "suggested_action": "ready",
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "opportunity_tag": None,
                    "outcome": {
                        "view_scope": "decision_top3",
                        "slot": "main",
                        "ts_code": "600001.SH",
                        "name": "Test Leader",
                        "buy_triggered": True,
                        "reference_entry_price": 10.2,
                        "trigger_price": 10.34,
                        "trigger_trade_date": "2026-04-11",
                        "t1_trade_date": "2026-04-11",
                        "t1_close_return_pct": 3.4,
                        "t1_profit_window_pct": 5.7,
                        "t1_max_drawdown_pct": 1.2,
                        "t2_trade_date": "2026-04-14",
                        "t2_close_return_pct": 4.8,
                        "t2_profit_window_pct": 7.3,
                        "t2_max_drawdown_pct": 1.5,
                        "real_strength_label": "strong",
                    },
                }
            ],
            "slot_view": [
                {
                    "slot": "main",
                    "rank": 1,
                    "ts_code": "600001.SH",
                    "name": "Test Leader",
                    "theme": "Power Equipment",
                    "role": "Leader Core",
                    "decision_score": 89.2,
                    "rank_score": 73.4,
                    "risk_score": 15.0,
                    "buy_point_status": "clear",
                    "suggested_action": "ready",
                    "entry_range_low": 10.34,
                    "entry_range_high": 10.66,
                    "opportunity_tag": None,
                    "outcome": {
                        "view_scope": "decision_top3",
                        "slot": "main",
                        "ts_code": "600001.SH",
                        "name": "Test Leader",
                        "buy_triggered": True,
                        "reference_entry_price": 10.2,
                        "trigger_price": 10.34,
                        "trigger_trade_date": "2026-04-11",
                        "t1_trade_date": "2026-04-11",
                        "t1_close_return_pct": 3.4,
                        "t1_profit_window_pct": 5.7,
                        "t1_max_drawdown_pct": 1.2,
                        "t2_trade_date": "2026-04-14",
                        "t2_close_return_pct": 4.8,
                        "t2_profit_window_pct": 7.3,
                        "t2_max_drawdown_pct": 1.5,
                        "real_strength_label": "strong",
                    },
                }
            ],
            "outcomes": {
                "candidate_top10": {
                    "metrics": {
                        "sample_count": 1,
                        "trigger_rate_pct": 100.0,
                        "positive_t1_rate_pct": 100.0,
                        "positive_t2_rate_pct": 100.0,
                        "avg_t1_profit_window_pct": 5.7,
                        "avg_t2_profit_window_pct": 7.3,
                        "avg_t2_max_drawdown_pct": 1.5,
                        "best_t2_profit_window_pct": 7.3,
                    },
                    "items": [],
                },
                "decision_top3": {
                    "metrics": {
                        "sample_count": 1,
                        "trigger_rate_pct": 100.0,
                        "positive_t1_rate_pct": 100.0,
                        "positive_t2_rate_pct": 100.0,
                        "avg_t1_profit_window_pct": 5.7,
                        "avg_t2_profit_window_pct": 7.3,
                        "avg_t2_max_drawdown_pct": 1.5,
                        "best_t2_profit_window_pct": 7.3,
                    },
                    "items": [],
                },
            },
            "diagnosis": {
                "summary_lines": ["????????????????"],
                "candidate_metrics": {
                    "sample_count": 1,
                    "trigger_rate_pct": 100.0,
                    "positive_t1_rate_pct": 100.0,
                    "positive_t2_rate_pct": 100.0,
                    "avg_t1_profit_window_pct": 5.7,
                    "avg_t2_profit_window_pct": 7.3,
                    "avg_t2_max_drawdown_pct": 1.5,
                    "best_t2_profit_window_pct": 7.3,
                },
                "decision_metrics": {
                    "sample_count": 1,
                    "trigger_rate_pct": 100.0,
                    "positive_t1_rate_pct": 100.0,
                    "positive_t2_rate_pct": 100.0,
                    "avg_t1_profit_window_pct": 5.7,
                    "avg_t2_profit_window_pct": 7.3,
                    "avg_t2_max_drawdown_pct": 1.5,
                    "best_t2_profit_window_pct": 7.3,
                },
                "gate_snapshot": [
                    {
                        "key": "market_environment",
                        "label": "市场环境",
                        "level": "medium",
                        "level_label": "中",
                        "score": 52.0,
                        "reason": "指数趋势中、赚钱效应中、情绪偏弱。",
                        "modules": [
                            {
                                "key": "sentiment",
                                "label": "市场情绪",
                                "group_key": "market_environment",
                                "group_label": "市场环境",
                                "level": "weak",
                                "level_label": "弱",
                                "score": 28.0,
                                "summary": "默认组合可执行个股偏少。",
                            }
                        ],
                    },
                    {
                        "key": "opportunity_quality",
                        "label": "机会质量",
                        "level": "weak",
                        "level_label": "弱",
                        "score": 43.3,
                        "reason": "买点清晰度和组合质量拖后腿。",
                        "modules": [
                            {
                                "key": "buy_point_clarity",
                                "label": "买点清晰度",
                                "group_key": "opportunity_quality",
                                "group_label": "机会质量",
                                "level": "weak",
                                "level_label": "弱",
                                "score": 24.0,
                                "summary": "主仓未形成清晰买点。",
                            }
                        ],
                    },
                    {
                        "key": "historical_validity",
                        "label": "20日进攻许可",
                        "level": "general",
                        "level_label": "一般",
                        "score": 51.0,
                        "reason": "当前只有一侧窗口健康。",
                        "modules": [],
                    },
                ],
                "gate_blockers": [
                    {
                        "key": "sentiment",
                        "label": "市场情绪",
                        "group_key": "market_environment",
                        "group_label": "市场环境",
                        "level": "weak",
                        "level_label": "弱",
                        "score": 28.0,
                        "summary": "默认组合可执行个股偏少。",
                    },
                    {
                        "key": "buy_point_clarity",
                        "label": "买点清晰度",
                        "group_key": "opportunity_quality",
                        "group_label": "机会质量",
                        "level": "weak",
                        "level_label": "弱",
                        "score": 24.0,
                        "summary": "主仓未形成清晰买点。",
                    },
                ],
                "issues": [],
            },
        }

    def get_issues(self, run_id):
        if run_id != self.run["run_id"]:
            raise ValueError(f"Backtest run not found: {run_id}")
        return {
            "run_id": run_id,
            "total_issues": 1,
            "severity_breakdown": {"critical": 0, "warning": 1, "info": 0},
            "issue_key_breakdown": {"trigger_efficiency_low": 1},
            "items": [
                {
                    "issue_key": "trigger_efficiency_low",
                    "severity": "warning",
                    "title": "????????",
                    "summary": "???????????????",
                    "affected_codes": ["600001.SH"],
                    "metrics": {"decision_trigger_rate_pct": 33.33},
                    "trade_date": "2026-04-10",
                    "action_level": "normal_go",
                    "action_label": "Normal Go",
                }
            ],
        }


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


def _build_fake_screening_result(profile="standard", candidate_count=1):
    result = {
        "rank": 1,
        "ts_code": "600001.SH",
        "name": "Test Leader",
        "market_segment": "main_board",
        "market_segment_label": "Main Board",
        "pct_chg": 9.8,
        "continuation_score": 88.0 if profile == "aggressive" else 86.5,
        "extension_score": 81.4 if profile == "aggressive" else 78.2,
        "risk_score": 6.7 if profile == "aggressive" else 15.0,
        "buyability_score": 72.5 if profile == "aggressive" else None,
        "opportunity_tag": "Breakout Setup" if profile == "aggressive" else None,
        "entry_range_low": 10.34 if profile == "aggressive" else None,
        "entry_range_high": 10.66 if profile == "aggressive" else None,
        "final_score": 91.0 if profile == "aggressive" else 84.0,
        "rank_score": 79.6 if profile == "aggressive" else 73.4,
        "themes": ["Power Equipment"],
        "leader_level": "leader",
        "top_reasons": ["Strength Confirmed", "Volume Structure"],
        "risk_tags": ["upper_shadow"] if profile == "aggressive" else [],
        "score_breakdown": {
            "strength_confirmation": {
                "score": 26.0 if profile == "aggressive" else 17.0,
                "max_score": 30.0 if profile == "aggressive" else 20.0,
                "items": {"pct_chg_strength": 6},
            }
        },
    }
    if profile == "aggressive":
        result["score_breakdown"]["buyability"] = {
            "score": 11.0,
            "max_score": 15.0,
            "items": {"amplitude_space": 6},
        }
    return {
        "profile": profile,
        "trade_date": "2026-04-10",
        "requested_trade_date": None,
        "trade_date_note": None,
        "entry_baseline_version": "v1_4_2_2",
        "market_scope_version": "v1_a_share_main_chinext_star",
        "candidate_count": candidate_count,
        "results": [result],
    }


def _build_fake_gate_module(key, label, level, score, summary):
    return {
        "key": key,
        "label": label,
        "level": level,
        "score": score,
        "summary": summary,
    }


def _build_fake_strategy_health(
    *,
    status="healthy",
    label="Normal",
    reason="Both 20d and 60d windows remain supportive.",
    recommendation_cap="full",
    can_full_recommend=True,
    data_source="historical",
    is_warming=False,
):
    return {
        "status": status,
        "label": label,
        "reason": reason,
        "recommendation_cap": recommendation_cap,
        "can_full_recommend": can_full_recommend,
        "short_window": {
            "window": "short_20d",
            "window_label": "20d current usability",
            "status": "healthy",
            "status_label": "Healthy",
            "score": 82.0,
            "threshold": 68.0,
            "sample_count": 20,
            "success_count": 14,
            "success_rate": 70.0,
            "avg_profit_window_pct": 2.6,
            "avg_max_drawdown_pct": 2.1,
            "avg_selected_count": 2.1,
            "summary": "20d window remains healthy.",
        },
        "long_window": {
            "window": "long_60d",
            "window_label": "60d structural confidence",
            "status": "healthy" if status == "healthy" else "recovering",
            "status_label": "Healthy" if status == "healthy" else "Recovering",
            "score": 78.0 if status == "healthy" else 61.0,
            "threshold": 64.0,
            "sample_count": 60,
            "success_count": 38 if status == "healthy" else 34,
            "success_rate": 63.3 if status == "healthy" else 56.7,
            "avg_profit_window_pct": 2.2 if status == "healthy" else 1.9,
            "avg_max_drawdown_pct": 2.8,
            "avg_selected_count": 2.0 if status == "healthy" else 1.5,
            "summary": "60d window remains healthy." if status == "healthy" else "60d window is still recovering.",
        },
        "blockers": [],
        "recovery_conditions": [],
        "data_source": data_source,
        "is_warming": is_warming,
        "validation_status": "final",
        "progress": {
            "status": "final",
            "processed_trade_date_count": 72,
            "total_trade_date_count": 72,
            "valid_sample_count": 60,
            "target_sample_count": 60,
            "progress_pct": 100.0,
            "last_evaluated_trade_date": "2026-04-09",
            "updated_at": "2026-04-10T18:30:00",
        },
    }


def _build_fake_decision(profile="aggressive", action_level="normal_go", checklist_mode="full"):
    action_labels = {
        "strong_go": "Strong Go",
        "normal_go": "Normal Go",
        "cautious_go": "Cautious Go",
        "observe_only": "Observe Only",
        "stand_aside": "Stand Aside",
    }
    screening = _build_fake_screening_result(profile=profile)
    result = screening["results"][0]
    checklist_enabled = checklist_mode != "disabled"
    return {
        "profile": profile,
        "trade_date": "2026-04-10",
        "action": {
            "level": action_level,
            "label": action_labels[action_level],
            "reason": "Current market and opportunity quality support follow-up.",
            "source_profile": profile,
        },
        "market_environment": {
            "level": "strong",
            "label": "Strong",
            "score": 78.0,
            "reason": "Trend, sentiment, and profitability are supportive.",
            "modules": [
                _build_fake_gate_module("profitability", "Profitability", "strong", 85.0, "Recent strong names continue well."),
                _build_fake_gate_module("sentiment", "Sentiment", "strong", 76.0, "Limit-up expansion remains healthy."),
            ],
        },
        "opportunity_quality": {
            "level": "strong" if action_level in {"strong_go", "normal_go"} else "medium",
            "label": "Strong" if action_level in {"strong_go", "normal_go"} else "Medium",
            "matrix_level": "strong" if action_level in {"strong_go", "normal_go"} else "mid",
            "matrix_label": "Strong" if action_level in {"strong_go", "normal_go"} else "Mid",
            "score": 74.0 if action_level in {"strong_go", "normal_go"} else 61.0,
            "reason": "The default portfolio has at least one executable core idea.",
            "modules": [
                _build_fake_gate_module("theme_clarity", "Theme Clarity", "strong", 80.0, "Theme structure is clear."),
                _build_fake_gate_module("buy_point_clarity", "Buy Point Clarity", "medium", 65.0, "Main slot is close to trigger."),
            ],
            "clear_count": 2,
            "clear_buy_point_count": 2,
            "main_risk_reward_pass": True,
            "theme_concentration_pass": True,
            "main_buy_point_clear": True,
            "secondary_buy_point_clear": True,
            "core_overextended_count": 0,
            "portfolio_unresolved": False,
        },
        "historical_validity": {
            "level": "healthy" if action_level in {"strong_go", "normal_go"} else "general",
            "label": "Healthy" if action_level in {"strong_go", "normal_go"} else "General",
            "score": 79.0 if action_level in {"strong_go", "normal_go"} else 62.0,
            "reason": "Recent 20/60 day validation is supportive enough.",
            "max_action_level": "normal_go" if action_level != "strong_go" else "strong_go",
            "recommendation_cap": "full" if action_level in {"strong_go", "normal_go"} else "limited",
            "attack_permission_status": "open" if action_level in {"strong_go", "normal_go"} else "recovering",
            "attack_permission_label": "Open" if action_level in {"strong_go", "normal_go"} else "Recovering",
        },
        "strategy_health": _build_fake_strategy_health(
            status="healthy" if action_level in {"strong_go", "normal_go"} else "partial_healthy",
            label="Normal" if action_level in {"strong_go", "normal_go"} else "Cautious",
            reason="Both 20d and 60d windows remain supportive." if action_level in {"strong_go", "normal_go"} else "History only supports limited recommendations.",
            recommendation_cap="full" if action_level in {"strong_go", "normal_go"} else "limited",
            can_full_recommend=action_level in {"strong_go", "normal_go"},
        ),
        "attack_permission": {
            "status": "open" if action_level in {"strong_go", "normal_go"} else "recovering",
            "status_label": "Open" if action_level in {"strong_go", "normal_go"} else "Recovering",
            "label": "Open" if action_level in {"strong_go", "normal_go"} else "Recovering",
            "score": 79.0 if action_level in {"strong_go", "normal_go"} else 62.0,
            "window": "short_20d",
            "window_label": "20d attack permission",
            "valid_sample_count": 12,
            "hit_rate": 62.0,
            "avg_profit_window_pct": 2.6,
            "avg_max_drawdown_pct": 2.1,
            "reason": "20d attack permission is open.",
            "summary": "20d attack permission is open.",
        },
        "theme_confidence": {
            "status": "credible",
            "status_label": "Credible",
            "label": "Credible",
            "score": 72.0,
            "window": "long_60d",
            "window_label": "60d theme confidence",
            "valid_sample_count": 32,
            "core_hit_rate": 61.0,
            "reason": "60d theme confidence remains credible.",
            "summary": "60d theme confidence remains credible.",
        },
        "risk_banner": None,
        "themes": [
            {
                "name": "Power Equipment",
                "score": 76.2,
                "strength_label": "Main Theme Clear",
                "candidate_count": 2,
                "clear_buy_point_count": 1,
                "leader_count": 1,
                "summary": "Power equipment still contains 2 strong candidates.",
                "representatives": [
                    {
                        "rank": 1,
                        "ts_code": "600001.SH",
                        "name": "Test Leader",
                        "role": "Leader Core",
                        "buy_point_label": "Clear",
                        "rank_score": result["rank_score"],
                    }
                ],
            }
        ],
        "portfolio": [
            {
                "slot": "main",
                "slot_label": "Main",
                "rank": 1,
                "ts_code": "600001.SH",
                "name": "Test Leader",
                "theme": "Power Equipment",
                "role": "Leader Core",
                "score": 89.2,
                "rank_score": result["rank_score"],
                "risk_score": result["risk_score"],
                "buy_point_status": "clear",
                "buy_point_label": "Clear",
                "suggested_action": "ready" if action_level in {"strong_go", "normal_go"} else "wait_for_trigger",
                "suggested_action_label": "Ready" if action_level in {"strong_go", "normal_go"} else "Wait",
                "primary_reason": "Strength Confirmed",
                "role_reason": "It is the clearest candidate in the set.",
                "execution_plan": "Watch 10.34 - 10.66 for confirmation.",
                "entry_hint": "Watch 10.34 - 10.66 for confirmation.",
                "entry_range_low": 10.34,
                "entry_range_high": 10.66,
                "opportunity_tag": "Breakout Setup" if profile == "aggressive" else None,
            }
        ],
        "excluded_candidates": [],
        "action_checklist": {
            "enabled": checklist_enabled,
            "mode": checklist_mode,
            "reason": "Current action level supports a checklist." if checklist_enabled else "Observation only; checklist disabled.",
            "steps": [
                {
                    "phase": "pre_open",
                    "phase_label": "Pre-open",
                    "objective": "Confirm whether the default portfolio is still valid before the open.",
                    "focus_items": ["Main: Test Leader (Power Equipment / Leader Core)"],
                    "tasks": ["Check auction strength first."],
                    "expected_outcome": "Know whether to prioritize the main slot after open.",
                }
            ] if checklist_enabled else [],
        },
        "evidence": {
            "theme_validation": ["Power Equipment theme score is 76.2."],
            "today_reasoning": [f"Decision was re-ranked from the {profile} profile output."],
        },
    }


def _build_fake_intraday_signal():
    return {
        "market_phase": "first_60m",
        "market_phase_label": "First 60 Minutes",
        "confidence_level": "medium",
        "confidence_label": "Medium Confidence",
        "can_emit_buy_signal": False,
        "status": "watching",
        "status_label": "Watching",
        "reason": "The intraday setup still needs more confirmation.",
        "watch_items": ["Main slot: wait for price to return to 10.34 - 10.66."],
        "final_recommendation": "watch",
        "final_recommendation_label": "Keep Watching",
        "closing_note": "Keep the fixed order and continue to watch the main slot trigger.",
        "updated_at": "2026-04-11T09:50:00",
        "focus_order": ["Priority: Main / Test Leader (waiting for trigger)"],
        "portfolio_items": [
            {
                "slot": "main",
                "slot_label": "Main",
                "ts_code": "600001.SH",
                "name": "Test Leader",
                "theme": "Power Equipment",
                "role": "Leader Core",
                "status": "watching",
                "status_label": "Watching",
                "reason": "The setup has not fully triggered yet.",
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
                "missing_conditions": ["Price needs to return to 10.34 - 10.66."],
                "update_time": "2026-04-11T09:50:00",
            }
        ],
    }

def test_momentum_screener_endpoint_returns_response(client):
    fake_result = _build_fake_screening_result(profile="standard")

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
    assert data["entry_baseline_version"] == "v1_4_2_2"
    assert data["market_scope_version"] == "v1_a_share_main_chinext_star"
    assert data["candidate_count"] == 1
    assert data["results"][0]["ts_code"] == "600001.SH"
    assert data["results"][0]["market_segment"] == "main_board"
    assert data["results"][0]["market_segment_label"] == fake_result["results"][0]["market_segment_label"]



def test_momentum_screener_endpoint_supports_aggressive_profile(client):
    fake_result = _build_fake_screening_result(profile="aggressive")

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
    assert data["results"][0]["opportunity_tag"] == fake_result["results"][0]["opportunity_tag"]
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
    assert data["results"][0]["themes"]
    assert data["entry_baseline_version"] == "v1_4_2_2"
    assert data["market_scope_version"] == "v1_a_share_main_chinext_star"
    assert "strength_confirmation" in data["results"][0]["score_breakdown"]
    assert data["results"][0]["entry_range_low"] is not None
    assert data["results"][0]["entry_range_high"] is not None
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
        "screening": _build_fake_screening_result(profile="aggressive", candidate_count=2),
        "decision": _build_fake_decision(profile="aggressive", action_level="normal_go", checklist_mode="full"),
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
    assert data["decision"]["market_environment"]["level"] == "strong"
    assert data["decision"]["opportunity_quality"]["level"] == "strong"
    assert data["decision"]["historical_validity"]["level"] == "healthy"
    assert data["decision"]["portfolio"][0]["slot"] == "main"
    assert data["decision"]["themes"][0]["name"] == fake_result["decision"]["themes"][0]["name"]
    assert data["decision"]["action_checklist"]["enabled"] is True
    assert data["decision"]["action_checklist"]["mode"] == "full"
    assert data["decision"]["action_checklist"]["steps"][0]["phase"] == "pre_open"

def test_momentum_secondary_decision_endpoint_runs_real_service_flow(client):
    with patch("api.deps.MomentumSecondaryDecisionService", _IntegrationMomentumSecondaryDecisionService):
        response = client.post(
            "/api/v1/stocks/screener/momentum/decision",
            json={"profile": "aggressive", "top_n": 2, "trade_date": "2026-04-10"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["screening"]["profile"] == "standard"
    assert data["screening"]["candidate_count"] == 2
    assert data["decision"]["profile"] == "standard"
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
            "screening": {**_build_fake_screening_result(profile="aggressive", candidate_count=0), "results": []},
            "decision": {
                **_build_fake_decision(profile="aggressive", action_level="observe_only", checklist_mode="disabled"),
                "action": {
                    "level": "observe_only",
                    "label": "???",
                    "reason": "???????????",
                    "source_profile": "aggressive",
                },
                "market_environment": {
                    "level": "medium",
                    "label": "?",
                    "score": 58.0,
                    "reason": "???????????????????",
                    "modules": [
                        _build_fake_gate_module("profitability", "????", "medium", 58.0, "?????????"),
                    ],
                },
                "opportunity_quality": {
                    "level": "medium",
                    "label": "?",
                    "score": 60.0,
                    "reason": "???????????????????",
                    "modules": [
                        _build_fake_gate_module("buy_point_clarity", "?????", "medium", 60.0, "????????????"),
                    ],
                },
                "historical_validity": {
                    "level": "general",
                    "label": "??",
                    "score": 61.0,
                    "reason": "20/60 ????????????",
                    "max_action_level": "cautious_go",
                    "recommendation_cap": "limited",
                },
                "strategy_health": _build_fake_strategy_health(
                    status="partial_healthy",
                    label="??",
                    reason="?????? 20/60 ???",
                    recommendation_cap="limited",
                    can_full_recommend=False,
                    data_source="historical",
                    is_warming=False,
                ),
                "themes": [],
                "portfolio": [],
                "excluded_candidates": [],
                "action_checklist": {"enabled": False, "mode": "disabled", "reason": "???", "steps": []},
                "evidence": {"theme_validation": [], "today_reasoning": []},
            },
        }

        response = client.post(
            "/api/v1/stocks/screener/momentum/decision?wait_for_strategy_health=true",
            json={"profile": "aggressive", "top_n": 5},
        )

    assert response.status_code == 200
    assert mock_service.build.call_args.kwargs["wait_for_strategy_health"] is True



def test_backtest_dependency_does_not_override_interactive_secondary_decision_service():
    created_decision_services = []

    class _FakeDecisionService:
        def __init__(
            self,
            screener_service=None,
            stock_service=None,
            strategy_health_async=False,
            strategy_health_async_delay_seconds=0.0,
            **kwargs,
        ):
            self.screener_service = screener_service
            self.stock_service = stock_service
            self.strategy_health_async = strategy_health_async
            self.strategy_health_async_delay_seconds = strategy_health_async_delay_seconds
            created_decision_services.append(self)

    class _FakeBacktestService:
        def __init__(self, screener_service=None, decision_service=None, repository=None):
            self.screener_service = screener_service
            self.decision_service = decision_service
            self.repository = repository

    request = types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace()))

    with (
        patch("api.deps.MomentumScreenerService", side_effect=lambda: types.SimpleNamespace(name="screener")),
        patch("api.deps.StockService", side_effect=lambda: types.SimpleNamespace(name="stock")),
        patch("api.deps.MomentumSecondaryDecisionService", _FakeDecisionService),
        patch("api.deps.MomentumBacktestService", _FakeBacktestService),
    ):
        backtest_service = get_momentum_backtest_service(request)

        assert backtest_service.decision_service.strategy_health_async is False
        assert not hasattr(request.app.state, "momentum_secondary_decision_service")

        interactive_service = get_momentum_secondary_decision_service(request)

    assert interactive_service.strategy_health_async is True
    assert getattr(request.app.state, "momentum_secondary_decision_service") is interactive_service
    assert backtest_service.decision_service is not interactive_service
    assert len(created_decision_services) == 2


def test_momentum_intraday_signal_endpoint_returns_response(client):
    fake_result = {
        "screening": _build_fake_screening_result(profile="aggressive"),
        "decision": _build_fake_decision(profile="aggressive", action_level="normal_go", checklist_mode="full"),
        "intraday_signal": _build_fake_intraday_signal(),
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
    assert data["decision"]["market_environment"]["level"] == "strong"
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
    assert data["screening"]["profile"] == "standard"
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


def test_momentum_backtest_create_endpoint_returns_run(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.post(
            "/api/v1/stocks/screener/momentum/backtests",
            json={
                "start_trade_date": "2026-04-08",
                "end_trade_date": "2026-04-10",
                "profile": "standard",
                "top_n": 30,
            },
        )
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["created_new"] is True
    assert data["message"] == "已创建回测任务，正在后台计算"
    assert data["run"]["run_id"] == "momentum_bt_running"
    assert data["run"]["status"] == "running"
    assert data["run"]["current_stage_key"] == "candidate_pool"


def test_momentum_backtest_list_endpoint_returns_recent_runs(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.get(
            "/api/v1/stocks/screener/momentum/backtests",
            params={"limit": 2, "profile": "standard"},
        )
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["current_running"]["run_id"] == "momentum_bt_running"
    assert data["queued"]["total"] == 1
    assert data["queued"]["items"][0]["run_id"] == "momentum_bt_queued"
    assert data["history"]["limit"] == 2
    assert len(data["history"]["items"]) == 2
    assert data["history"]["items"][0]["run_id"] == "momentum_bt_test_001"
    assert data["history"]["items"][1]["status"] == "cancelled"


def test_momentum_backtest_cancel_endpoint_returns_updated_run(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.post("/api/v1/stocks/screener/momentum/backtests/momentum_bt_running/cancel")
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_running"
    assert data["status"] == "cancelled"
    assert data["current_stage_key"] == "cancelled"


def test_momentum_backtest_delete_endpoint_returns_success(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.delete("/api/v1/stocks/screener/momentum/backtests/momentum_bt_test_001")
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_test_001"
    assert data["deleted"] is True
    assert data["message"] == "任务已删除"


def test_momentum_backtest_summary_endpoint_returns_summary(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.get("/api/v1/stocks/screener/momentum/backtests/momentum_bt_test_001/summary")
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_test_001"
    assert data["summary"]["decision_top3_buy_trigger_rate"] == 66.67
    assert "benchmark_comparison" in data["summary"]
    assert "layer_diagnostics" in data["summary"]
    assert "gate_module_breakdown" in data["summary"]
    assert "regime_breakdown" in data["summary"]


def test_momentum_backtest_daily_endpoint_returns_items(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.get(
            "/api/v1/stocks/screener/momentum/backtests/momentum_bt_test_001/daily",
            params={"market_regime": "strong", "slot": "main", "page": 1, "page_size": 10},
        )
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_test_001"
    assert data["total"] == 1
    assert data["page"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["trade_date"] == "2026-04-10"
    assert data["items"][0]["action_level"] == "normal_go"


def test_momentum_backtest_daily_detail_endpoint_returns_payload(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.get("/api/v1/stocks/screener/momentum/backtests/momentum_bt_test_001/daily/2026-04-10")
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_test_001"
    assert data["trade_date"] == "2026-04-10"
    assert data["daily_context"]["action_level"] == "normal_go"
    assert data["candidate_top10"][0]["ts_code"] == "600001.SH"
    assert data["decision_top3"][0]["slot"] == "main"
    assert data["outcomes"]["decision_top3"]["metrics"]["trigger_rate_pct"] == 100.0
    assert data["diagnosis"]["summary_lines"]
    assert data["diagnosis"]["gate_snapshot"]
    assert data["diagnosis"]["gate_blockers"][0]["key"] == "sentiment"


def test_momentum_backtest_issues_endpoint_returns_items(client):
    app = client.app
    app.dependency_overrides[get_momentum_backtest_service] = lambda: _FakeMomentumBacktestService()
    try:
        response = client.get("/api/v1/stocks/screener/momentum/backtests/momentum_bt_test_001/issues")
    finally:
        app.dependency_overrides.pop(get_momentum_backtest_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "momentum_bt_test_001"
    assert data["total_issues"] == 1
    assert data["severity_breakdown"]["warning"] == 1
    assert data["items"][0]["issue_key"] == "trigger_efficiency_low"


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


def _build_momentum_ai_request_body():
    return {
        "review_type": "candidate",
        "review_key": "600001.SH",
        "refresh_mode": "resume",
        "payload": {"profile": "standard", "top_n": 5},
        "screening": _build_fake_screening_result(profile="standard"),
    }

def test_momentum_ai_session_endpoint_returns_parsed_messages(client):
    with patch(
        "api.deps._get_momentum_screener_ai_commentary_service_cls",
        return_value=_FakeMomentumScreenerAICommentaryService,
    ):
        response = client.post(
            "/api/v1/stocks/screener/momentum/ai/session",
            json=_build_momentum_ai_request_body(),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "screener_ai:candidate:test-session"
    assert data["review_type"] == "candidate"
    assert data["messages"][0]["role"] == "assistant"
    assert data["messages"][0]["context_meta"]["rule_conclusion"]
    assert len(data["messages"][0]["suggested_questions"]) == 1

def test_momentum_ai_stream_endpoint_returns_stage_and_done_events(client):
    with patch(
        "api.deps._get_momentum_screener_ai_commentary_service_cls",
        return_value=_FakeMomentumScreenerAICommentaryService,
    ),          patch("api.v1.endpoints.stocks.get_config", return_value=types.SimpleNamespace(is_agent_available=lambda: True)):
        response = client.post(
            "/api/v1/stocks/screener/momentum/ai/stream",
            json=_build_momentum_ai_request_body(),
        )

    assert response.status_code == 200
    body = response.text
    assert '"type": "stage"' in body
    assert '"type": "tool_start"' in body
    assert '"type": "done"' in body
    assert '"session_id": "screener_ai:candidate:test-session"' in body
    assert '"rule_guardrail":' in body
    assert '"suggested_questions":' in body
