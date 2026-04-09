# -*- coding: utf-8 -*-
"""Service helpers for daily market review markdown reports."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


_REPORT_FILE_RE = re.compile(r"^market_review_(\d{8})\.md$")


class MarketReportService:
    """Read market review markdown files from the reports directory."""

    def __init__(self, reports_dir: Optional[Path] = None) -> None:
        configured_dir = os.getenv("MARKET_REPORTS_DIR", "").strip()
        self.reports_dir = Path(configured_dir) if configured_dir else (
            reports_dir or Path(__file__).resolve().parents[2] / "reports"
        )

    @staticmethod
    def _format_report_date(raw_date: str) -> str:
        return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

    @staticmethod
    def normalize_report_date(report_date: str) -> Optional[str]:
        normalized = (report_date or "").strip().replace("/", "-")
        if re.fullmatch(r"\d{8}", normalized):
            return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            return normalized
        return None

    def _to_item(self, file_path: Path, raw_date: str) -> Dict[str, str]:
        report_date = self._format_report_date(raw_date)
        updated_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        return {
            "date": report_date,
            "title": f"大盘复盘报告 {report_date}",
            "file_name": file_path.name,
            "updated_at": updated_at,
        }

    def list_reports(self) -> List[Dict[str, str]]:
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
        return [self._to_item(file_path, raw_date) for raw_date, file_path in items]

    def get_report(self, report_date: str) -> Optional[Dict[str, str]]:
        normalized_date = self.normalize_report_date(report_date)
        if not normalized_date:
            return None

        file_name = f"market_review_{normalized_date.replace('-', '')}.md"
        file_path = self.reports_dir / file_name
        if not file_path.exists() or not file_path.is_file():
            return None

        item = self._to_item(file_path, normalized_date.replace("-", ""))
        item["content"] = file_path.read_text(encoding="utf-8")
        return item
