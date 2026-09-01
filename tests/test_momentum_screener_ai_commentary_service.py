from __future__ import annotations

import sys
import types
from typing import Any

if "litellm" not in sys.modules:
    litellm_stub = types.ModuleType("litellm")
    litellm_stub.Router = object
    sys.modules["litellm"] = litellm_stub

from src.services.momentum_screener_ai_commentary_service import MomentumScreenerAICommentaryService


class FakeModel:
    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, FakeModel):
                return value.model_dump()
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return {key: convert(value) for key, value in self.__dict__.items()}


def _build_request(review_type: str):
    blocker = FakeModel(key="buyability_block", label="买点不清晰", delta=None, detail="开盘后不适合直接接。")
    adjustment = FakeModel(key="theme_tailwind", label="主线共振", delta=1.2, detail="题材强度高于候选池均值。")
    risk_stack = {
        "factor_count": 1,
        "veto": False,
        "threshold": 3,
        "factors": [
            {
                "key": "divergence_risk",
                "label": "量价背离风险",
                "triggered": True,
                "evidence": "buy_elg=-1000000, close=10.00, high20=10.00",
            }
        ],
        "triggered_keys": ["divergence_risk"],
    }
    result = FakeModel(
        rank=1,
        ts_code="600001.SH",
        name="测试龙头",
        market_segment="main_board",
        market_segment_label="主板",
        pct_chg=9.96,
        continuation_score=82.0,
        extension_score=88.0,
        risk_score=6.5,
        buyability_score=78.0,
        opportunity_tag="主线核心",
        entry_range_low=10.2,
        entry_range_high=10.8,
        final_score=74.1,
        official_score=78.6,
        mainline_intensity_count=3,
        mainline_intensity_multiplier=1.3,
        mainline_intensity_bonus=5.4,
        close=10.0,
        ma20=8.0,
        high_20d=10.0,
        v13_stock_buy_elg_amount=-1_000_000.0,
        amount=820_000_000.0,
        turnover_rate_f=28.0,
        volume_expand_5=4.2,
        amount_10d_high=True,
        price_gain_shrinking=True,
        close_position=0.52,
        upper_shadow_ratio=0.31,
        rank_score=73.2,
        themes=["电子"],
        leader_level="龙头",
        top_reasons=["主线共振"],
        risk_tags=["高波动"],
        score_breakdown={},
    )
    portfolio_item = FakeModel(
        slot="main",
        slot_label="主仓",
        rank=1,
        base_rank=1,
        ts_code="600001.SH",
        name="测试龙头",
        theme="电子",
        role="龙头",
        official_score=78.6,
        base_rank_score=78.6,
        buy_point_label="计划明确",
        suggested_action_label="等待触发",
        decision_adjustment=1.2,
        decision_adjustment_reason="题材强度和槽位匹配支持保留主仓。",
        hard_blockers=[blocker],
        soft_adjustments=[adjustment],
        risk_stack=risk_stack,
        risk_stack_count=1,
        risk_stack_veto=False,
        raw_alpha_shield={
            "status": "retained_by_raw_top3_sovereignty",
            "reason": "Raw Top 3 is protected unless Risk Stack reaches the hard-veto threshold.",
        },
        mainline_intensity_count=3,
        mainline_intensity_multiplier=1.3,
        mainline_intensity_bonus=5.4,
        adaptive_gate={"enabled": False, "mode": "normal", "required_mainline_count": 1},
        adaptive_mainline_count=3,
        adaptive_mainline_min_count=1,
        adaptive_mainline_pass=True,
        primary_reason="主线核心",
        execution_plan="关注开盘承接后再判断。",
    )
    excluded_item = FakeModel(
        rank=4,
        base_rank=4,
        ts_code="600004.SH",
        name="跟风票",
        theme="电子",
        role="后排",
        official_score=70.4,
        base_rank_score=70.4,
        reason_key="theme_rank_not_enough",
        reason="主线内名次不够",
        reason_detail="同一主线里已有更高的官方总分和更清晰的槽位位置。",
        decision_adjustment=-1.2,
        decision_adjustment_reason="主线内已有更优先的同题材标的。",
        hard_blockers=[blocker],
        soft_adjustments=[adjustment],
        risk_stack=risk_stack,
        risk_stack_count=1,
        risk_stack_veto=False,
        raw_alpha_shield={
            "status": "displaced_by_raw_alpha_shield",
            "reason": "Inserted candidate did not have sovereignty over a non-veto Raw Top 3 candidate.",
        },
        mainline_intensity_count=2,
        mainline_intensity_multiplier=1.2,
        mainline_intensity_bonus=3.1,
        adaptive_gate={"enabled": False, "mode": "normal", "required_mainline_count": 1},
    )
    screening = FakeModel(
        trade_date="2026-04-27",
        profile="standard",
        candidate_count=1,
        requested_trade_date=None,
        trade_date_note=None,
        results=[result],
    )
    decision = FakeModel(
        action=FakeModel(reason="今天可以跟踪主线。", label="可做", source_profile="standard"),
        strategy_health=FakeModel(label="健康", reason="近端策略有效。", status="healthy", recommendation_cap="full", blockers=[]),
        themes=[],
        portfolio=[portfolio_item],
        mainline_radar=[],
        short_term_sentiment=None,
        v13_data_status={"status": "ok"},
        adaptive_gate={"enabled": False, "mode": "normal", "required_mainline_count": 1},
        excluded_candidates=[excluded_item],
        action_checklist=FakeModel(steps=[]),
    )
    return FakeModel(
        review_type=review_type,
        review_key="600001.SH",
        screening=screening,
        decision=decision,
        intraday_signal=None,
        snapshot_assist=None,
    )


