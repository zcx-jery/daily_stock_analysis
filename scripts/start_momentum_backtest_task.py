# -*- coding: utf-8 -*-
"""Start a Momentum Screener V1 backtest task via API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a Momentum Screener V1 backtest task through the HTTP API.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("DSA_BASE_URL", "http://163.7.12.193"),
        help="Backtest API base URL, default reads DSA_BASE_URL or falls back to the test server.",
    )
    parser.add_argument("--start-trade-date", required=True, help="Backtest start trade date, YYYY-MM-DD.")
    parser.add_argument("--end-trade-date", required=True, help="Backtest end trade date, YYYY-MM-DD.")
    parser.add_argument("--profile", default="standard", choices=["standard", "aggressive"])
    parser.add_argument("--top-n", type=int, default=30, help="Compatible field; V1 server will normalize to Top30.")
    parser.add_argument(
        "--strict-strategy-health",
        action="store_true",
        help="Enable strict 20/60 window replay and wait for final strategy-health results per trade date.",
    )
    parser.add_argument("--timeout", type=int, default=120, help="HTTP request timeout in seconds.")
    return parser


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "start_trade_date": args.start_trade_date,
        "end_trade_date": args.end_trade_date,
        "profile": args.profile,
        "top_n": args.top_n,
        "strict_strategy_health": bool(args.strict_strategy_health),
    }


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    payload = _build_payload(args)
    endpoint = args.base_url.rstrip("/") + "/api/v1/stocks/screener/momentum/backtests"

    try:
        result = _post_json(endpoint, payload, timeout=args.timeout)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} when creating backtest task:", file=sys.stderr)
        print(detail, file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Failed to connect to {endpoint}: {exc}", file=sys.stderr)
        return 1

    run = result.get("run") or {}
    summary = {
        "created_new": result.get("created_new"),
        "message": result.get("message"),
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "strategy_health_mode": run.get("strategy_health_mode"),
        "start_trade_date": run.get("start_trade_date"),
        "end_trade_date": run.get("end_trade_date"),
        "total_trade_dates": run.get("total_trade_dates"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
