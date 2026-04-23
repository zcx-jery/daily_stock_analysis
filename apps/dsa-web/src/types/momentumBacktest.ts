export interface MomentumBacktestCreateRequest {
  startTradeDate: string;
  endTradeDate: string;
}

export interface MomentumBacktestTaskSection {
  total: number;
  limit?: number | null;
  items: MomentumBacktestRunResponse[];
}

export interface MomentumBacktestSummary {
  completedTradeDates: number;
  actionBreakdown: Record<string, number>;
  marketEnvironmentBreakdown: Record<string, number>;
  opportunityQualityBreakdown: Record<string, number>;
  historicalValidityBreakdown: Record<string, number>;
  avgCandidateCount?: number | null;
  avgSelectedCount?: number | null;
  avgBuyReadyCount?: number | null;
  candidateTop10BuyTriggerRate?: number | null;
  candidateTop10PositiveT2Rate?: number | null;
  candidateTop10AvgT2ProfitWindowPct?: number | null;
  candidateTop10AvgT2MaxDrawdownPct?: number | null;
  decisionTop3BuyTriggerRate?: number | null;
  decisionTop3PositiveT1Rate?: number | null;
  decisionTop3PositiveT2Rate?: number | null;
  decisionTop3AvgT1ProfitWindowPct?: number | null;
  decisionTop3AvgT2ProfitWindowPct?: number | null;
  decisionTop3AvgT2MaxDrawdownPct?: number | null;
  benchmarkComparison: MomentumBacktestBenchmarkItem[];
  layerDiagnostics: MomentumBacktestLayerDiagnostic[];
  gateModuleBreakdown: MomentumBacktestGateModuleBreakdownItem[];
  regimeBreakdown: MomentumBacktestRegimeBreakdownItem[];
}

export interface MomentumBacktestBenchmarkItem {
  key: string;
  label: string;
  sampleCount: number;
  triggerRatePct?: number | null;
  positiveT2RatePct?: number | null;
  avgT2ProfitWindowPct?: number | null;
  avgT2MaxDrawdownPct?: number | null;
  alphaVsOfficialTop3Pct?: number | null;
  alphaVsCandidateTop10Pct?: number | null;
}

export interface MomentumBacktestLayerDiagnostic {
  key: string;
  label: string;
  level: 'strong' | 'general' | 'weak';
  score: number;
  summary: string;
  metrics: Record<string, number | null>;
}

export interface MomentumBacktestGateModuleBreakdownItem {
  key: string;
  label: string;
  groupKey: string;
  groupLabel: string;
  sampleDays: number;
  strongDays: number;
  mediumDays: number;
  weakDays: number;
  blockerDays: number;
  restrictedDays: number;
  avgScore?: number | null;
  weakDayCandidatePositiveT2RatePct?: number | null;
  weakDayDecisionPositiveT2RatePct?: number | null;
  weakDayCandidateAvgT2ProfitWindowPct?: number | null;
  weakDayDecisionAvgT2ProfitWindowPct?: number | null;
  strongDayDecisionAvgT2ProfitWindowPct?: number | null;
  summary: string;
}

export interface MomentumBacktestGateSnapshotModule {
  key: string;
  label: string;
  groupKey: string;
  groupLabel: string;
  level: string;
  levelLabel: string;
  score?: number | null;
  summary: string;
}

export interface MomentumBacktestGateSnapshotGroup {
  key: string;
  label: string;
  level: string;
  levelLabel: string;
  score?: number | null;
  reason: string;
  modules: MomentumBacktestGateSnapshotModule[];
}

export interface MomentumBacktestRegimeBreakdownItem {
  level: 'strong' | 'general' | 'weak';
  label: string;
  tradeDays: number;
  decisionPositiveT2RatePct?: number | null;
  decisionAvgT2ProfitWindowPct?: number | null;
  decisionAvgT2MaxDrawdownPct?: number | null;
  missedOpportunityRatePct?: number | null;
  allowedTradePrecisionPct?: number | null;
  standAsideRatePct?: number | null;
}

