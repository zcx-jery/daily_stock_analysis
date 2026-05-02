export type MomentumProfile = 'standard' | 'aggressive';

export interface MomentumScreenerRequest {
  topN: number;
  tradeDate?: string;
  profile: MomentumProfile;
}

export interface MomentumScoreBreakdown {
  score: number;
  maxScore: number;
  items: Record<string, number | string | null>;
}

export interface MomentumScreenerResult {
  rank: number;
  tsCode: string;
  name: string;
  marketSegment: string;
  marketSegmentLabel: string;
  pctChg: number;
  continuationScore: number;
  extensionScore: number;
  riskScore: number;
  buyabilityScore?: number | null;
  opportunityTag?: string | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  finalScore: number;
  officialScore: number;
  mainlineIntensityCount?: number | null;
  mainlineIntensityMultiplier?: number | null;
  mainlineIntensityBonus?: number | null;
  close?: number | null;
  ma20?: number | null;
  high20d?: number | null;
  v13MainlineCandidateCount?: number | null;
  v13StockBuyElgAmount?: number | null;
  themes: string[];
  leaderLevel: string;
  topReasons: string[];
  riskTags: string[];
  scoreBreakdown: Record<string, MomentumScoreBreakdown>;
}

export interface MomentumScreenerResponse {
  profile: MomentumProfile;
  tradeDate: string;
  truthMode?: 'full' | 'light';
  requestedTradeDate?: string | null;
  tradeDateNote?: string | null;
  entryBaselineVersion: string;
  marketScopeVersion: string;
  candidateCount: number;
  results: MomentumScreenerResult[];
}

export interface MomentumScreeningRunRequest extends MomentumScreenerRequest {
  truthMode?: 'full' | 'light';
  useSectorContext?: boolean;
  maxScoredCandidates?: number | null;
}

export interface MomentumScreeningRunProgress {
  progressPct: number;
  processedItemCount: number;
  totalItemCount: number;
  cacheHits: Record<string, number>;
  cacheMisses: Record<string, number>;
}

