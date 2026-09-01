import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MomentumScreeningRunCreateResponse,
  MomentumScreeningRunListResponse,
  MomentumScreeningRunRequest,
  MomentumScreeningRunResponse,
  MomentumScreeningRunResultResponse,
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

type MomentumRunApiRequest = MomentumApiRequest & {
  truth_mode?: 'full' | 'light';
  use_sector_context?: boolean;
  max_scored_candidates?: number;
};

type DecisionRequestOptions = {
};

export const momentumScreenerApi = {
  async createRun(payload: MomentumScreeningRunRequest): Promise<MomentumScreeningRunCreateResponse> {
    const request: MomentumRunApiRequest = {
      top_n: payload.topN,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
      truth_mode: payload.truthMode ?? 'full',
      use_sector_context: payload.useSectorContext ?? true,
      max_scored_candidates: payload.maxScoredCandidates ?? undefined,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum/runs', request, {
      timeout: 30000,
    });
    return toCamelCase<MomentumScreeningRunCreateResponse>(response.data);
  },

  async listRuns(limit = 20, profile?: 'standard' | 'aggressive'): Promise<MomentumScreeningRunListResponse> {
    const response = await apiClient.get('/api/v1/stocks/screener/momentum/runs', {
      params: { limit, profile },
      timeout: 30000,
    });
    return toCamelCase<MomentumScreeningRunListResponse>(response.data);
  },

  async getRun(runId: string): Promise<MomentumScreeningRunResponse> {
    const response = await apiClient.get(`/api/v1/stocks/screener/momentum/runs/${encodeURIComponent(runId)}`, {
      timeout: 30000,
    });
    return toCamelCase<MomentumScreeningRunResponse>(response.data);
  },

  async getRunResult(runId: string): Promise<MomentumScreeningRunResultResponse> {
    const response = await apiClient.get(`/api/v1/stocks/screener/momentum/runs/${encodeURIComponent(runId)}/result`, {
      timeout: 30000,
    });
    return toCamelCase<MomentumScreeningRunResultResponse>(response.data);
  },

  async cancelRun(runId: string): Promise<MomentumScreeningRunResponse> {
    const response = await apiClient.post(
      `/api/v1/stocks/screener/momentum/runs/${encodeURIComponent(runId)}/cancel`,
      undefined,
      { timeout: 30000 },
    );
    return toCamelCase<MomentumScreeningRunResponse>(response.data);
  },

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
    _options: DecisionRequestOptions = {},
  ): Promise<MomentumScreenerDecisionResponse> {
    const request: MomentumApiRequest = {
      top_n: payload.topN,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum/decision', request, {
      timeout: 180000,
    });
    return toCamelCase<MomentumScreenerDecisionResponse>(response.data);
  },

  async fetchIntradaySignal(
    payload: MomentumScreenerRequest,
    _options: DecisionRequestOptions = {},
  ): Promise<MomentumScreenerIntradayResponse> {
    const request: MomentumApiRequest = {
      top_n: payload.topN,
      trade_date: payload.tradeDate || undefined,
      profile: payload.profile,
    };

    const response = await apiClient.post('/api/v1/stocks/screener/momentum/decision/intraday', request, {
      timeout: 180000,
    });
    return toCamelCase<MomentumScreenerIntradayResponse>(response.data);
  },
};
