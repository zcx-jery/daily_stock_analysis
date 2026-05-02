# -*- coding: utf-8 -*-
"""Momentum screener AI commentary service."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from api.v1.schemas.momentum_ai import (
    MomentumScreenerAIContextMeta,
    MomentumScreenerAIReviewRequest,
    MomentumScreenerAISessionResponse,
)
from src.agent.factory import get_tool_registry
from src.agent.llm_adapter import LLMToolAdapter
from src.agent.runner import run_agent_loop
from src.config import get_config
from src.storage import get_db

logger = logging.getLogger(__name__)

SESSION_PREFIX = "screener_ai"
SESSION_VERSION = "v2"
META_PREFIX = "__SCREENER_AI_META__:"

TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "get_realtime_quote": "实时行情",
    "get_daily_history": "历史 K 线",
    "get_chip_distribution": "筹码分布",
    "get_analysis_context": "历史分析上下文",
    "get_stock_info": "股票基本信息",
    "search_stock_news": "个股新闻",
    "search_comprehensive_intel": "综合情报",
    "analyze_trend": "技术趋势",
    "calculate_ma": "均线系统",
    "get_volume_analysis": "量能分析",
    "analyze_pattern": "形态识别",
    "get_market_indices": "市场指数",
    "get_sector_rankings": "板块强度",
}

REVIEW_TYPE_LABELS: Dict[str, str] = {
    "candidate": "候选股 AI 点评",
    "decision": "二次决策 AI 综合建议",
    "intraday": "盘中信号 AI 解读",
    "excluded": "落选说明 AI 分析",
}


class MomentumScreenerAICommentaryService:
    """Provide AI commentary for momentum screener page snapshots."""

    def __init__(
        self,
        config=None,
        tool_registry=None,
        llm_adapter=None,
    ) -> None:
        self.config = config or get_config()
        self.tool_registry = tool_registry or get_tool_registry()
        self.llm_adapter = llm_adapter or LLMToolAdapter(self.config)

    def load_session(self, request: MomentumScreenerAIReviewRequest) -> Dict[str, Any]:
        session_id = request.session_id or self.build_session_id(request)
        return MomentumScreenerAISessionResponse(
            session_id=session_id,
            review_type=request.review_type,
            review_type_label=self._review_type_label(request.review_type),
            session_title=self._build_session_title(request),
            messages=self._load_session_messages(session_id),
        ).model_dump()

    def stream_review(
        self,
        request: MomentumScreenerAIReviewRequest,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        session_id = request.session_id or self.build_session_id(request)
        user_message = (request.message or self._build_default_user_message(request)).strip()
        if not user_message:
            raise ValueError("AI 点评请求不能为空")

        if progress_callback:
            progress_callback(
                {
                    "type": "stage",
                    "stage": "context",
                    "message": "已载入规则结论、筛选快照和当前点评对象。",
                }
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt(request)},
        ]
        if request.message and request.refresh_mode == "resume":
            messages.extend(self._load_history_for_llm(session_id))
        messages.append({"role": "user", "content": user_message})

        translated_progress = self._build_progress_callback(progress_callback)
        result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=getattr(self.config, "agent_max_steps", 8),
            progress_callback=translated_progress,
            max_wall_clock_seconds=getattr(self.config, "agent_orchestrator_timeout_s", 0),
        )
        if not result.success or not result.content:
            raise RuntimeError(result.error or "AI 点评生成失败")

        context_meta = self._build_context_meta(request, result.tool_calls_log)
        suggested_questions = self._build_suggested_questions(request.review_type)
        self._persist_turn(
            session_id=session_id,
            user_message=user_message,
            assistant_message=result.content,
            context_meta=context_meta,
            suggested_questions=suggested_questions,
        )
        return {
            "session_id": session_id,
            "success": True,
            "content": result.content,
            "context_meta": context_meta.model_dump(),
            "suggested_questions": suggested_questions,
        }

    def build_session_id(self, request: MomentumScreenerAIReviewRequest) -> str:
        normalized_payload = {
            "session_version": SESSION_VERSION,
            "profile": request.payload.profile,
            "trade_date": request.screening.trade_date,
            "requested_trade_date": request.screening.requested_trade_date,
            "min_change_pct": request.payload.min_change_pct,
            "min_amount": request.payload.min_amount,
            "min_turnover": request.payload.min_turnover,
            "exclude_st": request.payload.exclude_st,
            "main_board_only": request.payload.main_board_only,
            "review_type": request.review_type,
            "review_key": request.review_key,
        }
        digest = hashlib.md5(
            json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        return f"{SESSION_PREFIX}:{SESSION_VERSION}:{request.review_type}:{digest}"

    def _build_progress_callback(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Optional[Callable[[Dict[str, Any]], None]]:
        if callback is None:
            return None

        state = {
            "last_stage": None,
            "tool_started": False,
        }

        def emit_stage(stage: str, message: str) -> None:
            if state["last_stage"] == stage:
                return
            state["last_stage"] = stage
            callback({"type": "stage", "stage": stage, "message": message})

        def wrapped(event: Dict[str, Any]) -> None:
            event_type = event.get("type")
            if event_type == "thinking":
                if state["tool_started"]:
                    emit_stage("synthesis", "正在整合规则结论和外部补充信息。")
                else:
                    emit_stage("rules", "正在围绕规则结论组织点评框架。")
                return
            if event_type == "tool_start":
                state["tool_started"] = True
                emit_stage("external", "正在补充外部行情、新闻或板块验证。")
                callback(
                    {
                        "type": "tool_start",
                        "tool": event.get("tool"),
                        "display_name": TOOL_DISPLAY_NAMES.get(event.get("tool", ""), event.get("tool", "")),
                    }
                )
                return
            if event_type == "tool_done":
                callback(
                    {
                        "type": "tool_done",
                        "tool": event.get("tool"),
                        "display_name": TOOL_DISPLAY_NAMES.get(event.get("tool", ""), event.get("tool", "")),
                        "success": event.get("success", False),
                        "duration": event.get("duration"),
                    }
                )
                return
            if event_type == "generating":
                emit_stage("drafting", "正在生成结构化 AI 点评。")

        return wrapped

    def _load_history_for_llm(self, session_id: str) -> List[Dict[str, str]]:
        raw_messages = get_db().get_conversation_messages(session_id, limit=100)
        history: List[Dict[str, str]] = []
        for item in raw_messages:
            role = item.get("role")
            content = item.get("content") or ""
            if role == "system" and content.startswith(META_PREFIX):
                continue
            if role not in {"user", "assistant"}:
                continue
            history.append({"role": role, "content": content})
        return history

    def _load_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        raw_messages = get_db().get_conversation_messages(session_id, limit=200)
        parsed: List[Dict[str, Any]] = []
        pending_meta: Optional[Dict[str, Any]] = None

        for item in raw_messages:
            role = item.get("role")
            content = item.get("content") or ""
            if role == "system" and content.startswith(META_PREFIX):
                pending_meta = self._parse_meta_message(content)
                continue
            if role not in {"user", "assistant"}:
                continue

            message = {
                "id": item.get("id", ""),
                "role": role,
                "content": content,
                "created_at": item.get("created_at"),
                "context_meta": None,
                "suggested_questions": [],
            }
            if role == "assistant" and pending_meta:
                message["context_meta"] = pending_meta.get("context_meta")
                message["suggested_questions"] = pending_meta.get("suggested_questions", [])
                pending_meta = None
            parsed.append(message)
        return parsed

    def _parse_meta_message(self, content: str) -> Dict[str, Any]:
        try:
            return json.loads(content[len(META_PREFIX) :])
        except Exception:
            logger.warning("Failed to parse screener AI meta message")
            return {}

    def _persist_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
        context_meta: MomentumScreenerAIContextMeta,
        suggested_questions: List[str],
    ) -> None:
        db = get_db()
        db.save_conversation_message(session_id, "user", user_message)
        db.save_conversation_message(
            session_id,
            "system",
            META_PREFIX
            + json.dumps(
                {
                    "context_meta": context_meta.model_dump(),
                    "suggested_questions": suggested_questions,
                },
                ensure_ascii=False,
            ),
        )
        db.save_conversation_message(session_id, "assistant", assistant_message)

    def _build_system_prompt(self, request: MomentumScreenerAIReviewRequest) -> str:
        review_context = json.dumps(
            self._build_review_context(request),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return f"""你是“强势筛选 AI 短线交易逻辑审计员”。

