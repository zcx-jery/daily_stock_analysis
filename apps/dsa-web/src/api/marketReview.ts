import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MarketReviewListResponse,
  MarketReviewResponse,
} from '../types/marketReview';

export const marketReviewApi = {
  list: async (params?: {
    startDate?: string;
    endDate?: string;
    limit?: number;
  }): Promise<MarketReviewListResponse> => {
    const response = await apiClient.get('/api/v1/market-review', { params });
    return toCamelCase<MarketReviewListResponse>(response.data);
  },

  get: async (reportDate: string): Promise<MarketReviewResponse> => {
    const response = await apiClient.get(`/api/v1/market-review/${encodeURIComponent(reportDate)}`);
    return toCamelCase<MarketReviewResponse>(response.data);
  },
};
