# -*- coding: utf-8 -*-
"""Regression tests for AgentOrchestrator sniper point fallbacks."""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext


class TestAgentOrchestratorSniperFallback(unittest.TestCase):
    def test_secondary_buy_does_not_duplicate_ideal_buy(self):
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="301308", stock_name="江波龙")

        payload = {
            "decision_type": "buy",
            "analysis_summary": "趋势仍强，等待回踩。",
            "dashboard": {
                "key_levels": {
                    "support": 301.61,
                    "stop_loss": 295.0,
                    "resistance": 340.44,
                }
            },
        }

        normalized = orch._normalize_dashboard_payload(payload, ctx)

        self.assertIsNotNone(normalized)
        sniper = normalized["dashboard"]["battle_plan"]["sniper_points"]
        self.assertEqual(sniper["ideal_buy"], 301.61)
        self.assertEqual(sniper["secondary_buy"], "N/A")

    def test_secondary_buy_numeric_string_does_not_duplicate_ideal_buy(self):
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="301308", stock_name="江波龙")

        payload = {
            "decision_type": "buy",
            "analysis_summary": "趋势仍强，等待回踩。",
            "dashboard": {
                "battle_plan": {
                    "sniper_points": {
                        "secondary_buy": "301.61",
                    }
                },
                "key_levels": {
                    "support": 301.61,
                    "stop_loss": 295.0,
                    "resistance": 340.44,
                },
            },
        }

        normalized = orch._normalize_dashboard_payload(payload, ctx)

        self.assertIsNotNone(normalized)
        sniper = normalized["dashboard"]["battle_plan"]["sniper_points"]
        self.assertEqual(sniper["ideal_buy"], 301.61)
        self.assertEqual(sniper["secondary_buy"], "N/A")

    def test_secondary_buy_uses_add_on_breakout_alias(self):
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="002534", stock_name="西子洁能")

        payload = {
            "decision_type": "watch",
            "analysis_summary": "等待回踩或放量突破。",
            "dashboard": {
                "key_levels": {
                    "buy_zone": "16.50 - 16.60",
                    "add_on_breakout": "17.66",
                    "stop_loss": "15.70",
                }
            },
        }

        normalized = orch._normalize_dashboard_payload(payload, ctx)

        self.assertIsNotNone(normalized)
        sniper = normalized["dashboard"]["battle_plan"]["sniper_points"]
        self.assertEqual(sniper["ideal_buy"], "16.50 - 16.60")
        self.assertEqual(sniper["secondary_buy"], 17.66)
        self.assertEqual(sniper["stop_loss"], 15.7)

    def test_chinese_key_levels_aliases_fill_canonical_fields(self):
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="603986", stock_name="兆易创新")

        payload = {
            "decision_type": "reduce",
            "analysis_summary": "反弹承压，控制仓位。",
            "dashboard": {
                "key_levels": {
                    "支撑位": "254.0 (MA5)",
                    "阻力位": "269.9 (MA20/前期套牢密集区)",
                    "止损位": "248.0 (近期结构低点/箱体下沿)",
                }
            },
        }

        normalized = orch._normalize_dashboard_payload(payload, ctx)

        self.assertIsNotNone(normalized)
        sniper = normalized["dashboard"]["battle_plan"]["sniper_points"]
        self.assertEqual(sniper["ideal_buy"], "254.0 (MA5)")
        self.assertEqual(sniper["secondary_buy"], "N/A")
        self.assertEqual(sniper["stop_loss"], "248.0 (近期结构低点/箱体下沿)")
        self.assertEqual(sniper["take_profit"], "269.9 (MA20/前期套牢密集区)")


if __name__ == "__main__":
    unittest.main()
