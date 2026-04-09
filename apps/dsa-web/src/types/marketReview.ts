export interface MarketReviewListItem {
  reportDate: string;
  title: string;
  sentiment: string;
  sentimentLabel: string;
  fileSize: number;
}

export interface MarketReviewItem {
  reportDate: string;
  title: string;
  sentiment: string;
  sentimentLabel: string;
  shanghaiIndex?: number;
  shanghaiChange?: number;
  shenzhenIndex?: number;
  shenzhenChange?: number;
  chiIndex?: number;
  chiChange?: number;
  totalVolume?: number;
  risingCount?: number;
  fallingCount?: number;
  limitUp?: number;
  limitDown?: number;
  topSectors: string[];
  bottomSectors: string[];
  strategy?: string;
  content: string;
}

export interface MarketReviewListResponse {
  items: MarketReviewListItem[];
  total: number;
}

export interface MarketReviewResponse {
  item: MarketReviewItem;
}

export function getSentimentBadgeVariant(sentiment: string): 'danger' | 'success' | 'default' {
  if (sentiment === '📉') {
    return 'danger';
  }
  if (sentiment === '📈') {
    return 'success';
  }
  return 'default';
}

export function getStrategyBadgeVariant(
  strategy?: string,
): 'warning' | 'info' | 'default' {
  if (!strategy) {
    return 'default';
  }
  if (strategy.includes('防守')) {
    return 'warning';
  }
  if (strategy.includes('进攻')) {
    return 'info';
  }
  return 'default';
}
