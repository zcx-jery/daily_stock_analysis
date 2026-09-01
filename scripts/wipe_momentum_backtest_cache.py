"""Verify or wipe local Momentum V1.3 backtest cache records."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_config  # noqa: E402


def verify_configured_sqlite(*, full_integrity: bool = False) -> dict:
    db_url = get_config().get_db_url()
    url = make_url(db_url)
    if url.get_backend_name() != "sqlite":
        return {"ok": True, "skipped": True, "reason": "non_sqlite", "database": str(url)}
    database = url.database or ""
    if database in {"", ":memory:"}:
        return {"ok": True, "skipped": True, "reason": "memory_or_empty_sqlite", "database": database}
    db_path = Path(database)
    if db_path.exists() and db_path.stat().st_size > 512 * 1024 * 1024 and not full_integrity:
        return {
            "ok": True,
            "skipped": True,
            "reason": "database_too_large_for_default_integrity_check",
            "database": database,
            "size_bytes": db_path.stat().st_size,
            "hint": "rerun with --full-integrity if you need a full PRAGMA integrity_check",
        }
    connection = sqlite3.connect(database, timeout=5.0)
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    messages = [str(row[0]) for row in rows if row and row[0] is not None]
    return {
        "ok": bool(messages) and all(message.lower() == "ok" for message in messages),
        "skipped": False,
        "messages": messages,
        "database": database,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or wipe local momentum backtest cache.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run SQLite PRAGMA integrity_check and print the result.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of local momentum backtest runs and artifacts.",
    )
    parser.add_argument(
        "--full-integrity",
        action="store_true",
        help="Run full PRAGMA integrity_check even for large SQLite files.",
    )
    args = parser.parse_args()

    if args.verify_only:
        print(json.dumps(verify_configured_sqlite(full_integrity=args.full_integrity), ensure_ascii=False, indent=2))
        return 0

    if not args.yes:
        print("Refusing to wipe cache without --yes. Use --verify-only to inspect integrity.", file=sys.stderr)
        return 2

    from src.repositories.momentum_backtest_repo import MomentumBacktestRepository
    from src.services.momentum_backtest_service import MomentumBacktestService

    repository = MomentumBacktestRepository()
    service = MomentumBacktestService(repository=repository, start_worker=False)
    print(json.dumps(service.wipe_and_rebuild_local_backtest_cache(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
