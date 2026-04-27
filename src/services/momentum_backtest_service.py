"""V1 momentum screener backtest service."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

import pandas as pd

from src.repositories.momentum_backtest_repo import MomentumBacktestRepository
from src.services.momentum_screener_service import (
    MOMENTUM_DEFAULT_TOP_N,
    MOMENTUM_ENTRY_BASELINE_VERSION,
    MOMENTUM_MARKET_SCOPE_VERSION,
    MomentumScreenerService,
)
from src.services.momentum_secondary_decision_service import (
    STRATEGY_HEALTH_MODE_CACHED_ONLY,
    STRATEGY_HEALTH_MODE_DEFAULT,
    STRATEGY_HEALTH_MODE_STRICT_FINAL,
    MomentumSecondaryDecisionService,
)
from src.storage import (
    MomentumBacktestCandidateRecord,
    MomentumBacktestDailySummary,
    MomentumBacktestDecisionRecord,
    MomentumBacktestOutcomeRecord,
    MomentumBacktestRun,
)

logger = logging.getLogger(__name__)

MOMENTUM_BACKTEST_ENGINE_VERSION = "v1"
MOMENTUM_BACKTEST_OFFICIAL_PROFILE = "standard"
MOMENTUM_BACKTEST_OFFICIAL_TOP_N = MOMENTUM_DEFAULT_TOP_N
MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_CACHED_ONLY = STRATEGY_HEALTH_MODE_CACHED_ONLY
MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL = STRATEGY_HEALTH_MODE_STRICT_FINAL
MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_LABELS = {
    MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_CACHED_ONLY: "兼容缓存口径",
    MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL: "严格 final 口径",
}
REGIME_LABELS = {
    "strong": "强市",
    "general": "中性市",
    "weak": "弱市",
}
LAYER_LEVEL_SCORES = {
    "strong": 84.0,
    "general": 62.0,
    "weak": 36.0,
}
GATE_GROUP_LABELS = {
    "market_environment": "市场环境",
    "opportunity_quality": "机会质量",
    "historical_validity": "20日进攻许可",
}
GATE_MODULE_LABELS = {
    "core_premium": "核心溢价",
    "breadth_premium": "广度溢价",
    "index_trend": "指数趋势",
    "profitability": "赚钱效应",
    "sentiment": "市场情绪",
    "theme_breadth": "主线扩散",
    "theme_clarity": "主线清晰度",
    "portfolio_quality": "组合质量",
    "buy_point_clarity": "买点清晰度",
    "role_structure": "角色结构",
    "risk_control": "风险可控度",
    "historical_validity": "20日进攻许可",
    "action_matrix": "鍔ㄤ綔鐭╅樀鏀跺彛",
}
RESTRICTED_ACTION_LEVELS = {"observe_only", "stand_aside"}
ACTIVE_RUN_STATUSES = {"queued", "running"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
RUN_STAGE_LABELS = {
    "queued": "等待后台调度",
    "preparing": "准备回测任务",
    "candidate_pool": "候选池计算中",
    "secondary_decision": "二次决策回放中",
    "outcome_validation": "T+1/T+2 结果验证中",
    "summary_build": "区间汇总生成中",
    "cancel_requested": "取消请求处理中",
    "cancelled": "任务已取消",
    "completed": "任务已完成",
    "failed": "任务执行失败",
}


class _MomentumBacktestCancelled(RuntimeError):
    """Raised when a backtest run is cancelled by the user."""


@dataclass
class _ReplayDayArtifacts:
    screening: Dict[str, Any]
    decision: Dict[str, Any]
    daily_summary: MomentumBacktestDailySummary
    candidate_records: List[MomentumBacktestCandidateRecord]
    decision_records: List[MomentumBacktestDecisionRecord]
    outcome_records: List[MomentumBacktestOutcomeRecord]


class MomentumBacktestService:
    """Replay the V1 momentum screener over historical trade dates."""

    def __init__(
        self,
        screener_service: Optional[MomentumScreenerService] = None,
        decision_service: Optional[MomentumSecondaryDecisionService] = None,
        repository: Optional[MomentumBacktestRepository] = None,
    ) -> None:
        self.screener_service = screener_service or MomentumScreenerService()
        self.decision_service = decision_service or MomentumSecondaryDecisionService(
            screener_service=self.screener_service,
        )
        self.repository = repository or MomentumBacktestRepository()
        self.stage_heartbeat_interval_seconds = 5.0
        self._run_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._worker_wake_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="momentum-backtest-queue",
            daemon=True,
        )
        requeued_count = self.repository.reset_running_runs_to_queued()
        if requeued_count:
            logger.info("Recovered %s running backtest run(s) back into the queue", requeued_count)
        self._worker_thread.start()

    def create_run(
        self,
        *,
        start_trade_date: str,
        end_trade_date: str,
        profile: str = MOMENTUM_BACKTEST_OFFICIAL_PROFILE,
        top_n: int = MOMENTUM_BACKTEST_OFFICIAL_TOP_N,
        strict_strategy_health: bool = False,
    ) -> Dict[str, Any]:
        profile = MOMENTUM_BACKTEST_OFFICIAL_PROFILE
        top_n = MOMENTUM_BACKTEST_OFFICIAL_TOP_N
        strategy_health_mode = self._normalize_strategy_health_mode(strict_strategy_health)
        run, trade_dates, _meta = self._create_or_reuse_run(
            start_trade_date=start_trade_date,
            end_trade_date=end_trade_date,
            profile=profile,
            top_n=top_n,
            strategy_health_mode=strategy_health_mode,
            allow_reuse=False,
            prefer_running=False,
        )
        self.repository.update_run(
            run.run_id,
            status="running",
            current_stage_key="preparing",
            current_stage_label=RUN_STAGE_LABELS["preparing"],
            heartbeat_at=datetime.now(),
            started_at=datetime.now(),
            finished_at=None,
            cancel_requested=False,
            error_message=None,
        )
        self._execute_run(
            run_id=run.run_id,
            trade_dates=trade_dates,
            profile=profile,
            top_n=top_n,
            strategy_health_mode=strategy_health_mode,
        )
        return self.get_run(run.run_id)

    def create_run_async(
        self,
        *,
        start_trade_date: str,
        end_trade_date: str,
        profile: str = MOMENTUM_BACKTEST_OFFICIAL_PROFILE,
        top_n: int = MOMENTUM_BACKTEST_OFFICIAL_TOP_N,
        strict_strategy_health: bool = False,
    ) -> Dict[str, Any]:
        profile = MOMENTUM_BACKTEST_OFFICIAL_PROFILE
        top_n = MOMENTUM_BACKTEST_OFFICIAL_TOP_N
        strategy_health_mode = self._normalize_strategy_health_mode(strict_strategy_health)
        run, _trade_dates, meta = self._create_or_reuse_run(
            start_trade_date=start_trade_date,
            end_trade_date=end_trade_date,
            profile=profile,
            top_n=top_n,
            strategy_health_mode=strategy_health_mode,
            allow_reuse=True,
            prefer_running=True,
        )
        self._worker_wake_event.set()
        serialized = self._serialize_run(run)
        return {
            "created_new": meta["created_new"],
            "message": meta["message"],
            "run": serialized,
        }

    def _create_or_reuse_run(
        self,
        *,
        start_trade_date: str,
        end_trade_date: str,
        profile: str,
        top_n: int,
        strategy_health_mode: str,
        allow_reuse: bool,
        prefer_running: bool,
    ) -> Tuple[MomentumBacktestRun, List[date], Dict[str, Any]]:
        profile = MOMENTUM_BACKTEST_OFFICIAL_PROFILE
        top_n = MOMENTUM_BACKTEST_OFFICIAL_TOP_N
        strategy_health_mode = self._normalize_strategy_health_mode(
            strategy_health_mode=strategy_health_mode,
        )

        start_dt = self._parse_trade_date(start_trade_date)
        end_dt = self._parse_trade_date(end_trade_date)
        if start_dt > end_dt:
            raise ValueError("start_trade_date must be earlier than or equal to end_trade_date")

        trade_dates = self._list_trade_dates(start_dt, end_dt)
        if not trade_dates:
            raise ValueError("No trade dates were found in the requested range")

        with self._run_lock:
            if allow_reuse:
                existing = self.repository.find_run_by_params(
                    start_trade_date=start_dt,
                    end_trade_date=end_dt,
                    profile=profile,
                    top_n=top_n,
                    strategy_health_mode=strategy_health_mode,
                    engine_version=MOMENTUM_BACKTEST_ENGINE_VERSION,
                    entry_baseline_version=MOMENTUM_ENTRY_BASELINE_VERSION,
                    market_scope_version=MOMENTUM_MARKET_SCOPE_VERSION,
                    statuses=("queued", "running", "completed"),
                )
                if existing is not None:
                    return (
                        existing,
                        trade_dates,
                        {
                            "created_new": False,
                            "message": "已存在相同参数任务，已为你定位到该任务",
                        },
                    )

            has_running = self.repository.get_first_run_by_statuses(("running",)) is not None
            has_queued = self.repository.get_first_run_by_statuses(("queued",), ascending=True) is not None
            now = datetime.now()
            initial_status = (
                "queued"
                if (allow_reuse and (has_running or has_queued or not prefer_running))
                else "running"
            )
            run = MomentumBacktestRun(
                run_id=f"momentum_bt_{uuid4().hex[:16]}",
                status=initial_status,
                profile=profile,
                engine_version=MOMENTUM_BACKTEST_ENGINE_VERSION,
                strategy_health_mode=strategy_health_mode,
                entry_baseline_version=MOMENTUM_ENTRY_BASELINE_VERSION,
                market_scope_version=MOMENTUM_MARKET_SCOPE_VERSION,
                top_n=top_n,
                start_trade_date=start_dt,
                end_trade_date=end_dt,
                total_trade_dates=len(trade_dates),
                processed_trade_dates=0,
                failed_trade_dates=0,
                current_stage_key="preparing" if initial_status == "running" else "queued",
                current_stage_label=RUN_STAGE_LABELS["preparing"] if initial_status == "running" else RUN_STAGE_LABELS["queued"],
                heartbeat_at=now,
                started_at=now if initial_status == "running" else None,
                finished_at=None,
                cancel_requested=False,
            )
            created = self.repository.create_run(run)
            message = (
                "当前已有任务在运行，你的回测已进入队列"
                if initial_status == "queued"
                else "已创建回测任务，正在后台计算"
            )
            return created, trade_dates, {"created_new": True, "message": message}

    @staticmethod
    def _normalize_strategy_health_mode(
        strict_strategy_health: Optional[bool] = None,
        strategy_health_mode: Optional[str] = None,
    ) -> str:
        if strict_strategy_health is True:
            return MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL
        if strategy_health_mode in {
            MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_CACHED_ONLY,
            MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL,
        }:
            return str(strategy_health_mode)
        return MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_CACHED_ONLY

    @staticmethod
    def _strategy_health_mode_label(strategy_health_mode: Optional[str]) -> str:
        normalized = MomentumBacktestService._normalize_strategy_health_mode(
            strategy_health_mode=strategy_health_mode,
        )
        return MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_LABELS[normalized]

    @staticmethod
    def _should_wait_for_strategy_health(strategy_health_mode: Optional[str]) -> bool:
        normalized = MomentumBacktestService._normalize_strategy_health_mode(
            strategy_health_mode=strategy_health_mode,
        )
        return normalized == MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL

    @staticmethod
    def _decision_strategy_health_mode(strategy_health_mode: Optional[str]) -> str:
        normalized = MomentumBacktestService._normalize_strategy_health_mode(
            strategy_health_mode=strategy_health_mode,
        )
        if normalized == MOMENTUM_BACKTEST_STRATEGY_HEALTH_MODE_STRICT_FINAL:
            return STRATEGY_HEALTH_MODE_STRICT_FINAL
        return STRATEGY_HEALTH_MODE_CACHED_ONLY

    def _worker_loop(self) -> None:
        while not self._shutdown_event.is_set():
            run = self.repository.get_first_run_by_statuses(("running",), ascending=True)
            if run is None:
                run = self._promote_next_queued_run()
            if run is None:
                self._worker_wake_event.wait(timeout=1.0)
                self._worker_wake_event.clear()
                continue
            try:
                trade_dates = self._list_trade_dates(run.start_trade_date, run.end_trade_date)
                if not trade_dates:
                    self.repository.update_run(
                        run.run_id,
                        status="failed",
                        current_stage_key="failed",
                        current_stage_label=RUN_STAGE_LABELS["failed"],
                        finished_at=datetime.now(),
                        error_message="No trade dates were found in the requested range",
                    )
                    continue
                self._execute_run(
                    run_id=run.run_id,
                    trade_dates=trade_dates,
                    profile=run.profile,
                    top_n=run.top_n,
                    strategy_health_mode=self._normalize_strategy_health_mode(
                        strategy_health_mode=getattr(run, "strategy_health_mode", None),
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Momentum backtest worker crashed on run %s: %s", run.run_id, exc)

    def close(self, *, timeout: float = 5.0) -> None:
        self._shutdown_event.set()
        self._worker_wake_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def _promote_next_queued_run(self) -> Optional[MomentumBacktestRun]:
        with self._run_lock:
            run = self.repository.get_first_run_by_statuses(("queued",), ascending=True)
            if run is None:
                return None
            return self.repository.update_run(
                run.run_id,
                status="running",
                current_stage_key="preparing",
                current_stage_label=RUN_STAGE_LABELS["preparing"],
                heartbeat_at=datetime.now(),
                started_at=datetime.now(),
                finished_at=None,
                cancel_requested=False,
                error_message=None,
            )

    def _execute_run(
        self,
        *,
        run_id: str,
        trade_dates: List[date],
        profile: str,
        top_n: int,
        strategy_health_mode: str,
    ) -> None:
        existing_run = self.repository.get_run(run_id)
        if existing_run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        strategy_health_mode = self._normalize_strategy_health_mode(
            strategy_health_mode=strategy_health_mode or getattr(existing_run, "strategy_health_mode", None),
        )

        attempted_count = min(
            max((existing_run.processed_trade_dates or 0) + (existing_run.failed_trade_dates or 0), 0),
            len(trade_dates),
        )
        processed_count = min(existing_run.processed_trade_dates or 0, attempted_count)
        failed_count = min(existing_run.failed_trade_dates or 0, attempted_count - processed_count)
        current_trade_dt: Optional[date] = None
        effective_total_trade_dates = len(trade_dates)
        remaining_trade_dates = trade_dates[attempted_count:]
        if attempted_count > 0:
            current_trade_dt = trade_dates[attempted_count - 1]
        try:
            self.repository.update_run(
                run_id,
                status="running",
                strategy_health_mode=strategy_health_mode,
                total_trade_dates=effective_total_trade_dates,
                processed_trade_dates=processed_count,
                failed_trade_dates=failed_count,
                current_stage_key="preparing",
                current_stage_label=RUN_STAGE_LABELS["preparing"],
                current_trade_date=remaining_trade_dates[0] if remaining_trade_dates else current_trade_dt,
                heartbeat_at=datetime.now(),
                started_at=existing_run.started_at or datetime.now(),
                finished_at=None,
                summary_json=None if attempted_count == 0 else existing_run.summary_json,
                error_message=None,
            )
            for trade_dt in remaining_trade_dates:
                current_trade_dt = trade_dt
                self._raise_if_cancel_requested(run_id)
                try:
                    trade_date = trade_dt.strftime("%Y-%m-%d")
                    request_params = self.decision_service._build_request_params(  # type: ignore[attr-defined]
                        top_n=top_n,
                        trade_date=trade_date,
                        profile=profile,
                    )
                    candidate_pool_label_state = {"value": RUN_STAGE_LABELS["candidate_pool"]}
                    self._update_stage(
                        run_id,
                        stage_key="candidate_pool",
                        trade_dt=trade_dt,
                        stage_label=candidate_pool_label_state["value"],
                    )
                    stop_candidate_pool_heartbeat = self._start_stage_heartbeat(
                        run_id=run_id,
                        stage_key="candidate_pool",
                        trade_dt=trade_dt,
                        label_state=candidate_pool_label_state,
                    )
                    try:
                        screening = self.screener_service.screen(
                            top_n=top_n,
                            trade_date=trade_date,
                            profile=profile,
                        )
                    finally:
                        stop_candidate_pool_heartbeat()
                    screening["_request_params"] = request_params

                    self._raise_if_cancel_requested(run_id)
                    secondary_decision_label_state = {"value": RUN_STAGE_LABELS["secondary_decision"]}
                    self._update_stage(
                        run_id,
                        stage_key="secondary_decision",
                        trade_dt=trade_dt,
                        stage_label=secondary_decision_label_state["value"],
                    )
                    stop_secondary_decision_heartbeat = self._start_stage_heartbeat(
                        run_id=run_id,
                        stage_key="secondary_decision",
                        trade_dt=trade_dt,
                        label_state=secondary_decision_label_state,
                    )
                    try:
                        decision = self.decision_service.build_from_screening(
                            screening,
                            request_params=request_params,
                            wait_for_strategy_health=self._should_wait_for_strategy_health(strategy_health_mode),
                            strategy_health_mode=self._decision_strategy_health_mode(strategy_health_mode),
                            strategy_health_progress_callback=self._build_secondary_decision_progress_callback(
                                run_id=run_id,
                                trade_dt=trade_dt,
                                label_state=secondary_decision_label_state,
                            ),
                        )
                    finally:
                        stop_secondary_decision_heartbeat()

                    self._raise_if_cancel_requested(run_id)
                    outcome_validation_label_state = {"value": RUN_STAGE_LABELS["outcome_validation"]}
                    self._update_stage(
                        run_id,
                        stage_key="outcome_validation",
                        trade_dt=trade_dt,
                        stage_label=outcome_validation_label_state["value"],
                    )
                    stop_outcome_validation_heartbeat = self._start_stage_heartbeat(
                        run_id=run_id,
                        stage_key="outcome_validation",
                        trade_dt=trade_dt,
                        label_state=outcome_validation_label_state,
                    )
                    try:
                        artifacts = self._freeze_trade_date_artifacts(
                            trade_dt=trade_dt,
                            screening=screening,
                            decision=decision,
                        )
                    finally:
                        stop_outcome_validation_heartbeat()
                    artifacts.daily_summary.run_id = run_id
                    for record in artifacts.candidate_records:
                        record.run_id = run_id
                    for record in artifacts.decision_records:
                        record.run_id = run_id
                    for record in artifacts.outcome_records:
                        record.run_id = run_id
                    self.repository.replace_daily_summary(artifacts.daily_summary)
                    self.repository.replace_candidate_records(
                        run_id=run_id,
                        trade_date=trade_dt,
                        records=artifacts.candidate_records,
                    )
                    self.repository.replace_decision_records(
                        run_id=run_id,
                        trade_date=trade_dt,
                        records=artifacts.decision_records,
                    )
                    self.repository.replace_outcome_records(
                        run_id=run_id,
                        trade_date=trade_dt,
                        records=artifacts.outcome_records,
                    )
                    processed_count += 1
                except Exception as exc:  # noqa: BLE001
                    failed_count += 1
                    logger.exception("Momentum backtest replay failed for %s: %s", trade_dt.isoformat(), exc)
                finally:
                    self.repository.update_run(
                        run_id,
                        processed_trade_dates=processed_count,
                        failed_trade_dates=failed_count,
                    )

            self._raise_if_cancel_requested(run_id)
            self._update_stage(
                run_id,
                stage_key="summary_build",
                trade_dt=current_trade_dt,
            )
            summary = self._build_run_summary(run_id)
            status = "completed" if processed_count > 0 else "failed"
            self.repository.update_run(
                run_id,
                status=status,
                processed_trade_dates=processed_count,
                failed_trade_dates=failed_count,
                summary_json=self._dump_json(summary),
                error_message=None if processed_count > 0 else "No trade dates were replayed successfully",
                current_stage_key=status,
                current_stage_label=RUN_STAGE_LABELS[status],
                current_trade_date=current_trade_dt,
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
            )
        except _MomentumBacktestCancelled:
            summary = self._build_run_summary(run_id) if processed_count > 0 else None
            self.repository.update_run(
                run_id,
                status="cancelled",
                processed_trade_dates=processed_count,
                failed_trade_dates=failed_count,
                summary_json=self._dump_json(summary) if summary is not None else None,
                error_message="任务已取消，已保留已完成部分",
                current_stage_key="cancelled",
                current_stage_label=RUN_STAGE_LABELS["cancelled"],
                current_trade_date=current_trade_dt,
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
            )
            logger.info("Momentum backtest run cancelled: %s", run_id)
        except Exception as exc:  # noqa: BLE001
            self.repository.update_run(
                run_id,
                status="failed",
                processed_trade_dates=processed_count,
                failed_trade_dates=failed_count or len(trade_dates),
                error_message=str(exc),
                current_stage_key="failed",
                current_stage_label=RUN_STAGE_LABELS["failed"],
                current_trade_date=current_trade_dt,
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
            )
            raise

    def get_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        return self._serialize_run(run)

    def list_runs(
        self,
        *,
        limit: int = 20,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_limit = min(max(int(limit), 1), 50)
        if profile and profile != MOMENTUM_BACKTEST_OFFICIAL_PROFILE:
            profile = None
        current_running = self.repository.get_first_run_by_statuses(("running",), profile=profile, ascending=True)
        queued_rows = self.repository.list_runs(
            limit=50,
            profile=profile,
            statuses=("queued",),
            ascending=True,
        )
        history_rows = self.repository.list_runs(
            limit=safe_limit,
            profile=profile,
            statuses=("completed", "failed", "cancelled"),
        )
        return {
            "current_running": self._serialize_run(current_running) if current_running else None,
            "queued": {
                "total": self.repository.count_runs(profile=profile, statuses=("queued",)),
                "items": [self._serialize_run(row) for row in queued_rows],
            },
            "history": {
                "total": self.repository.count_runs(
                    profile=profile,
                    statuses=("completed", "failed", "cancelled"),
                ),
                "limit": safe_limit,
                "items": [self._serialize_run(row) for row in history_rows],
            },
            "refreshed_at": datetime.now().isoformat(),
        }

    def cancel_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        if run.status != "running":
            raise ValueError("Only running tasks can be cancelled")
        updated = self.repository.update_run(
            run_id,
            cancel_requested=True,
            current_stage_key="cancel_requested",
            current_stage_label=RUN_STAGE_LABELS["cancel_requested"],
            heartbeat_at=datetime.now(),
        )
        if updated is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        self._worker_wake_event.set()
        payload = self._serialize_run(updated)
        payload["message"] = "任务已取消，已保留已完成部分"
        return payload

    def delete_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        if run.status == "running":
            raise ValueError("Running tasks must be cancelled before deletion")
        deleted = self.repository.delete_run(run_id)
        if not deleted:
            raise ValueError(f"Backtest run not found: {run_id}")
        self._worker_wake_event.set()
        return {
            "run_id": run_id,
            "deleted": True,
            "message": "任务已删除",
        }

    def get_summary(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        summary = self._load_complete_summary(run_id, run.summary_json)
        return {
            "run_id": run.run_id,
            "profile": run.profile,
            "engine_version": run.engine_version,
            "strategy_health_mode": self._normalize_strategy_health_mode(
                strategy_health_mode=getattr(run, "strategy_health_mode", None),
            ),
            "strategy_health_mode_label": self._strategy_health_mode_label(
                getattr(run, "strategy_health_mode", None),
            ),
            "summary": summary,
        }

    def list_daily(
        self,
        run_id: str,
        *,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        market_regime: Optional[str] = None,
        action_level: Optional[str] = None,
        slot: Optional[str] = None,
        theme_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        rows = self.repository.list_daily_summaries(run_id)
        decision_map: Dict[date, List[MomentumBacktestDecisionRecord]] = {}
        if slot or theme_name:
            for record in self.repository.list_decision_records_for_run(run_id):
                decision_map.setdefault(record.trade_date, []).append(record)

        start_dt = self._parse_trade_date(date_from) if date_from else None
        end_dt = self._parse_trade_date(date_to) if date_to else None
        filtered_rows = [
            row
            for row in rows
            if self._daily_row_matches_filters(
                row,
                decisions=decision_map.get(row.trade_date, []),
                start_dt=start_dt,
                end_dt=end_dt,
                market_regime=market_regime,
                action_level=action_level,
                slot=slot,
                theme_name=theme_name,
            )
        ]
        total = len(filtered_rows)
        safe_page = max(1, page)
        safe_page_size = min(max(1, page_size), 200)
        start_index = (safe_page - 1) * safe_page_size
        end_index = start_index + safe_page_size
        page_rows = filtered_rows[start_index:end_index]
        return {
            "run_id": run_id,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "has_more": end_index < total,
            "items": [self._serialize_daily_summary(row) for row in page_rows],
        }

    def get_daily_detail(self, run_id: str, trade_date: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")
        trade_dt = self._parse_trade_date(trade_date)
        daily_row = self.repository.get_daily_summary(run_id, trade_dt)
        if daily_row is None:
            raise ValueError(f"Backtest trade date not found: {trade_date}")

        candidate_rows = self.repository.list_candidate_records(run_id, trade_dt, view_scope="candidate_top10")
        decision_rows = self.repository.list_decision_records(run_id, trade_dt)
        outcome_rows = self.repository.list_outcomes(run_id, trade_date=trade_dt)
        outcome_map = {(row.view_scope, row.ts_code): row for row in outcome_rows}
        candidate_outcomes = [row for row in outcome_rows if row.view_scope == "candidate_top10"]
        decision_outcomes = [row for row in outcome_rows if row.view_scope == "decision_top3"]

        diagnosis = self._build_daily_diagnosis(
            daily_row=daily_row,
            candidate_rows=candidate_rows,
            decision_rows=decision_rows,
            candidate_outcomes=candidate_outcomes,
            decision_outcomes=decision_outcomes,
        )
        return {
            "run_id": run_id,
            "trade_date": trade_dt.isoformat(),
            "daily_context": self._serialize_daily_summary(daily_row),
            "candidate_top10": [
                self._serialize_candidate_record(row, outcome_map.get(("candidate_top10", row.ts_code)))
                for row in candidate_rows
            ],
            "decision_top3": [
                self._serialize_decision_record(row, outcome_map.get(("decision_top3", row.ts_code)))
                for row in decision_rows
            ],
            "slot_view": [
                self._serialize_decision_record(row, outcome_map.get(("decision_top3", row.ts_code)))
                for row in sorted(decision_rows, key=self._slot_sort_key)
            ],
            "outcomes": {
                "candidate_top10": self._build_outcome_group(candidate_outcomes),
                "decision_top3": self._build_outcome_group(decision_outcomes),
            },
            "diagnosis": diagnosis,
            "v13_diagnostics": self._extract_v13_diagnostics_from_daily_row(daily_row),
        }

    def get_issues(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Backtest run not found: {run_id}")

        items: List[Dict[str, Any]] = []
        severity_breakdown = {"critical": 0, "warning": 0, "info": 0}
        key_breakdown: Dict[str, int] = {}

        for daily_row in self.repository.list_daily_summaries(run_id):
            candidate_rows = self.repository.list_candidate_records(
                run_id,
                daily_row.trade_date,
                view_scope="candidate_top10",
            )
            decision_rows = self.repository.list_decision_records(run_id, daily_row.trade_date)
            outcome_rows = self.repository.list_outcomes(run_id, trade_date=daily_row.trade_date)
            candidate_outcomes = [row for row in outcome_rows if row.view_scope == "candidate_top10"]
            decision_outcomes = [row for row in outcome_rows if row.view_scope == "decision_top3"]
            diagnosis = self._build_daily_diagnosis(
                daily_row=daily_row,
                candidate_rows=candidate_rows,
                decision_rows=decision_rows,
                candidate_outcomes=candidate_outcomes,
                decision_outcomes=decision_outcomes,
            )
            for issue in diagnosis["issues"]:
                items.append(
                    {
                        **issue,
                        "trade_date": daily_row.trade_date.isoformat(),
                        "action_level": daily_row.action_level,
                        "action_label": daily_row.action_label,
                    }
                )
                severity = issue["severity"]
                severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1
                key = issue["issue_key"]
                key_breakdown[key] = key_breakdown.get(key, 0) + 1

        items.sort(
            key=lambda item: (
                self._issue_severity_rank(item["severity"]),
                item["trade_date"],
                item["issue_key"],
            ),
            reverse=True,
        )
        return {
            "run_id": run_id,
            "total_issues": len(items),
            "severity_breakdown": severity_breakdown,
            "issue_key_breakdown": key_breakdown,
            "items": items,
        }

    def _freeze_trade_date_artifacts(
        self,
        *,
        trade_dt: date,
        screening: Dict[str, Any],
        decision: Dict[str, Any],
    ) -> _ReplayDayArtifacts:
        ranked_results = list(screening.get("ranked_results") or screening.get("results") or [])
        top_candidates = ranked_results[:10]
        portfolio = list(decision.get("portfolio") or [])
        candidate_diagnostics_by_code = {
            str(item.get("ts_code") or ""): item
            for item in decision.get("candidate_diagnostics") or []
            if isinstance(item, dict) and item.get("ts_code")
        }
        gate_snapshot = self._extract_gate_snapshot(decision)
        gate_blockers = self._build_gate_blockers_from_snapshot(gate_snapshot, decision=decision)

        daily_summary = MomentumBacktestDailySummary(
            run_id="",
            trade_date=trade_dt,
            action_level=str(decision["action"]["level"]),
            action_label=str(decision["action"]["label"]),
            recommendation_cap=str(decision["strategy_health"]["recommendation_cap"]),
            action_checklist_mode=str((decision.get("action_checklist") or {}).get("mode", "disabled")),
            market_environment_level=str(decision["market_environment"]["level"]),
            opportunity_quality_level=str(decision["opportunity_quality"]["level"]),
            historical_validity_level=str(decision["historical_validity"]["level"]),
            candidate_count=int(screening.get("candidate_count") or 0),
            result_count=len(ranked_results),
            selected_count=len(portfolio),
            buy_ready_count=sum(1 for item in portfolio if item.get("suggested_action") == "ready"),
            main_ts_code=self._portfolio_slot_code(portfolio, "main"),
            secondary_ts_code=self._portfolio_slot_code(portfolio, "secondary"),
            watch_ts_code=self._portfolio_slot_code(portfolio, "watch"),
            screening_payload_json=self._dump_json(screening),
            decision_payload_json=self._dump_json(decision),
            diagnosis_json=self._dump_json(
                {
                    "market_environment_level": decision["market_environment"]["level"],
                    "opportunity_quality_level": decision["opportunity_quality"]["level"],
                    "historical_validity_level": decision["historical_validity"]["level"],
                    "gate_snapshot": gate_snapshot,
                    "gate_blockers": gate_blockers,
                }
            ),
        )

        candidate_records = [
            MomentumBacktestCandidateRecord(
                run_id="",
                trade_date=trade_dt,
                view_scope="candidate_top10",
                rank=int(item.get("rank") or 0),
                ts_code=str(item.get("ts_code") or ""),
                name=str(item.get("name") or ""),
                theme=self._first_theme(item),
                role=str(item.get("leader_level") or ""),
                market_segment=str(item.get("market_segment") or ""),
                rank_score=self._to_float(item.get("rank_score")),
                final_score=self._to_float(item.get("final_score")),
                continuation_score=self._to_float(item.get("continuation_score")),
                extension_score=self._to_float(item.get("extension_score")),
                risk_score=self._to_float(item.get("risk_score")),
                buyability_score=self._to_float(item.get("buyability_score")),
                candidate_payload_json=self._dump_json(
                    self._candidate_payload_with_diagnostics(
                        item,
                        candidate_diagnostics_by_code.get(str(item.get("ts_code") or "")),
                    )
                ),
            )
            for item in top_candidates
        ]

        decision_records = [
            MomentumBacktestDecisionRecord(
                run_id="",
                trade_date=trade_dt,
                slot=str(item.get("slot") or ""),
                rank=int(item.get("rank") or 0) if item.get("rank") is not None else None,
                ts_code=str(item.get("ts_code") or ""),
                name=str(item.get("name") or ""),
                theme=str(item.get("theme") or ""),
                role=str(item.get("role") or ""),
                decision_score=self._to_float(item.get("score")),
                rank_score=self._to_float(item.get("rank_score")),
                risk_score=self._to_float(item.get("risk_score")),
                buy_point_status=str(item.get("buy_point_status") or ""),
                suggested_action=str(item.get("suggested_action") or ""),
                entry_range_low=self._to_float(item.get("entry_range_low")),
                entry_range_high=self._to_float(item.get("entry_range_high")),
                opportunity_tag=str(item.get("opportunity_tag") or "") or None,
                decision_payload_json=self._dump_json(item),
            )
            for item in portfolio
        ]

        outcome_records = []
        for item in top_candidates:
            outcome_records.append(
                self._build_outcome_record(
                    trade_dt=trade_dt,
                    item=item,
                    view_scope="candidate_top10",
                    slot=None,
                )
            )
        for item in portfolio:
            outcome_records.append(
                self._build_outcome_record(
                    trade_dt=trade_dt,
                    item=item,
                    view_scope="decision_top3",
                    slot=str(item.get("slot") or ""),
                )
            )

        return _ReplayDayArtifacts(
            screening=screening,
            decision=decision,
            daily_summary=daily_summary,
            candidate_records=candidate_records,
            decision_records=decision_records,
            outcome_records=outcome_records,
        )

    @staticmethod
    def _candidate_payload_with_diagnostics(
        item: Dict[str, Any],
        diagnostics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = dict(item)
        if diagnostics:
            payload["_decision_diagnostics"] = dict(diagnostics)
        return payload

    def _update_stage(
        self,
        run_id: str,
        *,
        stage_key: str,
        trade_dt: Optional[date],
        stage_label: Optional[str] = None,
    ) -> None:
        self.repository.update_run(
            run_id,
            current_stage_key=stage_key,
            current_stage_label=stage_label or RUN_STAGE_LABELS.get(stage_key, stage_key),
            current_trade_date=trade_dt,
            heartbeat_at=datetime.now(),
        )

    def _start_stage_heartbeat(
        self,
        *,
        run_id: str,
        stage_key: str,
        trade_dt: Optional[date],
        label_state: Optional[Dict[str, Any]] = None,
        interval_seconds: Optional[float] = None,
    ):
        stop_event = threading.Event()
        heartbeat_interval_seconds = float(interval_seconds or self.stage_heartbeat_interval_seconds)

        def _heartbeat_loop() -> None:
            while not stop_event.wait(heartbeat_interval_seconds):
                try:
                    stage_label = (
                        str(label_state.get("value"))
                        if isinstance(label_state, dict) and label_state.get("value")
                        else RUN_STAGE_LABELS.get(stage_key, stage_key)
                    )
                    self.repository.update_run(
                        run_id,
                        current_stage_key=stage_key,
                        current_stage_label=stage_label,
                        current_trade_date=trade_dt,
                        heartbeat_at=datetime.now(),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to refresh heartbeat for momentum backtest stage: run_id=%s stage=%s",
                        run_id,
                        stage_key,
                    )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"momentum-stage-heartbeat-{run_id}-{stage_key}",
            daemon=True,
        )
        heartbeat_thread.start()

        def _stop() -> None:
            stop_event.set()
            if heartbeat_thread.is_alive():
                heartbeat_thread.join(timeout=1.0)

        return _stop

    def _build_secondary_decision_progress_callback(
        self,
        *,
        run_id: str,
        trade_dt: date,
        label_state: Optional[Dict[str, Any]] = None,
    ):
        last_progress_signature: Dict[str, Any] = {
            "valid_sample_count": None,
            "processed_trade_date_count": None,
            "total_trade_date_count": None,
            "status": None,
        }

        def _callback(runtime_metadata: Dict[str, Any]) -> None:
            progress = runtime_metadata.get("progress") if isinstance(runtime_metadata, dict) else None
            if not isinstance(progress, dict):
                return

            signature = {
                "valid_sample_count": int(progress.get("valid_sample_count", 0) or 0),
                "processed_trade_date_count": int(progress.get("processed_trade_date_count", 0) or 0),
                "total_trade_date_count": int(progress.get("total_trade_date_count", 0) or 0),
                "status": str(progress.get("status") or ""),
            }
            if signature == last_progress_signature:
                return
            last_progress_signature.update(signature)
            stage_label = self._build_secondary_decision_progress_label(progress)
            if isinstance(label_state, dict):
                label_state["value"] = stage_label

            self.repository.update_run(
                run_id,
                current_stage_key="secondary_decision",
                current_stage_label=stage_label,
                current_trade_date=trade_dt,
                heartbeat_at=datetime.now(),
            )

        return _callback

    def _build_secondary_decision_progress_label(self, progress: Dict[str, Any]) -> str:
        base_label = RUN_STAGE_LABELS["secondary_decision"]
        valid_sample_count = int(progress.get("valid_sample_count", 0) or 0)
        target_sample_count = int(progress.get("target_sample_count", 0) or 0)
        processed_trade_date_count = int(progress.get("processed_trade_date_count", 0) or 0)
        total_trade_date_count = int(progress.get("total_trade_date_count", 0) or 0)

        if valid_sample_count > 0 and target_sample_count > 0:
            return f"{base_label}（样本 {valid_sample_count}/{target_sample_count}）"
        if processed_trade_date_count > 0 and total_trade_date_count > 0:
            return f"{base_label}（扫描 {processed_trade_date_count}/{total_trade_date_count}）"
        return base_label

    def _raise_if_cancel_requested(self, run_id: str) -> None:
        run = self.repository.get_run(run_id)
        if run is not None and run.cancel_requested:
            raise _MomentumBacktestCancelled(run_id)

    def _extract_gate_snapshot(self, decision: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            self._normalize_gate_group_snapshot(
                key="market_environment",
                payload=decision.get("market_environment"),
            ),
            self._normalize_gate_group_snapshot(
                key="opportunity_quality",
                payload=decision.get("opportunity_quality"),
            ),
            self._normalize_gate_group_snapshot(
                key="historical_validity",
                payload=decision.get("historical_validity"),
            ),
        ]

    def _normalize_gate_group_snapshot(
        self,
        *,
        key: str,
        payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        group_payload = payload if isinstance(payload, dict) else {}
        group_label = GATE_GROUP_LABELS.get(key, key)
        modules: List[Dict[str, Any]] = []
        for raw_module in group_payload.get("modules") or []:
            if not isinstance(raw_module, dict):
                continue
            module_key = str(raw_module.get("key") or "")
            modules.append(
                {
                    "key": module_key,
                    "label": GATE_MODULE_LABELS.get(module_key, module_key or "未命名模块"),
                    "group_key": key,
                    "group_label": group_label,
                    "level": str(raw_module.get("level") or ""),
                    "level_label": self._gate_level_label(
                        raw_module.get("level"),
                        fallback=str(raw_module.get("label") or ""),
                    ),
                    "score": self._to_float(raw_module.get("score")),
                    "summary": str(raw_module.get("summary") or ""),
                }
            )
        return {
            "key": key,
            "label": group_label,
            "level": str(group_payload.get("level") or ""),
            "level_label": self._gate_level_label(
                group_payload.get("level"),
                fallback=str(group_payload.get("label") or ""),
            ),
            "score": self._to_float(group_payload.get("score")),
            "reason": str(group_payload.get("reason") or ""),
            "modules": modules,
        }

    def _build_gate_blockers_from_snapshot(
        self,
        gate_snapshot: List[Dict[str, Any]],
        *,
        decision: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        blockers: List[Dict[str, Any]] = []
        for group in gate_snapshot:
            if not isinstance(group, dict):
                continue
            group_key = str(group.get("key") or "")
            if group_key in {"market_environment", "opportunity_quality"}:
                for module in group.get("modules") or []:
                    if not isinstance(module, dict):
                        continue
                    if self._gate_breakdown_bucket(module.get("level")) == "weak":
                        blockers.append(module)
            elif group_key == "historical_validity" and self._gate_breakdown_bucket(group.get("level")) == "weak":
                blockers.append(
                    {
                        "key": "historical_validity",
                        "label": GATE_MODULE_LABELS["historical_validity"],
                        "group_key": group_key,
                        "group_label": str(group.get("label") or GATE_GROUP_LABELS[group_key]),
                        "level": str(group.get("level") or ""),
                        "level_label": str(group.get("level_label") or group.get("label") or ""),
                        "score": self._to_float(group.get("score")),
                        "summary": str(group.get("reason") or ""),
                    }
                )
        matrix_blocker = self._build_action_matrix_blocker(decision)
        if matrix_blocker and not any(item.get("key") == matrix_blocker["key"] for item in blockers):
            blockers.append(matrix_blocker)
        blockers.sort(
            key=lambda item: (
                item.get("score") if item.get("score") is not None else 999.0,
                str(item.get("group_key") or ""),
                str(item.get("key") or ""),
            )
        )
        return blockers

    def _build_action_matrix_blocker(self, decision: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(decision, dict):
            return None
        action = decision.get("action")
        if not isinstance(action, dict):
            return None
        gate_context = action.get("gate_context")
        if not isinstance(gate_context, dict):
            return None
        base_level = str(action.get("base_level") or gate_context.get("base_level") or "")
        final_level = str(action.get("level") or gate_context.get("final_level") or "")
        if base_level not in RESTRICTED_ACTION_LEVELS and final_level not in RESTRICTED_ACTION_LEVELS:
            return None
        restriction_reason = str(gate_context.get("restriction_reason") or "").strip()
        if not restriction_reason:
            return None
        return {
            "key": "action_matrix",
            "label": GATE_MODULE_LABELS["action_matrix"],
            "group_key": "opportunity_quality",
            "group_label": GATE_GROUP_LABELS["opportunity_quality"],
            "level": "weak",
            "level_label": self._gate_level_label("weak"),
            "score": 35.0,
            "summary": restriction_reason,
        }

    def _load_daily_gate_snapshot(self, daily_row: MomentumBacktestDailySummary) -> List[Dict[str, Any]]:
        diagnosis_payload = self._load_json(daily_row.diagnosis_json) or {}
        if isinstance(diagnosis_payload.get("gate_snapshot"), list):
            return list(diagnosis_payload["gate_snapshot"])
        decision_payload = self._load_json(daily_row.decision_payload_json) or {}
        return self._extract_gate_snapshot(decision_payload)

    def _load_daily_gate_blockers(self, daily_row: MomentumBacktestDailySummary) -> List[Dict[str, Any]]:
        diagnosis_payload = self._load_json(daily_row.diagnosis_json) or {}
        if isinstance(diagnosis_payload.get("gate_blockers"), list):
            return list(diagnosis_payload["gate_blockers"])
        decision_payload = self._load_json(daily_row.decision_payload_json) or {}
        return self._build_gate_blockers_from_snapshot(
            self._load_daily_gate_snapshot(daily_row),
            decision=decision_payload,
        )

    def _build_daily_diagnosis(
        self,
        *,
        daily_row: MomentumBacktestDailySummary,
        candidate_rows: List[MomentumBacktestCandidateRecord],
        decision_rows: List[MomentumBacktestDecisionRecord],
        candidate_outcomes: List[MomentumBacktestOutcomeRecord],
        decision_outcomes: List[MomentumBacktestOutcomeRecord],
    ) -> Dict[str, Any]:
        candidate_metrics = self._summarize_outcomes(candidate_outcomes)
        decision_metrics = self._summarize_outcomes(decision_outcomes)
        main_row = next((row for row in decision_rows if row.slot == "main"), None)
        main_outcome = next((row for row in decision_outcomes if row.slot == "main"), None)
        gate_snapshot = self._load_daily_gate_snapshot(daily_row)
        gate_blockers = self._load_daily_gate_blockers(daily_row)

        issues: List[Dict[str, Any]] = []

        if (
            decision_metrics["t1_direction_pass_rate_pct"] is not None
            and decision_metrics["settlement_pass_rate_pct"] is not None
            and decision_metrics["t1_direction_pass_rate_pct"] < 50.0
            and decision_metrics["settlement_pass_rate_pct"] < 50.0
        ):
            failed_t1_codes = [
                row.ts_code
                for row in decision_outcomes
                if not self._outcome_t1_direction_pass(row)
            ]
            issues.append(
                {
                    "issue_key": "t1_direction_failure_high",
                    "severity": "warning",
                    "title": "T+1 方向失败偏高",
                    "summary": "默认组合次日收盘强于开盘的比例偏低，短线延续主要卡在 T+1 方向确认。",
                    "affected_codes": failed_t1_codes or [row.ts_code for row in decision_rows],
                    "metrics": {
                        "decision_t1_direction_pass_rate_pct": decision_metrics["t1_direction_pass_rate_pct"],
                        "decision_t2_continuation_pass_rate_pct": decision_metrics["t2_continuation_pass_rate_pct"],
                        "decision_settlement_pass_rate_pct": decision_metrics["settlement_pass_rate_pct"],
                    },
                }
            )

        if (
            daily_row.action_level in {"observe_only", "stand_aside"}
            and candidate_metrics["positive_t2_rate_pct"] is not None
            and candidate_metrics["avg_t2_profit_window_pct"] is not None
            and candidate_metrics["positive_t2_rate_pct"] >= 60.0
            and candidate_metrics["avg_t2_profit_window_pct"] >= 3.0
        ):
            issues.append(
                {
                    "issue_key": "gate_missed_opportunity",
                    "severity": "critical" if daily_row.action_level == "stand_aside" else "warning",
                    "title": "总闸门可能错杀机会",
                    "summary": "当日被降到观察/不做，但候选池整体短线延续合格率和 T+2 利润窗口仍偏强。",
                    "affected_codes": [row.ts_code for row in candidate_rows[:3]],
                    "metrics": {
                        "candidate_positive_t2_rate_pct": candidate_metrics["positive_t2_rate_pct"],
                        "candidate_settlement_pass_rate_pct": candidate_metrics["settlement_pass_rate_pct"],
                        "candidate_avg_t2_profit_window_pct": candidate_metrics["avg_t2_profit_window_pct"],
                    },
                }
            )

        if main_row and main_outcome:
            best_candidate = max(
                candidate_outcomes,
                key=lambda row: (
                    row.t2_profit_window_pct if row.t2_profit_window_pct is not None else float("-inf"),
                    row.t2_close_return_pct if row.t2_close_return_pct is not None else float("-inf"),
                ),
                default=None,
            )
            if (
                best_candidate
                and best_candidate.ts_code != main_row.ts_code
                and best_candidate.t2_profit_window_pct is not None
                and main_outcome.t2_profit_window_pct is not None
                and best_candidate.t2_profit_window_pct - main_outcome.t2_profit_window_pct >= 2.0
            ):
                best_candidate_row = next(
                    (row for row in candidate_rows if row.ts_code == best_candidate.ts_code),
                    None,
                )
                best_candidate_same_theme = bool(
                    main_row.theme
                    and best_candidate_row
                    and best_candidate_row.theme == main_row.theme
                )
                best_candidate_in_selected_top3 = any(
                    row.ts_code == best_candidate.ts_code for row in decision_rows
                )
                if best_candidate_same_theme:
                    issues.append(
                        {
                            "issue_key": "main_slot_underperformed",
                            "severity": "warning",
                            "title": "主仓排序可能偏弱",
                            "summary": "同主线内或默认组合里已存在更强标的，说明主仓排序可能需要继续校准。",
                            "affected_codes": [main_row.ts_code, best_candidate.ts_code],
                            "metrics": {
                                "main_t2_profit_window_pct": main_outcome.t2_profit_window_pct,
                                "best_candidate_t2_profit_window_pct": best_candidate.t2_profit_window_pct,
                                "best_candidate_same_theme": best_candidate_same_theme,
                                "best_candidate_in_selected_top3": best_candidate_in_selected_top3,
                            },
                        }
                    )
                elif best_candidate_in_selected_top3:
                    issues.append(
                        {
                            "issue_key": "portfolio_anchor_underperformed",
                            "severity": "warning",
                            "title": "组合锚点可能偏弱",
                            "summary": "默认组合里已有其他主题/角色的更强标的，说明主仓承担组合锚点的力度可能偏弱，但不一定属于同主线错排。",
                            "affected_codes": [main_row.ts_code, best_candidate.ts_code],
                            "metrics": {
                                "main_t2_profit_window_pct": main_outcome.t2_profit_window_pct,
                                "best_candidate_t2_profit_window_pct": best_candidate.t2_profit_window_pct,
                                "best_candidate_same_theme": best_candidate_same_theme,
                                "best_candidate_in_selected_top3": best_candidate_in_selected_top3,
                            },
                        }
                    )

        if (
            decision_metrics["trigger_rate_pct"] is not None
            and decision_metrics["trigger_rate_pct"] < 34.0
            and candidate_metrics["avg_t2_profit_window_pct"] is not None
            and candidate_metrics["avg_t2_profit_window_pct"] >= 2.0
        ):
            issues.append(
                {
                    "issue_key": "trigger_efficiency_low",
                    "severity": "warning",
                    "title": "买点触发效率偏低",
                    "summary": "候选池后续表现并不弱，但二次决策组合的触发率明显偏低，说明买点规则仍可能过严。",
                    "affected_codes": [row.ts_code for row in decision_rows],
                    "metrics": {
                        "decision_trigger_rate_pct": decision_metrics["trigger_rate_pct"],
                        "candidate_avg_t2_profit_window_pct": candidate_metrics["avg_t2_profit_window_pct"],
                    },
                }
            )

        if (
            decision_metrics["avg_t2_max_drawdown_pct"] is not None
            and decision_metrics["avg_t2_max_drawdown_pct"] >= 4.0
        ):
            issues.append(
                {
                    "issue_key": "drawdown_pressure_high",
                    "severity": "warning",
                    "title": "组合回撤压力偏高",
                    "summary": "默认组合的 T+2 平均最大回撤偏高，需要关注风险约束和入场位置。",
                    "affected_codes": [row.ts_code for row in decision_rows],
                    "metrics": {
                        "decision_avg_t2_max_drawdown_pct": decision_metrics["avg_t2_max_drawdown_pct"],
                    },
                }
            )

        if (
            candidate_metrics["positive_t2_rate_pct"] is not None
            and candidate_metrics["avg_t2_profit_window_pct"] is not None
            and candidate_metrics["positive_t2_rate_pct"] < 40.0
            and candidate_metrics["avg_t2_profit_window_pct"] < 1.0
        ):
            issues.append(
                {
                    "issue_key": "candidate_pool_weak",
                    "severity": "info",
                    "title": "候选池整体偏弱",
                    "summary": "候选池后续延续性不足，当天可能更像噪音行情而非可持续强势。",
                    "affected_codes": [row.ts_code for row in candidate_rows[:3]],
                    "metrics": {
                        "candidate_positive_t2_rate_pct": candidate_metrics["positive_t2_rate_pct"],
                        "candidate_avg_t2_profit_window_pct": candidate_metrics["avg_t2_profit_window_pct"],
                    },
                }
            )

        summary_lines = self._build_diagnosis_summary_lines(
            daily_row=daily_row,
            candidate_metrics=candidate_metrics,
            decision_metrics=decision_metrics,
            gate_blockers=gate_blockers,
            issues=issues,
        )
        return {
            "summary_lines": summary_lines,
            "candidate_metrics": candidate_metrics,
            "decision_metrics": decision_metrics,
            "gate_snapshot": gate_snapshot,
            "gate_blockers": gate_blockers,
            "issues": issues,
        }

    def _build_outcome_record(
        self,
        *,
        trade_dt: date,
        item: Dict[str, Any],
        view_scope: str,
        slot: Optional[str],
    ) -> MomentumBacktestOutcomeRecord:
        bars = self._load_forward_bars(str(item.get("ts_code") or ""), trade_dt)
        reference_entry_price = self._to_float(bars[0].get("open")) if bars else None
        entry_low = self._to_float(item.get("entry_range_low"))
        entry_high = self._to_float(item.get("entry_range_high"))

        buy_triggered = False
        trigger_price = None
        trigger_trade_date = None
        trigger_index = 0
        if entry_low is not None and entry_high is not None:
            for index, bar in enumerate(bars[:2]):
                low = self._to_float(bar.get("low"))
                high = self._to_float(bar.get("high"))
                open_price = self._to_float(bar.get("open"))
                if low is None or high is None:
                    continue
                if low <= entry_high and high >= entry_low:
                    buy_triggered = True
                    trigger_trade_date = self._parse_trade_date(str(bar["date"]))
                    trigger_index = index
                    if open_price is not None and entry_low <= open_price <= entry_high:
                        trigger_price = open_price
                    elif low <= entry_low <= high:
                        trigger_price = entry_low
                    else:
                        trigger_price = entry_high
                    break

        if trigger_price is None:
            trigger_price = reference_entry_price

        window_bars = bars[trigger_index: trigger_index + 2] if bars else []
        t1_bar = window_bars[0] if len(window_bars) >= 1 else None
        t2_bar = window_bars[1] if len(window_bars) >= 2 else None
        base_price = trigger_price or reference_entry_price
        t1_stats = self._compute_window_stats(base_price, window_bars[:1])
        t2_stats = self._compute_window_stats(base_price, window_bars[:2])

        t1_open_price = self._to_float(t1_bar.get("open")) if t1_bar else None
        t1_close_price = self._to_float(t1_bar.get("close")) if t1_bar else None
        t2_high_price = self._to_float(t2_bar.get("high")) if t2_bar else None
        t1_direction_pass = (
            t1_open_price is not None
            and t1_close_price is not None
            and t1_close_price > t1_open_price
        )
        t2_continuation_pass = (
            t2_high_price is not None
            and t1_close_price is not None
            and t2_high_price > t1_close_price
        )
        settlement_pass = bool(t1_direction_pass and t2_continuation_pass)

        if not window_bars:
            real_strength_label = "insufficient"
        elif settlement_pass and (t2_stats.get("profit_window_pct") or 0.0) >= 5.0:
            real_strength_label = "strong"
        elif settlement_pass:
            real_strength_label = "medium"
        else:
            real_strength_label = "weak"

        return MomentumBacktestOutcomeRecord(
            run_id="",
            trade_date=trade_dt,
            view_scope=view_scope,
            slot=slot,
            ts_code=str(item.get("ts_code") or ""),
            name=str(item.get("name") or ""),
            buy_triggered=buy_triggered,
            reference_entry_price=reference_entry_price,
            trigger_price=trigger_price,
            trigger_trade_date=trigger_trade_date,
            t1_trade_date=self._parse_trade_date(str(t1_bar["date"])) if t1_bar else None,
            t1_close_return_pct=t1_stats.get("close_return_pct"),
            t1_profit_window_pct=t1_stats.get("profit_window_pct"),
            t1_max_drawdown_pct=t1_stats.get("max_drawdown_pct"),
            t2_trade_date=self._parse_trade_date(str(t2_bar["date"])) if t2_bar else None,
            t2_close_return_pct=t2_stats.get("close_return_pct"),
            t2_profit_window_pct=t2_stats.get("profit_window_pct"),
            t2_max_drawdown_pct=t2_stats.get("max_drawdown_pct"),
            real_strength_label=real_strength_label,
            outcome_payload_json=self._dump_json(
                {
                    "view_scope": view_scope,
                    "slot": slot,
                    "buy_triggered": buy_triggered,
                    "trigger_trade_date": trigger_trade_date.isoformat() if trigger_trade_date else None,
                    "trigger_price": trigger_price,
                    "bars": window_bars,
                    "settlement_rule": "t1_close_gt_open_and_t2_high_gt_t1_close",
                    "t1_open_price": t1_open_price,
                    "t1_close_price": t1_close_price,
                    "t2_high_price": t2_high_price,
                    "t1_direction_pass": t1_direction_pass,
                    "t2_continuation_pass": t2_continuation_pass,
                    "settlement_pass": settlement_pass,
                }
            ),
        )

    def _build_run_summary(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        daily_rows = self.repository.list_daily_summaries(run_id)
        candidate_rows = self.repository.list_candidate_records_for_run(run_id, view_scope="candidate_top10")
        decision_rows = self.repository.list_decision_records_for_run(run_id)
        outcome_rows = self.repository.list_outcomes(run_id)
        candidate_outcomes = [row for row in outcome_rows if row.view_scope == "candidate_top10"]
        decision_outcomes = [row for row in outcome_rows if row.view_scope == "decision_top3"]

        strategy_health_mode = self._normalize_strategy_health_mode(
            strategy_health_mode=getattr(run, "strategy_health_mode", None),
        )
        action_breakdown: Dict[str, int] = {}
        market_environment_breakdown: Dict[str, int] = {}
        opportunity_quality_breakdown: Dict[str, int] = {}
        historical_validity_breakdown: Dict[str, int] = {}
        strategy_health_validation_status_breakdown: Dict[str, int] = {}
        attack_permission_breakdown: Dict[str, int] = {}
        theme_confidence_breakdown: Dict[str, int] = {}
        for row in daily_rows:
            action_breakdown[row.action_level] = action_breakdown.get(row.action_level, 0) + 1
            market_environment_breakdown[row.market_environment_level] = (
                market_environment_breakdown.get(row.market_environment_level, 0) + 1
            )
            opportunity_quality_breakdown[row.opportunity_quality_level] = (
                opportunity_quality_breakdown.get(row.opportunity_quality_level, 0) + 1
            )
            historical_validity_breakdown[row.historical_validity_level] = (
                historical_validity_breakdown.get(row.historical_validity_level, 0) + 1
            )
            strategy_health_meta = self._extract_strategy_health_meta_from_daily_row(row)
            validation_status = strategy_health_meta.get("validation_status")
            if validation_status:
                strategy_health_validation_status_breakdown[validation_status] = (
                    strategy_health_validation_status_breakdown.get(validation_status, 0) + 1
                )
            attack_permission_status = strategy_health_meta.get("attack_permission_status")
            if attack_permission_status:
                attack_permission_breakdown[attack_permission_status] = (
                    attack_permission_breakdown.get(attack_permission_status, 0) + 1
                )
            theme_confidence_status = strategy_health_meta.get("theme_confidence_status")
            if theme_confidence_status:
                theme_confidence_breakdown[theme_confidence_status] = (
                    theme_confidence_breakdown.get(theme_confidence_status, 0) + 1
                )

        candidate_metrics = self._summarize_outcomes(candidate_outcomes)
        decision_metrics = self._summarize_outcomes(decision_outcomes)
        decision_outcomes_by_slot = self._group_outcomes_by_slot(decision_outcomes)

        candidate_rank_map = {(row.trade_date, row.ts_code): row.rank for row in candidate_rows}
        raw_rank_top3_outcomes = [
            row
            for row in candidate_outcomes
            if (candidate_rank_map.get((row.trade_date, row.ts_code)) or 999) <= 3
        ]
        leader_baseline_outcomes = [
            outcome
            for outcome in candidate_outcomes
            if self._is_leader_role(
                next(
                    (
                        row.role
                        for row in candidate_rows
                        if row.trade_date == outcome.trade_date and row.ts_code == outcome.ts_code
                    ),
                    None,
                )
            )
        ]

        candidate_rows_by_date: Dict[date, List[MomentumBacktestCandidateRecord]] = {}
        decision_rows_by_date: Dict[date, List[MomentumBacktestDecisionRecord]] = {}
        candidate_outcomes_by_date: Dict[date, List[MomentumBacktestOutcomeRecord]] = {}
        decision_outcomes_by_date: Dict[date, List[MomentumBacktestOutcomeRecord]] = {}
        for row in candidate_rows:
            candidate_rows_by_date.setdefault(row.trade_date, []).append(row)
        for row in decision_rows:
            decision_rows_by_date.setdefault(row.trade_date, []).append(row)
        for row in candidate_outcomes:
            candidate_outcomes_by_date.setdefault(row.trade_date, []).append(row)
        for row in decision_outcomes:
            decision_outcomes_by_date.setdefault(row.trade_date, []).append(row)

        diagnosis_by_date: Dict[date, Dict[str, Any]] = {}
        for row in daily_rows:
            diagnosis_by_date[row.trade_date] = self._build_daily_diagnosis(
                daily_row=row,
                candidate_rows=candidate_rows_by_date.get(row.trade_date, []),
                decision_rows=decision_rows_by_date.get(row.trade_date, []),
                candidate_outcomes=candidate_outcomes_by_date.get(row.trade_date, []),
                decision_outcomes=decision_outcomes_by_date.get(row.trade_date, []),
            )

        benchmark_comparison = self._build_benchmark_comparison(
            candidate_metrics=candidate_metrics,
            decision_metrics=decision_metrics,
            raw_rank_top3_outcomes=raw_rank_top3_outcomes,
            leader_baseline_outcomes=leader_baseline_outcomes,
            main_slot_outcomes=decision_outcomes_by_slot.get("main", []),
            total_trade_days=len(daily_rows),
        )
        gate_module_breakdown = self._build_gate_module_breakdown(
            daily_rows=daily_rows,
            diagnosis_by_date=diagnosis_by_date,
        )
        regime_breakdown = self._build_regime_breakdown(
            daily_rows=daily_rows,
            decision_outcomes=decision_outcomes,
            diagnosis_by_date=diagnosis_by_date,
        )
        layer_diagnostics = self._build_layer_diagnostics(
            candidate_metrics=candidate_metrics,
            decision_metrics=decision_metrics,
            decision_outcomes_by_slot=decision_outcomes_by_slot,
            raw_rank_top3_outcomes=raw_rank_top3_outcomes,
            daily_rows=daily_rows,
            diagnosis_by_date=diagnosis_by_date,
            gate_module_breakdown=gate_module_breakdown,
            regime_breakdown=regime_breakdown,
        )
        v13_diagnostics = self._build_v13_run_diagnostics(daily_rows)

        return {
            "strategy_health_mode": strategy_health_mode,
            "strategy_health_mode_label": self._strategy_health_mode_label(strategy_health_mode),
            "strategy_health_validation_status_breakdown": strategy_health_validation_status_breakdown,
            "attack_permission_breakdown": attack_permission_breakdown,
            "theme_confidence_breakdown": theme_confidence_breakdown,
            "completed_trade_dates": len(daily_rows),
            "action_breakdown": action_breakdown,
            "market_environment_breakdown": market_environment_breakdown,
            "opportunity_quality_breakdown": opportunity_quality_breakdown,
            "historical_validity_breakdown": historical_validity_breakdown,
            "avg_candidate_count": self._avg_metric(row.candidate_count for row in daily_rows),
            "avg_selected_count": self._avg_metric(row.selected_count for row in daily_rows),
            "avg_buy_ready_count": self._avg_metric(row.buy_ready_count for row in daily_rows),
            "candidate_top10_buy_trigger_rate": candidate_metrics["trigger_rate_pct"],
            "candidate_top10_positive_t2_rate": candidate_metrics["positive_t2_rate_pct"],
            "candidate_top10_settlement_pass_rate": candidate_metrics["settlement_pass_rate_pct"],
            "candidate_top10_t1_direction_pass_rate": candidate_metrics["t1_direction_pass_rate_pct"],
            "candidate_top10_t2_continuation_pass_rate": candidate_metrics["t2_continuation_pass_rate_pct"],
            "candidate_top10_avg_t2_profit_window_pct": candidate_metrics["avg_t2_profit_window_pct"],
            "candidate_top10_avg_t2_max_drawdown_pct": candidate_metrics["avg_t2_max_drawdown_pct"],
            "decision_top3_buy_trigger_rate": decision_metrics["trigger_rate_pct"],
            "decision_top3_positive_t1_rate": decision_metrics["positive_t1_rate_pct"],
            "decision_top3_positive_t2_rate": decision_metrics["positive_t2_rate_pct"],
            "decision_top3_settlement_pass_rate": decision_metrics["settlement_pass_rate_pct"],
            "decision_top3_t1_direction_pass_rate": decision_metrics["t1_direction_pass_rate_pct"],
            "decision_top3_t2_continuation_pass_rate": decision_metrics["t2_continuation_pass_rate_pct"],
            "decision_top3_avg_t1_profit_window_pct": decision_metrics["avg_t1_profit_window_pct"],
            "decision_top3_avg_t2_profit_window_pct": decision_metrics["avg_t2_profit_window_pct"],
            "decision_top3_avg_t2_max_drawdown_pct": decision_metrics["avg_t2_max_drawdown_pct"],
            "benchmark_comparison": benchmark_comparison,
            "layer_diagnostics": layer_diagnostics,
            "gate_module_breakdown": gate_module_breakdown,
            "regime_breakdown": regime_breakdown,
            "v13_diagnostics": v13_diagnostics,
        }

    def _load_complete_summary(self, run_id: str, payload: Optional[str]) -> Dict[str, Any]:
        summary = self._load_json(payload)
        if self._summary_requires_refresh(summary):
            return self._build_run_summary(run_id)
        return summary

    def _build_v13_run_diagnostics(self, daily_rows: List[MomentumBacktestDailySummary]) -> Dict[str, Any]:
        sentiment_breakdown: Dict[str, int] = {}
        data_status_breakdown: Dict[str, int] = {}
        top_theme_breakdown: Dict[str, int] = {}
        top_mainline_scores: List[float] = []
        radar_available_days = 0
        degraded_days = 0

        for row in daily_rows:
            diagnostics = self._extract_v13_diagnostics_from_daily_row(row)
            data_status = diagnostics.get("v13_data_status") or {}
            status = str(data_status.get("status") or "missing")
            data_status_breakdown[status] = data_status_breakdown.get(status, 0) + 1
            if data_status.get("is_degraded") or status in {"degraded", "failed"}:
                degraded_days += 1

            sentiment = diagnostics.get("short_term_sentiment") or {}
            sentiment_level = str(sentiment.get("level") or "missing")
            sentiment_breakdown[sentiment_level] = sentiment_breakdown.get(sentiment_level, 0) + 1

            radar = diagnostics.get("mainline_radar") or []
            if radar:
                radar_available_days += 1
                top_item = radar[0]
                top_theme = str(top_item.get("theme_name") or top_item.get("theme_id") or "unknown")
                top_theme_breakdown[top_theme] = top_theme_breakdown.get(top_theme, 0) + 1
                score = self._to_float(top_item.get("score"))
                if score is not None:
                    top_mainline_scores.append(score)

        top_themes = [
            {"theme": theme, "days": days}
            for theme, days in sorted(top_theme_breakdown.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        coverage = self._safe_ratio(radar_available_days, len(daily_rows))
        avg_score = self._avg_metric(top_mainline_scores)
        return {
            "evaluated_trade_dates": len(daily_rows),
            "radar_available_days": radar_available_days,
            "radar_coverage_pct": coverage,
            "avg_top_mainline_score": avg_score,
            "sentiment_breakdown": sentiment_breakdown,
            "data_status_breakdown": data_status_breakdown,
            "degraded_days": degraded_days,
            "top_theme_breakdown": top_themes,
            "summary": (
                f"V1.3 主线雷达覆盖 {radar_available_days}/{len(daily_rows)} 个交易日"
                f"（{self._format_pct(coverage)}），Top 主线均分 {self._format_number(avg_score)}，"
                f"数据降级 {degraded_days} 天。"
            ),
        }

    def _extract_v13_diagnostics_from_daily_row(
        self,
        row: MomentumBacktestDailySummary,
    ) -> Dict[str, Any]:
        decision = self._load_json(row.decision_payload_json)
        if not isinstance(decision, dict):
            return {
                "mainline_radar": [],
                "short_term_sentiment": None,
                "v13_data_status": {"status": "missing", "reason": "当日决策快照不可用。"},
                "top_mainline": None,
                "mainline_count": 0,
                "summary_lines": ["当日决策快照不可用，无法提取 V1.3 主线诊断。"],
            }
        radar = decision.get("mainline_radar")
        if not isinstance(radar, list):
            radar = []
        radar = [item for item in radar if isinstance(item, dict)]
        sentiment = decision.get("short_term_sentiment")
        if not isinstance(sentiment, dict):
            sentiment = None
        data_status = decision.get("v13_data_status")
        if not isinstance(data_status, dict):
            data_status = {"status": "missing"}
        top_mainline = radar[0] if radar else None
        summary_lines = []
        if top_mainline:
            summary_lines.append(
                f"Top 主线为 {top_mainline.get('theme_name') or top_mainline.get('theme_id') or '未命名主线'}，"
                f"主线雷达分 {self._format_number(self._to_float(top_mainline.get('score')))}。"
            )
        else:
            summary_lines.append("当日没有可用的 V1.3 主线雷达结果。")
        if sentiment:
            summary_lines.append(
                f"短线情绪为 {sentiment.get('level_label') or sentiment.get('level') or '未知'}，"
                f"分数 {self._format_number(self._to_float(sentiment.get('score')))}。"
            )
        if data_status.get("status") and data_status.get("status") != "ok":
            summary_lines.append(f"数据状态为 {data_status.get('status')}，需要关注降级或缺失。")
        return {
            "mainline_radar": radar,
            "short_term_sentiment": sentiment,
            "v13_data_status": data_status,
            "top_mainline": top_mainline,
            "mainline_count": len(radar),
            "summary_lines": summary_lines,
        }

    def _extract_strategy_health_meta_from_daily_row(
        self,
        row: MomentumBacktestDailySummary,
    ) -> Dict[str, str]:
        decision = self._load_json(row.decision_payload_json)
        if not isinstance(decision, dict):
            return {}
        strategy_health = decision.get("strategy_health") or {}
        attack_permission = decision.get("attack_permission") or {}
        theme_confidence = decision.get("theme_confidence") or {}
        return {
            "validation_status": str(strategy_health.get("validation_status") or ""),
            "attack_permission_status": str(attack_permission.get("status") or ""),
            "theme_confidence_status": str(theme_confidence.get("status") or ""),
        }

    @staticmethod
    def _summary_requires_refresh(summary: Optional[Dict[str, Any]]) -> bool:
        required_keys = {
            "benchmark_comparison",
            "layer_diagnostics",
            "gate_module_breakdown",
            "regime_breakdown",
            "candidate_top10_positive_t2_rate",
            "candidate_top10_t1_direction_pass_rate",
            "candidate_top10_t2_continuation_pass_rate",
            "decision_top3_t1_direction_pass_rate",
            "decision_top3_t2_continuation_pass_rate",
            "market_environment_breakdown",
            "strategy_health_mode",
            "strategy_health_validation_status_breakdown",
            "attack_permission_breakdown",
            "theme_confidence_breakdown",
            "v13_diagnostics",
        }
        if not isinstance(summary, dict):
            return True
        return any(key not in summary for key in required_keys)

    @staticmethod
    def _daily_row_matches_filters(
        row: MomentumBacktestDailySummary,
        *,
        decisions: List[MomentumBacktestDecisionRecord],
        start_dt: Optional[date],
        end_dt: Optional[date],
        market_regime: Optional[str],
        action_level: Optional[str],
        slot: Optional[str],
        theme_name: Optional[str],
    ) -> bool:
        if start_dt and row.trade_date < start_dt:
            return False
        if end_dt and row.trade_date > end_dt:
            return False
        if action_level and row.action_level != action_level:
            return False
        normalized_regime = MomentumBacktestService._normalize_market_regime(market_regime)
        if normalized_regime and row.market_environment_level != normalized_regime:
            return False
        if slot and not any(item.slot == slot for item in decisions):
            return False
        if theme_name:
            keyword = theme_name.casefold()
            if not any(keyword in (item.theme or "").casefold() for item in decisions):
                return False
        return True

    def _build_benchmark_comparison(
        self,
        *,
        candidate_metrics: Dict[str, Optional[float]],
        decision_metrics: Dict[str, Optional[float]],
        raw_rank_top3_outcomes: List[MomentumBacktestOutcomeRecord],
        leader_baseline_outcomes: List[MomentumBacktestOutcomeRecord],
        main_slot_outcomes: List[MomentumBacktestOutcomeRecord],
        total_trade_days: int,
    ) -> List[Dict[str, Any]]:
        decision_profit = decision_metrics["avg_t2_profit_window_pct"]
        candidate_profit = candidate_metrics["avg_t2_profit_window_pct"]
        benchmarks = [
            self._build_benchmark_item(
                key="official_top3",
                label="官方 Top3",
                metrics=decision_metrics,
                decision_profit=decision_profit,
                candidate_profit=candidate_profit,
            ),
            self._build_benchmark_item(
                key="candidate_top10",
                label="候选池 Top10",
                metrics=candidate_metrics,
                decision_profit=decision_profit,
                candidate_profit=candidate_profit,
            ),
            self._build_benchmark_item(
                key="raw_rank_top3",
                label="原始排序 Top3",
                metrics=self._summarize_outcomes(raw_rank_top3_outcomes),
                decision_profit=decision_profit,
                candidate_profit=candidate_profit,
            ),
            self._build_benchmark_item(
                key="leader_baseline",
                label="主线龙头基准",
                metrics=self._summarize_outcomes(leader_baseline_outcomes),
                decision_profit=decision_profit,
                candidate_profit=candidate_profit,
            ),
            self._build_benchmark_item(
                key="main_slot",
                label="主仓基准",
                metrics=self._summarize_outcomes(main_slot_outcomes),
                decision_profit=decision_profit,
                candidate_profit=candidate_profit,
            ),
            {
                "key": "stay_out",
                "label": "空仓基准",
                "sample_count": total_trade_days,
                "trigger_rate_pct": 0.0,
                "positive_t2_rate_pct": 0.0,
                "settlement_pass_rate_pct": 0.0,
                "avg_t2_profit_window_pct": 0.0,
                "avg_t2_max_drawdown_pct": 0.0,
                "alpha_vs_official_top3_pct": self._delta_pct(0.0, decision_profit),
                "alpha_vs_candidate_top10_pct": self._delta_pct(0.0, candidate_profit),
            },
        ]
        return benchmarks

    def _build_layer_diagnostics(
        self,
        *,
        candidate_metrics: Dict[str, Optional[float]],
        decision_metrics: Dict[str, Optional[float]],
        decision_outcomes_by_slot: Dict[str, List[MomentumBacktestOutcomeRecord]],
        raw_rank_top3_outcomes: List[MomentumBacktestOutcomeRecord],
        daily_rows: List[MomentumBacktestDailySummary],
        diagnosis_by_date: Dict[date, Dict[str, Any]],
        gate_module_breakdown: List[Dict[str, Any]],
        regime_breakdown: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        raw_rank_metrics = self._summarize_outcomes(raw_rank_top3_outcomes)
        main_metrics = self._summarize_outcomes(decision_outcomes_by_slot.get("main", []))
        secondary_metrics = self._summarize_outcomes(decision_outcomes_by_slot.get("secondary", []))
        watch_metrics = self._summarize_outcomes(decision_outcomes_by_slot.get("watch", []))
        triggered_rows = [
            row
            for row in decision_outcomes_by_slot.get("main", [])
            + decision_outcomes_by_slot.get("secondary", [])
            + decision_outcomes_by_slot.get("watch", [])
            if row.buy_triggered
        ]
        triggered_metrics = self._summarize_outcomes(triggered_rows)

        total_days = len(daily_rows)
        restricted_days = [row for row in daily_rows if row.action_level in {"observe_only", "stand_aside"}]
        tradable_days = [row for row in daily_rows if row.action_level in {"strong_go", "normal_go", "cautious_go"}]
        missed_days = sum(
            1
            for row in restricted_days
            if any(issue["issue_key"] == "gate_missed_opportunity" for issue in diagnosis_by_date[row.trade_date]["issues"])
        )
        allowed_days_success = sum(
            1
            for row in tradable_days
            if (
                diagnosis_by_date[row.trade_date]["decision_metrics"]["positive_t2_rate_pct"] or 0.0
            ) >= 50.0
        )
        missed_rate = self._safe_ratio(missed_days, len(restricted_days))
        allowed_trade_precision = self._safe_ratio(allowed_days_success, len(tradable_days))
        top_gate_blocker = next(
            (item for item in gate_module_breakdown if int(item.get("blocker_days") or 0) > 0),
            None,
        )

        ranking_alpha = self._delta_pct(
            decision_metrics["avg_t2_profit_window_pct"],
            raw_rank_metrics["avg_t2_profit_window_pct"],
        )
        regime_positive_values = [
            item["decision_positive_t2_rate_pct"]
            for item in regime_breakdown
            if item.get("decision_positive_t2_rate_pct") is not None
        ]
        regime_spread = None
        if regime_positive_values:
            regime_spread = round(max(regime_positive_values) - min(regime_positive_values), 4)

        candidate_level = self._quality_level(
            positive_rate=candidate_metrics["positive_t2_rate_pct"],
            avg_profit=candidate_metrics["avg_t2_profit_window_pct"],
            strong_positive=60.0,
            general_positive=45.0,
            strong_profit=3.0,
            general_profit=1.5,
        )
        ranking_level = self._ranking_level(
            alpha=ranking_alpha,
            main_profit=main_metrics["avg_t2_profit_window_pct"],
            secondary_profit=secondary_metrics["avg_t2_profit_window_pct"],
            watch_profit=watch_metrics["avg_t2_profit_window_pct"],
        )
        execution_level = self._execution_level(
            trigger_rate=decision_metrics["trigger_rate_pct"],
            triggered_positive_t2=triggered_metrics["positive_t2_rate_pct"],
            max_drawdown=triggered_metrics["avg_t2_max_drawdown_pct"],
        )
        gate_level = self._gate_level(
            missed_rate=missed_rate,
            allowed_trade_precision=allowed_trade_precision,
        )
        regime_level = self._regime_level(regime_breakdown)

        return [
            self._build_layer_item(
                key="candidate_pool",
                label="候选池",
                level=candidate_level,
                summary=(
                    f"候选池 Top10 短线延续合格率 {self._format_pct(candidate_metrics['positive_t2_rate_pct'])}，"
                    f"平均利润窗口 {self._format_pct(candidate_metrics['avg_t2_profit_window_pct'])}。"
                ),
                metrics={
                    "sample_count": candidate_metrics["sample_count"],
                    "positive_t2_rate_pct": candidate_metrics["positive_t2_rate_pct"],
                    "settlement_pass_rate_pct": candidate_metrics["settlement_pass_rate_pct"],
                    "t1_direction_pass_rate_pct": candidate_metrics["t1_direction_pass_rate_pct"],
                    "t2_continuation_pass_rate_pct": candidate_metrics["t2_continuation_pass_rate_pct"],
                    "avg_t2_profit_window_pct": candidate_metrics["avg_t2_profit_window_pct"],
                    "avg_t2_max_drawdown_pct": candidate_metrics["avg_t2_max_drawdown_pct"],
                },
            ),
            self._build_layer_item(
                key="ranking",
                label="排序",
                level=ranking_level,
                summary=(
                    f"官方 Top3 相对原始排序 Top3 的 T+2 利润窗口超额 {self._format_pct(ranking_alpha)}，"
                    f"主仓/次仓/观察仓利润窗口依次为 "
                    f"{self._format_pct(main_metrics['avg_t2_profit_window_pct'])} / "
                    f"{self._format_pct(secondary_metrics['avg_t2_profit_window_pct'])} / "
                    f"{self._format_pct(watch_metrics['avg_t2_profit_window_pct'])}。"
                ),
                metrics={
                    "top3_vs_raw_rank_top3_alpha_pct": ranking_alpha,
                    "main_slot_positive_t2_rate_pct": main_metrics["positive_t2_rate_pct"],
                    "secondary_slot_positive_t2_rate_pct": secondary_metrics["positive_t2_rate_pct"],
                    "watch_slot_positive_t2_rate_pct": watch_metrics["positive_t2_rate_pct"],
                },
            ),
            self._build_layer_item(
                key="execution",
                label="买点执行",
                level=execution_level,
                summary=(
                    f"默认组合买点触发率 {self._format_pct(decision_metrics['trigger_rate_pct'])}，"
                    f"触发后短线延续合格率 {self._format_pct(triggered_metrics['positive_t2_rate_pct'])}，"
                    f"平均回撤 {self._format_pct(triggered_metrics['avg_t2_max_drawdown_pct'])}。"
                ),
                metrics={
                    "buy_trigger_rate_pct": decision_metrics["trigger_rate_pct"],
                    "buy_signal_win_rate_t2_pct": triggered_metrics["positive_t2_rate_pct"],
                    "settlement_pass_rate_pct": triggered_metrics["settlement_pass_rate_pct"],
                    "profit_window_t2_pct": triggered_metrics["avg_t2_profit_window_pct"],
                    "max_drawdown_after_trigger_pct": triggered_metrics["avg_t2_max_drawdown_pct"],
                },
            ),
            self._build_layer_item(
                key="gate",
                label="总闸门",
                level=gate_level,
                summary=(
                    f"限制出手日 {len(restricted_days)} / {total_days}，"
                    f"错杀率 {self._format_pct(missed_rate)}，"
                    f"放行准确率 {self._format_pct(allowed_trade_precision)}"
                    + (
                        f"，最常见拖后腿模块为 {top_gate_blocker['label']}，弱项 {int(top_gate_blocker['blocker_days'])} 天。"
                        if top_gate_blocker
                        else "。"
                    )
                ),
                metrics={
                    "restricted_trade_days": float(len(restricted_days)),
                    "tradable_days": float(len(tradable_days)),
                    "missed_opportunity_rate_pct": missed_rate,
                    "allowed_trade_precision_pct": allowed_trade_precision,
                    "top_gate_blocker_days": float(top_gate_blocker["blocker_days"]) if top_gate_blocker else None,
                },
            ),
            self._build_layer_item(
                key="regime_fit",
                label="环境适配",
                level=regime_level,
                summary=(
                    f"强/中/弱市场的短线延续合格率分布为 "
                    f"{' / '.join(self._format_pct(item.get('decision_positive_t2_rate_pct')) for item in regime_breakdown)}，"
                    f"当前分桶离散度 {self._format_pct(regime_spread)}。"
                ),
                metrics={
                    "strong_regime_positive_t2_rate_pct": self._regime_metric(regime_breakdown, "strong", "decision_positive_t2_rate_pct"),
                    "general_regime_positive_t2_rate_pct": self._regime_metric(regime_breakdown, "general", "decision_positive_t2_rate_pct"),
                    "weak_regime_positive_t2_rate_pct": self._regime_metric(regime_breakdown, "weak", "decision_positive_t2_rate_pct"),
                    "regime_spread_pct": regime_spread,
                },
            ),
        ]

    def _build_gate_module_breakdown(
        self,
        *,
        daily_rows: List[MomentumBacktestDailySummary],
        diagnosis_by_date: Dict[date, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for row in daily_rows:
            diagnosis = diagnosis_by_date.get(row.trade_date) or {}
            decision_metrics = diagnosis.get("decision_metrics") or {}
            candidate_metrics = diagnosis.get("candidate_metrics") or {}
            for group in diagnosis.get("gate_snapshot") or self._load_daily_gate_snapshot(row):
                if not isinstance(group, dict):
                    continue
                group_key = str(group.get("key") or "")
                modules = list(group.get("modules") or [])
                if group_key == "historical_validity":
                    modules.append(
                        {
                            "key": "historical_validity",
                            "label": GATE_MODULE_LABELS["historical_validity"],
                            "group_key": group_key,
                            "group_label": str(group.get("label") or GATE_GROUP_LABELS[group_key]),
                            "level": str(group.get("level") or ""),
                            "level_label": str(group.get("level_label") or group.get("label") or ""),
                            "score": self._to_float(group.get("score")),
                            "summary": str(group.get("reason") or ""),
                        }
                    )
                for module in modules:
                    if not isinstance(module, dict):
                        continue
                    module_key = str(module.get("key") or "")
                    if not module_key:
                        continue
                    bucket = self._gate_breakdown_bucket(module.get("level"))
                    tracker = stats.setdefault(
                        module_key,
                        {
                            "key": module_key,
                            "label": str(module.get("label") or GATE_MODULE_LABELS.get(module_key, module_key)),
                            "group_key": str(module.get("group_key") or group_key),
                            "group_label": str(
                                module.get("group_label")
                                or GATE_GROUP_LABELS.get(str(module.get("group_key") or group_key), group_key)
                            ),
                            "sample_days": 0,
                            "strong_days": 0,
                            "medium_days": 0,
                            "weak_days": 0,
                            "blocker_days": 0,
                            "restricted_days": 0,
                            "_scores": [],
                            "_weak_candidate_positive_rates": [],
                            "_weak_decision_positive_rates": [],
                            "_weak_candidate_profit_values": [],
                            "_weak_decision_profit_values": [],
                            "_strong_decision_profit_values": [],
                        },
                    )
                    tracker["sample_days"] += 1
                    tracker[f"{bucket}_days"] += 1
                    score = self._to_float(module.get("score"))
                    if score is not None:
                        tracker["_scores"].append(score)
                    if bucket == "weak":
                        tracker["blocker_days"] += 1
                        if row.action_level in RESTRICTED_ACTION_LEVELS:
                            tracker["restricted_days"] += 1
                        if candidate_metrics.get("positive_t2_rate_pct") is not None:
                            tracker["_weak_candidate_positive_rates"].append(candidate_metrics["positive_t2_rate_pct"])
                        if decision_metrics.get("positive_t2_rate_pct") is not None:
                            tracker["_weak_decision_positive_rates"].append(decision_metrics["positive_t2_rate_pct"])
                        if candidate_metrics.get("avg_t2_profit_window_pct") is not None:
                            tracker["_weak_candidate_profit_values"].append(candidate_metrics["avg_t2_profit_window_pct"])
                        if decision_metrics.get("avg_t2_profit_window_pct") is not None:
                            tracker["_weak_decision_profit_values"].append(decision_metrics["avg_t2_profit_window_pct"])
                    elif bucket == "strong" and decision_metrics.get("avg_t2_profit_window_pct") is not None:
                        tracker["_strong_decision_profit_values"].append(decision_metrics["avg_t2_profit_window_pct"])

        items: List[Dict[str, Any]] = []
        for tracker in stats.values():
            avg_score = self._avg_metric(tracker.pop("_scores"))
            weak_decision_profit = self._avg_metric(tracker.pop("_weak_decision_profit_values"))
            item = {
                "key": tracker["key"],
                "label": tracker["label"],
                "group_key": tracker["group_key"],
                "group_label": tracker["group_label"],
                "sample_days": tracker["sample_days"],
                "strong_days": tracker["strong_days"],
                "medium_days": tracker["medium_days"],
                "weak_days": tracker["weak_days"],
                "blocker_days": tracker["blocker_days"],
                "restricted_days": tracker["restricted_days"],
                "avg_score": avg_score,
                "weak_day_candidate_positive_t2_rate_pct": self._avg_metric(tracker.pop("_weak_candidate_positive_rates")),
                "weak_day_decision_positive_t2_rate_pct": self._avg_metric(tracker.pop("_weak_decision_positive_rates")),
                "weak_day_candidate_avg_t2_profit_window_pct": self._avg_metric(tracker.pop("_weak_candidate_profit_values")),
                "weak_day_decision_avg_t2_profit_window_pct": weak_decision_profit,
                "strong_day_decision_avg_t2_profit_window_pct": self._avg_metric(tracker.pop("_strong_decision_profit_values")),
                "summary": (
                    f"弱项 {tracker['blocker_days']} 天，其中限制出手 {tracker['restricted_days']} 天；"
                    f"弱项日默认组合 T+2 利润窗口均值 {self._format_pct(weak_decision_profit)}。"
                ),
            }
            items.append(item)
        items.sort(
            key=lambda item: (
                -int(item["blocker_days"]),
                -int(item["restricted_days"]),
                item["avg_score"] if item["avg_score"] is not None else 999.0,
                item["key"],
            )
        )
        return items

    def _build_regime_breakdown(
        self,
        *,
        daily_rows: List[MomentumBacktestDailySummary],
        decision_outcomes: List[MomentumBacktestOutcomeRecord],
        diagnosis_by_date: Dict[date, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        breakdown: List[Dict[str, Any]] = []
        for level in ("strong", "general", "weak"):
            rows = [
                row
                for row in daily_rows
                if self._normalize_market_regime(row.market_environment_level) == level
            ]
            trade_dates = {row.trade_date for row in rows}
            outcomes = [row for row in decision_outcomes if row.trade_date in trade_dates]
            metrics = self._summarize_outcomes(outcomes)
            restricted_rows = [row for row in rows if row.action_level in {"observe_only", "stand_aside"}]
            tradable_rows = [row for row in rows if row.action_level in {"strong_go", "normal_go", "cautious_go"}]
            missed_days = sum(
                1
                for row in restricted_rows
                if any(issue["issue_key"] == "gate_missed_opportunity" for issue in diagnosis_by_date[row.trade_date]["issues"])
            )
            allowed_days_success = sum(
                1
                for row in tradable_rows
                if (
                    diagnosis_by_date[row.trade_date]["decision_metrics"]["positive_t2_rate_pct"] or 0.0
                ) >= 50.0
            )
            breakdown.append(
                {
                    "level": level,
                    "label": REGIME_LABELS[level],
                    "trade_days": len(rows),
                    "decision_positive_t2_rate_pct": metrics["positive_t2_rate_pct"],
                    "decision_avg_t2_profit_window_pct": metrics["avg_t2_profit_window_pct"],
                    "decision_avg_t2_max_drawdown_pct": metrics["avg_t2_max_drawdown_pct"],
                    "missed_opportunity_rate_pct": self._safe_ratio(missed_days, len(restricted_rows)),
                    "allowed_trade_precision_pct": self._safe_ratio(allowed_days_success, len(tradable_rows)),
                    "stand_aside_rate_pct": self._safe_ratio(
                        sum(1 for row in rows if row.action_level == "stand_aside"),
                        len(rows),
                    ),
                }
            )
        return breakdown

    def _build_benchmark_item(
        self,
        *,
        key: str,
        label: str,
        metrics: Dict[str, Optional[float]],
        decision_profit: Optional[float],
        candidate_profit: Optional[float],
    ) -> Dict[str, Any]:
        avg_profit = metrics.get("avg_t2_profit_window_pct")
        return {
            "key": key,
            "label": label,
            "sample_count": metrics.get("sample_count", 0),
            "trigger_rate_pct": metrics.get("trigger_rate_pct"),
            "positive_t2_rate_pct": metrics.get("positive_t2_rate_pct"),
            "settlement_pass_rate_pct": metrics.get("settlement_pass_rate_pct"),
            "t1_direction_pass_rate_pct": metrics.get("t1_direction_pass_rate_pct"),
            "t2_continuation_pass_rate_pct": metrics.get("t2_continuation_pass_rate_pct"),
            "avg_t2_profit_window_pct": avg_profit,
            "avg_t2_max_drawdown_pct": metrics.get("avg_t2_max_drawdown_pct"),
            "alpha_vs_official_top3_pct": self._delta_pct(avg_profit, decision_profit),
            "alpha_vs_candidate_top10_pct": self._delta_pct(avg_profit, candidate_profit),
        }

    def _build_layer_item(
        self,
        *,
        key: str,
        label: str,
        level: str,
        summary: str,
        metrics: Dict[str, Optional[float]],
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "level": level,
            "score": LAYER_LEVEL_SCORES[level],
            "summary": summary,
            "metrics": metrics,
        }

    @staticmethod
    def _group_outcomes_by_slot(
        rows: List[MomentumBacktestOutcomeRecord],
    ) -> Dict[str, List[MomentumBacktestOutcomeRecord]]:
        grouped: Dict[str, List[MomentumBacktestOutcomeRecord]] = {}
        for row in rows:
            if row.slot:
                grouped.setdefault(row.slot, []).append(row)
        return grouped

    @staticmethod
    def _is_leader_role(role: Optional[str]) -> bool:
        if not role:
            return False
        normalized = role.casefold()
        return "leader" in normalized or "龙头" in role

    @staticmethod
    def _normalize_market_regime(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip().casefold()
        aliases = {
            "strong": "strong",
            "bull": "strong",
            "general": "general",
            "neutral": "general",
            "medium": "general",
            "mid": "general",
            "weak": "weak",
            "bear": "weak",
        }
        return aliases.get(normalized, value.strip())

    @staticmethod
    def _gate_breakdown_bucket(level: Any) -> str:
        normalized = str(level or "").strip().casefold()
        if normalized in {"healthy", "strong"}:
            return "strong"
        if normalized in {"general", "medium"}:
            return "medium"
        if normalized == "weak":
            return "weak"
        return "medium"

    @staticmethod
    def _gate_level_label(level: Any, *, fallback: str = "") -> str:
        if fallback:
            return fallback
        normalized = str(level or "").strip().casefold()
        labels = {
            "healthy": "健康",
            "strong": "强",
            "general": "中",
            "medium": "中",
            "weak": "弱",
        }
        return labels.get(normalized, str(level or "--"))

    @staticmethod
    def _delta_pct(value: Optional[float], baseline: Optional[float]) -> Optional[float]:
        if value is None or baseline is None:
            return None
        return round(float(value) - float(baseline), 4)

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
        if denominator <= 0:
            return None
        return round(numerator * 100.0 / denominator, 4)

    @staticmethod
    def _quality_level(
        *,
        positive_rate: Optional[float],
        avg_profit: Optional[float],
        strong_positive: float,
        general_positive: float,
        strong_profit: float,
        general_profit: float,
    ) -> str:
        if (positive_rate or 0.0) >= strong_positive and (avg_profit or 0.0) >= strong_profit:
            return "strong"
        if (positive_rate or 0.0) >= general_positive and (avg_profit or 0.0) >= general_profit:
            return "general"
        return "weak"

    @staticmethod
    def _ranking_level(
        *,
        alpha: Optional[float],
        main_profit: Optional[float],
        secondary_profit: Optional[float],
        watch_profit: Optional[float],
    ) -> str:
        main_value = main_profit if main_profit is not None else -999.0
        secondary_value = secondary_profit if secondary_profit is not None else -999.0
        watch_value = watch_profit if watch_profit is not None else -999.0
        if (alpha or 0.0) >= 0.5 and main_value >= secondary_value >= watch_value:
            return "strong"
        if (alpha or 0.0) >= 0.0:
            return "general"
        return "weak"

    @staticmethod
    def _execution_level(
        *,
        trigger_rate: Optional[float],
        triggered_positive_t2: Optional[float],
        max_drawdown: Optional[float],
    ) -> str:
        if (
            (trigger_rate or 0.0) >= 40.0
            and (triggered_positive_t2 or 0.0) >= 60.0
            and (max_drawdown or 999.0) <= 3.5
        ):
            return "strong"
        if (trigger_rate or 0.0) >= 20.0 and (triggered_positive_t2 or 0.0) >= 50.0:
            return "general"
        return "weak"

    @staticmethod
    def _gate_level(
        *,
        missed_rate: Optional[float],
        allowed_trade_precision: Optional[float],
    ) -> str:
        if (missed_rate or 100.0) <= 20.0 and (allowed_trade_precision or 0.0) >= 55.0:
            return "strong"
        if (missed_rate or 100.0) <= 35.0 and (allowed_trade_precision or 0.0) >= 45.0:
            return "general"
        return "weak"

    @staticmethod
    def _regime_level(regime_breakdown: List[Dict[str, Any]]) -> str:
        strong_rate = MomentumBacktestService._regime_metric(
            regime_breakdown,
            "strong",
            "decision_positive_t2_rate_pct",
        )
        weak_rate = MomentumBacktestService._regime_metric(
            regime_breakdown,
            "weak",
            "decision_positive_t2_rate_pct",
        )
        if (strong_rate or 0.0) >= 60.0 and (weak_rate is None or weak_rate <= 50.0):
            return "strong"
        if (strong_rate or 0.0) >= 50.0:
            return "general"
        return "weak"

    @staticmethod
    def _regime_metric(
        regime_breakdown: List[Dict[str, Any]],
        level: str,
        field: str,
    ) -> Optional[float]:
        item = next((entry for entry in regime_breakdown if entry.get("level") == level), None)
        if not item:
            return None
        return item.get(field)

    @staticmethod
    def _summarize_outcomes(rows: List[MomentumBacktestOutcomeRecord]) -> Dict[str, Optional[float]]:
        if not rows:
            return {
                "sample_count": 0,
                "trigger_rate_pct": None,
                "positive_t1_rate_pct": None,
                "positive_t2_rate_pct": None,
                "settlement_pass_rate_pct": None,
                "t1_direction_pass_rate_pct": None,
                "t2_continuation_pass_rate_pct": None,
                "avg_t1_profit_window_pct": None,
                "avg_t2_profit_window_pct": None,
                "avg_t2_max_drawdown_pct": None,
                "best_t2_profit_window_pct": None,
            }

        sample_count = len(rows)
        trigger_rate_pct = round(sum(1 for row in rows if row.buy_triggered) * 100.0 / sample_count, 2)
        positive_t1_rate_pct = round(
            sum(1 for row in rows if MomentumBacktestService._outcome_t1_direction_pass(row)) * 100.0 / sample_count,
            2,
        )
        positive_t2_rate_pct = round(
            sum(1 for row in rows if MomentumBacktestService._outcome_settlement_pass(row)) * 100.0 / sample_count,
            2,
        )
        t2_continuation_pass_rate_pct = round(
            sum(1 for row in rows if MomentumBacktestService._outcome_t2_continuation_pass(row)) * 100.0 / sample_count,
            2,
        )
        return {
            "sample_count": sample_count,
            "trigger_rate_pct": trigger_rate_pct,
            "positive_t1_rate_pct": positive_t1_rate_pct,
            "positive_t2_rate_pct": positive_t2_rate_pct,
            "settlement_pass_rate_pct": positive_t2_rate_pct,
            "t1_direction_pass_rate_pct": positive_t1_rate_pct,
            "t2_continuation_pass_rate_pct": t2_continuation_pass_rate_pct,
            "avg_t1_profit_window_pct": MomentumBacktestService._avg_metric(row.t1_profit_window_pct for row in rows),
            "avg_t2_profit_window_pct": MomentumBacktestService._avg_metric(row.t2_profit_window_pct for row in rows),
            "avg_t2_max_drawdown_pct": MomentumBacktestService._avg_metric(row.t2_max_drawdown_pct for row in rows),
            "best_t2_profit_window_pct": MomentumBacktestService._max_metric(row.t2_profit_window_pct for row in rows),
        }

    @staticmethod
    def _outcome_payload(row: MomentumBacktestOutcomeRecord) -> Dict[str, Any]:
        try:
            payload = json.loads(row.outcome_payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _outcome_t1_direction_pass(row: MomentumBacktestOutcomeRecord) -> bool:
        payload = MomentumBacktestService._outcome_payload(row)
        if "t1_direction_pass" in payload:
            return bool(payload.get("t1_direction_pass"))
        if row.t1_close_return_pct is None and row.t2_close_return_pct is not None:
            return row.t2_close_return_pct > 0.0
        return (row.t1_close_return_pct or 0.0) > 0.0

    @staticmethod
    def _outcome_t2_continuation_pass(row: MomentumBacktestOutcomeRecord) -> bool:
        payload = MomentumBacktestService._outcome_payload(row)
        if "t2_continuation_pass" in payload:
            return bool(payload.get("t2_continuation_pass"))
        return (row.t2_close_return_pct or 0.0) > 0.0

    @staticmethod
    def _outcome_settlement_pass(row: MomentumBacktestOutcomeRecord) -> bool:
        payload = MomentumBacktestService._outcome_payload(row)
        if "settlement_pass" in payload:
            return bool(payload.get("settlement_pass"))
        if row.t1_close_return_pct is None and row.t2_close_return_pct is not None:
            return row.t2_close_return_pct > 0.0
        return (
            MomentumBacktestService._outcome_t1_direction_pass(row)
            and MomentumBacktestService._outcome_t2_continuation_pass(row)
        )

    @staticmethod
    def _avg_metric(values: Iterable[Optional[float]]) -> Optional[float]:
        valid = [float(value) for value in values if value is not None]
        if not valid:
            return None
        return round(sum(valid) / len(valid), 4)

    @staticmethod
    def _max_metric(values: Iterable[Optional[float]]) -> Optional[float]:
        valid = [float(value) for value in values if value is not None]
        if not valid:
            return None
        return round(max(valid), 4)

    def _build_outcome_group(self, rows: List[MomentumBacktestOutcomeRecord]) -> Dict[str, Any]:
        return {
            "metrics": self._summarize_outcomes(rows),
            "items": [self._serialize_outcome_record(row) for row in rows],
        }

    @staticmethod
    def _serialize_candidate_record(
        row: MomentumBacktestCandidateRecord,
        outcome: Optional[MomentumBacktestOutcomeRecord],
    ) -> Dict[str, Any]:
        payload_snapshot = MomentumBacktestService._load_json(row.candidate_payload_json) or {}
        payload = {
            "rank": row.rank,
            "ts_code": row.ts_code,
            "name": row.name,
            "theme": row.theme,
            "role": row.role,
            "market_segment": row.market_segment,
            "rank_score": row.rank_score,
            "final_score": row.final_score,
            "continuation_score": row.continuation_score,
            "extension_score": row.extension_score,
            "risk_score": row.risk_score,
            "buyability_score": row.buyability_score,
        }
        diagnostics = payload_snapshot.get("_decision_diagnostics")
        if isinstance(diagnostics, dict):
            payload["decision_diagnostics"] = diagnostics
        if outcome is not None:
            payload["outcome"] = MomentumBacktestService._serialize_outcome_record(outcome)
        return payload

    @staticmethod
    def _serialize_decision_record(
        row: MomentumBacktestDecisionRecord,
        outcome: Optional[MomentumBacktestOutcomeRecord],
    ) -> Dict[str, Any]:
        payload = {
            "slot": row.slot,
            "rank": row.rank,
            "ts_code": row.ts_code,
            "name": row.name,
            "theme": row.theme,
            "role": row.role,
            "decision_score": row.decision_score,
            "rank_score": row.rank_score,
            "risk_score": row.risk_score,
            "buy_point_status": row.buy_point_status,
            "suggested_action": row.suggested_action,
            "entry_range_low": row.entry_range_low,
            "entry_range_high": row.entry_range_high,
            "opportunity_tag": row.opportunity_tag,
        }
        if outcome is not None:
            payload["outcome"] = MomentumBacktestService._serialize_outcome_record(outcome)
        return payload

    @staticmethod
    def _serialize_outcome_record(row: MomentumBacktestOutcomeRecord) -> Dict[str, Any]:
        return {
            "view_scope": row.view_scope,
            "slot": row.slot,
            "ts_code": row.ts_code,
            "name": row.name,
            "buy_triggered": row.buy_triggered,
            "reference_entry_price": row.reference_entry_price,
            "trigger_price": row.trigger_price,
            "trigger_trade_date": row.trigger_trade_date.isoformat() if row.trigger_trade_date else None,
            "t1_trade_date": row.t1_trade_date.isoformat() if row.t1_trade_date else None,
            "t1_close_return_pct": row.t1_close_return_pct,
            "t1_profit_window_pct": row.t1_profit_window_pct,
            "t1_max_drawdown_pct": row.t1_max_drawdown_pct,
            "t2_trade_date": row.t2_trade_date.isoformat() if row.t2_trade_date else None,
            "t2_close_return_pct": row.t2_close_return_pct,
            "t2_profit_window_pct": row.t2_profit_window_pct,
            "t2_max_drawdown_pct": row.t2_max_drawdown_pct,
            "real_strength_label": row.real_strength_label,
            "settlement_rule": MomentumBacktestService._outcome_payload(row).get("settlement_rule"),
            "t1_direction_pass": MomentumBacktestService._outcome_t1_direction_pass(row),
            "t2_continuation_pass": MomentumBacktestService._outcome_t2_continuation_pass(row),
            "settlement_pass": MomentumBacktestService._outcome_settlement_pass(row),
        }

    def _build_diagnosis_summary_lines(
        self,
        *,
        daily_row: MomentumBacktestDailySummary,
        candidate_metrics: Dict[str, Optional[float]],
        decision_metrics: Dict[str, Optional[float]],
        gate_blockers: List[Dict[str, Any]],
        issues: List[Dict[str, Any]],
    ) -> List[str]:
        lines = [
            (
                f"当日结论为 {daily_row.action_label}，"
                f"候选池短线延续合格率 {self._format_pct(candidate_metrics['positive_t2_rate_pct'])}，"
                f"默认组合短线延续合格率 {self._format_pct(decision_metrics['positive_t2_rate_pct'])}。"
            ),
            (
                f"候选池 T+2 平均利润窗口 {self._format_pct(candidate_metrics['avg_t2_profit_window_pct'])}，"
                f"默认组合 T+2 平均利润窗口 {self._format_pct(decision_metrics['avg_t2_profit_window_pct'])}，"
                f"默认组合 T+2 平均最大回撤 {self._format_pct(decision_metrics['avg_t2_max_drawdown_pct'])}。"
            ),
        ]
        if gate_blockers:
            blocker_labels = "、".join(str(item.get("label") or "") for item in gate_blockers[:3] if item.get("label"))
            if blocker_labels:
                lines.append(f"当日总闸门拖后腿模块：{blocker_labels}。")
        if issues:
            titles = "；".join(issue["title"] for issue in issues[:3])
            lines.append(f"本日主要问题：{titles}。")
        else:
            lines.append("本日暂未识别出明显的候选池、排序、买点或总闸门问题。")
        return lines

    @staticmethod
    def _format_pct(value: Optional[float]) -> str:
        if value is None:
            return "--"
        return f"{value:.2f}%"

    @staticmethod
    def _format_number(value: Optional[float]) -> str:
        if value is None:
            return "--"
        return f"{value:.1f}"

    @staticmethod
    def _slot_sort_key(row: MomentumBacktestDecisionRecord) -> int:
        order = {"main": 0, "secondary": 1, "watch": 2}
        return order.get(row.slot, 99)

    @staticmethod
    def _issue_severity_rank(severity: str) -> int:
        order = {"critical": 3, "warning": 2, "info": 1}
        return order.get(severity, 0)

    def _list_trade_dates(self, start_dt: date, end_dt: date) -> List[date]:
        fetcher = self.screener_service.fetcher
        parsed: List[date] = []

        trade_dates_loader = getattr(fetcher, "_get_trade_dates", None)
        if callable(trade_dates_loader):
            try:
                trade_dates = list(trade_dates_loader(end_dt.strftime("%Y%m%d")) or [])
                parsed = self._filter_trade_dates_to_range(
                    trade_dates,
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
                if parsed and parsed[0] > start_dt:
                    logger.info(
                        "Momentum backtest trade dates cache is incomplete for %s -> %s, falling back to trade_cal",
                        start_dt.isoformat(),
                        end_dt.isoformat(),
                    )
                    parsed = []
            except Exception:  # noqa: BLE001
                logger.exception("Momentum backtest failed to load trade dates via _get_trade_dates")

        if not parsed:
            attr_dates = getattr(fetcher, "trade_dates", None)
            if isinstance(attr_dates, list) and attr_dates:
                parsed = self._filter_trade_dates_to_range(
                    [str(item) for item in attr_dates],
                    start_dt=start_dt,
                    end_dt=end_dt,
                )
                if parsed and parsed[0] > start_dt:
                    parsed = []

        if not parsed:
            try:
                calendar = fetcher._call_api_with_rate_limit(  # noqa: SLF001
                    "trade_cal",
                    exchange="SSE",
                    start_date=start_dt.strftime("%Y%m%d"),
                    end_date=end_dt.strftime("%Y%m%d"),
                )
                if isinstance(calendar, pd.DataFrame) and not calendar.empty and "cal_date" in calendar.columns:
                    if "is_open" in calendar.columns:
                        calendar = calendar[calendar["is_open"] == 1]
                    parsed = self._filter_trade_dates_to_range(
                        calendar["cal_date"].astype(str).tolist(),
                        start_dt=start_dt,
                        end_dt=end_dt,
                    )
            except Exception:  # noqa: BLE001
                logger.exception("Momentum backtest failed to load trade dates via trade_cal")

        return parsed

    @staticmethod
    def _filter_trade_dates_to_range(
        trade_dates: List[str],
        *,
        start_dt: date,
        end_dt: date,
    ) -> List[date]:
        parsed: List[date] = []
        for item in trade_dates:
            try:
                trade_dt = datetime.strptime(str(item), "%Y%m%d").date()
            except (TypeError, ValueError):
                continue
            if start_dt <= trade_dt <= end_dt:
                parsed.append(trade_dt)
        return sorted(set(parsed))

    def _load_forward_bars(self, ts_code: str, trade_dt: date, days: int = 2) -> List[Dict[str, Any]]:
        fetcher = self.screener_service.fetcher
        end_dt = trade_dt + timedelta(days=10)
        history = fetcher.get_daily_data(
            ts_code,
            start_date=trade_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
            days=20,
        )
        if history is None or history.empty:
            return []

        working = history.copy()
        if "date" in working.columns:
            working["date"] = pd.to_datetime(working["date"]).dt.date
        elif "trade_date" in working.columns:
            working["date"] = pd.to_datetime(working["trade_date"].astype(str)).dt.date
        else:
            return []

        working = working[working["date"] > trade_dt].sort_values("date")
        if working.empty:
            return []
        return working.head(days + 2).to_dict("records")

    @staticmethod
    def _compute_window_stats(base_price: Optional[float], bars: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
        if base_price is None or base_price <= 0 or not bars:
            return {
                "close_return_pct": None,
                "profit_window_pct": None,
                "max_drawdown_pct": None,
            }

        close_price = MomentumBacktestService._to_float(bars[-1].get("close"))
        highs = [MomentumBacktestService._to_float(bar.get("high")) for bar in bars]
        lows = [MomentumBacktestService._to_float(bar.get("low")) for bar in bars]
        valid_highs = [value for value in highs if value is not None]
        valid_lows = [value for value in lows if value is not None]
        return {
            "close_return_pct": MomentumBacktestService._pct(close_price, base_price),
            "profit_window_pct": MomentumBacktestService._pct(max(valid_highs), base_price) if valid_highs else None,
            "max_drawdown_pct": round(max(0.0, (base_price - min(valid_lows)) * 100.0 / base_price), 4)
            if valid_lows
            else None,
        }

    @staticmethod
    def _pct(value: Optional[float], base: Optional[float]) -> Optional[float]:
        if value is None or base in {None, 0}:
            return None
        return round((float(value) - float(base)) * 100.0 / float(base), 4)

    @staticmethod
    def _parse_trade_date(value: str) -> date:
        normalized = value.replace("-", "")
        return datetime.strptime(normalized, "%Y%m%d").date()

    @staticmethod
    def _dump_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _load_json(payload: Optional[str]) -> Optional[Dict[str, Any]]:
        if not payload:
            return None
        return json.loads(payload)

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _portfolio_slot_code(portfolio: List[Dict[str, Any]], slot: str) -> Optional[str]:
        for item in portfolio:
            if item.get("slot") == slot:
                return str(item.get("ts_code") or "")
        return None

    @staticmethod
    def _first_theme(item: Dict[str, Any]) -> Optional[str]:
        themes = item.get("themes")
        if isinstance(themes, list) and themes:
            return str(themes[0])
        return None

    def _serialize_run(self, run: MomentumBacktestRun) -> Dict[str, Any]:
        return {
            "run_id": run.run_id,
            "status": run.status,
            "profile": run.profile,
            "engine_version": run.engine_version,
            "strategy_health_mode": self._normalize_strategy_health_mode(
                strategy_health_mode=getattr(run, "strategy_health_mode", None),
            ),
            "strategy_health_mode_label": self._strategy_health_mode_label(
                getattr(run, "strategy_health_mode", None),
            ),
            "entry_baseline_version": run.entry_baseline_version,
            "market_scope_version": run.market_scope_version,
            "top_n": run.top_n,
            "start_trade_date": run.start_trade_date.isoformat(),
            "end_trade_date": run.end_trade_date.isoformat(),
            "total_trade_dates": run.total_trade_dates,
            "processed_trade_dates": run.processed_trade_dates,
            "failed_trade_dates": run.failed_trade_dates,
            "current_trade_date": run.current_trade_date.isoformat() if run.current_trade_date else None,
            "current_stage_key": run.current_stage_key,
            "current_stage_label": run.current_stage_label,
            "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "cancel_requested": bool(run.cancel_requested),
            "summary": self._load_json(run.summary_json),
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }

    @staticmethod
    def _serialize_daily_summary(row: MomentumBacktestDailySummary) -> Dict[str, Any]:
        return {
            "trade_date": row.trade_date.isoformat(),
            "action_level": row.action_level,
            "action_label": row.action_label,
            "recommendation_cap": row.recommendation_cap,
            "action_checklist_mode": row.action_checklist_mode,
            "market_environment_level": row.market_environment_level,
            "opportunity_quality_level": row.opportunity_quality_level,
            "historical_validity_level": row.historical_validity_level,
            "candidate_count": row.candidate_count,
            "result_count": row.result_count,
            "selected_count": row.selected_count,
            "buy_ready_count": row.buy_ready_count,
            "main_ts_code": row.main_ts_code,
            "secondary_ts_code": row.secondary_ts_code,
            "watch_ts_code": row.watch_ts_code,
        }
