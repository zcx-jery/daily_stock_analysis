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
      min_change_pct: payload.payload.minChangePct,
      min_amount: payload.payload.minAmount,
      min_turnover: payload.payload.minTurnover,
      exclude_st: payload.payload.excludeSt,
      main_board_only: payload.payload.mainBoardOnly,
      trade_date: payload.payload.tradeDate || undefined,
      profile: payload.payload.profile,
    },
    screening: {
      profile: payload.screening.profile,
      trade_date: payload.screening.tradeDate,
      requested_trade_date: payload.screening.requestedTradeDate ?? undefined,
      trade_date_note: payload.screening.tradeDateNote ?? undefined,
      candidate_count: payload.screening.candidateCount,
      results: payload.screening.results.map((item) => ({
        rank: item.rank,
        ts_code: item.tsCode,
        name: item.name,
        pct_chg: item.pctChg,
        continuation_score: item.continuationScore,
        extension_score: item.extensionScore,
        risk_score: item.riskScore,
        buyability_score: item.buyabilityScore ?? undefined,
        opportunity_tag: item.opportunityTag ?? undefined,
        entry_range_low: item.entryRangeLow ?? undefined,
        entry_range_high: item.entryRangeHigh ?? undefined,
        final_score: item.finalScore,
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
          strategy_health: payload.decision.strategyHealth,
          themes: payload.decision.themes,
          portfolio: payload.decision.portfolio.map((item) => ({
            slot: item.slot,
            slot_label: item.slotLabel,
            rank: item.rank,
            ts_code: item.tsCode,
            name: item.name,
            theme: item.theme,
            role: item.role,
            score: item.score,
            rank_score: item.rankScore,
            risk_score: item.riskScore,
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
            ts_code: item.tsCode,
            name: item.name,
            theme: item.theme,
            role: item.role,
            reason: item.reason,
            rank_score: item.rankScore,
          })),
          evidence: {
            theme_validation: payload.decision.evidence.themeValidation,
            today_reasoning: payload.decision.evidence.todayReasoning,
          },
          action_checklist: {
            enabled: payload.decision.actionChecklist.enabled,
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
