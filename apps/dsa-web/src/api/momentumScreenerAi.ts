import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';
import { toCamelCase } from './utils';
import type {
  MomentumScreenerAiReviewRequest,
  MomentumScreenerAiSessionResponse,
} from '../types/momentumScreenerAi';

type StreamOptions = {
  signal?: AbortSignal;
};

function toSnakeCaseKey(key: string): string {
  return key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
}

function toSnakeCaseDeep<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => toSnakeCaseDeep(item)) as T;
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, nested]) => [
        toSnakeCaseKey(key),
        toSnakeCaseDeep(nested),
      ]),
    ) as T;
  }
  return value;
}

function buildRequest(payload: MomentumScreenerAiReviewRequest) {
  return toSnakeCaseDeep({
    review_type: payload.reviewType,
    review_key: payload.reviewKey,
    refresh_mode: payload.refreshMode ?? 'resume',
    session_id: payload.sessionId,
    message: payload.message,
    payload: {
      top_n: payload.payload.topN,
      trade_date: payload.payload.tradeDate || undefined,
      profile: payload.payload.profile,
    },
    screening: {
      profile: payload.screening.profile,
      trade_date: payload.screening.tradeDate,
      requested_trade_date: payload.screening.requestedTradeDate ?? undefined,
      trade_date_note: payload.screening.tradeDateNote ?? undefined,
      entry_baseline_version: payload.screening.entryBaselineVersion,
      market_scope_version: payload.screening.marketScopeVersion,
      candidate_count: payload.screening.candidateCount,
      results: payload.screening.results.map((item) => ({
        rank: item.rank,
        ts_code: item.tsCode,
        name: item.name,
        market_segment: item.marketSegment,
        market_segment_label: item.marketSegmentLabel,
        pct_chg: item.pctChg,
        continuation_score: item.continuationScore,
        extension_score: item.extensionScore,
        risk_score: item.riskScore,
        buyability_score: item.buyabilityScore ?? undefined,
        opportunity_tag: item.opportunityTag ?? undefined,
        entry_range_low: item.entryRangeLow ?? undefined,
        entry_range_high: item.entryRangeHigh ?? undefined,
        final_score: item.finalScore,
        official_score: item.officialScore,
        rank_score: item.rankScore,
        themes: item.themes,
        leader_level: item.leaderLevel,
        top_reasons: item.topReasons,
        risk_tags: item.riskTags,
        score_breakdown: Object.fromEntries(
          Object.entries(item.scoreBreakdown).map(([key, value]) => [
            key,
            {
              score: value.score,
              max_score: value.maxScore,
              items: value.items,
            },
          ]),
        ),
      })),
    },
    decision: payload.decision
      ? {
          profile: payload.decision.profile,
          trade_date: payload.decision.tradeDate,
          action: {
            level: payload.decision.action.level,
            label: payload.decision.action.label,
            reason: payload.decision.action.reason,
            source_profile: payload.decision.action.sourceProfile,
          },
          market_environment: payload.decision.marketEnvironment,
          opportunity_quality: payload.decision.opportunityQuality,
          historical_validity: {
            level: payload.decision.historicalValidity.level,
            label: payload.decision.historicalValidity.label,
            score: payload.decision.historicalValidity.score,
            reason: payload.decision.historicalValidity.reason,
            max_action_level: payload.decision.historicalValidity.maxActionLevel,
            recommendation_cap: payload.decision.historicalValidity.recommendationCap,
            attack_permission_status: payload.decision.historicalValidity.attackPermissionStatus ?? undefined,
            attack_permission_label: payload.decision.historicalValidity.attackPermissionLabel ?? undefined,
          },
          strategy_health: payload.decision.strategyHealth,
          attack_permission: payload.decision.attackPermission,
          theme_confidence: payload.decision.themeConfidence,
          risk_banner: payload.decision.riskBanner ?? undefined,
          themes: payload.decision.themes,
          portfolio: payload.decision.portfolio.map((item) => ({
            slot: item.slot,
            slot_label: item.slotLabel,
            rank: item.rank,
            base_rank: item.baseRank,
            ts_code: item.tsCode,
            name: item.name,
            theme: item.theme,
            role: item.role,
            score: item.score,
            official_score: item.officialScore,
            base_rank_score: item.baseRankScore,
            rank_score: item.rankScore,
            risk_score: item.riskScore,
            decision_adjustment: item.decisionAdjustment ?? undefined,
            decision_adjustment_reason: item.decisionAdjustmentReason ?? undefined,
            hard_blockers: item.hardBlockers.map((reason) => ({
              key: reason.key,
              label: reason.label,
              delta: reason.delta ?? undefined,
              detail: reason.detail ?? undefined,
            })),
            soft_adjustments: item.softAdjustments.map((reason) => ({
              key: reason.key,
              label: reason.label,
              delta: reason.delta ?? undefined,
              detail: reason.detail ?? undefined,
            })),
            buy_point_status: item.buyPointStatus,
            buy_point_label: item.buyPointLabel,
            suggested_action: item.suggestedAction,
            suggested_action_label: item.suggestedActionLabel,
            primary_reason: item.primaryReason,
            role_reason: item.roleReason,
            execution_plan: item.executionPlan,
            entry_hint: item.entryHint ?? undefined,
            entry_range_low: item.entryRangeLow ?? undefined,
            entry_range_high: item.entryRangeHigh ?? undefined,
            opportunity_tag: item.opportunityTag ?? undefined,
          })),
          excluded_candidates: payload.decision.excludedCandidates.map((item) => ({
            rank: item.rank,
            base_rank: item.baseRank,
            ts_code: item.tsCode,
            name: item.name,
            theme: item.theme,
            role: item.role,
            reason_key: item.reasonKey,
            official_score: item.officialScore,
            base_rank_score: item.baseRankScore,
            reason: item.reason,
            reason_detail: item.reasonDetail ?? undefined,
            rank_score: item.rankScore,
            decision_adjustment: item.decisionAdjustment ?? undefined,
            decision_adjustment_reason: item.decisionAdjustmentReason ?? undefined,
            hard_blockers: item.hardBlockers.map((reason) => ({
              key: reason.key,
              label: reason.label,
              delta: reason.delta ?? undefined,
              detail: reason.detail ?? undefined,
            })),
            soft_adjustments: item.softAdjustments.map((reason) => ({
              key: reason.key,
              label: reason.label,
              delta: reason.delta ?? undefined,
              detail: reason.detail ?? undefined,
            })),
          })),
          evidence: {
            theme_validation: payload.decision.evidence.themeValidation,
            today_reasoning: payload.decision.evidence.todayReasoning,
          },
          action_checklist: {
            enabled: payload.decision.actionChecklist.enabled,
            mode: payload.decision.actionChecklist.mode,
            reason: payload.decision.actionChecklist.reason,
            steps: payload.decision.actionChecklist.steps.map((step) => ({
              phase: step.phase,
              phase_label: step.phaseLabel,
              objective: step.objective,
              focus_items: step.focusItems,
              tasks: step.tasks,
              expected_outcome: step.expectedOutcome,
            })),
          },
          mainline_radar: payload.decision.mainlineRadar ?? undefined,
          short_term_sentiment: payload.decision.shortTermSentiment ?? undefined,
          v13_data_status: payload.decision.v13DataStatus ?? undefined,
        }
      : undefined,
    intraday_signal: payload.intradaySignal
      ? {
          market_phase: payload.intradaySignal.marketPhase,
          market_phase_label: payload.intradaySignal.marketPhaseLabel,
          confidence_level: payload.intradaySignal.confidenceLevel,
          confidence_label: payload.intradaySignal.confidenceLabel,
          can_emit_buy_signal: payload.intradaySignal.canEmitBuySignal,
          status: payload.intradaySignal.status,
          status_label: payload.intradaySignal.statusLabel,
          reason: payload.intradaySignal.reason,
          watch_items: payload.intradaySignal.watchItems,
          final_recommendation: payload.intradaySignal.finalRecommendation,
          final_recommendation_label: payload.intradaySignal.finalRecommendationLabel,
          closing_note: payload.intradaySignal.closingNote,
          updated_at: payload.intradaySignal.updatedAt,
          focus_order: payload.intradaySignal.focusOrder,
          portfolio_items: payload.intradaySignal.portfolioItems.map((item) => ({
            slot: item.slot,
            slot_label: item.slotLabel,
            ts_code: item.tsCode,
            name: item.name,
            theme: item.theme,
            role: item.role,
            status: item.status,
            status_label: item.statusLabel,
            reason: item.reason,
            quote_available: item.quoteAvailable,
            signal_triggered: item.signalTriggered,
            do_not_chase: item.doNotChase,
            current_price: item.currentPrice ?? undefined,
            change_percent: item.changePercent ?? undefined,
            open_price: item.openPrice ?? undefined,
            entry_range_low: item.entryRangeLow ?? undefined,
            entry_range_high: item.entryRangeHigh ?? undefined,
            price_vs_open_pct: item.priceVsOpenPct ?? undefined,
            price_vs_entry_high_pct: item.priceVsEntryHighPct ?? undefined,
            missing_conditions: item.missingConditions,
            update_time: item.updateTime ?? undefined,
          })),
        }
      : undefined,
    snapshot_assist: payload.snapshotAssist ?? undefined,
  });
}

export const momentumScreenerAiApi = {
  async loadSession(payload: MomentumScreenerAiReviewRequest): Promise<MomentumScreenerAiSessionResponse> {
    const response = await apiClient.post('/api/v1/stocks/screener/momentum/ai/session', buildRequest(payload), {
      timeout: 180000,
    });
    return toCamelCase<MomentumScreenerAiSessionResponse>(response.data);
  },

  async streamReview(
    payload: MomentumScreenerAiReviewRequest,
    options?: StreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/stocks/screener/momentum/ai/stream`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequest(payload)),
        credentials: 'include',
        signal: options?.signal,
      });

      if (response.ok) {
        return response;
      }

      const contentType = response.headers.get('content-type') || '';
      let responseData: unknown = null;
      if (contentType.includes('application/json')) {
        responseData = await response.json().catch(() => null);
      } else {
        responseData = await response.text().catch(() => null);
      }

      const parsed = parseApiError({
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
      throw createApiError(parsed, {
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
    } catch (error: unknown) {
      if (isApiRequestError(error)) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }
      const parsed = parseApiError(error);
      throw createApiError(parsed, { cause: error });
    }
  },
};
