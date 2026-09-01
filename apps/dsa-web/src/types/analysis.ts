/**
 * Analysis-related type definitions.
 * Aligned with the API schema.
 */

// ============ Request Types ============

export interface AnalysisRequest {
  stockCode?: string;
  stockCodes?: string[];
  reportType?: 'simple' | 'detailed' | 'full' | 'brief';
  forceRefresh?: boolean;
  asyncMode?: boolean;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: 'manual' | 'autocomplete' | 'import' | 'image';
  notify?: boolean;
}

// ============ Report Types ============

export type ReportLanguage = 'zh' | 'en';

/** Report metadata */
export interface ReportMeta {
  id?: number;  // Analysis history record ID, present for persisted reports
  queryId: string;
  stockCode: string;
  stockName: string;
  reportType: 'simple' | 'detailed' | 'full' | 'brief';
  reportLanguage?: ReportLanguage;
  createdAt: string;
  currentPrice?: number;
  changePct?: number;
  modelUsed?: string;  // LLM model used for analysis
}

/** Sentiment label */
export type SentimentLabel =
  | '极度悲观'
  | '悲观'
  | '中性'
  | '乐观'
  | '极度乐观'
  | 'Very Bearish'
  | 'Bearish'
  | 'Neutral'
  | 'Bullish'
  | 'Very Bullish';

/** Report summary section */
export interface ReportSummary {
  analysisSummary: string;
  operationAdvice: string;
  trendPrediction: string;
  sentimentScore: number;
  sentimentLabel?: SentimentLabel;
}

/** Strategy section */
export interface ReportStrategy {
  idealBuy?: string;
  secondaryBuy?: string;
  stopLoss?: string;
  takeProfit?: string;
}

export interface ReportFieldDrift {
  mappedAliases?: Record<string, string>;
  rawKeyLevels?: Record<string, string | number | boolean>;
  unmappedKeyLevels?: Record<string, string | number | boolean>;
  dashboardExtra?: Record<string, string | number | boolean>;
}

export interface RelatedBoard {
  name: string;
  code?: string;
  type?: string;
}

export interface SectorRankingItem {
  name: string;
  changePct?: number;
}

export interface SectorRankings {
  top?: SectorRankingItem[];
  bottom?: SectorRankingItem[];
}

export interface SourceChainItem {
  provider: string;
  result?: string;
  durationMs?: number;
  error?: string;
}

export interface CapitalFlowMetrics {
  status?: string;
  signal?: string;
  mixedReason?: string;
  tradeDate?: string;
  stockFlow?: Record<string, unknown>;
  ths?: Record<string, unknown>;
  dc?: Record<string, unknown>;
  sourceChain?: SourceChainItem[];
  errors?: string[];
}

export interface ChipMetrics {
  status?: string;
  chipStatus?: string;
  chipSignal?: string;
  source?: string;
  asOf?: string;
  data?: Record<string, unknown>;
  sourceChain?: SourceChainItem[];
  errors?: string[];
}

export interface DataQualityBlock {
  status?: string;
  sourceChain?: SourceChainItem[];
  errors?: string[];
}

export interface DataQuality {
  status?: string;
  market?: string;
  enhancedByTushare?: boolean;
  coverage?: Record<string, string>;
  blocks?: Record<string, DataQualityBlock>;
  sourceChain?: SourceChainItem[];
  errors?: string[];
  elapsedMs?: number;
}

export interface TushareEnhancement {
  enabled?: boolean;
  blocks?: string[];
  sourceChain?: SourceChainItem[];
  coverage?: Record<string, string>;
}

export interface FundamentalMetrics {
  valuation?: Record<string, unknown>;
  profitability?: Record<string, unknown>;
  growth?: Record<string, unknown>;
  statuses?: Record<string, string>;
  sourceChain?: SourceChainItem[];
  errors?: string[];
}

export interface BoardLinkage {
  status?: string;
  matchedBoard?: string | null;
  reason?: string;
}