你的角色是：逻辑审计层与追问层，不是新的决策引擎。你不做行情记者式复述，而是审计“信心 vs 风险”的权衡是否成立。

必须遵守以下边界：
1. 所有回答都必须先复述规则结论，再解释为什么会得到这个结论。
2. 规则结论和规则边界高于 AI 判断；你不能推翻“今日不做 / 保留观察但不建议执行 / 不建议追入”等硬边界。
3. 盘中解读不能改写昨晚已经确定的主仓 / 次仓 / 观察仓顺序。
4. 不能输出“建议买入 / 立即买入 / 现在买”这类替代用户下单的表达，只能说“规则层显示/未显示触发”“可继续观察/不建议追入”。
5. 盘中快照辅助是低置信度提示，不能被描述成分钟级正式买点，也不能覆盖盘中信号的最终收口。
6. 你可以调用工具补充外部验证，但只能作为补充说明，不能改判规则层结论。
7. 如果没有必要，不要为了“显得聪明”强行调用工具；优先解释当前规则快照。
8. 只用中文回答，避免空泛结论，必须围绕具体股票、主线、风险和触发条件。
9. 必须显式使用 `decision_intelligence`、`risk_stack`、`mainline_intensity` 和 `adaptive_gate` 上下文。
10. 对默认 Top3 的每只股票，都必须扮演一次 Devil's Advocate：至少找出一个背离/瑕疵因子；若没有明显硬风险，也要说明“最接近风险的未确认项”。
11. 执行守卫必须落到 V1.3 可交易合同：若 T+1 开盘低于 T 日收盘价的 99%，只能放弃/仅观察，不能升级为执行。
12. 动态止损必须写清：若 T+1 未能突破开盘后 30 分钟高点，必须提示 `Reduce Position` / 降仓，而不是继续等待幻想修复。

