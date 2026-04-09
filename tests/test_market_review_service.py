# -*- coding: utf-8 -*-
"""Tests for structured market review parsing."""

import tempfile
import unittest
from pathlib import Path

from src.services.market_review_service import MarketReviewService


SAMPLE_REPORT = """# 🎯 大盘复盘

## 📉 2026-04-09 大盘复盘

### 一、市场总结
> 📈 上涨 **1140** 家 / 下跌 **4299** 家 / 平盘 **52** 家 | 涨停 **64** / 跌停 **14** | 成交额 **21473** 亿

### 二、指数点评
| 指数 | 最新 | 涨跌幅 | 成交额(亿) |
|------|------|--------|-----------|
| 上证指数 | 3966.17 | 🔴 -0.72% | 9025 |
| 深证成指 | 13996.27 | 🔴 -0.33% | 12316 |
| 创业板指 | 3323.30 | 🔴 -0.73% | 5748 |

### 四、热点解读
> 🔥 领涨: **通信线缆及配套**(+4.37%) | **激光设备**(+2.99%)
> 💧 领跌: **文字媒体**(-5.22%) | **光伏加工设备**(-4.02%)

### 七、策略计划
当前判定为**均衡偏防守**阶段。
"""


class MarketReviewServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reports_dir = Path(self.temp_dir.name) / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "market_review_20260409.md").write_text(
            SAMPLE_REPORT,
            encoding="utf-8",
        )
        self.service = MarketReviewService(reports_dir=self.reports_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_list_reviews_returns_structured_summary(self) -> None:
        items = self.service.list_reviews()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["report_date"], "2026-04-09")
        self.assertEqual(items[0]["sentiment"], "📉")
        self.assertEqual(items[0]["sentiment_label"], "弱势调整")
        self.assertEqual(items[0]["title"], "2026-04-09 大盘复盘")

    def test_get_review_returns_parsed_detail(self) -> None:
        item = self.service.get_review("2026-04-09")

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["shanghai_index"], 3966.17)
        self.assertEqual(item["shenzhen_change"], -0.33)
        self.assertEqual(item["rising_count"], 1140)
        self.assertEqual(item["limit_down"], 14)
        self.assertEqual(item["top_sectors"], ["通信线缆及配套(+4.37%)", "激光设备(+2.99%)"])
        self.assertEqual(item["bottom_sectors"], ["文字媒体(-5.22%)", "光伏加工设备(-4.02%)"])
        self.assertEqual(item["strategy"], "均衡偏防守")


if __name__ == "__main__":
    unittest.main()
