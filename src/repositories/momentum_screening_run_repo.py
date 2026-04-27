"""Repository helpers for taskized momentum screening runs."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import delete, desc, func, select

from src.storage import DatabaseManager, MomentumScreeningRun


class MomentumScreeningRunRepository:
    """Database access layer for momentum screening runs."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def create_run(self, run: MomentumScreeningRun) -> MomentumScreeningRun:
        with self.db.get_session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_run(self, run_id: str) -> Optional[MomentumScreeningRun]:
        with self.db.get_session() as session:
            return session.execute(
                select(MomentumScreeningRun)
                .where(MomentumScreeningRun.run_id == run_id)
                .limit(1)
            ).scalar_one_or_none()

    def list_runs(
        self,
        *,
        limit: int = 10,
        profile: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        ascending: bool = False,
    ) -> List[MomentumScreeningRun]:
        with self.db.get_session() as session:
            query = select(MomentumScreeningRun)
            if profile:
                query = query.where(MomentumScreeningRun.profile == profile)
            if statuses:
                query = query.where(MomentumScreeningRun.status.in_(list(statuses)))
            order_by = (
                (MomentumScreeningRun.created_at.asc(), MomentumScreeningRun.id.asc())
                if ascending
                else (desc(MomentumScreeningRun.created_at), desc(MomentumScreeningRun.id))
            )
            rows = session.execute(query.order_by(*order_by).limit(limit)).scalars().all()
            return list(rows)

    def count_runs(
        self,
        *,
        profile: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
    ) -> int:
        with self.db.get_session() as session:
            query = select(func.count()).select_from(MomentumScreeningRun)
            if profile:
                query = query.where(MomentumScreeningRun.profile == profile)
            if statuses:
                query = query.where(MomentumScreeningRun.status.in_(list(statuses)))
            return int(session.execute(query).scalar_one() or 0)

    def get_first_run_by_statuses(
        self,
        statuses: Sequence[str],
        *,
        profile: Optional[str] = None,
        ascending: bool = True,
    ) -> Optional[MomentumScreeningRun]:
        with self.db.get_session() as session:
            query = select(MomentumScreeningRun).where(MomentumScreeningRun.status.in_(list(statuses)))
            if profile:
                query = query.where(MomentumScreeningRun.profile == profile)
            order_by = (
                (MomentumScreeningRun.created_at.asc(), MomentumScreeningRun.id.asc())
                if ascending
                else (MomentumScreeningRun.created_at.desc(), MomentumScreeningRun.id.desc())
            )
            return session.execute(query.order_by(*order_by).limit(1)).scalar_one_or_none()

    def find_run_by_fingerprint(self, request_fingerprint: str) -> Optional[MomentumScreeningRun]:
        with self.db.get_session() as session:
            return session.execute(
                select(MomentumScreeningRun)
                .where(MomentumScreeningRun.request_fingerprint == request_fingerprint)
                .order_by(desc(MomentumScreeningRun.created_at), desc(MomentumScreeningRun.id))
                .limit(1)
            ).scalar_one_or_none()

    def reset_running_runs_to_queued(self) -> int:
        with self.db.get_session() as session:
            rows = session.execute(
                select(MomentumScreeningRun).where(MomentumScreeningRun.status == "running")
            ).scalars().all()
            count = 0
            now = datetime.now()
            for row in rows:
                if bool(getattr(row, "cancel_requested", False)):
                    row.status = "cancelled"
                    row.current_stage_key = "cancelled"
                    row.current_stage_label = "任务已取消"
                    row.error_message = "任务在服务重启前已请求取消，已停止继续执行。"
                    row.finished_at = now
                else:
                    row.status = "queued"
                    row.current_stage_key = "queued"
                    row.current_stage_label = "等待后台调度"
                    row.finished_at = None
                row.cancel_requested = False
                row.started_at = None
                row.updated_at = now
                count += 1
            if count:
                session.commit()
            return count

    def update_run(self, run_id: str, **fields) -> Optional[MomentumScreeningRun]:
        with self.db.get_session() as session:
            run = session.execute(
                select(MomentumScreeningRun)
                .where(MomentumScreeningRun.run_id == run_id)
                .limit(1)
            ).scalar_one_or_none()
            if run is None:
                return None
            for key, value in fields.items():
                setattr(run, key, value)
            run.updated_at = datetime.now()
            session.commit()
            session.refresh(run)
            return run

    def delete_run(self, run_id: str) -> bool:
        with self.db.get_session() as session:
            run = session.execute(
                select(MomentumScreeningRun)
                .where(MomentumScreeningRun.run_id == run_id)
                .limit(1)
            ).scalar_one_or_none()
            if run is None:
                return False
            session.execute(delete(MomentumScreeningRun).where(MomentumScreeningRun.run_id == run_id))
            session.commit()
            return True