本次回答必须使用以下结构：
{self._build_answer_contract(request.review_type)}

以下是当前规则快照，请把它当作本轮点评的权威上下文，不要原样复读 JSON：
```json
{review_context}
```"""

    def _build_answer_contract(self, review_type: str) -> str:
        if review_type == "candidate":
            return """## [Core Logic]
- 先复述规则结论，再说明它为什么具备主线/强度逻辑。
## [Risk Audit]
- 列出已触发的 Risk Stack 因子，并额外指出至少一个背离或未确认项。
## [Execution Guard]
- 明确 T+1 开盘、承接、放弃条件；若开盘 < T日收盘*0.99，结论必须是放弃或仅观察；若未突破首 30 分钟高点，提示 Reduce Position。
## [External Check]
- 若调用了工具，总结外部验证；若未调用，明确说明当前以规则快照为主。"""
        if review_type == "decision":
            return """## [Core Logic]
- 先明确今天做不做，再解释默认 Top3 的主线强度、角色分工和 Mainline Intensity。
## [Risk Audit]
- 逐只列出 Risk Stack 触发项；每只 Top3 必须给出至少一个 Devil's Advocate 背离/瑕疵因子。
## [Execution Guard]
- 用 V1.3 可交易合同描述明天的执行守卫；若 T+1 开盘 < T日收盘*0.99，必须放弃或仅观察；若未突破首 30 分钟高点，提示 Reduce Position。
## [External Check]
- 若调用了工具，总结外部验证是否支持当前主线和默认组合。"""
        if review_type == "intraday":
            return """## [Core Logic]
- 先说明当前盘中结论和收口方向，不得推翻昨晚总闸门。
## [Risk Audit]
- 分别审计主仓 / 次仓 / 观察仓的 Risk Stack、承接偏离和未确认项。
## [Execution Guard]
- 明确接下来 30-60 分钟还要看什么，哪些情况只能放弃/仅观察。
## [External Check]
- 若调用了工具，总结盘中行情或外部情报是否强化了当前结论。"""
        return """## [Core Logic]