/** Details section */
export interface ReportDetails {
  newsContent?: string;
  rawResult?: Record<string, unknown>;
  fieldDrift?: ReportFieldDrift;
  contextSnapshot?: Record<string, unknown>;
  financialReport?: Record<string, unknown>;
  dividendMetrics?: Record<string, unknown>;
  fundamentalMetrics?: FundamentalMetrics;
  belongBoards?: RelatedBoard[];
  sectorRankings?: SectorRankings;
  boardLinkage?: BoardLinkage;
  capitalFlowMetrics?: CapitalFlowMetrics;
  chipMetrics?: ChipMetrics;
  dataQuality?: DataQuality;
  tushareEnhancement?: TushareEnhancement;
}

/** Full analysis report */
export interface AnalysisReport {
  meta: ReportMeta;
  summary: ReportSummary;
  strategy?: ReportStrategy;
  details?: ReportDetails;
}

// ============ Analysis Result Types ============

/** Sync analysis response */
export interface AnalysisResult {
  queryId: string;
  stockCode: string;
  stockName: string;
  report: AnalysisReport;
  createdAt: string;
}

/** Async task accepted response */
export interface TaskAccepted {
  taskId: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchTaskAcceptedItem {
  taskId: string;
  stockCode: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchDuplicateTaskItem {
  stockCode: string;
  existingTaskId: string;
  message: string;
}

export interface BatchTaskAcceptedResponse {
  accepted: BatchTaskAcceptedItem[];
  duplicates: BatchDuplicateTaskItem[];
  message: string;
}

export type AnalyzeAsyncResponse = TaskAccepted | BatchTaskAcceptedResponse;

export type AnalyzeResponse = AnalysisResult | AnalyzeAsyncResponse;

/** Task status */
export interface TaskStatus {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
  result?: AnalysisResult;
  error?: string;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: string;
  progressEvents?: TaskProgressEvent[];
}

/** Task details used by task list and SSE events */
export interface TaskProgressEvent {
  progress: number;
  message: string;
  eventType: string;
  timestamp: string;
}

export interface TaskInfo {
  taskId: string;
  stockCode: string;
  stockName?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string;
  reportType: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  originalQuery?: string;
  selectionSource?: string;
  progressEvents?: TaskProgressEvent[];
}

/** Task list response */
export interface TaskListResponse {
  total: number;
  pending: number;
  processing: number;
  tasks: TaskInfo[];
}

/** Duplicate task error response */
export interface DuplicateTaskError {
  error: 'duplicate_task';
  message: string;
  stockCode: string;
  existingTaskId: string;
}

// ============ History Types ============

/** History item summary */
export interface HistoryItem {
  id: number;  // Record primary key ID, always present for persisted history items
  queryId: string;  // Linked analysis query ID
  stockCode: string;
  stockName?: string;
  reportType?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  createdAt: string;
}

/** History list response */
export interface HistoryListResponse {
  total: number;
  page: number;
  limit: number;
  items: HistoryItem[];
}

/** News item */
export interface NewsIntelItem {
  title: string;
  snippet: string;
  url: string;
}

/** News response */
export interface NewsIntelResponse {
  total: number;
  items: NewsIntelItem[];
}

/** History filter parameters */
export interface HistoryFilters {
  stockCode?: string;
  startDate?: string;
  endDate?: string;
}

/** History pagination parameters */
export interface HistoryPagination {
  page: number;
  limit: number;
}

// ============ Error Types ============

export interface ApiError {
  error: string;
  message: string;
  detail?: Record<string, unknown>;
}

// ============ Helper Functions ============

/** Get sentiment label by score */
export const getSentimentLabel = (score: number, language: ReportLanguage = 'zh'): SentimentLabel => {
  if (language === 'en') {
    if (score <= 20) return 'Very Bearish';
    if (score <= 40) return 'Bearish';
    if (score <= 60) return 'Neutral';
    if (score <= 80) return 'Bullish';
    return 'Very Bullish';
  }
  if (score <= 20) return '极度悲观';
  if (score <= 40) return '悲观';
  if (score <= 60) return '中性';
  if (score <= 80) return '乐观';
  return '极度乐观';
};

/** Get sentiment color by score */
export const getSentimentColor = (score: number): string => {
  if (score <= 20) return '#ef4444'; // red-500
  if (score <= 40) return '#f97316'; // orange-500
  if (score <= 60) return '#eab308'; // yellow-500
  if (score <= 80) return '#22c55e'; // green-500
  return '#10b981'; // emerald-500
};