export interface MomentumScreeningRunResponse {
  runId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  profile: MomentumProfile;
  truthMode: 'full' | 'light';
  engineVersion: string;
  entryBaselineVersion: string;
  marketScopeVersion: string;
  screeningCacheVersion: string;
  topN: number;
  requestedTradeDate?: string | null;
  tradeDate?: string | null;
  resultAvailable: boolean;
  requestParams: Record<string, unknown>;
  currentStageKey?: string | null;
  currentStageLabel?: string | null;
  progress: MomentumScreeningRunProgress;
  heartbeatAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  cancelRequested: boolean;
  errorMessage?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface MomentumScreeningRunCreateResponse {
  createdNew: boolean;
  message: string;
  run: MomentumScreeningRunResponse;
}

export interface MomentumScreeningRunTaskSection {
  total: number;
  items: MomentumScreeningRunResponse[];
}

export interface MomentumScreeningRunListResponse {
  currentRunning?: MomentumScreeningRunResponse | null;
  queued: MomentumScreeningRunTaskSection;
  history: MomentumScreeningRunTaskSection;
  refreshedAt?: string | null;
}

export type MomentumActionLevel =
  | 'strong_go'
  | 'normal_go'
  | 'cautious_go'
  | 'observe_only'
  | 'stand_aside';

export type MomentumDecisionSlot = 'main' | 'secondary' | 'watch';

export type MomentumBuyPointStatus = 'clear' | 'waiting' | 'unclear';

export type MomentumSuggestedAction = 'ready' | 'wait_for_trigger' | 'observe_only';

export interface MomentumDecisionAction {
  level: MomentumActionLevel;
  label: string;
  reason: string;
  sourceProfile: MomentumProfile;
}

export interface MomentumDecisionThemeRepresentative {
  rank: number;
  tsCode: string;
  name: string;
  role: string;
  buyPointLabel: string;
  officialScore?: number | null;
  v13MainlineScore?: number | null;
}

export interface MomentumDecisionTheme {
  name: string;
  score: number;
  strengthLabel: string;
  ruleThemeScore?: number | null;
  v13ThemeId?: string | null;
  v13MainlineScore?: number | null;
  v13Summary?: string | null;
  candidateCount: number;
  clearBuyPointCount: number;
  leaderCount: number;
  summary: string;
  representatives: MomentumDecisionThemeRepresentative[];
}

export interface MomentumDecisionReasonItem {
  key: string;
  label: string;
  delta?: number | null;
  detail?: string | null;
}

export interface MomentumRiskStackFactor {
  key: string;
  label: string;
  triggered: boolean;
  evidence?: string | null;
}

export interface MomentumRiskStackCheck {
  factorCount: number;
  veto: boolean;
  threshold: number;
  factors: MomentumRiskStackFactor[];
  triggeredKeys: string[];
}

export interface MomentumAdaptiveGateContext {
  enabled: boolean;
  mode: 'normal' | 'strict_mainline' | string;
  requiredMainlineCount: number;
  lookbackDays: number;
  evaluatedDays: number;
  successfulDefensiveGateRatePct?: number | null;
  sourceRunId?: string | null;
  reason?: string | null;
  [key: string]: unknown;
}

export interface MomentumDecisionIntelligenceFields {
  riskStack?: MomentumRiskStackCheck | null;
  riskStackCount?: number | null;
  riskStackVeto?: boolean | null;
  mainlineIntensityCount?: number | null;
  mainlineIntensityMultiplier?: number | null;
  mainlineIntensityBonus?: number | null;
  adaptiveGate?: MomentumAdaptiveGateContext | null;
  adaptiveMainlineCount?: number | null;
  adaptiveMainlineMinCount?: number | null;
  adaptiveMainlinePass?: boolean | null;
  v13LadderPosition?: Record<string, unknown> | null;
}

export interface MomentumDecisionPortfolioSlot extends MomentumDecisionIntelligenceFields {
  slot: MomentumDecisionSlot;
  slotLabel: string;
  rank: number;
  baseRank: number;
  tsCode: string;
  name: string;
  theme: string;
  v13ThemeId?: string | null;
  v13MainlineScore?: number | null;
  v13MainlineLevel?: string | null;
  v13MainlineLevelLabel?: string | null;
  v13ThemeStrengthScore?: number | null;
  v13FundSupportScore?: number | null;
  v13LimitStructureScore?: number | null;
  v13LadderPosition?: Record<string, unknown> | null;
  v13BuyabilityScore?: number | null;
  v13ChipRiskScore?: number | null;
  v13ShadowScore?: number | null;
  v13ShadowSummary?: string | null;
  role: string;
  score: number;
  officialScore: number;
  baseRankScore: number;
  riskScore: number;
  ruleBaseScore?: number | null;
  decisionAdjustment?: number | null;
  decisionAdjustmentReason?: string | null;
  hardBlockers: MomentumDecisionReasonItem[];
  softAdjustments: MomentumDecisionReasonItem[];
  forwardAlphaScore?: number | null;
  t1DirectionRiskAdjustment?: number | null;
  buyPointStatus: MomentumBuyPointStatus;
  buyPointLabel: string;
  suggestedAction: MomentumSuggestedAction;
  suggestedActionLabel: string;
  primaryReason: string;
  roleReason: string;
  executionPlan: string;
  entryHint?: string | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  opportunityTag?: string | null;
  riskTags?: string[];
}

export interface MomentumDecisionExcludedCandidate extends MomentumDecisionIntelligenceFields {
  rank: number;
  baseRank: number;
  tsCode: string;
  name: string;
  theme: string;
  role: string;
  reasonKey: string;
  reason: string;
  reasonDetail?: string | null;
  officialScore: number;
  baseRankScore: number;
  decisionAdjustment?: number | null;
  decisionAdjustmentReason?: string | null;
  hardBlockers: MomentumDecisionReasonItem[];
  softAdjustments: MomentumDecisionReasonItem[];
}

export interface MomentumDecisionCandidateDiagnostic extends MomentumDecisionIntelligenceFields {
  rank: number;
  baseRank: number;
  tsCode: string;
  name: string;
  theme: string;
  themeScore: number;
  v13ThemeId?: string | null;
  v13MainlineScore?: number | null;
  v13MainlineLevel?: string | null;
  v13MainlineLevelLabel?: string | null;
  v13ThemeStrengthScore?: number | null;
  v13FundSupportScore?: number | null;
  v13LimitStructureScore?: number | null;
  v13LadderPosition?: Record<string, unknown> | null;
  v13BuyabilityScore?: number | null;
  v13ChipRiskScore?: number | null;
  v13ShadowScore?: number | null;
  v13ShadowSummary?: string | null;
  roleKey: string;
  role: string;
  buyPointStatus: MomentumBuyPointStatus;
  buyPointLabel: string;
  officialScore: number;
  baseRankScore: number;
  continuationScore: number;
  extensionScore: number;
  extensionSignalScore: number;
  buyabilityScore?: number | null;
  riskScore: number;
  ruleBaseScore: number;
  decisionAdjustment?: number | null;
  decisionAdjustmentReason?: string | null;
  hardBlockers: MomentumDecisionReasonItem[];
  softAdjustments: MomentumDecisionReasonItem[];
  explainAdjustmentScore: number;
  t1DirectionRiskAdjustment?: number | null;
  forwardAlphaScore: number;
  forwardAlphaAdjustment: number;
  portfolioPriority: number;
  selectedSlot?: MomentumDecisionSlot | null;
  isSelected: boolean;
}

export interface MomentumDecisionEvidence {
  themeValidation: string[];
  todayReasoning: string[];
}

export interface MomentumDecisionGateModule {
  key: string;
  label: string;
  level: 'strong' | 'medium' | 'weak';
  score: number;
  summary: string;
}

export interface MomentumDecisionMarketEnvironment {
  level: 'strong' | 'medium' | 'weak';
  label: string;
  score: number;
  reason: string;
  modules: MomentumDecisionGateModule[];
}

export interface MomentumDecisionOpportunityQuality {
  level: 'strong' | 'medium' | 'weak';
  label: string;
  matrixLevel?: 'strong' | 'upper_mid' | 'mid' | 'weak' | null;
  matrixLabel?: string | null;
  score: number;
  reason: string;
  modules: MomentumDecisionGateModule[];
  clearCount?: number | null;
  clearBuyPointCount?: number | null;
  mainRiskRewardPass?: boolean | null;
  themeConcentrationPass?: boolean | null;
  mainBuyPointClear?: boolean | null;
  secondaryBuyPointClear?: boolean | null;
  coreOverextendedCount?: number | null;
  portfolioUnresolved?: boolean | null;
}

export interface MomentumDecisionHistoricalValidity {
  level: 'healthy' | 'general' | 'weak';
  label: string;
  score: number;
  reason: string;
  maxActionLevel: 'strong_go' | 'normal_go' | 'cautious_go';
  recommendationCap: 'full' | 'limited';
  attackPermissionStatus?: 'open' | 'recovering' | 'paused' | null;
  attackPermissionLabel?: string | null;
}

export interface MomentumDecisionAttackPermission {
  status: 'open' | 'recovering' | 'paused';
  statusLabel: string;
  label: string;
  score: number;
  window: 'short_20d';
  windowLabel: string;
  validSampleCount: number;
  hitRate: number;
  avgProfitWindowPct: number;
  avgMaxDrawdownPct: number;
  reason: string;
  summary: string;
}

export interface MomentumDecisionThemeConfidence {
  status: 'credible' | 'recovering' | 'questionable';
  statusLabel: string;
  label: string;
  score: number;
  window: 'long_60d';
  windowLabel: string;
  validSampleCount: number;
  coreHitRate: number;
  reason: string;
  summary: string;
}

export interface MomentumDecisionRiskBanner {
  tone: 'warning';
  title: string;
  message: string;
}

export interface MomentumMainlineRadarItem {
  themeId: string;
  themeName: string;
  score: number;
  level: string;
  levelLabel: string;
  candidateCount?: number;
  top10Count?: number;
  limitUpCount?: number;
  brokenLimitCount?: number;
  hotRank?: number | null;
  netAmount?: number | null;
  netAmountRate?: number | null;
  boardRank?: number | null;
  pctChange?: number | null;
  upNum?: number | null;
  downNum?: number | null;
  leaderStock?: string | null;
  dataSources?: string[];
  sourceThemeNames?: string[];
  representatives?: Record<string, unknown>[];
  evidence?: Record<string, unknown>[];
  isDegraded?: boolean;
  degradedReasons?: string[];
  summary?: string;
}

export interface MomentumShortTermSentiment {
  level: string;
  label: string;
  score: number;
  summary: string;
  modules?: Record<string, unknown>[];
  confidence?: 'high' | 'medium' | 'low' | string;
  isDegraded?: boolean;
  degradedReasons?: string[];
}

export interface MomentumV13DataStatus {
  enabled: boolean;
  status: 'ok' | 'degraded' | 'failed' | 'skipped' | 'not_applicable' | string;
  reason: string;
  dataAsOf?: string | null;
  sourceStatus?: Record<string, string>;
  degradedReasons?: string[];
  mainlineCount?: number;
  shortTermSentimentLevel?: string | null;
}

export interface MomentumActionChecklistStep {
  phase: 'pre_open' | 'first_30m' | 'first_60m';
  phaseLabel: string;
  objective: string;
  focusItems: string[];
  tasks: string[];
  expectedOutcome: string;
}

export interface MomentumActionChecklist {
  enabled: boolean;
  mode: 'full' | 'simplified' | 'disabled';
  reason: string;
  steps: MomentumActionChecklistStep[];
}

export type MomentumStrategyHealthStatus =
  | 'healthy'
  | 'partial_healthy'
  | 'recovery_mode'
  | 'disabled';

export type MomentumStrategyHealthWindowStatus = 'healthy' | 'recovering' | 'weak';

export interface MomentumStrategyHealthWindow {
  window: 'short_20d' | 'long_60d';
  windowLabel: string;
  status: MomentumStrategyHealthWindowStatus;
  statusLabel: string;
  score: number;
  threshold: number;
  sampleCount: number;
  successCount: number;
  successRate: number;
  avgProfitWindowPct: number;
  avgMaxDrawdownPct: number;
  avgSelectedCount: number;
  summary: string;
}

export interface MomentumStrategyHealthProgress {
  status: 'proxy' | 'queued' | 'running' | 'partial' | 'final' | 'failed';
  processedTradeDateCount: number;
  totalTradeDateCount: number;
  validSampleCount: number;
  targetSampleCount: number;
  progressPct: number;
  lastEvaluatedTradeDate?: string | null;
  updatedAt?: string | null;
}

export interface MomentumStrategyHealth {
  status: MomentumStrategyHealthStatus;
  label: string;
  reason: string;
  recommendationCap: 'full' | 'limited' | 'disabled';
  canFullRecommend: boolean;
  shortWindow: MomentumStrategyHealthWindow;
  longWindow: MomentumStrategyHealthWindow;
  blockers: string[];
  recoveryConditions: string[];
  dataSource?: 'historical' | 'proxy';
  isWarming?: boolean;
  validationStatus?: 'proxy' | 'partial' | 'final';
  progress?: MomentumStrategyHealthProgress;
}

export interface MomentumSecondaryDecision {
  profile: MomentumProfile;
  tradeDate: string;
  action: MomentumDecisionAction;
  marketEnvironment: MomentumDecisionMarketEnvironment;
  opportunityQuality: MomentumDecisionOpportunityQuality;
  historicalValidity: MomentumDecisionHistoricalValidity;
  strategyHealth: MomentumStrategyHealth;
  attackPermission: MomentumDecisionAttackPermission;
  themeConfidence: MomentumDecisionThemeConfidence;
  riskBanner?: MomentumDecisionRiskBanner | null;
  mainlineRadar?: MomentumMainlineRadarItem[];
  shortTermSentiment?: MomentumShortTermSentiment | null;
  v13DataStatus?: MomentumV13DataStatus | null;
  adaptiveGate?: MomentumAdaptiveGateContext | null;
  themes: MomentumDecisionTheme[];
  portfolio: MomentumDecisionPortfolioSlot[];
  candidateDiagnostics?: MomentumDecisionCandidateDiagnostic[];
  excludedCandidates: MomentumDecisionExcludedCandidate[];
  evidence: MomentumDecisionEvidence;
  actionChecklist: MomentumActionChecklist;
}

export interface MomentumScreenerDecisionResponse {
  screening: MomentumScreenerResponse;
  decision: MomentumSecondaryDecision;
}

export interface MomentumScreeningRunResultResponse {
  runId: string;
  status: 'completed';
  screening: MomentumScreenerResponse;
  decision: MomentumSecondaryDecision;
}

export type MomentumIntradayStatus =
  | 'not_started'
  | 'watching'
  | 'buy_ready'
  | 'low_confidence'
  | 'do_not_buy'
  | 'stand_aside'
  | 'not_applicable';

export type MomentumIntradayItemStatus =
  | 'triggered'
  | 'watching'
  | 'do_not_chase'
  | 'observe_only'
  | 'data_unavailable';

export type MomentumIntradayConfidenceLevel = 'high' | 'medium' | 'low';

export type MomentumIntradayFinalRecommendation = 'buy' | 'main_only_consider' | 'watch' | 'do_not_buy';

export interface MomentumIntradayPortfolioItem {
  slot: MomentumDecisionSlot;
  slotLabel: string;
  tsCode: string;
  name: string;
  theme: string;
  role: string;
  status: MomentumIntradayItemStatus;
  statusLabel: string;
  reason: string;
  quoteAvailable: boolean;
  signalTriggered: boolean;
  doNotChase: boolean;
  currentPrice?: number | null;
  changePercent?: number | null;
  openPrice?: number | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  priceVsOpenPct?: number | null;
  priceVsEntryHighPct?: number | null;
  missingConditions: string[];
  updateTime?: string | null;
}

export interface MomentumIntradaySignal {
  marketPhase: string;
  marketPhaseLabel: string;
  confidenceLevel: MomentumIntradayConfidenceLevel;
  confidenceLabel: string;
  canEmitBuySignal: boolean;
  status: MomentumIntradayStatus;
  statusLabel: string;
  reason: string;
  watchItems: string[];
  finalRecommendation: MomentumIntradayFinalRecommendation;
  finalRecommendationLabel: string;
  closingNote: string;
  updatedAt: string;
  focusOrder: string[];
  portfolioItems: MomentumIntradayPortfolioItem[];
}

export interface MomentumSnapshotAssistItem {
  slot?: MomentumDecisionSlot | string | null;
  slotLabel?: string | null;
  tsCode?: string | null;
  name?: string | null;
  status: 'near_watch_zone' | 'overextended' | 'quote_missing' | 'observe_only' | 'neutral' | string;
  statusLabel: string;
  currentPrice?: number | null;
  changePercent?: number | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  priceVsEntryHighPct?: number | null;
  manualCheck: string;
}

export interface MomentumSnapshotAssist {
  label: string;
  confidence: 'low' | string;
  dataAsOf?: string | null;
  isDegraded?: boolean;
  degradedReasons?: string[];
  summary: string;
  items: MomentumSnapshotAssistItem[];
}

export interface MomentumScreenerIntradayResponse extends MomentumScreenerDecisionResponse {
  intradaySignal: MomentumIntradaySignal;
  snapshotAssist?: MomentumSnapshotAssist | null;
}