export interface MomentumBacktestRunResponse {
  runId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  profile: 'standard' | 'aggressive';
  engineVersion: string;
  entryBaselineVersion: string;
  marketScopeVersion: string;
  topN: number;
  startTradeDate: string;
  endTradeDate: string;
  totalTradeDates: number;
  processedTradeDates: number;
  failedTradeDates: number;
  currentTradeDate?: string | null;
  currentStageKey?: string | null;
  currentStageLabel?: string | null;
  heartbeatAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  cancelRequested: boolean;
  summary?: MomentumBacktestSummary | null;
  errorMessage?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface MomentumBacktestCreateResponse {
  createdNew: boolean;
  message: string;
  run: MomentumBacktestRunResponse;
}

export interface MomentumBacktestRunListResponse {
  currentRunning?: MomentumBacktestRunResponse | null;
  queued: MomentumBacktestTaskSection;
  history: MomentumBacktestTaskSection;
  refreshedAt?: string | null;
}

export interface MomentumBacktestDeleteResponse {
  runId: string;
  deleted: boolean;
  message: string;
}

export interface MomentumBacktestSummaryResponse {
  runId: string;
  profile: 'standard' | 'aggressive';
  engineVersion: string;
  summary: MomentumBacktestSummary;
}

export interface MomentumBacktestDailyItem {
  tradeDate: string;
  actionLevel: string;
  actionLabel: string;
  recommendationCap: string;
  actionChecklistMode: string;
  marketEnvironmentLevel: string;
  opportunityQualityLevel: string;
  historicalValidityLevel: string;
  candidateCount: number;
  resultCount: number;
  selectedCount: number;
  buyReadyCount: number;
  mainTsCode?: string | null;
  secondaryTsCode?: string | null;
  watchTsCode?: string | null;
}

export interface MomentumBacktestDailyListResponse {
  runId: string;
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  items: MomentumBacktestDailyItem[];
}

export interface MomentumBacktestOutcomeItem {
  viewScope: string;
  slot?: string | null;
  tsCode: string;
  name: string;
  buyTriggered: boolean;
  referenceEntryPrice?: number | null;
  triggerPrice?: number | null;
  triggerTradeDate?: string | null;
  t1TradeDate?: string | null;
  t1CloseReturnPct?: number | null;
  t1ProfitWindowPct?: number | null;
  t1MaxDrawdownPct?: number | null;
  t2TradeDate?: string | null;
  t2CloseReturnPct?: number | null;
  t2ProfitWindowPct?: number | null;
  t2MaxDrawdownPct?: number | null;
  realStrengthLabel?: string | null;
}

export interface MomentumBacktestOutcomeMetrics {
  sampleCount: number;
  triggerRatePct?: number | null;
  positiveT1RatePct?: number | null;
  positiveT2RatePct?: number | null;
  avgT1ProfitWindowPct?: number | null;
  avgT2ProfitWindowPct?: number | null;
  avgT2MaxDrawdownPct?: number | null;
  bestT2ProfitWindowPct?: number | null;
}

export interface MomentumBacktestOutcomeGroup {
  metrics: MomentumBacktestOutcomeMetrics;
  items: MomentumBacktestOutcomeItem[];
}

export interface MomentumBacktestCandidateDetailItem {
  rank: number;
  tsCode: string;
  name: string;
  theme?: string | null;
  role?: string | null;
  marketSegment?: string | null;
  rankScore?: number | null;
  finalScore?: number | null;
  continuationScore?: number | null;
  extensionScore?: number | null;
  riskScore?: number | null;
  buyabilityScore?: number | null;
  decisionDiagnostics?: Record<string, unknown> | null;
  outcome?: MomentumBacktestOutcomeItem | null;
}

export interface MomentumBacktestDecisionDetailItem {
  slot: string;
  rank?: number | null;
  tsCode: string;
  name: string;
  theme?: string | null;
  role?: string | null;
  decisionScore?: number | null;
  rankScore?: number | null;
  riskScore?: number | null;
  buyPointStatus?: string | null;
  suggestedAction?: string | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  opportunityTag?: string | null;
  outcome?: MomentumBacktestOutcomeItem | null;
}

export interface MomentumBacktestIssueItem {
  issueKey: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  summary: string;
  affectedCodes: string[];
  metrics: Record<string, number | null>;
}

export interface MomentumBacktestDailyDiagnosis {
  summaryLines: string[];
  candidateMetrics: MomentumBacktestOutcomeMetrics;
  decisionMetrics: MomentumBacktestOutcomeMetrics;
  gateSnapshot: MomentumBacktestGateSnapshotGroup[];
  gateBlockers: MomentumBacktestGateSnapshotModule[];
  issues: MomentumBacktestIssueItem[];
}

export interface MomentumBacktestDailyDetailResponse {
  runId: string;
  tradeDate: string;
  dailyContext: MomentumBacktestDailyItem;
  candidateTop10: MomentumBacktestCandidateDetailItem[];
  decisionTop3: MomentumBacktestDecisionDetailItem[];
  slotView: MomentumBacktestDecisionDetailItem[];
  outcomes: Record<string, MomentumBacktestOutcomeGroup>;
  diagnosis: MomentumBacktestDailyDiagnosis;
}

export interface MomentumBacktestIssueListItem extends MomentumBacktestIssueItem {
  tradeDate: string;
  actionLevel: string;
  actionLabel: string;
}

export interface MomentumBacktestIssueListResponse {
  runId: string;
  totalIssues: number;
  severityBreakdown: Record<string, number>;
  issueKeyBreakdown: Record<string, number>;
  items: MomentumBacktestIssueListItem[];
}
