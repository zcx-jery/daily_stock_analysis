"""Tests for MomentumBacktestService."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.config import Config
from src.repositories.momentum_backtest_repo import MomentumBacktestRepository
from src.services.momentum_backtest_service import MomentumBacktestService
from src.services.momentum_screener_service import MomentumScreenerService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from src.storage import (
    DatabaseManager,
    MomentumBacktestCandidateRecord,
    MomentumBacktestDailySummary,
    MomentumBacktestDecisionRecord,
    MomentumBacktestOutcomeRecord,
    MomentumBacktestRun,
)
from tests.test_momentum_screener_service import _FakeFetcher


class _BacktestFetcher(_FakeFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.trade_snapshots["20260409"] = self.build_trade_snapshot("20260409", ready=True)
        self.trade_snapshots["20260408"] = self.build_trade_snapshot("20260408", ready=True)
        self.trade_dates = sorted(self.trade_snapshots.keys(), reverse=True)
        self.history["600001"] = pd.concat(
            [
                self.history["600001"],
                pd.DataFrame(
                    [
                        {
                            "date": "2026-04-11",
                            "open": 11.05,
                            "high": 11.62,
                            "low": 10.98,
                            "close": 11.48,
                            "volume": 1,
                            "amount": 7.2e8,
                            "pct_chg": 4.36,
                        },
                        {
                            "date": "2026-04-14",
                            "open": 11.42,
                            "high": 11.88,
                            "low": 11.22,
                            "close": 11.70,
                            "volume": 1,
                            "amount": 6.9e8,
                            "pct_chg": 1.92,
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )
        self.history["600002"] = pd.concat(
            [
                self.history["600002"],
                pd.DataFrame(
                    [
                        {
                            "date": "2026-04-11",
                            "open": 8.62,
                            "high": 8.94,
                            "low": 8.51,
                            "close": 8.90,
                            "volume": 1,
                            "amount": 4.9e8,
                            "pct_chg": 2.89,
                        },
                        {
                            "date": "2026-04-14",
                            "open": 8.88,
                            "high": 9.12,
                            "low": 8.75,
                            "close": 9.05,
                            "volume": 1,
                            "amount": 5.1e8,
                            "pct_chg": 1.69,
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )


class MomentumBacktestServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Config.reset_instance()
        MomentumScreenerService.reset_sector_cache()
        DatabaseManager.reset_instance()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "momentum_backtest.db"
        self.db_manager = DatabaseManager(db_url=f"sqlite:///{self.db_path.as_posix()}")
        self.fetcher = _BacktestFetcher()
        cache_root = Path(self.temp_dir.name) / "cache"
        screener_service = MomentumScreenerService(
            fetcher=self.fetcher,
            history_cache_dir=cache_root / "histories",
            trade_snapshot_cache_dir=cache_root / "snapshots",
            candidate_pool_cache_dir=cache_root / "candidate_pools",
        )
        decision_service = MomentumSecondaryDecisionService(
            screener_service=screener_service,
            strategy_health_async=False,
        )
        repository = MomentumBacktestRepository(self.db_manager)
        self.service = MomentumBacktestService(
            screener_service=screener_service,
            decision_service=decision_service,
            repository=repository,
        )

    def tearDown(self) -> None:
        self.service.close()
        Config.reset_instance()
        MomentumScreenerService.reset_sector_cache()
        DatabaseManager.reset_instance()
        self.temp_dir.cleanup()

    def _wait_for_terminal_status(self, run_id: str, *, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        latest = self.service.get_run(run_id)
        while time.time() < deadline and latest["status"] in {"queued", "running"}:
            time.sleep(0.05)
            latest = self.service.get_run(run_id)
        return latest

    def _slow_down_freeze(self, delay_seconds: float = 0.05) -> None:
        original = self.service._freeze_trade_date_artifacts

        def delayed(*args, **kwargs):
            time.sleep(delay_seconds)
            return original(*args, **kwargs)

        self.service._freeze_trade_date_artifacts = delayed  # type: ignore[method-assign]

    def _build_daily_summary_fixture(self) -> MomentumBacktestDailySummary:
        trade_date = pd.Timestamp("2026-04-10").date()
        return MomentumBacktestDailySummary(
            run_id="momentum_bt_diag",
            trade_date=trade_date,
            action_level="cautious_go",
            action_label="谨慎出手",
            recommendation_cap="partial",
            action_checklist_mode="disabled",
            market_environment_level="strong",
            opportunity_quality_level="medium",
            historical_validity_level="healthy",
            candidate_count=3,
            result_count=3,
            selected_count=1,
            buy_ready_count=1,
            main_ts_code="600001.SH",
            decision_payload_json="{}",
            diagnosis_json="{}",
        )

    def _build_candidate_record(
        self,
        *,
        ts_code: str,
        name: str,
        theme: str,
        role: str,
        rank: int,
    ) -> MomentumBacktestCandidateRecord:
        return MomentumBacktestCandidateRecord(
            run_id="momentum_bt_diag",
            trade_date=pd.Timestamp("2026-04-10").date(),
            view_scope="candidate_top10",
            rank=rank,
            ts_code=ts_code,
            name=name,
            theme=theme,
            role=role,
        )

    def _build_decision_record(
        self,
        *,
        slot: str,
        ts_code: str,
        name: str,
        theme: str,
        role: str,
    ) -> MomentumBacktestDecisionRecord:
        return MomentumBacktestDecisionRecord(
            run_id="momentum_bt_diag",
            trade_date=pd.Timestamp("2026-04-10").date(),
            slot=slot,
            rank=1,
            ts_code=ts_code,
            name=name,
            theme=theme,
            role=role,
            buy_point_status="clear",
            suggested_action="ready",
        )

    def _build_outcome_record(
        self,
        *,
        view_scope: str,
        ts_code: str,
        name: str,
        t2_profit_window_pct: float,
        slot: str | None = None,
    ) -> MomentumBacktestOutcomeRecord:
        return MomentumBacktestOutcomeRecord(
            run_id="momentum_bt_diag",
            trade_date=pd.Timestamp("2026-04-10").date(),
            view_scope=view_scope,
            slot=slot,
            ts_code=ts_code,
            name=name,
            buy_triggered=True,
            t2_profit_window_pct=t2_profit_window_pct,
            t2_close_return_pct=t2_profit_window_pct / 2,
        )

    def test_create_run_replays_trade_dates_and_persists_summary(self) -> None:
        result = self.service.create_run(
            start_trade_date="2026-04-08",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["profile"], "standard")
        self.assertEqual(result["total_trade_dates"], 3)
        self.assertEqual(result["processed_trade_dates"], 3)
        self.assertEqual(result["failed_trade_dates"], 0)
        self.assertIsNotNone(result["summary"])
        self.assertEqual(result["summary"]["completed_trade_dates"], 3)
        self.assertIn("action_breakdown", result["summary"])

        daily = self.service.list_daily(result["run_id"])
        self.assertEqual(len(daily["items"]), 3)
        self.assertEqual(daily["total"], 3)
        self.assertEqual(daily["page"], 1)
        self.assertEqual(daily["items"][0]["trade_date"], "2026-04-10")

        summary = self.service.get_summary(result["run_id"])
        self.assertEqual(summary["run_id"], result["run_id"])
        self.assertIn("decision_top3_buy_trigger_rate", summary["summary"])
        self.assertIn("benchmark_comparison", summary["summary"])
        self.assertIn("layer_diagnostics", summary["summary"])
        self.assertIn("gate_module_breakdown", summary["summary"])
        self.assertIn("regime_breakdown", summary["summary"])
        self.assertTrue(any(item["key"] == "buy_point_clarity" for item in summary["summary"]["gate_module_breakdown"]))

        detail = self.service.get_daily_detail(result["run_id"], "2026-04-10")
        self.assertEqual(detail["trade_date"], "2026-04-10")
        self.assertTrue(detail["candidate_top10"])
        self.assertTrue(detail["decision_top3"])
        self.assertIn("decision_diagnostics", detail["candidate_top10"][0])
        self.assertIn("forward_alpha_score", detail["candidate_top10"][0]["decision_diagnostics"])
        self.assertIn("gate_snapshot", detail["diagnosis"])
        self.assertIn("gate_blockers", detail["diagnosis"])

        issues = self.service.get_issues(result["run_id"])
        self.assertEqual(issues["run_id"], result["run_id"])
        self.assertIn("severity_breakdown", issues)
        self.assertIn("issue_key_breakdown", issues)

    def test_create_run_rejects_invalid_date_range(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_run(
                start_trade_date="2026-04-10",
                end_trade_date="2026-04-08",
                profile="standard",
            )

    def test_daily_diagnosis_flags_main_slot_issue_for_same_theme_outperformer(self) -> None:
        diagnosis = self.service._build_daily_diagnosis(
            daily_row=self._build_daily_summary_fixture(),
            candidate_rows=[
                self._build_candidate_record(
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                    rank=1,
                ),
                self._build_candidate_record(
                    ts_code="300001.SZ",
                    name="同主线更强股",
                    theme="电子",
                    role="前排换手",
                    rank=2,
                ),
            ],
            decision_rows=[
                self._build_decision_record(
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                )
            ],
            candidate_outcomes=[
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                ),
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="300001.SZ",
                    name="同主线更强股",
                    t2_profit_window_pct=9.5,
                ),
            ],
            decision_outcomes=[
                self._build_outcome_record(
                    view_scope="decision_top3",
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                )
            ],
        )

        issue = next(item for item in diagnosis["issues"] if item["issue_key"] == "main_slot_underperformed")
        self.assertTrue(issue["metrics"]["best_candidate_same_theme"])
        self.assertFalse(issue["metrics"]["best_candidate_in_selected_top3"])

    def test_daily_diagnosis_skips_cross_theme_unselected_outlier_for_main_slot_issue(self) -> None:
        diagnosis = self.service._build_daily_diagnosis(
            daily_row=self._build_daily_summary_fixture(),
            candidate_rows=[
                self._build_candidate_record(
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                    rank=1,
                ),
                self._build_candidate_record(
                    ts_code="300002.SZ",
                    name="跨主线黑马",
                    theme="公用事业",
                    role="龙头核心",
                    rank=2,
                ),
            ],
            decision_rows=[
                self._build_decision_record(
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                )
            ],
            candidate_outcomes=[
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                ),
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="300002.SZ",
                    name="跨主线黑马",
                    t2_profit_window_pct=12.0,
                ),
            ],
            decision_outcomes=[
                self._build_outcome_record(
                    view_scope="decision_top3",
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                )
            ],
        )

        self.assertFalse(any(item["issue_key"] == "main_slot_underperformed" for item in diagnosis["issues"]))

    def test_daily_diagnosis_splits_cross_theme_selected_outperformer_into_anchor_issue(self) -> None:
        diagnosis = self.service._build_daily_diagnosis(
            daily_row=self._build_daily_summary_fixture(),
            candidate_rows=[
                self._build_candidate_record(
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                    rank=1,
                ),
                self._build_candidate_record(
                    ts_code="300003.SZ",
                    name="组合内更强股",
                    theme="公用事业",
                    role="龙头核心",
                    rank=2,
                ),
            ],
            decision_rows=[
                self._build_decision_record(
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    theme="电子",
                    role="龙头核心",
                ),
                self._build_decision_record(
                    slot="watch",
                    ts_code="300003.SZ",
                    name="组合内更强股",
                    theme="公用事业",
                    role="龙头核心",
                ),
            ],
            candidate_outcomes=[
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                ),
                self._build_outcome_record(
                    view_scope="candidate_top10",
                    ts_code="300003.SZ",
                    name="组合内更强股",
                    t2_profit_window_pct=12.0,
                ),
            ],
            decision_outcomes=[
                self._build_outcome_record(
                    view_scope="decision_top3",
                    slot="main",
                    ts_code="600001.SH",
                    name="主仓股",
                    t2_profit_window_pct=4.0,
                ),
                self._build_outcome_record(
                    view_scope="decision_top3",
                    slot="watch",
                    ts_code="300003.SZ",
                    name="组合内更强股",
                    t2_profit_window_pct=12.0,
                ),
            ],
        )

        issue = next(item for item in diagnosis["issues"] if item["issue_key"] == "portfolio_anchor_underperformed")
        self.assertFalse(issue["metrics"]["best_candidate_same_theme"])
        self.assertTrue(issue["metrics"]["best_candidate_in_selected_top3"])

    def test_async_create_reuses_same_params_and_queues_different_tasks(self) -> None:
        self._slow_down_freeze()

        first = self.service.create_run_async(
            start_trade_date="2026-04-08",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )
        second = self.service.create_run_async(
            start_trade_date="2026-04-09",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )
        duplicate = self.service.create_run_async(
            start_trade_date="2026-04-09",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )

        self.assertTrue(first["created_new"])
        self.assertTrue(second["created_new"])
        self.assertFalse(duplicate["created_new"])
        self.assertEqual(duplicate["run"]["run_id"], second["run"]["run_id"])
        self.assertEqual(duplicate["message"], "已存在相同参数任务，已为你定位到该任务")

        listed = self.service.list_runs(limit=20)
        self.assertEqual(listed["current_running"]["run_id"], first["run"]["run_id"])
        self.assertEqual(listed["queued"]["total"], 1)
        self.assertEqual(listed["queued"]["items"][0]["run_id"], second["run"]["run_id"])

        latest_first = self._wait_for_terminal_status(first["run"]["run_id"])
        latest_second = self._wait_for_terminal_status(second["run"]["run_id"])
        self.assertEqual(latest_first["status"], "completed")
        self.assertEqual(latest_second["status"], "completed")

    def test_cancel_running_task_preserves_processed_results(self) -> None:
        self._slow_down_freeze(delay_seconds=0.08)

        created = self.service.create_run_async(
            start_trade_date="2026-04-08",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )
        run_id = created["run"]["run_id"]

        partially_done = created["run"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            partially_done = self.service.get_run(run_id)
            if partially_done["processed_trade_dates"] >= 1:
                break
            time.sleep(0.05)

        cancel_response = self.service.cancel_run(run_id)
        self.assertEqual(cancel_response["run_id"], run_id)
        self.assertTrue(cancel_response["cancel_requested"])

        latest = self._wait_for_terminal_status(run_id)
        self.assertEqual(latest["status"], "cancelled")
        self.assertGreaterEqual(latest["processed_trade_dates"], 1)
        self.assertLess(latest["processed_trade_dates"], latest["total_trade_dates"])
        self.assertIsNotNone(latest["summary"])

    def test_async_run_resyncs_total_trade_dates_with_execution_calendar(self) -> None:
        planned_dates = [
            pd.Timestamp("2026-04-08").date(),
            pd.Timestamp("2026-04-09").date(),
            pd.Timestamp("2026-04-10").date(),
        ]
        execution_dates = planned_dates[1:]
        call_count = 0
        original_list_trade_dates = self.service._list_trade_dates

        def drifting_list_trade_dates(start_dt, end_dt):
            nonlocal call_count
            call_count += 1
            if start_dt == planned_dates[0] and end_dt == planned_dates[-1]:
                return planned_dates if call_count == 1 else execution_dates
            return original_list_trade_dates(start_dt, end_dt)

        self.service._list_trade_dates = drifting_list_trade_dates  # type: ignore[method-assign]

        created = self.service.create_run_async(
            start_trade_date="2026-04-08",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )

        latest = self._wait_for_terminal_status(created["run"]["run_id"])
        self.assertEqual(latest["status"], "completed")
        self.assertEqual(latest["total_trade_dates"], 2)
        self.assertEqual(latest["processed_trade_dates"], 2)
        self.assertEqual(latest["failed_trade_dates"], 0)
        self.assertIsNotNone(latest["summary"])
        self.assertEqual(latest["summary"]["completed_trade_dates"], 2)

    def test_list_trade_dates_falls_back_to_trade_cal_when_cached_range_is_incomplete(self) -> None:
        fetcher = self.service.screener_service.fetcher
        original_call_api = fetcher._call_api_with_rate_limit
        trade_cal_calls: list[dict[str, object]] = []
        fetcher._get_trade_dates = lambda _end_date=None: ["20260410", "20260409"]  # type: ignore[attr-defined]
        fetcher.trade_dates = ["20260410", "20260409"]

        def fake_call_api(method_name: str, **kwargs):
            if method_name == "trade_cal":
                trade_cal_calls.append(kwargs)
                return pd.DataFrame(
                    {
                        "cal_date": ["20260408", "20260409", "20260410"],
                        "is_open": [1, 1, 1],
                    }
                )
            return original_call_api(method_name, **kwargs)

        fetcher._call_api_with_rate_limit = fake_call_api  # type: ignore[method-assign]

        trade_dates = self.service._list_trade_dates(
            pd.Timestamp("2026-04-08").date(),
            pd.Timestamp("2026-04-10").date(),
        )

        self.assertEqual(
            trade_dates,
            [
                pd.Timestamp("2026-04-08").date(),
                pd.Timestamp("2026-04-09").date(),
                pd.Timestamp("2026-04-10").date(),
            ],
        )
        self.assertEqual(len(trade_cal_calls), 1)

    def test_backtest_replay_uses_cached_only_strategy_health_mode(self) -> None:
        captured_modes: list[str | None] = []
        original_build_from_screening = self.service.decision_service.build_from_screening

        def wrapped_build_from_screening(screening, *args, **kwargs):
            captured_modes.append(kwargs.get("strategy_health_mode"))
            return original_build_from_screening(screening, *args, **kwargs)

        self.service.decision_service.build_from_screening = wrapped_build_from_screening  # type: ignore[method-assign]

        result = self.service.create_run(
            start_trade_date="2026-04-08",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )

        self.assertEqual(result["status"], "completed")
        self.assertGreaterEqual(len(captured_modes), 3)
        self.assertTrue(captured_modes)
        self.assertTrue(all(mode == "cached_only" for mode in captured_modes))

    def test_async_run_refreshes_heartbeat_during_long_secondary_decision(self) -> None:
        self.service.stage_heartbeat_interval_seconds = 0.05
        original_build_from_screening = self.service.decision_service.build_from_screening

        def slow_build_from_screening(screening, *args, **kwargs):
            time.sleep(0.15)
            return original_build_from_screening(screening, *args, **kwargs)

        self.service.decision_service.build_from_screening = slow_build_from_screening  # type: ignore[method-assign]

        created = self.service.create_run_async(
            start_trade_date="2026-04-10",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )
        run_id = created["run"]["run_id"]

        stage_state = None
        deadline = time.time() + 5.0
        while time.time() < deadline:
            latest = self.service.get_run(run_id)
            if latest["current_stage_key"] == "secondary_decision":
                stage_state = latest
                break
            time.sleep(0.01)

        self.assertIsNotNone(stage_state)
        initial_heartbeat = stage_state["heartbeat_at"]

        refreshed_state = None
        deadline = time.time() + 5.0
        while time.time() < deadline:
            latest = self.service.get_run(run_id)
            if latest["status"] in {"completed", "failed", "cancelled"}:
                break
            if (
                latest["current_stage_key"] == "secondary_decision"
                and latest["heartbeat_at"] != initial_heartbeat
            ):
                refreshed_state = latest
                break
            time.sleep(0.02)

        self.assertIsNotNone(refreshed_state)
        self.assertEqual(refreshed_state["current_stage_key"], "secondary_decision")
        self.assertTrue(refreshed_state["current_stage_label"].startswith("二次决策回放中"))

        latest = self._wait_for_terminal_status(run_id)
        self.assertEqual(latest["status"], "completed")

    def test_secondary_decision_progress_label_prefers_sample_count(self) -> None:
        label = self.service._build_secondary_decision_progress_label(
            {
                "valid_sample_count": 12,
                "target_sample_count": 60,
                "processed_trade_date_count": 18,
                "total_trade_date_count": 72,
            }
        )
        self.assertEqual(label, "二次决策回放中（样本 12/60）")

    def test_delete_run_hard_deletes_frozen_records(self) -> None:
        result = self.service.create_run(
            start_trade_date="2026-04-10",
            end_trade_date="2026-04-10",
            profile="standard",
            top_n=20,
        )

        delete_result = self.service.delete_run(result["run_id"])
        self.assertTrue(delete_result["deleted"])

        with self.assertRaises(ValueError):
            self.service.get_run(result["run_id"])

        listed = self.service.list_runs(limit=20)
        self.assertEqual(listed["history"]["total"], 0)

    def test_service_init_requeues_stale_running_runs(self) -> None:
        repository = MomentumBacktestRepository(self.db_manager)
        stale_run = MomentumBacktestRun(
            run_id="momentum_bt_stale_running",
            status="running",
            profile="standard",
            engine_version="v1",
            entry_baseline_version="v1_4_2_2",
            market_scope_version="v1_a_share_main_chinext_star",
            top_n=30,
            start_trade_date=pd.Timestamp("2026-04-08").date(),
            end_trade_date=pd.Timestamp("2026-04-10").date(),
            total_trade_dates=3,
            processed_trade_dates=1,
            failed_trade_dates=0,
        )
        repository.create_run(stale_run)

        with patch("src.services.momentum_backtest_service.threading.Thread.start", lambda *_args, **_kwargs: None):
            recovered_service = MomentumBacktestService(
                screener_service=self.service.screener_service,
                decision_service=self.service.decision_service,
                repository=repository,
            )

        recovered = repository.get_run("momentum_bt_stale_running")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.current_stage_key, "queued")
        self.assertEqual(recovered.current_stage_label, "等待后台调度")
        self.assertFalse(recovered.cancel_requested)
        self.assertIsNone(recovered.started_at)
        self.assertIsNone(recovered.finished_at)
        recovered_service.close()
        self.assertIsNotNone(recovered_service)

    def test_execute_run_resumes_from_attempted_trade_date_count(self) -> None:
        repository = MomentumBacktestRepository(self.db_manager)
        resumable_run = MomentumBacktestRun(
            run_id="momentum_bt_resume",
            status="queued",
            profile="standard",
            engine_version="v1",
            entry_baseline_version="v1_4_2_2",
            market_scope_version="v1_a_share_main_chinext_star",
            top_n=20,
            start_trade_date=pd.Timestamp("2026-04-08").date(),
            end_trade_date=pd.Timestamp("2026-04-10").date(),
            total_trade_dates=3,
            processed_trade_dates=1,
            failed_trade_dates=1,
            current_trade_date=pd.Timestamp("2026-04-09").date(),
        )
        repository.create_run(resumable_run)

        replayed_trade_dates: list[str | None] = []
        original_screen = self.service.screener_service.screen

        def wrapped_screen(*args, **kwargs):
            replayed_trade_dates.append(kwargs.get("trade_date"))
            return original_screen(*args, **kwargs)

        self.service.screener_service.screen = wrapped_screen  # type: ignore[method-assign]
        self.service._build_run_summary = lambda _run_id: {"completed_trade_dates": 2}  # type: ignore[method-assign]

        self.service._execute_run(
            run_id="momentum_bt_resume",
            trade_dates=[
                pd.Timestamp("2026-04-08").date(),
                pd.Timestamp("2026-04-09").date(),
                pd.Timestamp("2026-04-10").date(),
            ],
            profile="standard",
            top_n=20,
        )

        latest = self.service.get_run("momentum_bt_resume")
        self.assertEqual(latest["status"], "completed")
        self.assertEqual(latest["processed_trade_dates"], 2)
        self.assertEqual(latest["failed_trade_dates"], 1)
        self.assertEqual(latest["current_trade_date"], "2026-04-10")
        self.assertEqual(replayed_trade_dates, ["2026-04-10"])


if __name__ == "__main__":
    unittest.main()
