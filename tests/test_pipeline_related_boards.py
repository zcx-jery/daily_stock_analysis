# -*- coding: utf-8 -*-
"""Regression tests for pipeline-level related board enrichment."""

import unittest
import sys
from unittest.mock import MagicMock

from tests.litellm_stub import ensure_litellm_stub
from data_provider.realtime_types import ChipDistribution

ensure_litellm_stub()

if "markdown2" not in sys.modules:
    sys.modules["markdown2"] = MagicMock()
if "newspaper" not in sys.modules:
    sys.modules["newspaper"] = MagicMock()

pipeline_module = sys.modules.get("src.core.pipeline")
if getattr(pipeline_module, "StockAnalysisPipeline", None) is object:
    sys.modules.pop("src.core.pipeline", None)
    import src.core as _src_core

    if getattr(_src_core, "pipeline", None) is pipeline_module:
        delattr(_src_core, "pipeline")

from src.core.pipeline import StockAnalysisPipeline


class PipelineRelatedBoardsTestCase(unittest.TestCase):
    def test_attach_belong_boards_shallow_copies_context_before_injecting(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.fetcher_manager.get_belong_boards.return_value = [{"name": "白酒", "type": "行业"}]

        cached_context = {
            "market": "cn",
            "status": "ok",
            "coverage": {"boards": "ok"},
            "boards": {"status": "ok", "data": {"top": [], "bottom": []}},
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("600519", cached_context)

        self.assertIsNot(enriched, cached_context)
        self.assertNotIn("belong_boards", cached_context)
        self.assertEqual(enriched["belong_boards"], [{"name": "白酒", "type": "行业"}])

    def test_attach_belong_boards_copies_existing_board_list(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()

        existing_boards = [{"name": "白酒", "type": "行业"}]
        context = {
            "market": "cn",
            "status": "ok",
            "belong_boards": existing_boards,
            "coverage": {"boards": "ok"},
            "boards": {"status": "ok", "data": {"top": [], "bottom": []}},
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("600519", context)

        self.assertIsNot(enriched, context)
        self.assertEqual(enriched["belong_boards"], existing_boards)
        self.assertIsNot(enriched["belong_boards"], existing_boards)
        pipeline.fetcher_manager.get_belong_boards.assert_not_called()

    def test_attach_belong_boards_reuses_board_block_membership(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()

        context = {
            "market": "cn",
            "status": "ok",
            "coverage": {"boards": "ok"},
            "boards": {
                "status": "ok",
                "data": {"belong_boards": [{"name": "白酒", "type": "行业"}]},
            },
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("600519", context)

        self.assertEqual(enriched["belong_boards"], [{"name": "白酒", "type": "行业"}])
        self.assertIsNot(enriched["belong_boards"], context["boards"]["data"]["belong_boards"])
        pipeline.fetcher_manager.get_belong_boards.assert_not_called()

    def test_attach_belong_boards_skips_provider_for_non_cn(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()

        context = {"market": "us", "status": "not_supported"}
        enriched = pipeline._attach_belong_boards_to_fundamental_context("AAPL", context)

        self.assertEqual(enriched["belong_boards"], [])
        pipeline.fetcher_manager.get_belong_boards.assert_not_called()

    def test_attach_belong_boards_skips_provider_when_board_block_not_supported(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()

        context = {
            "market": "cn",
            "status": "partial",
            "coverage": {"boards": "not_supported"},
            "boards": {"status": "not_supported", "data": {}},
            "errors": ["etf not fully supported"],
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("159915", context)

        self.assertEqual(enriched["belong_boards"], [])
        pipeline.fetcher_manager.get_belong_boards.assert_not_called()

    def test_attach_belong_boards_skips_provider_when_pipeline_disabled_payload(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()

        context = {
            "market": "cn",
            "status": "not_supported",
            "coverage": {"boards": "not_supported"},
            "boards": {"status": "not_supported", "data": {}},
            "errors": ["fundamental pipeline disabled"],
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("600519", context)

        self.assertEqual(enriched["belong_boards"], [])
        pipeline.fetcher_manager.get_belong_boards.assert_not_called()

    def test_attach_belong_boards_uses_normalized_a_share_code_when_market_missing(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.fetcher_manager.get_belong_boards.return_value = [{"name": "白酒"}]

        context = {
            "status": "ok",
            "coverage": {"boards": "ok"},
            "boards": {"status": "ok", "data": {"top": [], "bottom": []}},
        }

        enriched = pipeline._attach_belong_boards_to_fundamental_context("SH600519", context)

        self.assertEqual(enriched["belong_boards"], [{"name": "白酒"}])
        pipeline.fetcher_manager.get_belong_boards.assert_called_once_with("SH600519")

    def test_attach_chip_to_fundamental_context_adds_snapshot_block(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        chip = ChipDistribution(
            code="600519",
            date="2026-04-24",
            source="tushare.cyq_chips",
            profit_ratio=0.62,
            avg_cost=45.0,
            cost_90_low=40.0,
            cost_90_high=50.0,
            concentration_90=0.11,
            cost_70_low=42.0,
            cost_70_high=48.0,
            concentration_70=0.07,
        )
        quote = MagicMock()
        quote.price = 52.0
        context = {
            "market": "cn",
            "status": "partial",
            "coverage": {"valuation": "ok"},
            "source_chain": [],
        }

        enriched = pipeline._attach_chip_to_fundamental_context("600519", context, chip, quote)

        self.assertIsNot(enriched, context)
        self.assertEqual(enriched["coverage"]["chip"], "ok")
        self.assertTrue(enriched["enhanced_by_tushare"])
        self.assertEqual(enriched["chip"]["data"]["chip_signal"], "supportive")
        self.assertEqual(enriched["chip"]["data"]["data_source"], "tushare.cyq_chips")

    def test_attach_chip_to_fundamental_context_noops_without_chip_data(self) -> None:
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        context = {"market": "cn", "coverage": {"valuation": "ok"}}

        enriched = pipeline._attach_chip_to_fundamental_context("600519", context, None)

        self.assertEqual(enriched, context)
        self.assertNotIn("chip", enriched)

if __name__ == "__main__":
    unittest.main()