def test_build_review_context_prefers_official_score_and_structured_reasons():
    service = MomentumScreenerAICommentaryService(config=object(), tool_registry=object(), llm_adapter=object())
    request = _build_request("candidate")

    context = service._build_review_context(request)
    candidate = context["target"]["candidate"]
    portfolio = context["decision"]["portfolio"][0]

    assert candidate["official_score"] == 78.6
    assert "rank_score" not in candidate
    assert portfolio["official_score"] == 78.6
    assert portfolio["base_rank"] == 1
    assert portfolio["decision_adjustment_reason"] == "题材强度和槽位匹配支持保留主仓。"
    assert portfolio["hard_blockers"][0]["label"] == "买点不清晰"
    assert portfolio["risk_stack_count"] == 1
    assert portfolio["raw_alpha_shield"]["status"] == "retained_by_raw_top3_sovereignty"
    assert portfolio["mainline_intensity"]["count"] == 3
    top3_audit = context["decision"]["decision_intelligence"]["top3_audit"]
    assert top3_audit[0]["risk_stack_triggered_factors"][0]["key"] == "divergence_risk"
    assert top3_audit[0]["raw_alpha_shield"]["status"] == "retained_by_raw_top3_sovereignty"
    assert top3_audit[0]["exhaustion_volume_audit"]["status"] == "extreme_churn"
    assert any(
        "TRADING WARNING: Extreme Churn Detected" in item
        for item in top3_audit[0]["suggested_divergence_factors"]
    )
    assert service._build_rule_conclusion(request) == "主仓 / 计划明确 / 等待触发"


def test_build_review_context_for_excluded_candidates_uses_structured_reason_fields():
    service = MomentumScreenerAICommentaryService(config=object(), tool_registry=object(), llm_adapter=object())
    request = _build_request("excluded")

    context = service._build_review_context(request)
    excluded = context["target"]["excluded_candidates"][0]

    assert excluded["official_score"] == 70.4
    assert excluded["reason_key"] == "theme_rank_not_enough"
    assert excluded["reason_detail"] == "同一主线里已有更高的官方总分和更清晰的槽位位置。"
    assert excluded["decision_adjustment_reason"] == "主线内已有更优先的同题材标的。"
    assert excluded["hard_blockers"][0]["label"] == "买点不清晰"
    assert excluded["risk_stack_count"] == 1
    assert excluded["raw_alpha_shield"]["status"] == "displaced_by_raw_alpha_shield"
    assert "rank_score" not in excluded


def test_system_prompt_requires_logic_audit_sections_and_risk_stack_context():
    service = MomentumScreenerAICommentaryService(config=object(), tool_registry=object(), llm_adapter=object())
    request = _build_request("decision")

    prompt = service._build_system_prompt(request)

    assert "短线交易逻辑审计员" in prompt
    assert "Devil's Advocate" in prompt
    assert "[Risk Audit]" in prompt
    assert "risk_stack" in prompt
    assert "mainline_intensity" in prompt
    assert "exhaustion_volume_audit" in prompt
    assert "raw_alpha_shield" in prompt
    assert "RETAINED_LEADER_DIVERGENCE" in prompt
    assert "Weak-to-Strong" in prompt
    assert "Volatility Gap" in prompt
    assert "Track B" in prompt
    assert "Directional Conviction" in prompt
    assert "continuation_alpha" in prompt
    assert "continuation_score" in prompt
    assert "continuation_rank" in prompt
    assert "Deep Continuation Challenger" in prompt
    assert "Main_Slot_Pivot" in prompt
    assert "Anchor_Supremacy" in prompt
    assert "Top10%" in prompt
    assert "不得仅因 T+1 低开低于 99% 就强制 Abandon" in prompt
    assert "CRITICAL_REJECTION_ADVICE" in prompt
    assert "TRADING WARNING: Extreme Churn Detected" in prompt
    assert "T+1 Open >= T0 Close * 0.99" in prompt
    assert "Reduce Position" in prompt


def test_execution_guard_supports_dual_track_recovery_entry():
    guard = MomentumScreenerAICommentaryService._build_execution_guard({"close": 10.0})

    assert guard["dual_track_contract"]["track_a_momentum"].startswith("T+1 Open >= T0 Close")
    assert "low-open recovery" in guard["dual_track_contract"]["track_b_recovery"]
    assert "Track B" in guard["t1_gap_threshold"]
    assert "收复 T0 收盘价" in guard["abandon_if"]
    assert "低开低于 9.9" in guard["reversal_entry_if"]
    assert "低于 9.9，按 V1.3 可交易合同放弃" not in guard["abandon_if"]
