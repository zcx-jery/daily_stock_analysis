import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MomentumBacktestCreateRequest,
  MomentumBacktestCreateResponse,
  MomentumBacktestDailyDetailResponse,
  MomentumBacktestDailyListResponse,
  MomentumBacktestDeleteResponse,
  MomentumBacktestIssueListResponse,
  MomentumBacktestRunListResponse,
  MomentumBacktestRunResponse,
  MomentumBacktestSummaryResponse,
} from '../types/momentumBacktest';

export interface MomentumBacktestDailyQuery {
  dateFrom?: string;
  dateTo?: string;
  marketRegime?: string;
  actionLevel?: string;
  slot?: string;
  themeName?: string;
  page?: number;
  pageSize?: number;
}

export interface MomentumBacktestRunListQuery {
  limit?: number;
  profile?: 'standard' | 'aggressive';
}

export const momentumBacktestApi = {
  createRun: async (payload: MomentumBacktestCreateRequest): Promise<MomentumBacktestCreateResponse> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stocks/screener/momentum/backtests', {
      start_trade_date: payload.startTradeDate,
      end_trade_date: payload.endTradeDate,
      profile: payload.profile ?? 'standard',
      top_n: payload.topN ?? 30,
    });
    return toCamelCase<MomentumBacktestCreateResponse>(response.data);
  },

  listRuns: async (query: MomentumBacktestRunListQuery = {}): Promise<MomentumBacktestRunListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stocks/screener/momentum/backtests', {
      params: {
        limit: query.limit,
        profile: query.profile,
      },
    });
    return toCamelCase<MomentumBacktestRunListResponse>(response.data);
  },

  getRun: async (runId: string): Promise<MomentumBacktestRunResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}`,
    );
    return toCamelCase<MomentumBacktestRunResponse>(response.data);
  },

  cancelRun: async (runId: string): Promise<MomentumBacktestRunResponse> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}/cancel`,
    );
    return toCamelCase<MomentumBacktestRunResponse>(response.data);
  },

  deleteRun: async (runId: string): Promise<MomentumBacktestDeleteResponse> => {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}`,
    );
    return toCamelCase<MomentumBacktestDeleteResponse>(response.data);
  },

  getSummary: async (runId: string): Promise<MomentumBacktestSummaryResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}/summary`,
    );
    return toCamelCase<MomentumBacktestSummaryResponse>(response.data);
  },

  getDaily: async (runId: string, query: MomentumBacktestDailyQuery = {}): Promise<MomentumBacktestDailyListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}/daily`,
      {
        params: {
          date_from: query.dateFrom,
          date_to: query.dateTo,
          market_regime: query.marketRegime,
          action_level: query.actionLevel,
          slot: query.slot,
          theme_name: query.themeName,
          page: query.page,
          page_size: query.pageSize,
        },
      },
    );
    return toCamelCase<MomentumBacktestDailyListResponse>(response.data);
  },

  getDailyDetail: async (runId: string, tradeDate: string): Promise<MomentumBacktestDailyDetailResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}/daily/${encodeURIComponent(tradeDate)}`,
    );
    return toCamelCase<MomentumBacktestDailyDetailResponse>(response.data);
  },

  getIssues: async (runId: string): Promise<MomentumBacktestIssueListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/screener/momentum/backtests/${encodeURIComponent(runId)}/issues`,
    );
    return toCamelCase<MomentumBacktestIssueListResponse>(response.data);
  },
};
