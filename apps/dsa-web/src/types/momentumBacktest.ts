export interface MomentumBacktestCreateRequest {
  startTradeDate: string;
  endTradeDate: string;
  strictStrategyHealth?: boolean;
}

export interface MomentumBacktestTaskSection {
  total: number;
  limit?: number | null;
  items: MomentumBacktestRunResponse[];
}

export interface MomentumBacktestSummary {
  strategyHealthMode?: string;
  strategyHealthModeLabel?: string;
  strategyHealthValidationStatusBreakdown?: Record<string, number>;
  attackPermissionBreakdown?: Record<string, number>;
  themeConfidenceBreakdown?: Record<string, number>;
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
  candidateTop10SettlementPassRate?: number | null;
  candidateTop10WeakContinuityRate?: number | null;
  candidateTop10TradableSuccessRate?: number | null;
  candidateTop10T1DirectionPassRate?: number | null;
  candidateTop10T2ContinuationPassRate?: number | null;
  candidateTop10AvgT2ProfitWindowPct?: number | null;
  candidateTop10AvgT2MaxDrawdownPct?: number | null;
  candidatePoolTradableSuccessRate?: number | null;
  candidatePoolWeakContinuityRate?: number | null;
  candidatePoolAvgT2ProfitWindowPct?: number | null;
  candidatePoolAvgT2MaxDrawdownPct?: number | null;
  decisionTop3BuyTriggerRate?: number | null;
  decisionTop3PositiveT1Rate?: number | null;
  decisionTop3PositiveT2Rate?: number | null;
  decisionTop3SettlementPassRate?: number | null;
  decisionTop3WeakContinuityRate?: number | null;
  decisionTop3TradableSuccessRate?: number | null;
  decisionTop3T1DirectionPassRate?: number | null;
  decisionTop3T2ContinuationPassRate?: number | null;
  decisionTop3AvgT1ProfitWindowPct?: number | null;
  decisionTop3AvgT2ProfitWindowPct?: number | null;
  decisionTop3AvgT2MaxDrawdownPct?: number | null;
  benchmarkComparison: MomentumBacktestBenchmarkItem[];
  strategyAlphaReport?: MomentumBacktestStrategyAlphaReport | null;
  gateJustificationReport?: MomentumBacktestGateJustificationReport | null;
  layerDiagnostics: MomentumBacktestLayerDiagnostic[];
  gateModuleBreakdown: MomentumBacktestGateModuleBreakdownItem[];
  regimeBreakdown: MomentumBacktestRegimeBreakdownItem[];
  v13Diagnostics?: MomentumBacktestV13Diagnostics | null;
}

export interface MomentumBacktestBenchmarkItem {
  key: string;
  label: string;
  sampleCount: number;
  triggerRatePct?: number | null;
  positiveT2RatePct?: number | null;
  settlementPassRatePct?: number | null;
  weakContinuityPassRatePct?: number | null;
  tradableSuccessRatePct?: number | null;
  t1DirectionPassRatePct?: number | null;
  t2ContinuationPassRatePct?: number | null;
  avgT2ProfitWindowPct?: number | null;
  avgT2MaxDrawdownPct?: number | null;
  alphaVsOfficialTop3Pct?: number | null;
  alphaVsCandidateTop10Pct?: number | null;
  alphaVsMarketBasePct?: number | null;
  tradableSuccessAlphaVsOfficialTop3Pct?: number | null;
  tradableSuccessAlphaVsMarketBasePct?: number | null;
}

export interface MomentumBacktestStrategyAlphaReport {
  status: string;
  warningTriggered: boolean;
  warningMessage?: string | null;
  officialTop3SampleCount: number;
  rawMomentumTop3SampleCount: number;
  marketBaseSampleCount: number;
  officialTop3TradableSuccessRatePct?: number | null;
  rawMomentumTop3TradableSuccessRatePct?: number | null;
  marketBaseTradableSuccessRatePct?: number | null;
  v13AlphaVsPoolPct?: number | null;
  selectionEfficiencyPct?: number | null;
  officialTop3AvgT2ProfitWindowPct?: number | null;
  rawMomentumTop3AvgT2ProfitWindowPct?: number | null;
  marketBaseAvgT2ProfitWindowPct?: number | null;
}

export interface MomentumBacktestGateJustificationItem {
  tradeDate: string;
  actionLevel: string;
  actionLabel: string;
  poolBaseWinRatePct?: number | null;
  candidatePoolSampleCount: number;
  classification: 'Successful_Defensive_Gate' | 'False_Alarm_Warning' | 'Neutral_Gate';
  summary: string;
}

export interface MomentumBacktestGateJustificationReport {
  standAsideDays: number;
  evaluatedStandAsideDays: number;
  successfulDefensiveGateCount: number;
  falseAlarmWarningCount: number;
  evaluatedGateDays: MomentumBacktestGateJustificationItem[];
  recentGateLookbackDays: number;
  recentSuccessfulDefensiveGateRatePct?: number | null;
  successfulDefensiveGate: MomentumBacktestGateJustificationItem[];
  falseAlarmWarnings: MomentumBacktestGateJustificationItem[];
  successfulDefensiveGateThresholdPct: number;
  falseAlarmWarningThresholdPct: number;
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
  decisionWeakContinuityRatePct?: number | null;
  decisionTradableSuccessRatePct?: number | null;
  decisionAvgT2ProfitWindowPct?: number | null;
  decisionAvgT2MaxDrawdownPct?: number | null;
  missedOpportunityRatePct?: number | null;
  allowedTradePrecisionPct?: number | null;
  standAsideRatePct?: number | null;
}

