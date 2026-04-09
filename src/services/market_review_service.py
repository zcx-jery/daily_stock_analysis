# -*- coding: utf-8 -*-
"""Structured helpers for daily market review markdown reports."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


_REPORT_FILE_RE = re.compile(r"^market_review_(\d{8})\.md$")
_SENTIMENT_LABELS = {
    "📉": "弱势调整",
    "📈": "强势上涨",
    "➡️": "震荡整理",
    "➡": "震荡整理",
}
_INDEX_FIELD_MAP = {
    "上证指数": ("shanghai_index", "shanghai_change"),
    "深证成指": ("shenzhen_index", "shenzhen_change"),
    "创业板指": ("chi_index", "chi_change"),
}


class MarketReviewService:
    """Read and parse structured data from market review markdown reports."""

    def __init__(self, reports_dir: Optional[Path] = None) -> None:
        configured_dir = os.getenv("MARKET_REPORTS_DIR", "").strip()
        self.reports_dir = Path(configured_dir) if configured_dir else (
            reports_dir or Path(__file__).resolve().parents[2] / "reports"
        )

    @staticmethod
    def normalize_report_date(report_date: str) -> Optional[str]:
        normalized = (report_date or "").strip().replace("/", "-")
        if re.fullmatch(r"\d{8}", normalized):
            return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            return normalized
        return None

    @staticmethod
    def _format_report_date(raw_date: str) -> str:
        return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

    @staticmethod
    def _extract_sentiment(content: str) -> tuple[str, str]:
        match = re.search(r"📉|📈|➡️|➡", content)
        if not match:
            return "➡️", _SENTIMENT_LABELS["➡️"]
        sentiment = match.group(0)
        return sentiment, _SENTIMENT_LABELS.get(sentiment, _SENTIMENT_LABELS["➡️"])

    @staticmethod
    def _extract_title(content: str, report_date: str) -> str:
        title_match = re.search(r"^##\s*(?:📉|📈|➡️|➡)?\s*(.+?)\s*$", content, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()
        return f"{report_date} 大盘复盘"

    @staticmethod
    def _parse_change_percent(change_text: str) -> Optional[float]:
        match = re.search(r"([+-]?\d+(?:\.\d+)?)", change_text)
        if not match:
            return None
        return float(match.group(1))

    @classmethod
    def parse_market_review_content(cls, content: str) -> Dict[str, object]:
        result: Dict[str, object] = {
            "shanghai_index": None,
            "shanghai_change": None,
            "shenzhen_index": None,
            "shenzhen_change": None,
            "chi_index": None,
            "chi_change": None,
            "total_volume": None,
            "rising_count": None,
            "falling_count": None,
            "limit_up": None,
            "limit_down": None,
            "top_sectors": [],
            "bottom_sectors": [],
            "strategy": None,
        }

        index_pattern = re.compile(
            r"\|\s*(上证指数|深证成指|创业板指)\s*\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|",
        )
        for match in index_pattern.finditer(content):
            field_name, change_name = _INDEX_FIELD_MAP[match.group(1)]
            result[field_name] = float(match.group(2))
            result[change_name] = cls._parse_change_percent(match.group(3))

        summary_pattern = re.compile(
            r"上涨\s*\*\*(\d+)\*\*\s*家.*?"
            r"下跌\s*\*\*(\d+)\*\*\s*家.*?"
            r"涨停\s*\*\*(\d+)\*\*.*?"
            r"跌停\s*\*\*(\d+)\*\*.*?"
            r"成交额\s*\*\*(\d+(?:\.\d+)?)\*\*\s*亿",
            re.S,
        )
        summary_match = summary_pattern.search(content)
        if summary_match:
            result["rising_count"] = int(summary_match.group(1))
            result["falling_count"] = int(summary_match.group(2))
            result["limit_up"] = int(summary_match.group(3))
            result["limit_down"] = int(summary_match.group(4))
            result["total_volume"] = float(summary_match.group(5))

        top_match = re.search(r"领涨:\s*(.+)", content)
        if top_match:
            result["top_sectors"] = [
                f"{name.strip()}({pct})"
                for name, pct in re.findall(r"\*\*([^*]+)\*\*\(([+-]?\d+(?:\.\d+)?%)\)", top_match.group(1))
            ]

        bottom_match = re.search(r"领跌:\s*(.+)", content)
        if bottom_match:
            result["bottom_sectors"] = [
                f"{name.strip()}({pct})"
                for name, pct in re.findall(r"\*\*([^*]+)\*\*\(([+-]?\d+(?:\.\d+)?%)\)", bottom_match.group(1))
            ]

        strategy_match = re.search(r"当前判定为\*\*(.+?)\*\*阶段", content)
        if strategy_match:
            result["strategy"] = strategy_match.group(1).strip()

        return result

    def _iter_report_files(self) -> List[tuple[str, Path]]:
        if not self.reports_dir.exists() or not self.reports_dir.is_dir():
            return []

        items = []
        for file_path in self.reports_dir.iterdir():
            if not file_path.is_file():
                continue
            match = _REPORT_FILE_RE.fullmatch(file_path.name)
            if not match:
                continue
            items.append((match.group(1), file_path))

        items.sort(key=lambda item: item[0], reverse=True)
        return items

    def list_reviews(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, object]]:
        items: List[Dict[str, object]] = []
        normalized_start = self.normalize_report_date(start_date) if start_date else None
        normalized_end = self.normalize_report_date(end_date) if end_date else None

        for raw_date, file_path in self._iter_report_files():
            report_date = self._format_report_date(raw_date)
            if normalized_start and report_date < normalized_start:
                continue
            if normalized_end and report_date > normalized_end:
                continue

            content = file_path.read_text(encoding="utf-8")
            sentiment, sentiment_label = self._extract_sentiment(content)
            items.append(
                {
                    "report_date": report_date,
                    "title": self._extract_title(content, report_date),
                    "sentiment": sentiment,
                    "sentiment_label": sentiment_label,
                    "file_size": file_path.stat().st_size,
                }
            )
            if len(items) >= max(limit, 0):
                break

        return items

    def get_review(self, report_date: str) -> Optional[Dict[str, object]]:
        normalized_date = self.normalize_report_date(report_date)
        if not normalized_date:
            return None

        file_name = f"market_review_{normalized_date.replace('-', '')}.md"
        file_path = self.reports_dir / file_name
        if not file_path.exists() or not file_path.is_file():
            return None

        content = file_path.read_text(encoding="utf-8")
        sentiment, sentiment_label = self._extract_sentiment(content)
        parsed = self.parse_market_review_content(content)

        return {
            "report_date": normalized_date,
            "title": self._extract_title(content, normalized_date),
            "sentiment": sentiment,
            "sentiment_label": sentiment_label,
            **parsed,
            "content": content,
        }