- 先说明当前最可惜落选的是哪些票，以及它们没进默认组合的主因。
## [Risk Audit]
- 逐只列出硬阻断、Risk Stack 或主线/买点瑕疵，不要只说分数不够。
## [Execution Guard]
- 给出继续观察和直接剔除的边界，不要强行拔高成可执行推荐。
## [External Check]
- 若调用了工具，总结外部验证是否支持继续观察这些落选票。"""

    def _build_default_user_message(self, request: MomentumScreenerAIReviewRequest) -> str:
        if request.review_type == "candidate":
            candidate = self._find_candidate(request)
            return (
                f"请点评候选股 {candidate['name']}（{candidate['ts_code']}），"
                "告诉我它为什么入选、最大风险是什么、明天什么情况下考虑、什么情况下直接放弃。"
            )
        if request.review_type == "decision":
            return (
                "请综合点评当前二次决策，先告诉我今天做不做，"
                "再解释为什么是这 1-3 只，以及什么情况下应该直接放弃。"
            )
        if request.review_type == "intraday":
            return (
                "请解读当前盘中信号，说明主仓、次仓、观察仓现在分别是什么状态，"
                "谁还差条件，谁不建议继续追。"
            )
        return (
            "请解释当前最可惜落选的股票，分别说明它们为什么没进默认组合，"
            "以及是暂时不合适还是今天就不该看。"
        )

    def _build_review_context(self, request: MomentumScreenerAIReviewRequest) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "screening": {
                "trade_date": request.screening.trade_date,
                "profile": request.screening.profile,
                "candidate_count": request.screening.candidate_count,
                "requested_trade_date": request.screening.requested_trade_date,
                "trade_date_note": request.screening.trade_date_note,
            },
            "review_type": request.review_type,
            "review_type_label": self._review_type_label(request.review_type),
        }

        if request.decision is not None:
            context["decision"] = {
                "action": {
                    "label": request.decision.action.label,
                    "reason": request.decision.action.reason,
                    "source_profile": request.decision.action.source_profile,
                },
                "strategy_health": {
                    "label": request.decision.strategy_health.label,
                    "reason": request.decision.strategy_health.reason,
                    "status": request.decision.strategy_health.status,
                    "recommendation_cap": request.decision.strategy_health.recommendation_cap,
                    "blockers": request.decision.strategy_health.blockers,
                },
                "themes": [
                    {
                        "name": theme.name,
                        "score": theme.score,
                        "strength_label": theme.strength_label,
                        "summary": theme.summary,
                    }
                    for theme in request.decision.themes[:3]
                ],
                "portfolio": [
                    {
                        "slot": item.slot,
                        "slot_label": item.slot_label,
                        "rank": item.rank,
                        "base_rank": item.base_rank,
                        "ts_code": item.ts_code,
                        "name": item.name,
                        "theme": item.theme,
                        "role": item.role,
                        "official_score": item.official_score,
                        "base_rank_score": item.base_rank_score,
                        "buy_point_label": item.buy_point_label,
                        "suggested_action_label": item.suggested_action_label,
                        "decision_adjustment": item.decision_adjustment,
                        "decision_adjustment_reason": item.decision_adjustment_reason,
                        "hard_blockers": self._serialize_reason_items(item.hard_blockers),
                        "soft_adjustments": self._serialize_reason_items(item.soft_adjustments),
                        "risk_stack": self._model_value(item, "risk_stack"),
                        "risk_stack_count": self._model_value(item, "risk_stack_count"),
                        "risk_stack_veto": self._model_value(item, "risk_stack_veto"),
                        "mainline_intensity": self._build_model_mainline_intensity(item),
                        "ladder_position": self._model_value(item, "v13_ladder_position"),
                        "adaptive_gate": self._model_value(item, "adaptive_gate"),
                        "adaptive_mainline_count": self._model_value(item, "adaptive_mainline_count"),
                        "adaptive_mainline_min_count": self._model_value(item, "adaptive_mainline_min_count"),
                        "adaptive_mainline_pass": self._model_value(item, "adaptive_mainline_pass"),
                        "primary_reason": item.primary_reason,
                        "execution_plan": item.execution_plan,
                    }
                    for item in request.decision.portfolio[:3]
                ],
                "decision_intelligence": self._build_decision_intelligence_context(request),
                "v13_mainline_radar": [
                    {
                        "theme_id": item.get("theme_id"),
                        "theme_name": item.get("theme_name"),
                        "score": item.get("score"),
                        "level": item.get("level"),
                        "summary": item.get("summary"),
                        "candidate_count": item.get("candidate_count"),
                        "limit_up_count": item.get("limit_up_count"),
                        "break_limit_count": item.get("break_limit_count"),
                    }
                    for item in (request.decision.mainline_radar or [])[:5]
                    if isinstance(item, dict)
                ],
                "v13_short_term_sentiment": request.decision.short_term_sentiment,
                "v13_data_status": request.decision.v13_data_status,
            }

        if request.review_type == "candidate":
            candidate = self._find_candidate(request)
            slot = self._find_portfolio_slot(request, candidate["ts_code"])
            intraday_item = self._find_intraday_item(request, candidate["ts_code"])
            context["target"] = {
                "candidate": {
                    "rank": candidate["rank"],
                    "ts_code": candidate["ts_code"],
                    "name": candidate["name"],
                    "pct_chg": candidate["pct_chg"],
                    "official_score": candidate.get("official_score"),
                    "base_final_score": candidate.get("final_score"),
                    "continuation_score": candidate["continuation_score"],
                    "extension_score": candidate["extension_score"],
                    "risk_score": candidate["risk_score"],
                    "themes": candidate["themes"],
                    "leader_level": candidate["leader_level"],
                    "top_reasons": candidate["top_reasons"],
                    "risk_tags": candidate["risk_tags"],
                    "mainline_intensity": self._build_candidate_mainline_intensity(candidate, slot),
                    "ladder_position": slot.get("v13_ladder_position") if isinstance(slot, dict) else None,
                    "risk_stack": slot.get("risk_stack") if isinstance(slot, dict) else None,
                    "risk_stack_count": slot.get("risk_stack_count") if isinstance(slot, dict) else None,
                    "risk_stack_veto": slot.get("risk_stack_veto") if isinstance(slot, dict) else None,
                    "entry_range_low": candidate["entry_range_low"],
                    "entry_range_high": candidate["entry_range_high"],
                },
                "portfolio_slot": slot,
                "intraday_item": intraday_item,
            }
        elif request.review_type == "decision":
            context["target"] = {
                "rule_summary": request.decision.action.reason if request.decision else "当前暂无二次决策快照",
                "action_checklist": (
                    [
                        {
                            "phase_label": step.phase_label,
                            "objective": step.objective,
                            "expected_outcome": step.expected_outcome,
                        }
                        for step in request.decision.action_checklist.steps[:3]
                    ]
                    if request.decision
                    else []
                ),
            }
        elif request.review_type == "intraday":
            context["target"] = {
                "intraday_signal": (
                    {
                        "status_label": request.intraday_signal.status_label,
                        "reason": request.intraday_signal.reason,
                        "final_recommendation_label": request.intraday_signal.final_recommendation_label,
                        "closing_note": request.intraday_signal.closing_note,
                        "watch_items": request.intraday_signal.watch_items,
                        "portfolio_items": [
                            {
                                "slot_label": item.slot_label,
                                "name": item.name,
                                "status_label": item.status_label,
                                "reason": item.reason,
                                "missing_conditions": item.missing_conditions,
                                "do_not_chase": item.do_not_chase,
                            }
                            for item in request.intraday_signal.portfolio_items[:3]
                        ],
                    }
                    if request.intraday_signal
                    else None
                ),
                "snapshot_assist": request.snapshot_assist,
                "snapshot_assist_guardrail": (
                    "盘中快照辅助只提示是否接近观察区、是否偏离过大和还需人工确认什么；"
                    "它不是正式买点，不允许覆盖盘中信号最终收口。"
                    if request.snapshot_assist
                    else None
                ),
            }
        else:
            excluded_items = request.decision.excluded_candidates[:3] if request.decision else []
            context["target"] = {
                "excluded_candidates": [
                    {
                        "rank": item.rank,
                        "base_rank": item.base_rank,
                        "ts_code": item.ts_code,
                        "name": item.name,
                        "theme": item.theme,
                        "role": item.role,
                        "official_score": item.official_score,
                        "base_rank_score": item.base_rank_score,
                        "reason_key": item.reason_key,
                        "reason": item.reason,
                        "reason_detail": item.reason_detail,
                        "decision_adjustment": item.decision_adjustment,
                        "decision_adjustment_reason": item.decision_adjustment_reason,
                        "hard_blockers": self._serialize_reason_items(item.hard_blockers),
                        "soft_adjustments": self._serialize_reason_items(item.soft_adjustments),
                        "risk_stack": self._model_value(item, "risk_stack"),
                        "risk_stack_count": self._model_value(item, "risk_stack_count"),
                        "risk_stack_veto": self._model_value(item, "risk_stack_veto"),
                        "mainline_intensity": self._build_model_mainline_intensity(item),
                        "ladder_position": self._model_value(item, "v13_ladder_position"),
                        "adaptive_gate": self._model_value(item, "adaptive_gate"),
                    }
                    for item in excluded_items
                ],
            }

        return context

    def _build_context_meta(
        self,
        request: MomentumScreenerAIReviewRequest,
        tool_calls_log: List[Dict[str, Any]],
    ) -> MomentumScreenerAIContextMeta:
        tools_used: List[str] = []
        for item in tool_calls_log:
            if not item.get("success"):
                continue
            label = TOOL_DISPLAY_NAMES.get(item.get("tool", ""), item.get("tool", ""))
            if label and label not in tools_used:
                tools_used.append(label)
        return MomentumScreenerAIContextMeta(
            review_type=request.review_type,
            review_type_label=self._review_type_label(request.review_type),
            review_target=self._build_review_target(request),
            trade_date=request.screening.trade_date,
            profile=request.screening.profile,
            rule_conclusion=self._build_rule_conclusion(request),
            rule_guardrail=self._build_rule_guardrail(request),
            market_data_as_of=self._resolve_market_data_as_of(request),
            tools_used=tools_used,
        )

    def _build_session_title(self, request: MomentumScreenerAIReviewRequest) -> str:
        return f"{self._review_type_label(request.review_type)} · {self._build_review_target(request)}"

    def _build_review_target(self, request: MomentumScreenerAIReviewRequest) -> str:
        if request.review_type == "candidate":
            candidate = self._find_candidate(request)
            return f"{candidate['name']} ({candidate['ts_code']})"
        if request.review_type == "decision":
            return "当前二次决策总览"
        if request.review_type == "intraday":
            return "当前盘中信号总览"
        if request.decision and request.decision.excluded_candidates:
            names = [item.name for item in request.decision.excluded_candidates[:3]]
            return " / ".join(names)
        return "当前落选说明"

    def _build_rule_conclusion(self, request: MomentumScreenerAIReviewRequest) -> str:
        if request.review_type == "candidate":
            candidate = self._find_candidate(request)
            slot = self._find_portfolio_slot(request, candidate["ts_code"])
            if slot:
                return f"{slot['slot_label']} / {slot['buy_point_label']} / {slot['suggested_action_label']}"
            official_score = candidate.get("official_score")
            if official_score is not None:
                return f"候选池第 #{candidate['rank']}，官方总分 {official_score:.1f}，{candidate['leader_level']}"
            return f"候选池第 #{candidate['rank']}，{candidate['leader_level']}"

        if request.review_type == "decision" and request.decision:
            return request.decision.action.reason
        if request.review_type == "intraday":
            if request.intraday_signal:
                return request.intraday_signal.reason
            if request.decision:
                return "盘中信号尚未刷新，当前先沿用昨晚二次决策结论。"
        if request.decision and request.decision.excluded_candidates:
            first = request.decision.excluded_candidates[0]
            return f"{first.name} 等落选，主因：{first.reason}"
        return "当前暂无足够规则结论"

    def _build_rule_guardrail(self, request: MomentumScreenerAIReviewRequest) -> str:
        if request.review_type == "intraday" and request.intraday_signal:
            parts = [request.intraday_signal.final_recommendation_label, request.intraday_signal.status_label]
            if request.snapshot_assist:
                parts.append("快照辅助不等于正式买点")
            return " / ".join(part for part in parts if part)
        if request.decision:
            parts = [request.decision.action.label, request.decision.strategy_health.label]
            data_status = request.decision.v13_data_status or {}
            if isinstance(data_status, dict) and data_status.get("status") not in {None, "", "ok"}:
                parts.append("V1.3 数据降级")
            if request.review_type == "candidate":
                candidate = self._find_candidate(request)
                slot = self._find_portfolio_slot(request, candidate["ts_code"])
                if slot:
                    parts.append(slot["suggested_action_label"])
            return " / ".join(part for part in parts if part)
        return "当前以规则快照为准，不可越界提升结论"

    def _resolve_market_data_as_of(self, request: MomentumScreenerAIReviewRequest) -> Optional[str]:
        if request.snapshot_assist and request.snapshot_assist.get("data_as_of"):
            return str(request.snapshot_assist["data_as_of"])
        if request.intraday_signal and request.intraday_signal.updated_at:
            return request.intraday_signal.updated_at
        return request.screening.trade_date

    def _build_suggested_questions(self, review_type: str) -> List[str]:
        if review_type == "candidate":
            return [
                "这只票最大的风险是什么？",
                "和主仓相比它差在哪里？",
                "明天什么情况下直接放弃？",
                "如果主线转弱怎么办？",
            ]
        if review_type == "decision":
            return [
                "为什么今天是这 1-3 只？",
                "主线雷达支持这个组合吗？",
                "短线情绪最大的风险是什么？",
                "什么情况下应该直接劝退？",
            ]
        if review_type == "intraday":
            return [
                "主仓现在还差哪些条件？",
                "为什么当前不建议追入？",
                "快照辅助里哪个条件最关键？",
                "接下来 30 分钟最该人工确认什么？",
            ]
        return [
            "哪只票最可惜？",
            "这些落选票是暂时不行还是今天就不该看？",
            "如果想继续观察，先盯哪一只？",
            "它们和默认组合差在哪里？",
        ]

    def _build_decision_intelligence_context(self, request: MomentumScreenerAIReviewRequest) -> Dict[str, Any]:
        if request.decision is None:
            return {
                "role": "Logic Auditor",
                "summary": "当前没有二次决策快照，AI 只能解释原始候选池。",
                "top3_audit": [],
            }

        candidates_by_code = {
            item.ts_code: item.model_dump()
            for item in request.screening.results
        }
        top3_audit: List[Dict[str, Any]] = []
        for item in request.decision.portfolio[:3]:
            candidate = candidates_by_code.get(item.ts_code, {})
            risk_stack = self._model_value(item, "risk_stack") or {}
            triggered_factors = self._triggered_risk_factors(risk_stack)
            top3_audit.append(
                {
                    "slot": item.slot,
                    "slot_label": item.slot_label,
                    "ts_code": item.ts_code,
                    "name": item.name,
                    "theme": item.theme,
                    "official_score": item.official_score,
                    "mainline_intensity": self._build_candidate_mainline_intensity(candidate, item),
                    "ladder_position": self._model_value(item, "v13_ladder_position"),
                    "risk_stack": risk_stack,
                    "risk_stack_triggered_factors": triggered_factors,
                    "devils_advocate_required": True,
                    "suggested_divergence_factors": self._infer_divergence_factors(
                        portfolio_item=item,
                        candidate=candidate,
                        triggered_factors=triggered_factors,
                    ),
                    "execution_guard": self._build_execution_guard(candidate),
                }
            )

        adaptive_gate = request.decision.adaptive_gate if hasattr(request.decision, "adaptive_gate") else None
        return {
            "role": "Logic Auditor",
            "objective": "解释每只 Top3 的信心来源，同时主动寻找背离、瑕疵和 T+1 执行失败条件。",
            "adaptive_gate": adaptive_gate,
            "top3_audit": top3_audit,
            "required_output_sections": ["[Core Logic]", "[Risk Audit]", "[Execution Guard]", "[External Check]"],
        }

    @staticmethod
    def _model_value(item: Any, key: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    def _build_model_mainline_intensity(self, item: Any) -> Dict[str, Any]:
        return {
            "count": self._model_value(item, "mainline_intensity_count"),
            "multiplier": self._model_value(item, "mainline_intensity_multiplier"),
            "bonus": self._model_value(item, "mainline_intensity_bonus"),
            "v13_mainline_score": self._model_value(item, "v13_mainline_score"),
        }

    def _build_candidate_mainline_intensity(self, candidate: Dict[str, Any], slot: Any = None) -> Dict[str, Any]:
        slot_context = self._build_model_mainline_intensity(slot) if slot is not None else {}
        return {
            "count": candidate.get("mainline_intensity_count", slot_context.get("count")),
            "multiplier": candidate.get("mainline_intensity_multiplier", slot_context.get("multiplier")),
            "bonus": candidate.get("mainline_intensity_bonus", slot_context.get("bonus")),
            "v13_mainline_candidate_count": candidate.get("v13_mainline_candidate_count"),
            "v13_mainline_score": slot_context.get("v13_mainline_score"),
        }

    @staticmethod
    def _triggered_risk_factors(risk_stack: Any) -> List[Dict[str, Any]]:
        if not isinstance(risk_stack, dict):
            return []
        factors = risk_stack.get("factors")
        if not isinstance(factors, list):
            return []
        return [
            {
                "key": factor.get("key"),
                "label": factor.get("label"),
                "evidence": factor.get("evidence"),
            }
            for factor in factors
            if isinstance(factor, dict) and factor.get("triggered")
        ]

    def _infer_divergence_factors(
        self,
        *,
        portfolio_item: Any,
        candidate: Dict[str, Any],
        triggered_factors: List[Dict[str, Any]],
    ) -> List[str]:
        factors: List[str] = []
        labels = [str(item.get("label")) for item in triggered_factors if item.get("label")]
        if labels:
            factors.append("Risk Stack 已触发：" + "、".join(labels))

        buy_elg = candidate.get("v13_stock_buy_elg_amount")
        close_price = candidate.get("close")
        high_20d = candidate.get("high_20d")
        try:
            if buy_elg is not None and float(buy_elg) <= 0:
                factors.append("价格强势但超大单买入不占优，需要防资金背离。")
            if close_price is not None and high_20d is not None and float(close_price) >= float(high_20d):
                factors.append("价格处于 20 日高位，若明天承接不足容易形成兑现压力。")
        except (TypeError, ValueError):
            pass

        mainline_count = (
            candidate.get("mainline_intensity_count")
            or self._model_value(portfolio_item, "mainline_intensity_count")
            or candidate.get("v13_mainline_candidate_count")
            or 0
        )
        try:
            if int(mainline_count) < 2:
                factors.append("主线共振计数不足，可能是孤立强势而不是板块推动。")
        except (TypeError, ValueError):
            pass

        if not factors:
            factors.append("暂无硬背离，但仍需验证 T+1 开盘溢价和分时承接是否兑现。")
        return factors[:3]

    @staticmethod
    def _build_execution_guard(candidate: Dict[str, Any]) -> Dict[str, Any]:
        close_price = candidate.get("close")
        try:
            gap_floor = round(float(close_price) * 0.99, 3) if close_price is not None else None
        except (TypeError, ValueError):
            gap_floor = None
        return {
            "t1_gap_threshold": "T+1 Open >= T0 Close * 0.99",
            "dynamic_stop_loss": "If T+1 fails to break the first 30-min high, trigger Reduce Position warning.",
            "t0_close": close_price,
            "abandon_if": (
                f"T+1 开盘低于 {gap_floor}，按 V1.3 可交易合同放弃/仅观察。"
                if gap_floor is not None
                else "T+1 开盘低于 T 日收盘价的 99%，按 V1.3 可交易合同放弃/仅观察。"
            ),
            "reduce_if": "T+1 不能突破开盘后 30 分钟高点，触发 Reduce Position / 降仓提醒。",
            "confirm_if": "T+1 开盘不深低开，且收盘强于开盘，T+2 滑点调整退出价需提供 >=2% 利润缓冲。",
        }

    def _find_candidate(self, request: MomentumScreenerAIReviewRequest) -> Dict[str, Any]:
        for item in request.screening.results:
            if item.ts_code == request.review_key:
                return item.model_dump()
        raise ValueError(f"未找到点评对象 {request.review_key}")

    def _find_portfolio_slot(
        self,
        request: MomentumScreenerAIReviewRequest,
        ts_code: str,
    ) -> Optional[Dict[str, Any]]:
        if request.decision is None:
            return None
        for item in request.decision.portfolio:
            if item.ts_code == ts_code:
                return item.model_dump()
        return None

    def _find_intraday_item(
        self,
        request: MomentumScreenerAIReviewRequest,
        ts_code: str,
    ) -> Optional[Dict[str, Any]]:
        if request.intraday_signal is None:
            return None
        for item in request.intraday_signal.portfolio_items:
            if item.ts_code == ts_code:
                return item.model_dump()
        return None

    @staticmethod
    def _serialize_reason_items(items: List[Any]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for item in items or []:
            if hasattr(item, "model_dump"):
                serialized.append(item.model_dump())
            elif isinstance(item, dict):
                serialized.append(dict(item))
        return serialized

    @staticmethod
    def _review_type_label(review_type: str) -> str:
        return REVIEW_TYPE_LABELS.get(review_type, review_type)
