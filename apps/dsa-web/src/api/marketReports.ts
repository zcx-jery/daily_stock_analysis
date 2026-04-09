import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  MarketReportDetail,
  MarketReportItem,
  MarketReportListResponse,
} from '../types/marketReports';

export const marketReportsApi = {
  getList: async (): Promise<MarketReportListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/market-reports');
    const data = toCamelCase<MarketReportListResponse>(response.data);

    return {
      items: (data.items || []).map((item) => toCamelCase<MarketReportItem>(item)),
    };
  },

  getDetail: async (reportDate: string): Promise<MarketReportDetail> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/market-reports/${encodeURIComponent(reportDate)}`,
    );
    return toCamelCase<MarketReportDetail>(response.data);
  },
};
