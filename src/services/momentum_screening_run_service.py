from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import date, datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from src.repositories.momentum_screening_run_repo import MomentumScreeningRunRepository
from src.services.momentum_screener_service import (
    MOMENTUM_DEFAULT_MIN_AMOUNT,
    MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
    MOMENTUM_DEFAULT_MIN_TURNOVER,
    MOMENTUM_DEFAULT_TOP_N,
    MOMENTUM_ENTRY_BASELINE_VERSION,
    MOMENTUM_MARKET_SCOPE_VERSION,
    MOMENTUM_SCREENING_CACHE_VERSION,
    MomentumScreenerService,
)
from src.services.momentum_secondary_decision_service import (
    STRATEGY_HEALTH_MODE_CACHED_ONLY,
    MomentumSecondaryDecisionService,
)
from src.storage import MomentumScreeningRun

logger = logging.getLogger(__name__)

MOMENTUM_SCREENING_RUN_ENGINE_VERSION = "v1_5_taskized"
MOMENTUM_SCREENING_TRUTH_MODE_FULL = "full"
MOMENTUM_SCREENING_TRUTH_MODE_LIGHT = "light"
ACTIVE_RUN_STATUSES = {"queued", "running"}
REUSABLE_RUN_STATUSES = {"queued", "running", "completed"}
RUN_STAGE_LABELS = {
    "queued": "等待后台调度",
    "preparing": "准备筛选任务",
    "trade_snapshot": "加载交易日快照",
    "candidate_pool": "构建候选池",
    "sector_context": "加载题材与板块上下文",
    "v13_context": "加载 V1.3 真实题材画像",
    "scoring": "执行评分排序",
    "secondary_decision": "生成二次决策",
    "result_persist": "写入筛选结果",
    "cancel_requested": "取消请求处理中",
    "cancelled": "任务已取消",
    "completed": "任务已完成",
    "failed": "任务执行失败",
}


class _MomentumScreeningCancelled(RuntimeError):
    """Raised when a screening run is cancelled by the user."""


