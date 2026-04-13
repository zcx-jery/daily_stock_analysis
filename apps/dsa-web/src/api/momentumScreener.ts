import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MomentumScreenerDecisionResponse,
  MomentumScreenerIntradayResponse,
  MomentumScreenerRequest,
  MomentumScreenerResponse,
} from '../types/momentumScreener';

type MomentumApiRequest = {
  top_n: number;
  min_change_pct: number;
  min_amount: number;
  min_turnover: number;
  exclude_st: boolean;
  main_board_only: boolean;
  trade_date?: string;
  profile: 'standard' | 'aggressive';
};

type DecisionRequestOptions = {
  waitForStrategyHealth?: boolean;
};

export const momentumScreenerApi = {
  async screen(payload: MomentumScreenerRequest): Promise<MomentumScreenerResponse> {
    const request: MomentumApiRequest = {
      top_n: payload.topN,
      min_change_pct: payload.minChangePct,
      min_amount: payload.minAmount,
      min_turnover: payload.minTurnover,
      exclude_st: payload.excludeSt,
      main_board_only: payload.mainBoardOnly,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum', request, {
      // Real Tushare-backed screening is materially slower than ordinary CRUD requests.
      timeout: 180000,
    });
    return toCamelCase<MomentumScreenerResponse>(response.data);
  },

  async screenWithDecision(
    payload: MomentumScreenerRequest,
    options: DecisionRequestOptions = {},
  ): Promise<MomentumScreenerDecisionResponse> {
    const request: MomentumApiRequest = {
      top_n: payload.topN,
      min_change_pct: payload.minChangePct,
      min_amount: payload.minAmount,
      min_turnover: payload.minTurnover,
      exclude_st: payload.excludeSt,
      main_board_only: payload.mainBoardOnly,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum/decision', request, {
      params: options.waitForStrategyHealth ? { wait_for_strategy_health: true } : undefined,
      timeout: options.waitForStrategyHealth ? 600000 : 180000,
    });
    return toCamelCase<MomentumScreenerDecisionResponse>(response.data);
  },

  async fetchIntradaySignal(
    payload: MomentumScreenerRequest,
    options: DecisionRequestOptions = {},
  ): Promise<MomentumScreenerIntradayResponse> {
    const request: MomentumApiRequest = {
      top_n: payload.topN,
      min_change_pct: payload.minChangePct,
      min_amount: payload.minAmount,
      min_turnover: payload.minTurnover,
      exclude_st: payload.excludeSt,
      main_board_only: payload.mainBoardOnly,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum/decision/intraday', request, {
      params: options.waitForStrategyHealth ? { wait_for_strategy_health: true } : undefined,
      timeout: options.waitForStrategyHealth ? 600000 : 180000,
    });
    return toCamelCase<MomentumScreenerIntradayResponse>(response.data);
  },
};
