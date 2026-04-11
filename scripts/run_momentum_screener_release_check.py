# -*- coding: utf-8 -*-
"""Momentum Screener release readiness check."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.momentum_screener_service import MomentumScreenerService
from src.auth import is_auth_enabled


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run release checks for Momentum Screener.")
    parser.add_argument("--profile", default="standard", choices=["standard", "aggressive"])
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--min-change-pct", type=float, default=7.0)
    parser.add_argument("--min-amount-yi", type=float, default=3.0)
    parser.add_argument("--min-turnover", type=float, default=3.0)
    parser.add_argument("--trade-date", default="", help="Optional trade date in YYYYMMDD or YYYY-MM-DD")
    return parser


def _print_check(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "BLOCKED"
    print(f"[{status}] {name}: {detail}")


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    first = result["results"][0] if result.get("results") else None
    return {
        "profile": result.get("profile"),
        "trade_date": result.get("trade_date"),
        "candidate_count": result.get("candidate_count"),
        "top_result": None if first is None else {
            "ts_code": first.get("ts_code"),
            "name": first.get("name"),
            "rank_score": first.get("rank_score"),
            "continuation_score": first.get("continuation_score"),
            "extension_score": first.get("extension_score"),
            "risk_score": first.get("risk_score"),
            "buyability_score": first.get("buyability_score"),
            "themes": first.get("themes"),
            "leader_level": first.get("leader_level"),
        },
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    tushare_token = os.getenv("TUSHARE_TOKEN", "").strip()
    smoke_password = os.getenv("DSA_WEB_SMOKE_PASSWORD", "").strip()
    auth_enabled = is_auth_enabled()

    _print_check("TUSHARE_TOKEN", bool(tushare_token), "configured" if tushare_token else "missing")
    if auth_enabled:
        _print_check(
            "DSA_WEB_SMOKE_PASSWORD",
            bool(smoke_password),
            "configured" if smoke_password else "missing; Playwright smoke will be skipped when auth is enabled",
        )
    else:
        _print_check("DSA_WEB_SMOKE_PASSWORD", True, "not required; ADMIN_AUTH_ENABLED is false")

    if not tushare_token:
        print("\nReal data check skipped: set TUSHARE_TOKEN then rerun this script.")
        return 0

    service = MomentumScreenerService()
    result = service.screen(
        profile=args.profile,
        top_n=args.top_n,
        min_change_pct=args.min_change_pct,
        min_amount=args.min_amount_yi * 1e8,
        min_turnover=args.min_turnover,
        trade_date=args.trade_date or None,
    )
    print("\nMomentum Screener real-data check summary:")
    print(json.dumps(_summarize(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
