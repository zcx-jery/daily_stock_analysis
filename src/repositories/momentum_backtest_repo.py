"""Repository helpers for V1 momentum screener backtests."""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List, Optional

from sqlalchemy import and_, delete, desc, select

from src.storage import (
    DatabaseManager,
    MomentumBacktestCandidateRecord,
    MomentumBacktestDailySummary,
    MomentumBacktestDecisionRecord,
    MomentumBacktestOutcomeRecord,
    MomentumBacktestRun,
)


class MomentumBacktestRepository:
    """Database access layer for V1 momentum screener backtests."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def create_run(self, run: MomentumBacktestRun) -> MomentumBacktestRun:
        with self.db.get_session() as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_run(self, run_id: str) -> Optional[MomentumBacktestRun]:
        with self.db.get_session() as session:
            return session.execute(
                select(MomentumBacktestRun)
                .where(MomentumBacktestRun.run_id == run_id)
                .limit(1)
            ).scalar_one_or_none()

    def update_run(self, run_id: str, **fields) -> Optional[MomentumBacktestRun]:
        with self.db.get_session() as session:
            run = session.execute(
                select(MomentumBacktestRun)
                .where(MomentumBacktestRun.run_id == run_id)
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

    def replace_daily_summary(self, summary: MomentumBacktestDailySummary) -> None:
        with self.db.get_session() as session:
            session.execute(
                delete(MomentumBacktestDailySummary).where(
                    and_(
                        MomentumBacktestDailySummary.run_id == summary.run_id,
                        MomentumBacktestDailySummary.trade_date == summary.trade_date,
                    )
                )
            )
            session.add(summary)
            session.commit()

    def replace_candidate_records(
        self,
        *,
        run_id: str,
        trade_date: date,
        records: Iterable[MomentumBacktestCandidateRecord],
    ) -> int:
        return self._replace_records(
            model=MomentumBacktestCandidateRecord,
            run_id=run_id,
            trade_date=trade_date,
            records=list(records),
        )

    def replace_decision_records(
        self,
        *,
        run_id: str,
        trade_date: date,
        records: Iterable[MomentumBacktestDecisionRecord],
    ) -> int:
        return self._replace_records(
            model=MomentumBacktestDecisionRecord,
            run_id=run_id,
            trade_date=trade_date,
            records=list(records),
        )

    def replace_outcome_records(
        self,
        *,
        run_id: str,
        trade_date: date,
        records: Iterable[MomentumBacktestOutcomeRecord],
    ) -> int:
        return self._replace_records(
            model=MomentumBacktestOutcomeRecord,
            run_id=run_id,
            trade_date=trade_date,
            records=list(records),
        )

    def list_daily_summaries(self, run_id: str) -> List[MomentumBacktestDailySummary]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(MomentumBacktestDailySummary)
                .where(MomentumBacktestDailySummary.run_id == run_id)
                .order_by(desc(MomentumBacktestDailySummary.trade_date))
            ).scalars().all()
            return list(rows)

    def get_daily_summary(self, run_id: str, trade_date: date) -> Optional[MomentumBacktestDailySummary]:
        with self.db.get_session() as session:
            return session.execute(
                select(MomentumBacktestDailySummary)
                .where(
                    and_(
                        MomentumBacktestDailySummary.run_id == run_id,
                        MomentumBacktestDailySummary.trade_date == trade_date,
                    )
                )
                .limit(1)
            ).scalar_one_or_none()

    def list_candidate_records(
        self,
        run_id: str,
        trade_date: date,
        *,
        view_scope: Optional[str] = None,
    ) -> List[MomentumBacktestCandidateRecord]:
        with self.db.get_session() as session:
            query = select(MomentumBacktestCandidateRecord).where(
                and_(
                    MomentumBacktestCandidateRecord.run_id == run_id,
                    MomentumBacktestCandidateRecord.trade_date == trade_date,
                )
            )
            if view_scope:
                query = query.where(MomentumBacktestCandidateRecord.view_scope == view_scope)
            rows = session.execute(
                query.order_by(MomentumBacktestCandidateRecord.rank.asc(), MomentumBacktestCandidateRecord.ts_code.asc())
            ).scalars().all()
            return list(rows)

    def list_candidate_records_for_run(
        self,
        run_id: str,
        *,
        view_scope: Optional[str] = None,
    ) -> List[MomentumBacktestCandidateRecord]:
        with self.db.get_session() as session:
            query = select(MomentumBacktestCandidateRecord).where(MomentumBacktestCandidateRecord.run_id == run_id)
            if view_scope:
                query = query.where(MomentumBacktestCandidateRecord.view_scope == view_scope)
            rows = session.execute(
                query.order_by(
                    desc(MomentumBacktestCandidateRecord.trade_date),
                    MomentumBacktestCandidateRecord.rank.asc(),
                    MomentumBacktestCandidateRecord.ts_code.asc(),
                )
            ).scalars().all()
            return list(rows)

    def list_decision_records(self, run_id: str, trade_date: date) -> List[MomentumBacktestDecisionRecord]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(MomentumBacktestDecisionRecord)
                .where(
                    and_(
                        MomentumBacktestDecisionRecord.run_id == run_id,
                        MomentumBacktestDecisionRecord.trade_date == trade_date,
                    )
                )
                .order_by(
                    MomentumBacktestDecisionRecord.rank.asc().nulls_last(),
                    MomentumBacktestDecisionRecord.ts_code.asc(),
                )
            ).scalars().all()
            return list(rows)

    def list_decision_records_for_run(self, run_id: str) -> List[MomentumBacktestDecisionRecord]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(MomentumBacktestDecisionRecord)
                .where(MomentumBacktestDecisionRecord.run_id == run_id)
                .order_by(
                    desc(MomentumBacktestDecisionRecord.trade_date),
                    MomentumBacktestDecisionRecord.rank.asc().nulls_last(),
                    MomentumBacktestDecisionRecord.ts_code.asc(),
                )
            ).scalars().all()
            return list(rows)

    def list_outcomes(
        self,
        run_id: str,
        *,
        trade_date: Optional[date] = None,
        view_scope: Optional[str] = None,
    ) -> List[MomentumBacktestOutcomeRecord]:
        with self.db.get_session() as session:
            query = select(MomentumBacktestOutcomeRecord).where(MomentumBacktestOutcomeRecord.run_id == run_id)
            if trade_date is not None:
                query = query.where(MomentumBacktestOutcomeRecord.trade_date == trade_date)
            if view_scope:
                query = query.where(MomentumBacktestOutcomeRecord.view_scope == view_scope)
            rows = session.execute(
                query.order_by(
                    desc(MomentumBacktestOutcomeRecord.trade_date),
                    MomentumBacktestOutcomeRecord.view_scope.asc(),
                    MomentumBacktestOutcomeRecord.ts_code.asc(),
                )
            ).scalars().all()
            return list(rows)

    def _replace_records(self, *, model, run_id: str, trade_date: date, records: list) -> int:
        with self.db.get_session() as session:
            session.execute(
                delete(model).where(
                    and_(
                        model.run_id == run_id,
                        model.trade_date == trade_date,
                    )
                )
            )
            if records:
                session.add_all(records)
            session.commit()
            return len(records)
