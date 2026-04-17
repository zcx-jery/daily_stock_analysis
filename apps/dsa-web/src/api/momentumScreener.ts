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
