# -*- coding: utf-8 -*-
"""Tests for market review report loading."""

import tempfile
import unittest
from pathlib import Path

from src.services.market_report_service import MarketReportService


class MarketReportServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reports_dir = Path(self.temp_dir.name) / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "market_review_20260401.md").write_text(
            "# 2026-04-01\n\n市场情绪回暖。",
            encoding="utf-8",
        )
        (self.reports_dir / "market_review_20260331.md").write_text(
            "# 2026-03-31\n\n市场震荡整理。",
            encoding="utf-8",
        )
        (self.reports_dir / "ignore_me.md").write_text("ignored", encoding="utf-8")
        self.service = MarketReportService(reports_dir=self.reports_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_reports_returns_sorted_items(self) -> None:
        items = self.service.list_reports()

        self.assertEqual([item["date"] for item in items], ["2026-04-01", "2026-03-31"])
        self.assertEqual(items[0]["title"], "大盘复盘报告 2026-04-01")
        self.assertEqual(items[0]["file_name"], "market_review_20260401.md")

    def test_get_report_returns_markdown_content(self) -> None:
        item = self.service.get_report("2026-04-01")

        self.assertIsNotNone(item)
        self.assertEqual(item["date"], "2026-04-01")
        self.assertIn("市场情绪回暖。", item["content"])

    def test_get_report_accepts_compact_date(self) -> None:
        item = self.service.get_report("20260401")

        self.assertIsNotNone(item)
        self.assertEqual(item["date"], "2026-04-01")

    def test_get_report_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.service.get_report("2026-04-30"))


if __name__ == "__main__":
    unittest.main()