export interface MomentumBacktestV13ThemeBreakdownItem {
  theme: string;
  days: number;
}

export interface MomentumBacktestV13MainlineItem {
  themeId?: string | null;
  themeName?: string | null;
  score?: number | null;
  level?: string | null;
  levelLabel?: string | null;
  summary?: string | null;
  sourceThemeNames?: string[];
  candidateCount?: number | null;
  top10Count?: number | null;
  limitUpCount?: number | null;
  brokenLimitCount?: number | null;
  hotRank?: number | null;
  boardRank?: number | null;
  leaderStock?: string | null;
  netAmount?: number | null;
  pctChange?: number | null;
}

export interface MomentumBacktestV13ShortTermSentiment {
  level?: string | null;
  levelLabel?: string | null;
  score?: number | null;
  summary?: string | null;
}

export interface MomentumBacktestV13DataStatus {
  status?: string | null;
  reason?: string | null;
  isDegraded?: boolean | null;
}

export interface MomentumBacktestV13StructuredDiagnostic {
  key?: string | null;
  label?: string | null;
  level?: string | null;
  levelLabel?: string | null;
  score?: number | null;
  avgScore?: number | null;
  summary?: string | null;
  metrics?: Record<string, unknown> | null;
  sampleDays?: number;
  strongDays?: number;
  generalDays?: number;
  weakDays?: number;
}

export interface MomentumBacktestV13FailureAttributionItem {
  key?: string | null;
  label?: string | null;
  summary?: string | null;
  days?: number;
}

export interface MomentumBacktestV13Diagnostics {
  evaluatedTradeDates?: number;
  radarAvailableDays?: number;
  radarCoveragePct?: number | null;
  avgTopMainlineScore?: number | null;
  sentimentBreakdown?: Record<string, number>;
  dataStatusBreakdown?: Record<string, number>;
  degradedDays?: number;
  topThemeBreakdown?: MomentumBacktestV13ThemeBreakdownItem[];
  summary?: string | null;
  mainlineRadar?: MomentumBacktestV13MainlineItem[];
  shortTermSentiment?: MomentumBacktestV13ShortTermSentiment | null;
  v13DataStatus?: MomentumBacktestV13DataStatus | null;
  topMainline?: MomentumBacktestV13MainlineItem | null;
  mainlineCount?: number;
  summaryLines?: string[];
  mainlineQuality?: MomentumBacktestV13StructuredDiagnostic | null;
  themeConcentration?: MomentumBacktestV13StructuredDiagnostic | null;
  sentimentAlignment?: MomentumBacktestV13StructuredDiagnostic | null;
  roleFit?: MomentumBacktestV13StructuredDiagnostic | null;
  pricePosition?: MomentumBacktestV13StructuredDiagnostic | null;
  candidatePoolBias?: MomentumBacktestV13StructuredDiagnostic | null;
  failureAttribution?: MomentumBacktestV13FailureAttributionItem[];
  failureAttributionBreakdown?: MomentumBacktestV13FailureAttributionItem[];
}

export interface MomentumBacktestRunResponse {
  runId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  profile: 'standard' | 'aggressive';
  engineVersion: string;
  strategyHealthMode?: string;
  strategyHealthModeLabel?: string;
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
  strategyHealthMode?: string;
  strategyHealthModeLabel?: string;
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
  settlementRule?: string | null;
  weakContinuityRule?: string | null;
  tradableSuccessRule?: string | null;
  t0ClosePrice?: number | null;
  t1OpenPrice?: number | null;
  t1HighPrice?: number | null;
  t1LowPrice?: number | null;
  t1ClosePrice?: number | null;
  t2HighPrice?: number | null;
  t2ClosePrice?: number | null;
  t2SlippageAdjustedExitPrice?: number | null;
  t1DirectionPass?: boolean | null;
  t2ContinuationPass?: boolean | null;
  weakContinuityPass?: boolean | null;
  t1OneWordLimit?: boolean | null;
  t1BuyabilityPass?: boolean | null;
  t1GapRiskPass?: boolean | null;
  tradableProfitWindowPass?: boolean | null;
  tradableSuccessPass?: boolean | null;
  settlementPass?: boolean | null;
}

export interface MomentumBacktestOutcomeMetrics {
  sampleCount: number;
  triggerRatePct?: number | null;
  positiveT1RatePct?: number | null;
  positiveT2RatePct?: number | null;
  settlementPassRatePct?: number | null;
  weakContinuityPassRatePct?: number | null;
  tradableSuccessRatePct?: number | null;
  t1DirectionPassRatePct?: number | null;
  t2ContinuationPassRatePct?: number | null;
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
  officialScore?: number | null;
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
  officialScore?: number | null;
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
  v13Diagnostics?: MomentumBacktestV13Diagnostics | null;
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