class MomentumScreeningRunService:
    """Taskized momentum screener execution with progress polling and reuse."""

    def __init__(
        self,
        screener_service: Optional[MomentumScreenerService] = None,
        decision_service: Optional[MomentumSecondaryDecisionService] = None,
        repository: Optional[MomentumScreeningRunRepository] = None,
    ) -> None:
        self.screener_service = screener_service or MomentumScreenerService()
        self.decision_service = decision_service or MomentumSecondaryDecisionService(
            screener_service=self.screener_service,
            strategy_health_async=False,
        )
        self.repository = repository or MomentumScreeningRunRepository()
        self.stage_heartbeat_interval_seconds = 5.0
        self._run_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._worker_wake_event = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="momentum-screening-run-queue",
            daemon=True,
        )
        requeued_count = self.repository.reset_running_runs_to_queued()
        if requeued_count:
            logger.info("Recovered %s running screening run(s) back into the queue", requeued_count)
        self._worker_thread.start()

    def create_run_async(
        self,
        *,
        top_n: int = MOMENTUM_DEFAULT_TOP_N,
        min_change_pct: float = MOMENTUM_DEFAULT_MIN_CHANGE_PCT,
        min_amount: float = MOMENTUM_DEFAULT_MIN_AMOUNT,
        min_turnover: float = MOMENTUM_DEFAULT_MIN_TURNOVER,
        exclude_st: bool = True,
        main_board_only: bool = False,
        trade_date: Optional[str] = None,
        profile: str = "standard",
        truth_mode: str = MOMENTUM_SCREENING_TRUTH_MODE_FULL,
        use_sector_context: bool = True,
        max_scored_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:
        if profile not in {"standard", "aggressive"}:
            raise ValueError("Only standard/aggressive profiles are supported")

        normalized_truth_mode = self._normalize_truth_mode(truth_mode)
        request_params = self._build_request_params(
            top_n=top_n,
            min_change_pct=min_change_pct,
            min_amount=min_amount,
            min_turnover=min_turnover,
            exclude_st=exclude_st,
            main_board_only=main_board_only,
            trade_date=trade_date,
            profile=profile,
            truth_mode=normalized_truth_mode,
            use_sector_context=use_sector_context,
            max_scored_candidates=max_scored_candidates,
        )
        request_fingerprint = self._build_request_fingerprint(request_params)

        with self._run_lock:
            existing = self.repository.find_run_by_fingerprint(request_fingerprint)
            if existing is not None and existing.status in REUSABLE_RUN_STATUSES:
                return {
                    "created_new": False,
                    "message": "已存在相同参数任务，已为你定位到该任务",
                    "run": self._serialize_run(existing),
                }

            has_running = self.repository.get_first_run_by_statuses(("running",), ascending=True) is not None
            has_queued = self.repository.get_first_run_by_statuses(("queued",), ascending=True) is not None
            initial_status = "queued" if (has_running or has_queued) else "running"
            now = datetime.now()
            run = MomentumScreeningRun(
                run_id=f"momentum_sr_{uuid4().hex[:16]}",
                status=initial_status,
                profile=profile,
                truth_mode=normalized_truth_mode,
                engine_version=MOMENTUM_SCREENING_RUN_ENGINE_VERSION,
                entry_baseline_version=MOMENTUM_ENTRY_BASELINE_VERSION,
                market_scope_version=MOMENTUM_MARKET_SCOPE_VERSION,
                screening_cache_version=MOMENTUM_SCREENING_CACHE_VERSION,
                top_n=int(top_n),
                requested_trade_date=self._normalize_trade_date_str(trade_date),
                trade_date=None,
                min_change_pct=float(min_change_pct),
                min_amount=float(min_amount),
                min_turnover=float(min_turnover),
                exclude_st=bool(exclude_st),
                main_board_only=bool(main_board_only),
                use_sector_context=bool(use_sector_context),
                max_scored_candidates=int(max_scored_candidates or 0) or None,
                request_fingerprint=request_fingerprint,
                request_params_json=self._dump_json(request_params),
                progress_pct=0.0,
                processed_item_count=0,
                total_item_count=0,
                current_stage_key="preparing" if initial_status == "running" else "queued",
                current_stage_label=RUN_STAGE_LABELS["preparing"] if initial_status == "running" else RUN_STAGE_LABELS["queued"],
                cache_hits_json=self._dump_json({}),
                cache_misses_json=self._dump_json({}),
                screening_payload_json=None,
                decision_payload_json=None,
                error_message=None,
                heartbeat_at=now,
                started_at=now if initial_status == "running" else None,
                finished_at=None,
                cancel_requested=False,
            )
            created = self.repository.create_run(run)

        self._worker_wake_event.set()
        message = (
            "当前已有筛选任务在运行，你的任务已进入队列"
            if initial_status == "queued"
            else "已创建筛选任务，正在后台计算"
        )
        return {
            "created_new": True,
            "message": message,
            "run": self._serialize_run(created),
        }

    def get_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Screening run not found: {run_id}")
        return self._serialize_run(run)

    def list_runs(
        self,
        *,
        limit: int = 20,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_limit = min(max(int(limit), 1), 50)
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

    def get_result(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Screening run not found: {run_id}")
        if run.status != "completed":
            raise ValueError("Screening run result is not ready yet")

        screening = self._load_json(run.screening_payload_json)
        decision = self._load_json(run.decision_payload_json)
        if not isinstance(screening, dict) or not isinstance(decision, dict):
            raise ValueError("Screening run result payload is incomplete")

        return {
            "run_id": run.run_id,
            "status": run.status,
            "screening": screening,
            "decision": decision,
        }

    def cancel_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Screening run not found: {run_id}")
        if run.status == "queued":
            updated = self.repository.update_run(
                run_id,
                status="cancelled",
                current_stage_key="cancelled",
                current_stage_label=RUN_STAGE_LABELS["cancelled"],
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
                error_message="任务在开始前已取消",
            )
        elif run.status == "running":
            updated = self.repository.update_run(
                run_id,
                cancel_requested=True,
                current_stage_key="cancel_requested",
                current_stage_label=RUN_STAGE_LABELS["cancel_requested"],
                heartbeat_at=datetime.now(),
            )
        else:
            raise ValueError("Only queued or running tasks can be cancelled")

        if updated is None:
            raise ValueError(f"Screening run not found: {run_id}")

        self._worker_wake_event.set()
        payload = self._serialize_run(updated)
        payload["message"] = "任务取消请求已提交"
        return payload

    def close(self, *, timeout: float = 5.0) -> None:
        self._shutdown_event.set()
        self._worker_wake_event.set()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

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
                self._execute_run(run.run_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Momentum screening worker crashed on run %s: %s", run.run_id, exc)

    def _promote_next_queued_run(self) -> Optional[MomentumScreeningRun]:
        with self._run_lock:
            queued = self.repository.get_first_run_by_statuses(("queued",), ascending=True)
            if queued is None:
                return None
            return self.repository.update_run(
                queued.run_id,
                status="running",
                current_stage_key="preparing",
                current_stage_label=RUN_STAGE_LABELS["preparing"],
                heartbeat_at=datetime.now(),
                started_at=datetime.now(),
                finished_at=None,
                cancel_requested=False,
                error_message=None,
            )

    def _execute_run(self, run_id: str) -> None:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"Screening run not found: {run_id}")

        request_params = self._load_request_params(run)
        truth_mode = self._normalize_truth_mode(getattr(run, "truth_mode", None))
        try:
            self.repository.update_run(
                run_id,
                status="running",
                truth_mode=truth_mode,
                current_stage_key="preparing",
                current_stage_label=RUN_STAGE_LABELS["preparing"],
                progress_pct=1.0,
                heartbeat_at=datetime.now(),
                started_at=run.started_at or datetime.now(),
                finished_at=None,
                error_message=None,
            )
            self._raise_if_cancel_requested(run_id)

            screening_label_state = {"value": RUN_STAGE_LABELS["candidate_pool"]}
            self._update_stage(run_id, stage_key="candidate_pool", label_state=screening_label_state)
            stop_screening_heartbeat = self._start_stage_heartbeat(
                run_id=run_id,
                stage_key="candidate_pool",
                label_state=screening_label_state,
            )
            try:
                screening = self.screener_service.screen(
                    top_n=int(request_params.get("top_n", MOMENTUM_DEFAULT_TOP_N)),
                    min_change_pct=float(request_params.get("min_change_pct", MOMENTUM_DEFAULT_MIN_CHANGE_PCT)),
                    min_amount=float(request_params.get("min_amount", MOMENTUM_DEFAULT_MIN_AMOUNT)),
                    min_turnover=float(request_params.get("min_turnover", MOMENTUM_DEFAULT_MIN_TURNOVER)),
                    exclude_st=bool(request_params.get("exclude_st", True)),
                    main_board_only=bool(request_params.get("main_board_only", False)),
                    trade_date=request_params.get("trade_date"),
                    profile=str(request_params.get("profile") or "standard"),
                    truth_mode=truth_mode,
                    use_sector_context=bool(request_params.get("use_sector_context", True)),
                    max_scored_candidates=self._optional_int(request_params.get("max_scored_candidates")),
                    progress_callback=self._build_screening_progress_callback(
                        run_id=run_id,
                        label_state=screening_label_state,
                    ),
                )
            finally:
                stop_screening_heartbeat()

            screening["_request_params"] = request_params
            self._raise_if_cancel_requested(run_id)

            decision_label_state = {"value": RUN_STAGE_LABELS["secondary_decision"]}
            self._update_stage(run_id, stage_key="secondary_decision", label_state=decision_label_state, progress_pct=94.0)
            stop_decision_heartbeat = self._start_stage_heartbeat(
                run_id=run_id,
                stage_key="secondary_decision",
                label_state=decision_label_state,
            )
            try:
                decision = self.decision_service.build_from_screening(
                    screening,
                    request_params=request_params,
                    wait_for_strategy_health=False,
                    strategy_health_mode=STRATEGY_HEALTH_MODE_CACHED_ONLY,
                    strategy_health_progress_callback=self._build_secondary_decision_progress_callback(
                        run_id=run_id,
                        label_state=decision_label_state,
                    ),
                )
            finally:
                stop_decision_heartbeat()

            self._raise_if_cancel_requested(run_id)
            self.repository.update_run(
                run_id,
                current_stage_key="result_persist",
                current_stage_label=RUN_STAGE_LABELS["result_persist"],
                trade_date=self._coerce_trade_date_value(screening.get("trade_date")),
                progress_pct=98.0,
                heartbeat_at=datetime.now(),
                screening_payload_json=self._dump_json(screening),
                decision_payload_json=self._dump_json(decision),
            )
            self.repository.update_run(
                run_id,
                status="completed",
                current_stage_key="completed",
                current_stage_label=RUN_STAGE_LABELS["completed"],
                trade_date=self._coerce_trade_date_value(screening.get("trade_date")),
                progress_pct=100.0,
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
                screening_payload_json=self._dump_json(screening),
                decision_payload_json=self._dump_json(decision),
                error_message=None,
            )
        except _MomentumScreeningCancelled:
            self.repository.update_run(
                run_id,
                status="cancelled",
                current_stage_key="cancelled",
                current_stage_label=RUN_STAGE_LABELS["cancelled"],
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
                error_message="任务已取消，已保留阶段进度",
            )
            logger.info("Momentum screening run cancelled: %s", run_id)
        except Exception as exc:  # noqa: BLE001
            self.repository.update_run(
                run_id,
                status="failed",
                current_stage_key="failed",
                current_stage_label=RUN_STAGE_LABELS["failed"],
                heartbeat_at=datetime.now(),
                finished_at=datetime.now(),
                cancel_requested=False,
                error_message=str(exc),
            )
            raise

    def _raise_if_cancel_requested(self, run_id: str) -> None:
        run = self.repository.get_run(run_id)
        if run is None:
            raise _MomentumScreeningCancelled("run missing during cancellation check")
        if bool(getattr(run, "cancel_requested", False)):
            raise _MomentumScreeningCancelled("run cancelled")

    def _update_stage(
        self,
        run_id: str,
        *,
        stage_key: str,
        label_state: Optional[Dict[str, Any]] = None,
        progress_pct: Optional[float] = None,
    ) -> None:
        stage_label = (
            str(label_state.get("value"))
            if isinstance(label_state, dict) and label_state.get("value")
            else RUN_STAGE_LABELS.get(stage_key, stage_key)
        )
        fields: Dict[str, Any] = {
            "current_stage_key": stage_key,
            "current_stage_label": stage_label,
            "heartbeat_at": datetime.now(),
        }
        if progress_pct is not None:
            fields["progress_pct"] = float(progress_pct)
        self.repository.update_run(run_id, **fields)

    def _start_stage_heartbeat(
        self,
        *,
        run_id: str,
        stage_key: str,
        label_state: Optional[Dict[str, Any]] = None,
        interval_seconds: Optional[float] = None,
    ):
        stop_event = threading.Event()
        heartbeat_interval_seconds = float(interval_seconds or self.stage_heartbeat_interval_seconds)

        def _heartbeat_loop() -> None:
            while not stop_event.wait(heartbeat_interval_seconds):
                try:
                    self._update_stage(run_id, stage_key=stage_key, label_state=label_state)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to refresh heartbeat for momentum screening stage: run_id=%s stage=%s",
                        run_id,
                        stage_key,
                    )

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"momentum-screening-heartbeat-{run_id}-{stage_key}",
            daemon=True,
        )
        heartbeat_thread.start()

        def _stop() -> None:
            stop_event.set()
            if heartbeat_thread.is_alive():
                heartbeat_thread.join(timeout=1.0)

        return _stop

    def _build_screening_progress_callback(
        self,
        *,
        run_id: str,
        label_state: Optional[Dict[str, Any]] = None,
    ):
        last_signature: Dict[str, Any] = {}

        def _callback(progress: Dict[str, Any]) -> None:
            if not isinstance(progress, dict):
                return
            stage_key = str(progress.get("stage_key") or "candidate_pool")
            stage_label = str(progress.get("stage_label") or RUN_STAGE_LABELS.get(stage_key, stage_key))
            signature = {
                "stage_key": stage_key,
                "stage_label": stage_label,
                "progress_pct": round(float(progress.get("progress_pct") or 0.0), 2),
                "processed_item_count": int(progress.get("processed_item_count") or 0),
                "total_item_count": int(progress.get("total_item_count") or 0),
            }
            if signature == last_signature:
                return
            last_signature.clear()
            last_signature.update(signature)
            if isinstance(label_state, dict):
                label_state["value"] = stage_label
            self.repository.update_run(
                run_id,
                current_stage_key=stage_key,
                current_stage_label=stage_label,
                trade_date=self._coerce_trade_date_value(progress.get("trade_date")),
                progress_pct=signature["progress_pct"],
                processed_item_count=signature["processed_item_count"],
                total_item_count=signature["total_item_count"],
                cache_hits_json=self._dump_json(progress.get("cache_hits") or {}),
                cache_misses_json=self._dump_json(progress.get("cache_misses") or {}),
                heartbeat_at=datetime.now(),
            )

        return _callback

    def _build_secondary_decision_progress_callback(
        self,
        *,
        run_id: str,
        label_state: Optional[Dict[str, Any]] = None,
    ):
        last_signature: Dict[str, Any] = {}

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
            if signature == last_signature:
                return
            last_signature.clear()
            last_signature.update(signature)

            label_builder = getattr(self.decision_service, "_build_secondary_decision_progress_label", None)
            stage_label = (
                label_builder(progress)
                if callable(label_builder)
                else RUN_STAGE_LABELS["secondary_decision"]
            )
            if isinstance(label_state, dict):
                label_state["value"] = stage_label

            self.repository.update_run(
                run_id,
                current_stage_key="secondary_decision",
                current_stage_label=str(stage_label),
                progress_pct=96.0,
                processed_item_count=signature["valid_sample_count"],
                total_item_count=signature["total_trade_date_count"],
                heartbeat_at=datetime.now(),
            )

        return _callback

    def _serialize_run(self, run: MomentumScreeningRun) -> Dict[str, Any]:
        return {
            "run_id": run.run_id,
            "status": run.status,
            "profile": run.profile,
            "truth_mode": self._normalize_truth_mode(getattr(run, "truth_mode", None)),
            "engine_version": run.engine_version,
            "entry_baseline_version": run.entry_baseline_version,
            "market_scope_version": run.market_scope_version,
            "screening_cache_version": run.screening_cache_version,
            "top_n": run.top_n,
            "requested_trade_date": self._format_trade_date_str(run.requested_trade_date),
            "trade_date": self._format_trade_date_str(run.trade_date),
            "result_available": bool(run.status == "completed" and run.screening_payload_json and run.decision_payload_json),
            "request_params": self._load_json(run.request_params_json) or {},
            "current_stage_key": run.current_stage_key,
            "current_stage_label": run.current_stage_label,
            "progress": {
                "progress_pct": float(run.progress_pct or 0.0),
                "processed_item_count": int(run.processed_item_count or 0),
                "total_item_count": int(run.total_item_count or 0),
                "cache_hits": self._load_json(run.cache_hits_json) or {},
                "cache_misses": self._load_json(run.cache_misses_json) or {},
            },
            "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "cancel_requested": bool(run.cancel_requested),
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }

    @staticmethod
    def _normalize_truth_mode(truth_mode: Optional[str]) -> str:
        return (
            MOMENTUM_SCREENING_TRUTH_MODE_FULL
            if str(truth_mode or "").strip().lower() == MOMENTUM_SCREENING_TRUTH_MODE_FULL
            else MOMENTUM_SCREENING_TRUTH_MODE_LIGHT
        )

    @staticmethod
    def _normalize_trade_date_str(trade_date: Any) -> Optional[str]:
        normalized = str(trade_date or "").strip().replace("-", "")
        if len(normalized) != 8 or not normalized.isdigit():
            return None
        return normalized

    @staticmethod
    def _coerce_trade_date_value(trade_date: Any) -> Optional[date]:
        normalized = MomentumScreeningRunService._normalize_trade_date_str(trade_date)
        if not normalized:
            return None
        return datetime.strptime(normalized, "%Y%m%d").date()

    @staticmethod
    def _format_trade_date_str(trade_date: Optional[str]) -> Optional[str]:
        normalized = MomentumScreeningRunService._normalize_trade_date_str(trade_date)
        if not normalized:
            return None
        return f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}"

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _build_request_params(
        self,
        *,
        top_n: int,
        min_change_pct: float,
        min_amount: float,
        min_turnover: float,
        exclude_st: bool,
        main_board_only: bool,
        trade_date: Optional[str],
        profile: str,
        truth_mode: str,
        use_sector_context: bool,
        max_scored_candidates: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "top_n": int(top_n),
            "min_change_pct": float(min_change_pct),
            "min_amount": float(min_amount),
            "min_turnover": float(min_turnover),
            "exclude_st": bool(exclude_st),
            "main_board_only": bool(main_board_only),
            "trade_date": self._format_trade_date_str(trade_date),
            "reuse_scope_date": self._build_reuse_scope_date(trade_date),
            "profile": str(profile),
            "truth_mode": self._normalize_truth_mode(truth_mode),
            "use_sector_context": bool(use_sector_context),
            "max_scored_candidates": self._optional_int(max_scored_candidates),
        }

    def _build_reuse_scope_date(self, trade_date: Optional[str]) -> str:
        explicit_trade_date = self._format_trade_date_str(trade_date)
        if explicit_trade_date:
            return explicit_trade_date
        current_time = getattr(self.screener_service, "_get_china_now", None)
        if callable(current_time):
            try:
                resolved = current_time()
                if isinstance(resolved, datetime):
                    return resolved.strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                logger.debug("Failed to resolve current China date for screening run reuse scope", exc_info=True)
        return datetime.now().strftime("%Y-%m-%d")

    def _build_request_fingerprint(self, request_params: Dict[str, Any]) -> str:
        fingerprint_payload = {
            **request_params,
            "engine_version": MOMENTUM_SCREENING_RUN_ENGINE_VERSION,
            "entry_baseline_version": MOMENTUM_ENTRY_BASELINE_VERSION,
            "market_scope_version": MOMENTUM_MARKET_SCOPE_VERSION,
            "screening_cache_version": MOMENTUM_SCREENING_CACHE_VERSION,
        }
        canonical = json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(canonical.encode("utf-8")).hexdigest()

    def _load_request_params(self, run: MomentumScreeningRun) -> Dict[str, Any]:
        payload = self._load_json(run.request_params_json)
        if isinstance(payload, dict) and payload:
            return payload
        return self._build_request_params(
            top_n=int(run.top_n or MOMENTUM_DEFAULT_TOP_N),
            min_change_pct=float(run.min_change_pct or MOMENTUM_DEFAULT_MIN_CHANGE_PCT),
            min_amount=float(run.min_amount or MOMENTUM_DEFAULT_MIN_AMOUNT),
            min_turnover=float(run.min_turnover or MOMENTUM_DEFAULT_MIN_TURNOVER),
            exclude_st=bool(run.exclude_st),
            main_board_only=bool(run.main_board_only),
            trade_date=run.requested_trade_date,
            profile=run.profile or "standard",
            truth_mode=run.truth_mode or MOMENTUM_SCREENING_TRUTH_MODE_FULL,
            use_sector_context=bool(run.use_sector_context),
            max_scored_candidates=run.max_scored_candidates,
        )

    @staticmethod
    def _dump_json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _load_json(payload: Optional[str]) -> Any:
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
