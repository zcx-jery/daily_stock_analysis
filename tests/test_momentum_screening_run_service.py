from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from src.config import Config
from src.repositories.momentum_screening_run_repo import MomentumScreeningRunRepository
from src.services.momentum_screening_run_service import MomentumScreeningRunService
from src.services.momentum_screener_service import (
    MOMENTUM_ENTRY_BASELINE_VERSION,
    MOMENTUM_MARKET_SCOPE_VERSION,
    MOMENTUM_SCREENING_CACHE_VERSION,
)
from src.storage import DatabaseManager


class _FakeTaskizedScreenerService:
    def __init__(self, *, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds
        self.calls = []

    def screen(self, **kwargs):
        self.calls.append(dict(kwargs))
        progress_callback = kwargs.get("progress_callback")
        trade_date = kwargs.get("trade_date") or "2026-04-10"
        if progress_callback:
            progress_callback(
                {
                    "stage_key": "candidate_pool",
                    "stage_label": "构建候选池",
                    "progress_pct": 24.0,
                    "processed_item_count": 1,
                    "total_item_count": 2,
                    "trade_date": trade_date,
                }
            )
            progress_callback(
                {
                    "stage_key": "v13_context",
                    "stage_label": "加载 V1.3 真实题材画像",
                    "progress_pct": 68.0,
                    "processed_item_count": 2,
                    "total_item_count": 2,
                    "trade_date": trade_date,
                    "cache_hits": {"trade_snapshot": 1},
                    "cache_misses": {"screening_result": 1},
                }
            )
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        result = {
            "rank": 1,
            "ts_code": "600001.SH",
            "name": "Test Leader",
            "market_segment": "main_board",
            "market_segment_label": "Main Board",
            "pct_chg": 9.8,
            "continuation_score": 86.5,
            "extension_score": 78.2,
            "risk_score": 15.0,
            "final_score": 84.0,
            "rank_score": 73.4,
            "themes": ["Power Equipment"],
            "leader_level": "leader",
            "top_reasons": ["Strength Confirmed"],
            "risk_tags": [],
            "score_breakdown": {},
        }
        return {
            "profile": kwargs.get("profile", "standard"),
            "truth_mode": kwargs.get("truth_mode", "full"),
            "trade_date": trade_date,
            "requested_trade_date": trade_date,
            "trade_date_note": None,
            "entry_baseline_version": MOMENTUM_ENTRY_BASELINE_VERSION,
            "market_scope_version": MOMENTUM_MARKET_SCOPE_VERSION,
            "candidate_count": 1,
            "ranked_results": [result],
            "results": [result],
        }


class _FakeTaskizedDecisionService:
    def __init__(self) -> None:
        self.calls = []

    def build_from_screening(self, screening, **kwargs):
        self.calls.append({"screening": dict(screening), "kwargs": dict(kwargs)})
        progress_callback = kwargs.get("strategy_health_progress_callback")
        if progress_callback:
            progress_callback(
                {
                    "progress": {
                        "status": "final",
                        "processed_trade_date_count": 20,
                        "total_trade_date_count": 20,
                        "valid_sample_count": 18,
                    }
                }
            )
        return {
            "profile": screening.get("profile", "standard"),
            "trade_date": screening.get("trade_date"),
            "action": {"level": "normal_go"},
            "portfolio": [{"slot": "main", "ts_code": "600001.SH"}],
        }

    def _build_secondary_decision_progress_label(self, progress):
        status = progress.get("status") or "running"
        return f"生成二次决策 ({status})"


class MomentumScreeningRunServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "momentum_screening_run.db"
        self.db_manager = DatabaseManager(db_url=f"sqlite:///{self.db_path.as_posix()}")
        self.screener_service = _FakeTaskizedScreenerService()
        self.decision_service = _FakeTaskizedDecisionService()
        repository = MomentumScreeningRunRepository(self.db_manager)
        self.service = MomentumScreeningRunService(
            screener_service=self.screener_service,
            decision_service=self.decision_service,
            repository=repository,
        )

    def tearDown(self) -> None:
        self.service.close()
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.temp_dir.cleanup()

    def _wait_for_terminal_status(self, run_id: str, *, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        latest = self.service.get_run(run_id)
        while time.time() < deadline and latest["status"] in {"queued", "running"}:
            time.sleep(0.05)
            latest = self.service.get_run(run_id)
        return latest

    def test_create_run_async_completes_and_returns_result(self) -> None:
        created = self.service.create_run_async(
            trade_date="2026-04-10",
            profile="standard",
            truth_mode="full",
        )

        run_id = created["run"]["run_id"]
        terminal = self._wait_for_terminal_status(run_id)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["truth_mode"], "full")
        self.assertEqual(terminal["progress"]["progress_pct"], 100.0)
        self.assertEqual(self.screener_service.calls[0]["truth_mode"], "full")

        result = self.service.get_result(run_id)
        self.assertEqual(result["run_id"], run_id)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["screening"]["profile"], "standard")
        self.assertEqual(result["decision"]["action"]["level"], "normal_go")

    def test_create_run_async_reuses_completed_run_by_fingerprint(self) -> None:
        created = self.service.create_run_async(
            trade_date="2026-04-10",
            profile="standard",
            truth_mode="full",
        )
        run_id = created["run"]["run_id"]
        terminal = self._wait_for_terminal_status(run_id)
        self.assertEqual(terminal["status"], "completed")

        reused = self.service.create_run_async(
            trade_date="2026-04-10",
            profile="standard",
            truth_mode="full",
        )
        self.assertFalse(reused["created_new"])
        self.assertEqual(reused["run"]["run_id"], run_id)

    def test_cancel_run_marks_running_task_cancelled(self) -> None:
        self.service.close()
        self.screener_service = _FakeTaskizedScreenerService(delay_seconds=0.2)
        self.decision_service = _FakeTaskizedDecisionService()
        repository = MomentumScreeningRunRepository(self.db_manager)
        self.service = MomentumScreeningRunService(
            screener_service=self.screener_service,
            decision_service=self.decision_service,
            repository=repository,
        )

        created = self.service.create_run_async(
            trade_date="2026-04-10",
            profile="standard",
            truth_mode="full",
        )
        run_id = created["run"]["run_id"]
        time.sleep(0.05)
        cancelled = self.service.cancel_run(run_id)
        self.assertTrue(cancelled["cancel_requested"])

        terminal = self._wait_for_terminal_status(run_id)
        self.assertEqual(terminal["status"], "cancelled")
        self.assertEqual(terminal["current_stage_key"], "cancelled")


if __name__ == "__main__":
    unittest.main()
