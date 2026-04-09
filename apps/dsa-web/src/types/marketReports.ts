export interface MarketReportItem {
  date: string;
  title: string;
  fileName: string;
  updatedAt?: string;
}

export interface MarketReportListResponse {
  items: MarketReportItem[];
}

export interface MarketReportDetail extends MarketReportItem {
  content: string;
}
