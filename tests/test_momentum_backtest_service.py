"""Tests for MomentumBacktestService."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.config import Config
from src.repositories.momentum_backtest_repo import MomentumBacktestRepository
from src.services.momentum_backtest_service import MomentumBacktestService
from src.services.momentum_screener_service import MomentumScreenerService
from src.services.momentum_secondary_decision_service import MomentumSecondaryDecisionService
from src.storage import DatabaseManager
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
        Config.reset_instance()
        MomentumScreenerService.reset_sector_cache()
        DatabaseManager.reset_instance()
        self.temp_dir.cleanup()

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

        filtered = self.service.list_daily(
            result["run_id"],
            date_from="2026-04-09",
            date_to="2026-04-10",
            page=1,
            page_size=2,
        )
        self.assertGreaterEqual(filtered["total"], 2)
        self.assertLessEqual(len(filtered["items"]), 2)

        detail = self.service.get_daily_detail(result["run_id"], "2026-04-10")
        self.assertEqual(detail["trade_date"], "2026-04-10")
        self.assertEqual(detail["daily_context"]["action_level"], daily["items"][0]["action_level"])
        self.assertTrue(detail["candidate_top10"])
        self.assertTrue(detail["decision_top3"])
        self.assertIn("candidate_top10", detail["outcomes"])
        self.assertIn("decision_top3", detail["outcomes"])
        self.assertIn("issues", detail["diagnosis"])
        self.assertIn("gate_snapshot", detail["diagnosis"])
        self.assertIn("gate_blockers", detail["diagnosis"])
        self.assertTrue(any(item["key"] == "buy_point_clarity" for item in detail["diagnosis"]["gate_blockers"]))

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


if __name__ == "__main__":
    unittest.main()
