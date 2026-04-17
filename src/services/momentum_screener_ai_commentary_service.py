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
        return f"""你是“强势筛选 AI 点评助手”。

你的角色是：解释层与追问层，不是新的决策引擎。

必须遵守以下边界：
1. 所有回答都必须先复述规则结论，再解释为什么会得到这个结论。
2. 规则结论和规则边界高于 AI 判断；你不能推翻“今日不做 / 保留观察但不建议执行 / 不建议追入”等硬边界。
3. 盘中解读不能改写昨晚已经确定的主仓 / 次仓 / 观察仓顺序。
4. 你可以调用工具补充外部验证，但只能作为补充说明，不能改判规则层结论。
5. 如果没有必要，不要为了“显得聪明”强行调用工具；优先解释当前规则快照。
6. 只用中文回答，避免空泛结论，必须围绕具体股票、主线、风险和触发条件。

本次回答必须使用以下结构：
{self._build_answer_contract(request.review_type)}

以下是当前规则快照，请把它当作本轮点评的权威上下文，不要原样复读 JSON：
```json
{review_context}
```"""

    def _build_answer_contract(self, review_type: str) -> str:
        if review_type == "candidate":
            return """## 规则结论
- 先用一句话说明这只候选股当前在规则里处于什么位置。
## AI解释
- 说明它为什么入选、为什么值得关注、最大风险是什么。
## 外部补充
- 若调用了工具，总结新闻、行情或板块验证；若未调用，明确说明当前以规则快照为主。
## 可执行提醒
- 说明明天什么情况下继续观察，什么情况下直接放弃。"""
        if review_type == "decision":
            return """## 规则结论
- 先明确今天做不做，以及规则层为什么这样判断。
## AI解释
- 解释为什么是这 1-3 只、为什么没选其他票、默认组合各自承担什么角色。
## 外部补充
- 若调用了工具，总结外部验证是否支持当前主线和默认组合。
## 可执行提醒
- 明确哪些条件允许继续跟踪，哪些条件出现时应该直接劝退。"""
        if review_type == "intraday":
            return """## 规则结论
- 先说明当前盘中结论和收口方向。
## AI解释
- 分别解释主仓 / 次仓 / 观察仓的当前状态，谁已触发、谁还差条件、谁不建议追。
## 外部补充
- 若调用了工具，总结盘中行情或外部情报是否强化了当前结论。
## 可执行提醒
- 明确接下来 30-60 分钟还要看什么，不得推翻规则总闸门。"""
        return """## 规则结论
- 先说明当前最可惜落选的是哪些票，以及它们没进默认组合的主因。
## AI解释
- 逐只解释它们是暂时不合适，还是今天就不该看。
## 外部补充
- 若调用了工具，总结外部验证是否支持继续观察这些落选票。
## 可执行提醒
- 给出继续观察和直接剔除的边界，不要强行拔高成可执行推荐。"""

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
                        "ts_code": item.ts_code,
                        "name": item.name,
                        "theme": item.theme,
                        "role": item.role,
                        "buy_point_label": item.buy_point_label,
                        "suggested_action_label": item.suggested_action_label,
                        "primary_reason": item.primary_reason,
                        "execution_plan": item.execution_plan,
                    }
                    for item in request.decision.portfolio[:3]
                ],
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
                    "rank_score": candidate["rank_score"],
                    "continuation_score": candidate["continuation_score"],
                    "extension_score": candidate["extension_score"],
                    "risk_score": candidate["risk_score"],
                    "themes": candidate["themes"],
                    "leader_level": candidate["leader_level"],
                    "top_reasons": candidate["top_reasons"],
                    "risk_tags": candidate["risk_tags"],
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
            }
        else:
            excluded_items = request.decision.excluded_candidates[:3] if request.decision else []
            context["target"] = {
                "excluded_candidates": [
                    {
                        "rank": item.rank,
                        "ts_code": item.ts_code,
                        "name": item.name,
                        "theme": item.theme,
                        "role": item.role,
                        "reason": item.reason,
                        "rank_score": item.rank_score,
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
                return f"{slot['slot_label']} · {slot['buy_point_label']} · {slot['suggested_action_label']}"
            return f"候选池第 #{candidate['rank']} 名 · {candidate['leader_level']}"
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
            return f"{request.intraday_signal.final_recommendation_label} / {request.intraday_signal.status_label}"
        if request.decision:
            parts = [request.decision.action.label, request.decision.strategy_health.label]
            if request.review_type == "candidate":
                candidate = self._find_candidate(request)
                slot = self._find_portfolio_slot(request, candidate["ts_code"])
                if slot:
                    parts.append(slot["suggested_action_label"])
            return " / ".join(part for part in parts if part)
        return "当前以规则快照为准，不可越界提升结论"

    def _resolve_market_data_as_of(self, request: MomentumScreenerAIReviewRequest) -> Optional[str]:
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
                "为什么没选其他票？",
                "什么情况下应该直接劝退？",
                "如果主线转弱，先砍谁的优先级？",
            ]
        if review_type == "intraday":
            return [
                "主仓现在还差哪些条件？",
                "为什么当前不建议追入？",
                "如果主仓触发，次仓怎么处理？",
                "接下来 30 分钟最该看什么？",
            ]
        return [
            "哪只票最可惜？",
            "这些落选票是暂时不行还是今天就不该看？",
            "如果想继续观察，先盯哪一只？",
            "它们和默认组合差在哪里？",
        ]

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
    def _review_type_label(review_type: str) -> str:
        return REVIEW_TYPE_LABELS.get(review_type, review_type)
