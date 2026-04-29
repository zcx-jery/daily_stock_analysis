import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, Flame, ListChecks, Radar, RefreshCw, ShieldAlert, Sparkles, Target, TrendingUp } from 'lucide-react';
import { momentumScreenerApi } from '../api/momentumScreener';
import { systemConfigApi } from '../api/systemConfig';
import ScreenerAiDrawer from '../components/screener/ScreenerAiDrawer';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Drawer, EmptyState, Input } from '../components/common';
import type {
  MomentumActionLevel,
  MomentumBuyPointStatus,
  MomentumDecisionCandidateDiagnostic,
  MomentumDecisionExcludedCandidate,
  MomentumDecisionPortfolioSlot,
  MomentumDecisionReasonItem,
  MomentumDecisionTheme,
  MomentumIntradayPortfolioItem,
  MomentumIntradaySignal,
  MomentumMainlineRadarItem,
  MomentumProfile,
  MomentumScreeningRunResponse,
  MomentumSecondaryDecision,
  MomentumSnapshotAssist,
  MomentumScreenerRequest,
  MomentumScreenerResponse,
  MomentumScreenerResult,
} from '../types/momentumScreener';
import type { MomentumScreenerAiReviewTarget } from '../types/momentumScreenerAi';
import { useMomentumScreenerAiStore } from '../stores/momentumScreenerAiStore';

type FormState = {
  tradeDate: string;
};

type SelectedResultState = {
  source: MomentumProfile;
  item: MomentumScreenerResult;
};

const STORAGE_KEY = 'dsa.momentum-screener.page-state';
const OFFICIAL_TOP_N = 30;
const SCREENING_RUN_POLL_INTERVAL_MS = 1500;

const OFFICIAL_SCORE_LABEL = '官方总分';

const DEFAULT_FORM: FormState = {
  tradeDate: '',
};

function buildScreeningPayload(nextForm: FormState): MomentumScreenerRequest {
  return {
    profile: 'standard',
    topN: OFFICIAL_TOP_N,
    tradeDate: nextForm.tradeDate || undefined,
  };
}

type PersistedState = {
  form: FormState;
  hasPersisted: boolean;
};

const dimensionLabelMap: Record<string, string> = {
  strength_confirmation: '强势确认',
  volume_price_structure: '量价结构',
  trend_position: '趋势位置',
  sector_resonance: '板块共振',
  capital_support: '资金承接',
  elasticity_activity: '弹性与股性',
  buyability: '买入可行性',
  volume_price_track: '量价双轨',
  trend_elasticity: '趋势位置与弹性',
};

const itemLabelMap: Record<string, string> = {
  pct_chg_strength: '涨幅强度',
  close_position: '收盘位置',
  limit_proximity: '涨停接近度',
  body_ratio: 'K线实体',
  volume_ratio: '量比',
  turnover_rate: '换手率',
  amount_rank: '成交额分位',
  volume_expand_5: '五日放量',
  ma_structure: '均线结构',
  breakout: '突破结构',
  strong_trend_5d: '五日强势',
  sector_rank: '板块强度',
  sector_breadth: '板块联动',
  sector_ladder: '板块梯队',
  sector_leader: '板块地位',
  main_inflow_abs: '主力净流入',
  main_inflow_ratio: '资金强度',
  top_list: '龙虎榜',
  price_flow_alignment: '价资一致',
  circ_mv: '流通市值',
  historical_activity: '历史股性',
  recognition: '辨识度',
  limit_strength: '近涨停强度',
  gap_open_strength: '跳空高开',
  close_status: '收盘地位',
  acceleration_confirmation: '加速确认',
  amplitude_space: '日内振幅',
  amount_golden_zone: '成交额黄金区',
  turnover_golden_zone: '换手黄金区',
  consensus_limit: '缩量一致',
  healthy_turnover: '健康换手',
};

function normalizeMetricLookupKey(key: string): string {
  return key.trim().replace(/[^a-zA-Z0-9]+/g, '').toLowerCase();
}

function buildMetricLabelLookup(labelMap: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(labelMap).map(([key, label]) => [normalizeMetricLookupKey(key), label]),
  );
}

const dimensionLabelLookup = buildMetricLabelLookup(dimensionLabelMap);
const itemLabelLookup = buildMetricLabelLookup(itemLabelMap);

const riskTagLabelMap: Record<string, string> = {
  upper_shadow: '长上影/冲高回落',
  blowoff_volume: '爆量滞涨',
  late_session_weakness: '尾盘走弱',
  high_acceleration: '高位连续加速',
  price_flow_divergence: '价资背离',
  sector_fade: '板块退潮',
  top_list_distribution: '龙虎榜偏兑现',
  'risk-alert': '风险提示',
  'risk-drift': '风险漂移',
};

const gateModuleLabelMap: Record<string, string> = {
  index_trend: '指数趋势',
  profitability: '赚钱效应',
  sentiment: '市场情绪',
  theme_breadth: '主线扩散',
  theme_clarity: '主线清晰度',
  portfolio_quality: '组合质量',
  buy_point_clarity: '买点清晰度',
  role_structure: '角色结构',
  risk_control: '风险可控度',
};

function loadPersistedState(): PersistedState {
  if (typeof window === 'undefined') {
    return { form: DEFAULT_FORM, hasPersisted: false };
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { form: DEFAULT_FORM, hasPersisted: false };
    }

    const parsed = JSON.parse(raw) as Partial<{ form: Partial<FormState> }>;
    const parsedForm = parsed.form;
    return {
      form: { tradeDate: parsedForm?.tradeDate ?? DEFAULT_FORM.tradeDate },
      hasPersisted: true,
    };
  } catch {
    return { form: DEFAULT_FORM, hasPersisted: false };
  }
}

function buildFormFromSystemConfig(): FormState {
  return {
    tradeDate: DEFAULT_FORM.tradeDate,
  };
}

function persistState(form: FormState) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ form }));
}

function translateLeaderLevel(level: string): string {
  const normalized = level.trim().toLowerCase();
  if (normalized === 'leader' || normalized === '龙头' || normalized === '榫欏ご') return '龙头';
  if (normalized === 'front' || normalized === '前排' || normalized === '鍓嶆帓') return '前排';
  if (normalized === 'mid' || normalized === '中位' || normalized === '涓綅') return '中位';
  return '后排';
}

function translateRiskTag(tag: string): string {
  return riskTagLabelMap[tag] ?? tag;
}

function translateGateModuleKey(key: string): string {
  return gateModuleLabelMap[key] ?? key;
}

function translateDimensionKey(key: string): string {
  return dimensionLabelLookup[normalizeMetricLookupKey(key)] ?? key;
}

function translateItemKey(key: string): string {
  return itemLabelLookup[normalizeMetricLookupKey(key)] ?? key;
}

function leaderBadgeVariant(level: string): 'success' | 'warning' | 'default' {
  const translated = translateLeaderLevel(level);
  if (translated === '龙头') return 'success';
  if (translated === '前排') return 'warning';
  return 'default';
}

function scoreTone(score: number): string {
  if (score >= 85) return 'text-success';
  if (score >= 70) return 'text-cyan';
  if (score >= 55) return 'text-warning';
  return 'text-danger';
}

function actionLevelBadgeVariant(level: MomentumActionLevel): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (level === 'strong_go') return 'success';
  if (level === 'normal_go') return 'info';
  if (level === 'cautious_go') return 'warning';
  if (level === 'stand_aside') return 'danger';
  return 'default';
}

function gateLevelBadgeVariant(level: 'strong' | 'medium' | 'weak'): 'success' | 'warning' | 'danger' {
  if (level === 'strong') return 'success';
  if (level === 'medium') return 'warning';
  return 'danger';
}

function attackPermissionBadgeVariant(
  status: MomentumSecondaryDecision['attackPermission']['status'],
): 'success' | 'warning' | 'danger' {
  if (status === 'open') return 'success';
  if (status === 'recovering') return 'warning';
  return 'danger';
}

function themeConfidenceBadgeVariant(
  status: MomentumSecondaryDecision['themeConfidence']['status'],
): 'success' | 'warning' | 'danger' {
  if (status === 'credible') return 'success';
  if (status === 'recovering') return 'warning';
  return 'danger';
}

function v13DataStatusBadgeVariant(status?: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'ok') return 'success';
  if (status === 'degraded' || status === 'skipped' || status === 'not_applicable') return 'warning';
  if (status === 'failed') return 'danger';
  return 'default';
}

function shortTermSentimentBadgeVariant(level?: string): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (level === 'hot') return 'success';
  if (level === 'tradable') return 'info';
  if (level === 'divergent') return 'warning';
  if (level === 'ebb') return 'danger';
  return 'default';
}

function decisionSlotBadgeVariant(slot: MomentumDecisionPortfolioSlot['slot']): 'success' | 'info' | 'warning' {
  if (slot === 'main') return 'success';
  if (slot === 'secondary') return 'info';
  return 'warning';
}

function buyPointBadgeVariant(status: MomentumBuyPointStatus): 'success' | 'warning' | 'default' {
  if (status === 'clear') return 'success';
  if (status === 'waiting') return 'warning';
  return 'default';
}

function decisionActionBadgeVariant(
  action: MomentumDecisionPortfolioSlot['suggestedAction'],
): 'success' | 'warning' | 'default' {
  if (action === 'ready') return 'success';
  if (action === 'wait_for_trigger') return 'warning';
  return 'default';
}

function intradayStatusBadgeVariant(
  status: MomentumIntradaySignal['status'],
): 'success' | 'warning' | 'danger' | 'default' | 'info' {
  if (status === 'buy_ready') return 'success';
  if (status === 'watching' || status === 'not_started') return 'info';
  if (status === 'low_confidence') return 'warning';
  if (status === 'do_not_buy' || status === 'stand_aside') return 'danger';
  return 'default';
}

function resolveStrategyHealthValidationStatus(
  health: MomentumSecondaryDecision['strategyHealth'],
): 'proxy' | 'partial' | 'final' {
  if (health.validationStatus) {
    return health.validationStatus;
  }
  return health.dataSource === 'proxy' ? 'proxy' : 'final';
}

function shouldShowStrategyHealthRefresh(health: MomentumSecondaryDecision['strategyHealth']): boolean {
  return health.isWarming === true || resolveStrategyHealthValidationStatus(health) !== 'final';
}

function buildStrategyHealthDataSourceLabel(health: MomentumSecondaryDecision['strategyHealth']): string {
  const validationStatus = resolveStrategyHealthValidationStatus(health);
  if (validationStatus === 'partial') {
    return '历史验证 Partial';
  }
  if (validationStatus === 'proxy') {
    return health.isWarming ? '历史验证计算中' : '代理健康度';
  }
  return '历史验证 Final';
}

function buildStrategyHealthProgressSummary(health: MomentumSecondaryDecision['strategyHealth']): string | null {
  const progress = health.progress;
  if (!progress) {
    return null;
  }

  const processed =
    progress.totalTradeDateCount > 0
      ? `已处理 ${progress.processedTradeDateCount}/${progress.totalTradeDateCount} 个历史交易日`
      : null;
  const samples =
    progress.validSampleCount > 0
      ? `累计有效样本 ${progress.validSampleCount}/${progress.targetSampleCount}`
      : null;
  const lastTradeDate = progress.lastEvaluatedTradeDate ? `最近样本 ${progress.lastEvaluatedTradeDate}` : null;

  return [processed, samples, lastTradeDate].filter(Boolean).join('，') || null;
}

function screeningRunBadgeVariant(
  status: MomentumScreeningRunResponse['status'],
): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (status === 'completed') return 'success';
  if (status === 'running') return 'info';
  if (status === 'queued') return 'warning';
  if (status === 'failed') return 'danger';
  return 'default';
}

function screeningRunStatusLabel(status: MomentumScreeningRunResponse['status']): string {
  if (status === 'completed') return '已完成';
  if (status === 'running') return '运行中';
  if (status === 'queued') return '排队中';
  if (status === 'failed') return '失败';
  return '已取消';
}

function buildScreeningRunProgressSummary(run: MomentumScreeningRunResponse): string | null {
  const parts: string[] = [];
  if (run.progress.totalItemCount > 0) {
    parts.push(`已处理 ${run.progress.processedItemCount}/${run.progress.totalItemCount}`);
  }
  const cacheHitSummary = Object.entries(run.progress.cacheHits ?? {})
    .filter(([, value]) => Number(value) > 0)
    .map(([key, value]) => `${key} 命中 ${value}`)
    .slice(0, 2);
  if (cacheHitSummary.length > 0) {
    parts.push(cacheHitSummary.join('，'));
  }
  if (run.tradeDate) {
    parts.push(`交易日 ${run.tradeDate}`);
  }
  return parts.length > 0 ? parts.join('，') : null;
}

function formatDurationLabel(startedAt?: string | null, finishedAt?: string | null): string | null {
  if (!startedAt) {
    return null;
  }
  const started = new Date(startedAt);
  if (Number.isNaN(started.getTime())) {
    return null;
  }
  const finished = finishedAt ? new Date(finishedAt) : new Date();
  if (Number.isNaN(finished.getTime())) {
    return null;
  }
  const totalSeconds = Math.max(0, Math.floor((finished.getTime() - started.getTime()) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}小时${minutes}分钟`;
  }
  if (minutes > 0) {
    return `${minutes}分钟${seconds}秒`;
  }
  return `${seconds}秒`;
}

function buildScreeningRunStageHint(run: MomentumScreeningRunResponse): string | null {
  const stageKey = run.currentStageKey ?? '';
  const stageLabel = run.currentStageLabel ?? '';
  const isFullTruth = run.truthMode === 'full';
  const processedCount = run.progress.processedItemCount ?? 0;
  const totalCount = run.progress.totalItemCount ?? 0;

  if (run.status === 'queued') {
    return '前面还有真实性优先任务在执行，当前任务会在工作线程空出来后自动接管。';
  }
  if (run.status === 'cancelled') {
    return '任务已停止，当前页面保留了最后一次已知进度，方便你判断停在了哪里。';
  }
  if (run.status === 'failed') {
    return run.errorMessage ?? '任务执行失败，当前页面保留了失败前最后一次心跳与阶段信息。';
  }
  if (run.status === 'completed') {
    return run.resultAvailable
      ? '真实性优先任务已经全部完成，筛选结果和二次决策已落到下方视图。'
      : '任务已结束，但结果文件还没准备好，刷新任务状态后会自动继续加载。';
  }
  if (stageKey === 'preparing') {
    return '正在校验交易日、统一参数，并准备官方候选池入口。';
  }
  if (stageKey === 'trade_snapshot') {
    return '正在加载当日行情、涨停和成交快照，为候选池与题材判断准备底稿。';
  }
  if (stageKey === 'sector_context' || stageKey === 'sector_context_load') {
    return '正在整理板块、题材与资金映射，这一步会决定“资金主攻题材”的解释底稿。';
  }
  if (stageKey === 'prepare_candidate_scoring_rows') {
    return '正在逐股加载历史、结构与资金特征，为全候选正式评分准备统一画像。';
  }
  if (stageKey === 'provisional_candidate_scoring') {
    return '正在执行第一遍候选评分，先用基础信号给全候选建立初步排序。';
  }
  if (stageKey === 'scoring') {
    return '候选池和题材画像已经齐了，后台正在执行正式评分、排序和结果收口。';
  }
  if (stageKey === 'secondary_decision') {
    return '排序已经完成，当前在生成主线、默认组合、买点与风险解释。';
  }
  if (stageKey === 'result_persist') {
    return '结果已经算完，正在把筛选结果、诊断和二次决策写回任务记录。';
  }
  if (stageKey === 'cancel_requested') {
    return '取消请求已经提交；当前子步骤收尾后，任务会自动进入已取消状态。';
  }
  if (stageKey === 'candidate_pool') {
    if (isFullTruth && stageLabel.includes('V1.3')) {
      if (totalCount > 0 && processedCount >= totalCount && run.progress.progressPct < 100) {
        return '候选样本数量已经收齐，但后台还在把 V1.3 题材成分、资金快照和正式评分合并进结果，所以会出现“385/385 但还没结束”的状态。';
      }
      return '正在构建候选池，并补齐 Full Truth 所需的 V1.3 真实题材画像、资金快照和成分映射。';
    }
    return '正在按官方统一入口构建候选池，并补齐当日基础快照。';
  }
  if (stageKey === 'v13_context' || stageLabel.includes('V1.3')) {
    return isFullTruth
      ? '正在汇总 V1.3 真实题材画像；这一步会继续拉取真实成分、资金与主线映射。'
      : '正在补齐轻量 V1.3 上下文，用于给候选池和排序提供题材解释。';
  }
  if (stageKey === 'dc_members') {
    return '正在拉取东财题材成分映射，这通常是 Full Truth 画像里的固定大头。';
  }
  if (stageKey === 'cyq_perf') {
    return '正在补齐获利盘与成本分布摘要，用于判断筹码优势和上方压力。';
  }
  if (stageKey === 'cyq_chips') {
    return '正在逐股拉取筹码明细，这通常是当前真实性链路里最重的真实数据步骤之一。';
  }
  if (stageKey === 'official_candidate_scoring' || stageKey === 'official_result_finalize') {
    return 'V1.3 正式画像已经齐了，后台正在生成官方总分并收口最终排序。';
  }
  return null;
}

function formatRunTimestamp(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

function intradayConfidenceBadgeVariant(
  level: MomentumIntradaySignal['confidenceLevel'],
): 'success' | 'warning' | 'default' {
  if (level === 'high') return 'success';
  if (level === 'medium') return 'warning';
  return 'default';
}

function intradayItemStatusBadgeVariant(
  status: MomentumIntradayPortfolioItem['status'],
): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'triggered') return 'success';
  if (status === 'watching') return 'warning';
  if (status === 'do_not_chase') return 'danger';
  return 'default';
}

function snapshotAssistBadgeVariant(status: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'near_watch_zone') return 'success';
  if (status === 'overextended') return 'danger';
  if (status === 'quote_missing') return 'warning';
  return 'default';
}

function intradayFinalRecommendationBadgeVariant(
  recommendation: MomentumIntradaySignal['finalRecommendation'],
): 'success' | 'warning' | 'danger' {
  if (recommendation === 'buy') return 'success';
  if (recommendation === 'main_only_consider') return 'warning';
  if (recommendation === 'watch') return 'warning';
  return 'danger';
}

function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return '--';
  }
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

function formatCapitalAmount(value?: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return '--';
  }
  const abs = Math.abs(value);
  const prefix = value > 0 ? '+' : value < 0 ? '-' : '';
  if (abs >= 100_000_000) {
    return `${prefix}${(abs / 100_000_000).toFixed(2)}亿`;
  }
  if (abs >= 10_000) {
    return `${prefix}${(abs / 10_000).toFixed(1)}万`;
  }
  return `${prefix}${abs.toFixed(0)}`;
}

function formatOptionalScore(value?: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return '--';
  }
  return value.toFixed(1);
}

function formatSignedScoreDelta(value?: number | null): string {
  if (value == null || Number.isNaN(value) || Math.abs(value) < 0.05) {
    return '0.0';
  }
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
}

function decisionReasonBadgeVariant(
  item: MomentumDecisionReasonItem,
): 'success' | 'warning' | 'default' | 'info' {
  if (item.delta == null) {
    return 'warning';
  }
  if (item.delta > 0.05) {
    return 'success';
  }
  if (item.delta < -0.05) {
    return 'warning';
  }
  return 'default';
}

const DecisionReasonBadgeList: React.FC<{
  items: MomentumDecisionReasonItem[];
  emptyText: string;
}> = ({ items, emptyText }) => {
  if (items.length === 0) {
    return <p className="text-xs leading-5 text-secondary-text">{emptyText}</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((reason) => (
        <Badge key={`${reason.key}-${reason.label}`} variant={decisionReasonBadgeVariant(reason)}>
          {reason.label}
          {reason.delta != null ? ` ${formatSignedScoreDelta(reason.delta)}` : ''}
        </Badge>
      ))}
    </div>
  );
};

function sortResults(results: MomentumScreenerResult[]): MomentumScreenerResult[] {
  const sorted = [...results];
  sorted.sort(
    (a, b) =>
      b.officialScore - a.officialScore ||
      b.finalScore - a.finalScore ||
      a.rank - b.rank,
  );

  return sorted.map((item, index) => ({ ...item, rank: index + 1 }));
}

function buildCopyText(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  results: MomentumScreenerResult[],
): string {
  const header = [
    '强势筛选结果',
    `画像：${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    tradeDate ? `交易日：${tradeDate}` : null,
    `排序口径：${OFFICIAL_SCORE_LABEL}`,
  ].filter(Boolean);

  const lines = results.map((item) => {
    const parts = [
      `#${item.rank}`,
      `${item.name}(${item.tsCode})`,
      `\u6da8\u5e45 ${item.pctChg.toFixed(2)}%`,
      `${OFFICIAL_SCORE_LABEL} ${item.officialScore.toFixed(1)}`,
      `\u5ef6\u7eed\u5206 ${item.continuationScore.toFixed(1)}`,
      `\u5f39\u6027\u5206 ${item.extensionScore.toFixed(1)}`,
      `\u98ce\u9669\u5206 ${item.riskScore.toFixed(1)}`,
    ];

    if (item.buyabilityScore != null) {
      parts.push(`\u53ef\u4e70\u5206 ${item.buyabilityScore.toFixed(1)}`);
    }
    if (item.opportunityTag) {
      parts.push(`机会 ${item.opportunityTag}`);
    }
    if (item.entryRangeLow != null && item.entryRangeHigh != null) {
      parts.push(`区间 ${item.entryRangeLow.toFixed(2)}-${item.entryRangeHigh.toFixed(2)}`);
    }

    if (item.themes[0]) {
      parts.push(`\u677f\u5757 ${item.themes[0]}`);
    }

    parts.push(`\u5730\u4f4d ${translateLeaderLevel(item.leaderLevel)}`);

    if (item.topReasons.length > 0) {
      parts.push(`\u4eae\u70b9 ${item.topReasons.join('\u3001')}`);
    }

    if (item.riskTags.length > 0) {
      parts.push(`\u98ce\u9669 ${item.riskTags.map(translateRiskTag).join('\u3001')}`);
    }

    return parts.join(' | ');
  });

  return [...header, '', ...lines].join('\n');
}

function buildSingleResultText(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  item: MomentumScreenerResult,
): string {
  const lines = [
    '强势筛选个股明细',
    `画像：${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    tradeDate ? `交易日：${tradeDate}` : null,
    `排名：#${item.rank}`,
    `股票：${item.name} (${item.tsCode})`,
    `涨幅：${item.pctChg.toFixed(2)}%`,
    `官方总分：${item.officialScore.toFixed(1)}`,
    `延续分：${item.continuationScore.toFixed(1)}`,
    `弹性分：${item.extensionScore.toFixed(1)}`,
    `风险分：${item.riskScore.toFixed(1)}`,
    item.buyabilityScore != null ? `可买分：${item.buyabilityScore.toFixed(1)}` : null,
    item.opportunityTag ? `机会标签：${item.opportunityTag}` : null,
    item.entryRangeLow != null && item.entryRangeHigh != null
      ? `建议区间：${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}`
      : null,
    `基础总分：${item.finalScore.toFixed(1)}`,
    `板块：${item.themes[0] ?? '--'}`,
    `地位：${translateLeaderLevel(item.leaderLevel)}`,
    `亮点：${item.topReasons.length > 0 ? item.topReasons.join('、') : '--'}`,
    `风险：${item.riskTags.length > 0 ? item.riskTags.map(translateRiskTag).join('、') : '--'}`,
  ].filter(Boolean);

  return lines.join('\n');
}

function buildSingleResultMarkdown(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  item: MomentumScreenerResult,
): string {
  const lines: string[] = [
    `# #${item.rank} ${item.name} (${item.tsCode})`,
    '',
    `- 画像：${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    `- 交易日：${tradeDate ?? '--'}`,
    `- 涨幅：${item.pctChg.toFixed(2)}%`,
    `- 官方总分：${item.officialScore.toFixed(1)}`,
    `- 延续分：${item.continuationScore.toFixed(1)}`,
    `- 弹性分：${item.extensionScore.toFixed(1)}`,
    `- 风险分：${item.riskScore.toFixed(1)}`,
    `- 可买分：${item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'}`,
    `- 机会标签：${item.opportunityTag ?? '--'}`,
    `- 建议区间：${item.entryRangeLow != null && item.entryRangeHigh != null ? `${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}` : '--'}`,
    `- 基础总分：${item.finalScore.toFixed(1)}`,
    `- 板块：${item.themes[0] ?? '--'}`,
    `- 地位：${translateLeaderLevel(item.leaderLevel)}`,
    '',
    '## 亮点',
    '',
    ...(item.topReasons.length > 0 ? item.topReasons.map((reason) => `- ${reason}`) : ['- --']),
    '',
    '## 风险',
    '',
    ...(item.riskTags.length > 0 ? item.riskTags.map((tag) => `- ${translateRiskTag(tag)}`) : ['- --']),
  ];

  return lines.join('\n');
}

function buildMarkdownText(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  results: MomentumScreenerResult[],
): string {
  const lines: string[] = [
    '# 强势筛选结果',
    '',
    `- 画像：${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    `- 交易日：${tradeDate ?? '--'}`,
    `- 排序口径：${OFFICIAL_SCORE_LABEL}`,
    `- 结果数量：${results.length}`,
    '',
    '| 排名 | 股票 | 涨幅 | 官方总分 | 延续分 | 弹性分 | 风险分 | 可买分 | 板块 | 地位 |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |',
  ];

  for (const item of results) {
    lines.push(
      `| ${item.rank} | ${item.name} (${item.tsCode}) | ${item.pctChg.toFixed(2)}% | ${item.officialScore.toFixed(1)} | ${item.continuationScore.toFixed(1)} | ${item.extensionScore.toFixed(1)} | ${item.riskScore.toFixed(1)} | ${item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'} | ${item.themes[0] ?? '--'} | ${translateLeaderLevel(item.leaderLevel)} |`,
    );
  }

  lines.push('');
  lines.push('## 亮点与风险');
  lines.push('');

  for (const item of results) {
    lines.push(`### #${item.rank} ${item.name} (${item.tsCode})`);
    lines.push('');
    lines.push(`- 亮点：${item.topReasons.length > 0 ? item.topReasons.join('、') : '--'}`);
    lines.push(`- 风险：${item.riskTags.length > 0 ? item.riskTags.map(translateRiskTag).join('、') : '--'}`);
    lines.push('');
  }

  return lines.join('\n');
}

function escapeCsvField(value: string): string {
  const normalized = value.replace(/"/g, '""');
  return /[",\n]/.test(normalized) ? `"${normalized}"` : normalized;
}

function formatEntryRange(item: MomentumScreenerResult): string {
  if (item.entryRangeLow == null || item.entryRangeHigh == null) {
    return '';
  }
  return `${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}`;
}

function buildCsvText(results: MomentumScreenerResult[]): string {
  const header = [
    'rank',
    'name',
    'ts_code',
    'pct_chg',
    'official_score',
    'final_score',
    'continuation_score',
    'extension_score',
    'risk_score',
    'buyability_score',
    'opportunity_tag',
    'entry_range_low',
    'entry_range_high',
    'theme',
    'leader_level',
    'top_reasons',
    'risk_tags',
  ];

  const rows = results.map((item) => [
    String(item.rank),
    item.name,
    item.tsCode,
    item.pctChg.toFixed(2),
    item.officialScore.toFixed(1),
    item.finalScore.toFixed(1),
    item.continuationScore.toFixed(1),
    item.extensionScore.toFixed(1),
    item.riskScore.toFixed(1),
    item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '',
    item.opportunityTag ?? '',
    item.entryRangeLow != null ? item.entryRangeLow.toFixed(2) : '',
    item.entryRangeHigh != null ? item.entryRangeHigh.toFixed(2) : '',
    item.themes[0] ?? '',
    translateLeaderLevel(item.leaderLevel),
    item.topReasons.join('、'),
    item.riskTags.map(translateRiskTag).join('、'),
  ]);

  return [header, ...rows].map((row) => row.map(escapeCsvField).join(',')).join('\n');
}

function downloadTextFile(content: string, fileName: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

const SummaryCard: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  subtext?: string;
}> = ({ icon: Icon, label, value, subtext }) => (
  <Card className="rounded-2xl border-border/60 bg-card/60">
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-xs text-secondary-text">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
        {subtext ? <p className="mt-1 text-xs text-secondary-text">{subtext}</p> : null}
      </div>
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-hover/60 text-cyan">
        <Icon className="h-5 w-5" />
      </div>
    </div>
  </Card>
);

const AggressiveSupplementPanel: React.FC<{
  officialActionLevel: MomentumActionLevel | null;
  tradeDate?: string;
  loading: boolean;
  error: ParsedApiError | null;
  items: MomentumScreenerResult[];
  onReview: (item: MomentumScreenerResult) => void;
  onOpenDetail: (item: MomentumScreenerResult) => void;
}> = ({ officialActionLevel, tradeDate, loading, error, items, onReview, onOpenDetail }) => {
  const isExecutionBlocked =
    officialActionLevel === 'observe_only' || officialActionLevel === 'stand_aside';

  return (
    <Card data-testid="momentum-aggressive-supplement" className="rounded-3xl border-border/60 bg-card/55">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">Aggressive 进攻补充视图</p>
            <Badge variant="warning">补充视图</Badge>
            <Badge variant="default">不推翻 Standard 总闸门</Badge>
            {tradeDate ? <Badge variant="default">{tradeDate}</Badge> : null}
          </div>
          <p className="mt-2 text-xs leading-6 text-secondary-text">
            这里只补充更有弹性、可参与性更强的候选，不单独输出新的官方组合。真正的出手级别、默认组合和盘中权限，仍以 Standard 主引擎为准。
          </p>
        </div>
      </div>

      {error ? <ApiErrorAlert error={error} className="mt-4" onDismiss={() => undefined} /> : null}

      {loading ? (
        <div className="pt-4">
          <div className="rounded-2xl border border-border/50 bg-hover/10 px-4 py-5 text-sm text-secondary-text">
            Aggressive 补充视图加载中，先展示 Standard 官方主结论。
          </div>
        </div>
      ) : items.length === 0 ? (
        <div className="pt-4">
          <EmptyState
            title="暂无 Aggressive 补充结果"
            description="当前没有额外的进攻型补充标的，先以 Standard 官方主结论为主。"
          />
        </div>
      ) : (
        <details className="group pt-4">
          <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 rounded-2xl border border-warning/25 bg-warning/10 px-4 py-3 text-sm text-secondary-text transition-colors hover:bg-warning/15">
            <span>
              发现 {items.length} 只额外进攻补充标的，默认折叠；展开后仅用于观察，不纳入官方组合。
            </span>
            <Badge variant="warning">展开查看</Badge>
          </summary>
          <div className="mt-4 space-y-4">
          <div
            className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${
              isExecutionBlocked
                ? 'border-amber-500/25 bg-amber-500/10 text-secondary-text'
                : 'border-border/50 bg-hover/10 text-secondary-text'
            }`}
          >
            {isExecutionBlocked
              ? '当前 Standard 官方结论还未开放执行，这里的 Aggressive 结果只保留进攻观察价值，不构成翻盘信号。'
              : '当前官方总闸门允许继续跟踪机会，以下标的用于补充观察更高弹性位置，但仍需服从 Standard 的主仓 / 次仓顺序和纪律。'}
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            {items.map((item) => (
              <div key={item.tsCode} className="rounded-2xl border border-border/50 bg-card/50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="warning">进攻补充 #{item.rank}</Badge>
                      <Badge variant={leaderBadgeVariant(item.leaderLevel)}>
                        {translateLeaderLevel(item.leaderLevel)}
                      </Badge>
                    </div>
                    <p className="mt-3 text-sm font-semibold text-foreground">{item.name}</p>
                    <p className="mt-1 text-xs text-secondary-text">
                      {item.tsCode} · {item.marketSegmentLabel} · {item.themes[0] ?? '未标记题材'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={`text-lg font-semibold ${scoreTone(item.officialScore)}`}>
                      {item.officialScore.toFixed(1)}
                    </p>
                    <p className="mt-1 text-xs text-secondary-text">补充总分</p>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
                    <p className="text-xs text-secondary-text">可买分</p>
                    <p className="mt-1 text-sm font-medium text-foreground">
                      {item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'}
                    </p>
                  </div>
                  <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
                    <p className="text-xs text-secondary-text">风险分</p>
                    <p className="mt-1 text-sm font-medium text-foreground">{item.riskScore.toFixed(1)}</p>
                  </div>
                  <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
                    <p className="text-xs text-secondary-text">建议区间</p>
                    <p className="mt-1 text-sm font-medium text-foreground">
                      {formatEntryRange(item) || '--'}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {item.opportunityTag ? <Badge variant="warning">{item.opportunityTag}</Badge> : null}
                  {item.topReasons.slice(0, 2).map((reason) => (
                    <Badge key={reason} variant="success">
                      {reason}
                    </Badge>
                  ))}
                </div>

                <p className="mt-4 text-sm leading-6 text-secondary-text">
                  {isExecutionBlocked
                    ? '当前只保留进攻观察价值；如果价格明显偏离区间或总闸门继续收紧，不建议据此执行。'
                    : '适合作为进攻补充对象继续跟踪，重点看承接、区间确认和次日触发效率，不单独替代 Standard 官方排序。'}
                </p>

                <div className="mt-4 flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => onReview(item)}>
                    <Sparkles className="h-4 w-4" />
                    AI 点评
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onOpenDetail(item)}>
                    查看详情
                  </Button>
                </div>
              </div>
            ))}
          </div>
          </div>
        </details>
      )}
    </Card>
  );
};

const DecisionThemeCard: React.FC<{ theme: MomentumDecisionTheme }> = ({ theme }) => (
  <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <p className="text-sm font-semibold text-foreground">{theme.name}</p>
        <p className="mt-1 text-xs text-secondary-text">{theme.summary}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="info">{theme.strengthLabel}</Badge>
        <Badge variant="default">{theme.score.toFixed(1)}</Badge>
        {theme.v13MainlineScore != null ? (
          <Badge variant="success">题材强度 {theme.v13MainlineScore.toFixed(1)}</Badge>
        ) : null}
      </div>
    </div>
    {theme.v13Summary ? (
      <p className="mt-3 text-xs leading-5 text-secondary-text">{theme.v13Summary}</p>
    ) : null}
    <div className="mt-4 flex flex-wrap gap-2 text-xs text-secondary-text">
      <Badge variant="default">候选 {theme.candidateCount}</Badge>
      <Badge variant="success">清晰 {theme.clearBuyPointCount}</Badge>
      <Badge variant="warning">龙头 {theme.leaderCount}</Badge>
    </div>
    <div className="mt-4 space-y-2">
      {theme.representatives.map((item) => (
        <div
          key={item.tsCode}
          className="flex items-center justify-between gap-3 rounded-xl border border-border/40 bg-hover/20 px-3 py-2"
        >
          <div>
            <p className="text-sm font-medium text-foreground">
              #{item.rank} {item.name}
            </p>
            <p className="mt-1 text-xs text-secondary-text">
              {item.tsCode} · {item.role}
            </p>
          </div>
          <div className="text-right">
            <Badge variant={buyPointBadgeVariant(item.buyPointLabel === '买点清晰' ? 'clear' : item.buyPointLabel === '等待触发' ? 'waiting' : 'unclear')}>
              {item.buyPointLabel}
            </Badge>
            <p className="mt-1 text-xs text-secondary-text">
              官方总分 {formatOptionalScore(item.officialScore)}
            </p>
          </div>
        </div>
      ))}
    </div>
  </div>
);

const PortfolioDecisionCard: React.FC<{ item: MomentumDecisionPortfolioSlot }> = ({ item }) => (
  <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={decisionSlotBadgeVariant(item.slot)}>{item.slotLabel}</Badge>
          <Badge variant="default">现排 #{item.rank}</Badge>
          <Badge variant="default">基准 #{item.baseRank}</Badge>
          <Badge variant={buyPointBadgeVariant(item.buyPointStatus)}>{item.buyPointLabel}</Badge>
        </div>
        <p className="mt-3 text-base font-semibold text-foreground">{item.name}</p>
        <p className="mt-1 text-sm text-secondary-text">
          {item.tsCode} · {item.theme} · {item.role}
        </p>
      </div>
      <div className="text-right">
        <p className={`text-lg font-semibold ${scoreTone(item.score)}`}>{item.score.toFixed(1)}</p>
        <p className="mt-1 text-xs text-secondary-text">槽位匹配度</p>
      </div>
    </div>

    <div className="mt-4 flex flex-wrap gap-2">
      <Badge variant={decisionActionBadgeVariant(item.suggestedAction)}>{item.suggestedActionLabel}</Badge>
      <Badge variant="info">官方总分 {item.officialScore.toFixed(1)}</Badge>
      <Badge variant="default">基准总分 {item.baseRankScore.toFixed(1)}</Badge>
      <Badge variant={item.decisionAdjustment != null && item.decisionAdjustment >= 0 ? 'success' : 'warning'}>
        收口修正 {formatSignedScoreDelta(item.decisionAdjustment)}
      </Badge>
      <Badge variant="warning">风险分 {item.riskScore.toFixed(1)}</Badge>
      {item.v13MainlineScore != null ? (
        <Badge variant="success">题材强度 {item.v13MainlineScore.toFixed(1)}</Badge>
      ) : null}
      {item.v13ShadowScore != null ? (
        <Badge variant="info">V1.3影子分 {item.v13ShadowScore.toFixed(1)}</Badge>
      ) : null}
      {item.opportunityTag ? <Badge variant="warning">{item.opportunityTag}</Badge> : null}
    </div>

    {item.v13ShadowScore != null ? (
      <p className="mt-3 text-xs leading-5 text-secondary-text">
        题材 {item.v13ThemeStrengthScore?.toFixed(1) ?? '-'} / 资金 {item.v13FundSupportScore?.toFixed(1) ?? '-'} /
        涨停结构 {item.v13LimitStructureScore?.toFixed(1) ?? '-'} / 买点 {item.v13BuyabilityScore?.toFixed(1) ?? '-'} /
        筹码风险 {item.v13ChipRiskScore?.toFixed(1) ?? '-'}
      </p>
    ) : null}

    <div className="mt-4 space-y-3 text-sm leading-6 text-secondary-text">
      <p>
        <span className="font-medium text-foreground">主因：</span>
        {item.primaryReason}
      </p>
      <p>
        <span className="font-medium text-foreground">仓位理由：</span>
        {item.roleReason}
      </p>
      {item.decisionAdjustmentReason ? (
        <p>
          <span className="font-medium text-foreground">收口说明：</span>
          {item.decisionAdjustmentReason}
        </p>
      ) : null}
      <div>
        <p className="font-medium text-foreground">轻修正</p>
        <div className="mt-2">
          <DecisionReasonBadgeList items={item.softAdjustments} emptyText="当前槽位没有额外轻修正，直接沿用官方顺序。" />
        </div>
      </div>
      <div>
        <p className="font-medium text-foreground">硬阻断检查</p>
        <div className="mt-2">
          <DecisionReasonBadgeList items={item.hardBlockers} emptyText="当前槽位未命中硬阻断。" />
        </div>
      </div>
      <p>
        <span className="font-medium text-foreground">执行提示：</span>
        {item.executionPlan}
      </p>
      {item.entryHint ? (
        <p>
          <span className="font-medium text-foreground">优先买入区：</span>
          {item.entryHint}
        </p>
      ) : null}
    </div>
  </div>
);

const ExcludedCandidateList: React.FC<{ items: MomentumDecisionExcludedCandidate[] }> = ({ items }) => {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-border/50 bg-card/50 p-4 text-sm text-secondary-text">
        当前筛选结果已经全部纳入重点观察范围，暂无额外落选说明。
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.tsCode} className="rounded-2xl border border-border/50 bg-card/50 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">
                #{item.rank} {item.name}
              </p>
              <p className="mt-1 text-xs text-secondary-text">
                {item.tsCode} · {item.theme} · {item.role}
              </p>
            </div>
            <div className="text-right">
              <Badge variant="default">{item.officialScore.toFixed(1)}</Badge>
              <p className="mt-1 text-xs text-secondary-text">基准 #{item.baseRank}</p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="default">原因 {item.reason}</Badge>
            <Badge variant={item.decisionAdjustment != null && item.decisionAdjustment >= 0 ? 'success' : 'warning'}>
              收口修正 {formatSignedScoreDelta(item.decisionAdjustment)}
            </Badge>
            {item.hardBlockers.length > 0 ? (
              <Badge variant="warning">命中硬阻断 {item.hardBlockers.length} 项</Badge>
            ) : null}
          </div>
          <p className="mt-3 text-sm leading-6 text-secondary-text">
            <span className="font-medium text-foreground">主淘汰原因：</span>
            {item.reason}
          </p>
          {item.reasonDetail ? (
            <p className="mt-2 text-sm leading-6 text-secondary-text">
              <span className="font-medium text-foreground">展开说明：</span>
              {item.reasonDetail}
            </p>
          ) : null}
          {item.decisionAdjustmentReason ? (
            <p className="mt-2 text-sm leading-6 text-secondary-text">
              <span className="font-medium text-foreground">收口比较：</span>
              {item.decisionAdjustmentReason}
            </p>
          ) : null}
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-foreground">硬阻断</p>
              <div className="mt-2">
                <DecisionReasonBadgeList items={item.hardBlockers} emptyText="未命中硬阻断。" />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-foreground">轻修正</p>
              <div className="mt-2">
                <DecisionReasonBadgeList items={item.softAdjustments} emptyText="没有额外轻修正。" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

const GateLayerPanel: React.FC<{
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  layer:
    | MomentumSecondaryDecision['marketEnvironment']
    | MomentumSecondaryDecision['opportunityQuality'];
}> = ({ title, icon: Icon, layer }) => {
  const matrixLabel = 'matrixLabel' in layer ? layer.matrixLabel : null;

  return (
    <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-hover/30 text-cyan">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{title}</p>
            <Badge variant={gateLevelBadgeVariant(layer.level)}>{layer.label}</Badge>
            <Badge variant="default">{layer.score.toFixed(1)}</Badge>
            {matrixLabel ? <Badge variant="info">矩阵 {matrixLabel}</Badge> : null}
          </div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{layer.reason}</p>
        </div>
      </div>

      {'modules' in layer && layer.modules.length > 0 ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {layer.modules.map((module) => (
            <div key={module.key} className="rounded-2xl border border-border/40 bg-hover/10 p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-foreground">{translateGateModuleKey(module.key)}</p>
                <div className="flex items-center gap-2">
                  <Badge variant={gateLevelBadgeVariant(module.level)}>{module.label}</Badge>
                  <span className="text-xs text-secondary-text">{module.score.toFixed(1)}</span>
                </div>
              </div>
              <p className="mt-2 text-sm leading-6 text-secondary-text">{module.summary}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

const MAINLINE_RAW_CODE_PATTERN = /^\d{6}\.TI$/i;

function isMainlineRawCode(value?: string | null): boolean {
  return MAINLINE_RAW_CODE_PATTERN.test(String(value ?? '').trim());
}

function formatMainlineThemeDisplay(item: MomentumMainlineRadarItem): { name: string; rawCode: string | null } {
  const themeName = String(item.themeName ?? '').trim();
  const themeId = String(item.themeId ?? '').trim();
  const rawCode = [themeName, themeId].find(isMainlineRawCode) ?? null;

  if (themeName && !isMainlineRawCode(themeName)) {
    return { name: themeName, rawCode };
  }

  if (rawCode) {
    return { name: '题材待翻译', rawCode };
  }

  return { name: themeName || themeId || '未命名题材', rawCode: null };
}

function formatMainlineLevelLabel(label?: string | null): string {
  return String(label || '待确认').replace(/主线/g, '题材');
}

function formatMainlineSummary(item: MomentumMainlineRadarItem, displayName: string): string {
  const summary = item.summary || '等待更多题材强弱证据。';
  const rawValues = [item.themeName, item.themeId].filter((value): value is string => Boolean(value));
  return rawValues.reduce(
    (text, rawValue) => (isMainlineRawCode(rawValue) ? text.replaceAll(rawValue, displayName) : text),
    summary,
  ).replace(/主线/g, '题材');
}

const V13MainlineInsightPanel: React.FC<{ decision: MomentumSecondaryDecision }> = ({ decision }) => {
  const radarItems = decision.mainlineRadar ?? [];
  const sentiment = decision.shortTermSentiment;
  const dataStatus = decision.v13DataStatus;

  if (!dataStatus && radarItems.length === 0 && !sentiment) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Flame className="h-4 w-4 text-cyan" />
            <p className="text-sm font-semibold text-foreground">资金题材雷达</p>
            {dataStatus ? (
              <Badge variant={v13DataStatusBadgeVariant(dataStatus.status)}>
                {dataStatus.status === 'ok' ? '数据完整' : dataStatus.status}
              </Badge>
            ) : null}
            {sentiment ? (
              <Badge variant={shortTermSentimentBadgeVariant(sentiment.level)}>
                情绪 {sentiment.label}
              </Badge>
            ) : null}
          </div>
            <p className="mt-2 text-sm leading-6 text-secondary-text">
              这块优先用东财板块强度、板块资金流、东财成分和开盘啦题材解释资金去了哪些方向；它只增强排序理解，不替代总闸门和买点判断。
            </p>
        </div>
        {sentiment ? (
          <div className="rounded-2xl border border-border/40 bg-card/60 px-4 py-3 text-right">
            <p className={`text-lg font-semibold ${scoreTone(sentiment.score)}`}>{sentiment.score.toFixed(1)}</p>
            <p className="mt-1 text-xs text-secondary-text">短线情绪分</p>
          </div>
        ) : null}
      </div>

      {dataStatus?.reason ? (
        <p className="mt-3 text-sm leading-6 text-secondary-text">{dataStatus.reason}</p>
      ) : null}

      {sentiment?.summary ? (
        <div className="mt-4 rounded-2xl border border-border/40 bg-card/40 p-3">
          <p className="text-sm font-medium text-foreground">短线情绪结论</p>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{sentiment.summary}</p>
        </div>
      ) : null}

      {radarItems.length > 0 ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {radarItems.map((item) => {
            const themeDisplay = formatMainlineThemeDisplay(item);
            return (
            <div key={item.themeId || item.themeName} className="rounded-2xl border border-border/40 bg-card/45 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">{themeDisplay.name}</p>
                      {themeDisplay.rawCode ? <Badge variant="warning">待翻译代码</Badge> : null}
                      {item.boardRank != null ? <Badge variant="info">板块第 {item.boardRank}</Badge> : null}
                    </div>
                  <p className="mt-1 text-xs text-secondary-text">
                    {formatMainlineSummary(item, themeDisplay.name)}
                  </p>
                  {item.sourceThemeNames && item.sourceThemeNames.length > 0 ? (
                    <p className="mt-1 text-xs text-secondary-text">
                      覆盖子题材：{item.sourceThemeNames.slice(0, 5).join('、')}
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={gateLevelBadgeVariant(item.level === 'strong' ? 'strong' : item.level === 'medium' ? 'medium' : 'weak')}>
                    {formatMainlineLevelLabel(item.levelLabel)}
                  </Badge>
                  <Badge variant="default">强弱分 {item.score.toFixed(1)}</Badge>
                </div>
              </div>

              <div className="mt-4 grid gap-2 text-xs text-secondary-text sm:grid-cols-2">
                <p>候选股 {item.candidateCount ?? '--'} 只</p>
                <p>前 10 名 {item.top10Count ?? '--'} 只</p>
                  <p>涨停数 {item.limitUpCount ?? '--'}</p>
                  <p>炸板数 {item.brokenLimitCount ?? '--'}</p>
                  <p>热榜排名 {item.hotRank != null ? `第 ${item.hotRank}` : '--'}</p>
                  <p>主力净额 {formatCapitalAmount(item.netAmount)}</p>
                  <p>板块涨跌 {formatSignedPercent(item.pctChange)}</p>
                  <p>
                    上涨家数 {item.upNum ?? '--'} / 下跌家数 {item.downNum ?? '--'}
                  </p>
                  <p>领涨股 {item.leaderStock || '--'}</p>
                </div>

              {item.evidence && item.evidence.length > 0 ? (
                <div className="mt-4 space-y-2">
                  {item.evidence.slice(0, 3).map((evidence, index) => (
                    <p key={`${item.themeId}-${index}`} className="text-xs leading-5 text-secondary-text">
                      {String(evidence.label ?? evidence.key ?? '证据')}：{String(evidence.summary ?? '--')}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
            );
          })}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-border/40 bg-card/40 p-4 text-sm leading-6 text-secondary-text">
          当前还没有形成可展示的资金题材雷达，系统继续使用旧主线规则输出二次决策。
        </div>
      )}
    </div>
  );
};

const ActionChecklistPanel: React.FC<{
  checklist: MomentumSecondaryDecision['actionChecklist'];
}> = ({ checklist }) => (
  <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
    <div className="flex items-start gap-3">
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-hover/30 text-cyan">
        <ListChecks className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-foreground">明日行动清单</p>
          <Badge variant={checklist.mode === 'full' ? 'success' : checklist.mode === 'simplified' ? 'warning' : 'default'}>
            {checklist.mode === 'full' ? '完整版' : checklist.mode === 'simplified' ? '简化版' : '未启用'}
          </Badge>
        </div>
        <p className="mt-2 text-sm leading-6 text-secondary-text">{checklist.reason}</p>
      </div>
    </div>

    {!checklist.enabled ? (
      <div className="mt-4 rounded-2xl border border-border/40 bg-hover/10 p-4 text-sm leading-6 text-secondary-text">
        当前仅保留组合与观察信息，不生成分时行动步骤。
      </div>
    ) : (
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        {checklist.steps.map((step) => (
          <div key={step.phase} className="rounded-2xl border border-border/40 bg-hover/10 p-4">
            <Badge variant="info">{step.phaseLabel}</Badge>
            <p className="mt-3 text-sm font-medium text-foreground">{step.objective}</p>

            <div className="mt-4 space-y-3 text-sm leading-6 text-secondary-text">
              <div>
                <p className="font-medium text-foreground">优先关注</p>
                <div className="mt-2 space-y-2">
                  {step.focusItems.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>

              <div>
                <p className="font-medium text-foreground">建议动作</p>
                <div className="mt-2 space-y-2">
                  {step.tasks.map((task) => (
                    <p key={task}>{task}</p>
                  ))}
                </div>
              </div>

              <div>
                <p className="font-medium text-foreground">阶段收口</p>
                <p className="mt-2">{step.expectedOutcome}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

const DecisionConfidencePanel: React.FC<{
  decision: MomentumSecondaryDecision;
  onRefresh: () => void;
  refreshing: boolean;
  refreshDisabled: boolean;
}> = ({ decision, onRefresh, refreshing, refreshDisabled }) => {
  const { attackPermission, themeConfidence, strategyHealth: health } = decision;
  const validationStatus = resolveStrategyHealthValidationStatus(health);
  const showRefresh = shouldShowStrategyHealthRefresh(health);
  const healthDataSourceLabel = buildStrategyHealthDataSourceLabel(health);
  const progressSummary = buildStrategyHealthProgressSummary(health);

  return (
    <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-hover/30 text-cyan">
          <Radar className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">进攻许可与主线可信度</p>
            <Badge variant={attackPermissionBadgeVariant(attackPermission.status)}>
              20日 {attackPermission.label}
            </Badge>
            <Badge variant={themeConfidenceBadgeVariant(themeConfidence.status)}>
              60日 {themeConfidence.label}
            </Badge>
            <Badge variant={validationStatus === 'final' ? 'success' : 'warning'}>
              {healthDataSourceLabel}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">
            20日决定今天进攻上限，60日只提示主线结构可信度，不再直接压低今日动作级别。
          </p>
          {progressSummary ? (
            <p className="mt-2 text-xs leading-6 text-secondary-text">{progressSummary}</p>
          ) : null}
          {validationStatus === 'partial' ? (
            <p className="mt-2 text-xs leading-6 text-secondary-text">
              当前展示的是 partial 历史验证结果，后台仍会继续补齐更早样本，刷新后可切换到最新进度或 final 结果。
            </p>
          ) : null}
          {health.isWarming ? (
            <p className="mt-2 text-xs leading-6 text-secondary-text">
              首轮请求已切换为后台预热模式，页面先给你代理结果；等真实 20/60 日历史结果算完后，点击下方刷新即可看到正式结论。
            </p>
          ) : null}
        </div>
      </div>

      {decision.riskBanner ? (
        <div className="mt-4 rounded-2xl border border-warning/30 bg-warning/10 p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <div>
              <p className="text-sm font-medium text-foreground">{decision.riskBanner.title}</p>
              <p className="mt-1 text-sm leading-6 text-secondary-text">{decision.riskBanner.message}</p>
            </div>
          </div>
        </div>
      ) : null}

      {showRefresh ? (
        <div className="mt-4 rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">刷新 20/60 结果</p>
              <p className="mt-1 text-xs leading-6 text-secondary-text">
                {health.isWarming
                  ? '后台正在计算真实历史验证；点击后会直接等待正式结果返回，不再只看代理结果。'
                  : '当前仍不是 final 结果；点击后会优先尝试返回真实 20/60 历史验证结果。'}
              </p>
            </div>
            <Button
              data-testid="momentum-secondary-refresh-inline"
              variant="outline"
              size="sm"
              className="shrink-0"
              disabled={refreshDisabled}
              isLoading={refreshing}
              loadingText="等待真实结果..."
              onClick={onRefresh}
            >
              <RefreshCw className="h-4 w-4" />
              刷新 20/60 结果
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-border/40 bg-hover/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-foreground">20日进攻许可</p>
            <Badge variant={attackPermissionBadgeVariant(attackPermission.status)}>
              {attackPermission.statusLabel}
            </Badge>
          </div>
          <p className={`mt-3 text-lg font-semibold ${scoreTone(attackPermission.score)}`}>
            {attackPermission.score.toFixed(1)}
          </p>
          <div className="mt-3 grid gap-2 text-xs text-secondary-text sm:grid-cols-2">
            <p>有效样本 {attackPermission.validSampleCount}</p>
            <p>命中率 {attackPermission.hitRate.toFixed(1)}%</p>
            <p>利润窗口 {attackPermission.avgProfitWindowPct.toFixed(2)}%</p>
            <p>平均回撤 {attackPermission.avgMaxDrawdownPct.toFixed(2)}%</p>
          </div>
          <p className="mt-3 text-sm leading-6 text-secondary-text">{attackPermission.summary}</p>
        </div>

        <div className="rounded-2xl border border-border/40 bg-hover/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-foreground">60日主线可信度</p>
            <Badge variant={themeConfidenceBadgeVariant(themeConfidence.status)}>
              {themeConfidence.statusLabel}
            </Badge>
          </div>
          <p className={`mt-3 text-lg font-semibold ${scoreTone(themeConfidence.score)}`}>
            {themeConfidence.score.toFixed(1)}
          </p>
          <div className="mt-3 grid gap-2 text-xs text-secondary-text sm:grid-cols-2">
            <p>有效样本 {themeConfidence.validSampleCount}</p>
            <p>结构参考 {themeConfidence.coreHitRate.toFixed(1)}%</p>
          </div>
          <p className="mt-3 text-sm leading-6 text-secondary-text">{themeConfidence.summary}</p>
        </div>
      </div>

      {health.blockers.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-danger/30 bg-danger/5 p-4">
          <p className="text-sm font-medium text-foreground">当前阻断项</p>
          <div className="mt-2 space-y-2 text-sm leading-6 text-secondary-text">
            {health.blockers.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </div>
      ) : null}

      {health.recoveryConditions.length > 0 ? (
        <div className="mt-4 rounded-2xl border border-border/40 bg-hover/10 p-4">
          <p className="text-sm font-medium text-foreground">恢复条件</p>
          <div className="mt-2 space-y-2 text-sm leading-6 text-secondary-text">
            {health.recoveryConditions.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

type SecondaryDecisionPanelProps = {
  decision: MomentumSecondaryDecision | null;
  onRefresh: () => void;
  refreshing: boolean;
  refreshDisabled: boolean;
  onAiDecisionReview: () => void;
  onAiExcludedReview: () => void;
};

const SecondaryDecisionPanel: React.FC<SecondaryDecisionPanelProps> = ({
  decision,
  onRefresh,
  refreshing,
  refreshDisabled,
  onAiDecisionReview,
  onAiExcludedReview,
}) => (
  <div data-testid="momentum-secondary-decision">
    <Card className="rounded-3xl border-border/60 bg-card/55">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-4">
      <div>
        <p className="text-sm font-semibold text-foreground">二次决策</p>
        <p className="mt-1 text-xs text-secondary-text">
          从候选池继续收口成主线、默认组合、落选原因和执行提示，帮助判断今天到底该不该做。
        </p>
      </div>
      {decision ? (
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            data-testid="momentum-secondary-action-level"
            variant={actionLevelBadgeVariant(decision.action.level)}
            size="md"
          >
            {decision.action.label}
          </Badge>
          <Badge variant="default">{decision.tradeDate}</Badge>
          <Badge variant="info">Standard 官方主引擎</Badge>
          <Button
            data-testid="momentum-secondary-ai-review"
            variant="outline"
            size="sm"
            disabled={!decision}
            onClick={onAiDecisionReview}
          >
            <Sparkles className="h-4 w-4" />
            AI 综合建议
          </Button>
          <Button
            data-testid="momentum-secondary-refresh"
            variant={shouldShowStrategyHealthRefresh(decision.strategyHealth) ? 'outline' : 'ghost'}
            size="sm"
            className="shrink-0"
            disabled={refreshDisabled}
            isLoading={refreshing}
            loadingText="刷新中..."
            onClick={onRefresh}
          >
            <RefreshCw className="h-4 w-4" />
            刷新二次决策
          </Button>
        </div>
      ) : null}
    </div>

    {!decision ? (
      <div className="pt-4">
        <EmptyState
          title="暂无二次决策结果"
          description="先执行一次强势筛选，系统会自动生成今日出手级别、默认组合和落选原因。"
        />
      </div>
    ) : (
      <div className="grid gap-4 pt-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-border/50 bg-hover/20 p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-card/70 text-cyan">
                <Target className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">今日出手级别</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Badge variant={attackPermissionBadgeVariant(decision.attackPermission.status)}>
                    20日进攻许可：{decision.attackPermission.label}
                  </Badge>
                  <Badge variant={themeConfidenceBadgeVariant(decision.themeConfidence.status)}>
                    60日主线可信度：{decision.themeConfidence.label}
                  </Badge>
                </div>
                <p className="mt-2 text-base leading-7 text-foreground">{decision.action.reason}</p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <GateLayerPanel
              title="市场环境"
              icon={BarChart3}
              layer={decision.marketEnvironment}
            />
            <GateLayerPanel
              title="当日机会质量"
              icon={Target}
              layer={decision.opportunityQuality}
            />
          </div>

          <V13MainlineInsightPanel decision={decision} />

          <DecisionConfidencePanel
            decision={decision}
            onRefresh={onRefresh}
            refreshing={refreshing}
            refreshDisabled={refreshDisabled}
          />

          <ActionChecklistPanel checklist={decision.actionChecklist} />

          <div>
            <div className="mb-3 flex items-center gap-2">
              <ListChecks className="h-4 w-4 text-cyan" />
              <p className="text-sm font-semibold text-foreground">默认 1-3 票组合</p>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              {decision.portfolio.map((item) => (
                <PortfolioDecisionCard key={`${item.slot}-${item.tsCode}`} item={item} />
              ))}
            </div>
          </div>

          <div>
            <div className="mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-cyan" />
              <p className="text-sm font-semibold text-foreground">主线识别</p>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {decision.themes.map((theme) => (
                <DecisionThemeCard key={theme.name} theme={theme} />
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <div className="mb-3 flex items-center justify-between gap-3">
              <ShieldAlert className="h-4 w-4 text-cyan" />
              <p className="text-sm font-semibold text-foreground">落选说明</p>
              <Button
                data-testid="momentum-excluded-ai-review"
                variant="ghost"
                size="sm"
                disabled={!decision}
                onClick={onAiExcludedReview}
              >
                <Sparkles className="h-4 w-4" />
                AI 落选分析
              </Button>
            </div>
            <ExcludedCandidateList items={decision.excludedCandidates} />
          </div>

          <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
            <p className="text-sm font-semibold text-foreground">证据区</p>
            <div className="mt-4 space-y-4 text-sm leading-6 text-secondary-text">
              <div>
                <p className="font-medium text-foreground">主线验证</p>
                <div className="mt-2 space-y-2">
                  {decision.evidence.themeValidation.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>
              <div>
                <p className="font-medium text-foreground">今日结论</p>
                <div className="mt-2 space-y-2">
                  {decision.evidence.todayReasoning.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    )}
    </Card>
  </div>
);

const IntradaySignalItemCard: React.FC<{ item: MomentumIntradayPortfolioItem }> = ({ item }) => (
  <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={decisionSlotBadgeVariant(item.slot)}>{item.slotLabel}</Badge>
          <Badge variant={intradayItemStatusBadgeVariant(item.status)}>{item.statusLabel}</Badge>
          {item.doNotChase && item.status !== 'do_not_chase' ? <Badge variant="danger">不建议追入</Badge> : null}
        </div>
        <p className="mt-3 text-sm font-semibold text-foreground">{item.name}</p>
        <p className="mt-1 text-xs text-secondary-text">
          {item.tsCode} · {item.theme} · {item.role}
        </p>
      </div>
      <div className="text-right">
        <p className="text-lg font-semibold text-foreground">
          {item.currentPrice != null ? item.currentPrice.toFixed(2) : '--'}
        </p>
        <p className="mt-1 text-xs text-secondary-text">{formatSignedPercent(item.changePercent)}</p>
      </div>
    </div>

    <p className="mt-4 text-sm leading-6 text-secondary-text">{item.reason}</p>

    <div className="mt-4 grid gap-3 md:grid-cols-3">
      <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
        <p className="text-xs text-secondary-text">建议区间</p>
        <p className="mt-1 text-sm font-medium text-foreground">
          {item.entryRangeLow != null && item.entryRangeHigh != null
            ? `${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}`
            : '--'}
        </p>
      </div>
      <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
        <p className="text-xs text-secondary-text">相对开盘价</p>
        <p className="mt-1 text-sm font-medium text-foreground">{formatSignedPercent(item.priceVsOpenPct)}</p>
      </div>
      <div className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
        <p className="text-xs text-secondary-text">相对区间上沿</p>
        <p className="mt-1 text-sm font-medium text-foreground">{formatSignedPercent(item.priceVsEntryHighPct)}</p>
      </div>
    </div>

    {item.missingConditions.length > 0 ? (
      <div className="mt-4 rounded-2xl border border-border/40 bg-hover/10 p-3">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-secondary-text">还差哪些条件</p>
        <div className="mt-2 space-y-2 text-sm leading-6 text-secondary-text">
          {item.missingConditions.map((condition) => (
            <p key={condition}>{condition}</p>
          ))}
        </div>
      </div>
    ) : null}
  </div>
);

const SnapshotAssistPanel: React.FC<{ snapshotAssist: MomentumSnapshotAssist | null }> = ({ snapshotAssist }) => {
  if (!snapshotAssist) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Radar className="h-4 w-4 text-cyan" />
            <p className="text-sm font-semibold text-foreground">{snapshotAssist.label}</p>
            <Badge variant="warning">低置信度</Badge>
            {snapshotAssist.isDegraded ? <Badge variant="warning">数据降级</Badge> : null}
          </div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{snapshotAssist.summary}</p>
          {snapshotAssist.dataAsOf ? (
            <p className="mt-2 text-xs text-secondary-text">
              数据时间：{new Date(snapshotAssist.dataAsOf).toLocaleString('zh-CN', { hour12: false })}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {snapshotAssist.items.map((item) => (
          <div key={`${item.slot}-${item.tsCode}`} className="rounded-2xl border border-border/40 bg-card/45 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-foreground">{item.name ?? '--'}</p>
                <p className="mt-1 text-xs text-secondary-text">
                  {item.slotLabel ?? '--'} · {item.tsCode ?? '--'}
                </p>
              </div>
              <Badge variant={snapshotAssistBadgeVariant(item.status)}>{item.statusLabel}</Badge>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-secondary-text">
              <p>现价 {item.currentPrice != null ? item.currentPrice.toFixed(2) : '--'}</p>
              <p>涨跌 {formatSignedPercent(item.changePercent)}</p>
              <p>
                观察区{' '}
                {item.entryRangeLow != null && item.entryRangeHigh != null
                  ? `${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}`
                  : '--'}
              </p>
              <p>相对区间上沿 {formatSignedPercent(item.priceVsEntryHighPct)}</p>
            </div>
            <p className="mt-3 text-xs leading-5 text-secondary-text">{item.manualCheck}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

type IntradaySignalPanelProps = {
  decision: MomentumSecondaryDecision | null;
  intradaySignal: MomentumIntradaySignal | null;
  snapshotAssist: MomentumSnapshotAssist | null;
  loading: boolean;
  error: ParsedApiError | null;
  onRefresh: () => void;
  onDismissError: () => void;
  onAiReview: () => void;
};

const IntradaySignalPanel: React.FC<IntradaySignalPanelProps> = ({
  decision,
  intradaySignal,
  snapshotAssist,
  loading,
  error,
  onRefresh,
  onDismissError,
  onAiReview,
}) => (
  <div data-testid="momentum-intraday-signal">
    <Card className="rounded-3xl border-border/60 bg-card/55">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-4">
        <div>
          <p className="text-sm font-semibold text-foreground">盘中信号</p>
          <p className="mt-1 text-xs text-secondary-text">
            固定沿用昨晚的主仓 / 次仓 / 观察仓顺序，只补充盘中是否触发、是否偏离过大，以及 60 分钟内的买 / 不买收口。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {intradaySignal ? (
            <>
              <Badge variant={intradayStatusBadgeVariant(intradaySignal.status)}>
                {intradaySignal.statusLabel}
              </Badge>
              <Badge variant={intradayConfidenceBadgeVariant(intradaySignal.confidenceLevel)}>
                {intradaySignal.confidenceLabel}
              </Badge>
              <Badge variant={intradayFinalRecommendationBadgeVariant(intradaySignal.finalRecommendation)}>
                {intradaySignal.finalRecommendationLabel}
              </Badge>
            </>
          ) : null}
          <Button
            data-testid="momentum-intraday-ai-review"
            variant="outline"
            size="sm"
            disabled={!decision}
            onClick={onAiReview}
          >
            <Sparkles className="h-4 w-4" />
            AI 盘中解读
          </Button>
          <Button
            data-testid="momentum-intraday-refresh"
            variant="ghost"
            disabled={!decision}
            isLoading={loading}
            loadingText="刷新中..."
            onClick={onRefresh}
          >
            刷新盘中信号
          </Button>
        </div>
      </div>

      {error ? <ApiErrorAlert error={error} className="mt-4" onDismiss={onDismissError} /> : null}

      {!decision ? (
        <div className="pt-4">
          <EmptyState
            title="暂无盘中信号"
            description="先执行一次强势筛选并生成二次决策，再按需手动刷新盘中信号。"
          />
        </div>
      ) : !intradaySignal ? (
        <div className="pt-4">
          <EmptyState
            title="盘中信号尚未刷新"
            description="当前先保留昨晚的静态二次决策；你点击“刷新盘中信号”后，系统再补充盘中状态与买/不买收口。"
          />
        </div>
      ) : (
        <div className="grid gap-4 pt-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <div className="rounded-2xl border border-border/50 bg-hover/20 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default">{intradaySignal.marketPhaseLabel}</Badge>
                <Badge variant={intradayStatusBadgeVariant(intradaySignal.status)}>
                  {intradaySignal.statusLabel}
                </Badge>
              </div>
              <p className="mt-3 text-sm leading-7 text-foreground">{intradaySignal.reason}</p>
              <p className="mt-3 text-xs text-secondary-text">
                更新时间：{new Date(intradaySignal.updatedAt).toLocaleString('zh-CN', { hour12: false })}
              </p>
            </div>

            <SnapshotAssistPanel snapshotAssist={snapshotAssist} />

            <div className="grid gap-4">
              {intradaySignal.portfolioItems.map((item) => (
                <IntradaySignalItemCard key={`${item.slot}-${item.tsCode}`} item={item} />
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
              <p className="text-sm font-semibold text-foreground">今日收口</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge variant={intradayFinalRecommendationBadgeVariant(intradaySignal.finalRecommendation)}>
                  {intradaySignal.finalRecommendationLabel}
                </Badge>
                <Badge variant={intradayConfidenceBadgeVariant(intradaySignal.confidenceLevel)}>
                  {intradaySignal.confidenceLabel}
                </Badge>
              </div>
              <p className="mt-3 text-sm leading-6 text-secondary-text">{intradaySignal.closingNote}</p>
              <p className="mt-3 text-xs leading-6 text-secondary-text">
                {intradaySignal.canEmitBuySignal
                  ? '当前允许给出更明确的买点信号，但仍沿用昨晚排好的顺序，不在盘中改排序。'
                  : '当前不输出明确买入指令；如果只是观察或低置信度，页面会明确劝退或继续观察。'}
              </p>
            </div>

            <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
              <p className="text-sm font-semibold text-foreground">优先关注顺序</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-secondary-text">
                {intradaySignal.focusOrder.length > 0 ? (
                  intradaySignal.focusOrder.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>当前没有额外顺序提示，继续按主仓 / 次仓 / 观察仓固定顺序跟踪即可。</p>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
              <p className="text-sm font-semibold text-foreground">继续关注</p>
              <div className="mt-3 space-y-2 text-sm leading-6 text-secondary-text">
                {intradaySignal.watchItems.length > 0 ? (
                  intradaySignal.watchItems.map((item) => <p key={item}>{item}</p>)
                ) : (
                  <p>当前没有额外观察项，继续按主仓 / 次仓 / 观察仓顺序跟踪即可。</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  </div>
);

const MomentumScreenerPage: React.FC = () => {
  const persisted = useMemo(() => loadPersistedState(), []);
  const [form, setForm] = useState<FormState>(persisted.form);
  const [response, setResponse] = useState<MomentumScreenerResponse | null>(null);
  const [aggressiveResponse, setAggressiveResponse] = useState<MomentumScreenerResponse | null>(null);
  const [decision, setDecision] = useState<MomentumSecondaryDecision | null>(null);
  const [intradaySignal, setIntradaySignal] = useState<MomentumIntradaySignal | null>(null);
  const [snapshotAssist, setSnapshotAssist] = useState<MomentumSnapshotAssist | null>(null);
  const [screeningRun, setScreeningRun] = useState<MomentumScreeningRunResponse | null>(null);
  const [screeningRunMessage, setScreeningRunMessage] = useState<string | null>(null);
  const [screeningQueuedRuns, setScreeningQueuedRuns] = useState<MomentumScreeningRunResponse[]>([]);
  const [screeningRunHistory, setScreeningRunHistory] = useState<MomentumScreeningRunResponse[]>([]);
  const [screeningRunListLoading, setScreeningRunListLoading] = useState(false);
  const [lastSubmittedPayload, setLastSubmittedPayload] = useState<MomentumScreenerRequest | null>(null);
  const [selectedResult, setSelectedResult] = useState<SelectedResultState | null>(null);
  const [loading, setLoading] = useState(false);
  const [aggressiveLoading, setAggressiveLoading] = useState(false);
  const [decisionRefreshing, setDecisionRefreshing] = useState(false);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [aggressiveError, setAggressiveError] = useState<ParsedApiError | null>(null);
  const [intradayError, setIntradayError] = useState<ParsedApiError | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const openAiPanel = useMomentumScreenerAiStore((state) => state.openPanel);
  const resolvedRunIdRef = useRef<string | null>(null);
  const activeScreeningRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    document.title = '强势筛选 - DSA';
  }, []);

  useEffect(() => {
    persistState(form);
  }, [form]);

  useEffect(() => {
    activeScreeningRunIdRef.current = screeningRun?.runId ?? null;
  }, [screeningRun]);

  const openMomentumAiPanel = async (target: MomentumScreenerAiReviewTarget) => {
    await openAiPanel(target);
  };

  const buildPayloadFromRun = useCallback((run: MomentumScreeningRunResponse): MomentumScreenerRequest => ({
    profile: run.profile,
    topN: run.topN,
    tradeDate: run.requestedTradeDate ?? undefined,
  }), []);

  const refreshScreeningRunList = useCallback(
    async ({ resumeActive = false, silent = false }: { resumeActive?: boolean; silent?: boolean } = {}) => {
      if (!silent) {
        setScreeningRunListLoading(true);
      }
      try {
        const data = await momentumScreenerApi.listRuns(6, 'standard');
        setScreeningQueuedRuns(data.queued.items);
        setScreeningRunHistory(data.history.items);

        if (resumeActive && !activeScreeningRunIdRef.current && data.currentRunning) {
          const payload = buildPayloadFromRun(data.currentRunning);
          setLastSubmittedPayload(payload);
          setScreeningRun(data.currentRunning);
          setScreeningRunMessage('已恢复上次未完成的筛选任务，页面会继续跟踪进度。');
          setLoading(true);
        }
      } catch {
        if (!silent) {
          setScreeningQueuedRuns([]);
          setScreeningRunHistory([]);
        }
      } finally {
        if (!silent) {
          setScreeningRunListLoading(false);
        }
      }
    },
    [buildPayloadFromRun],
  );

  const loadAggressiveSupplement = useCallback(async (payload: MomentumScreenerRequest) => {
    setAggressiveLoading(true);
    setAggressiveError(null);

    try {
      const data = await momentumScreenerApi.screen({ ...payload, profile: 'aggressive' });
      setAggressiveResponse(data);
    } catch (err) {
      setAggressiveResponse(null);
      setAggressiveError(getParsedApiError(err));
    } finally {
      setAggressiveLoading(false);
    }
  }, []);

  const applyCompletedScreeningRun = useCallback(async (
    run: MomentumScreeningRunResponse,
    payload: MomentumScreenerRequest,
  ) => {
    const data = await momentumScreenerApi.getRunResult(run.runId);
    resolvedRunIdRef.current = run.runId;
    setScreeningRun(run);
    setScreeningRunMessage(run.status === 'completed' ? '真实性优先任务已完成，结果已同步到下方视图。' : null);
    setResponse(data.screening);
    setDecision(data.decision);
    setLastSubmittedPayload(payload);
    setLoading(false);
    void loadAggressiveSupplement(payload);
    void refreshScreeningRunList({ silent: true });
  }, [loadAggressiveSupplement, refreshScreeningRunList]);

  const restoreScreeningRun = useCallback(async (
    run: MomentumScreeningRunResponse,
    options: { manual?: boolean } = {},
  ) => {
    const payload = buildPayloadFromRun(run);
    setLastSubmittedPayload(payload);
    setSelectedResult(null);
    setError(null);
    setIntradaySignal(null);
    setSnapshotAssist(null);
    setIntradayError(null);

    if (run.status === 'completed' && run.resultAvailable) {
      resolvedRunIdRef.current = run.runId;
      await applyCompletedScreeningRun(run, payload);
      if (options.manual) {
        setScreeningRunMessage('已加载历史筛选任务结果。');
      }
      return;
    }

    resolvedRunIdRef.current = null;
    setResponse(null);
    setDecision(null);
    setAggressiveResponse(null);
    setScreeningRun(run);
    setLoading(run.status === 'queued' || run.status === 'running');
    setScreeningRunMessage(
      run.status === 'running'
        ? '已切换到进行中的筛选任务，页面会继续跟踪进度。'
        : run.status === 'queued'
          ? '已切换到排队中的筛选任务，等待前序任务完成后继续。'
          : run.status === 'failed'
            ? run.errorMessage ?? '该筛选任务执行失败。'
            : '该筛选任务已取消。',
    );
  }, [applyCompletedScreeningRun, buildPayloadFromRun]);

  const runScreening = async (nextForm = form) => {
    setLoading(true);
    setError(null);
    setResponse(null);
    setDecision(null);
    setIntradaySignal(null);
    setSnapshotAssist(null);
    setIntradayError(null);
    setSelectedResult(null);
    setAggressiveResponse(null);
    setAggressiveError(null);
    setScreeningRun(null);
    setScreeningRunMessage(null);
    resolvedRunIdRef.current = null;

    const payload = buildScreeningPayload(nextForm);
    setLastSubmittedPayload(payload);

    try {
      const created = await momentumScreenerApi.createRun({
        ...payload,
        truthMode: 'full',
        useSectorContext: true,
      });
      setScreeningRun(created.run);
      setScreeningRunMessage(created.message);
      void refreshScreeningRunList({ silent: true });
      if (created.run.status === 'completed' && created.run.resultAvailable) {
        resolvedRunIdRef.current = created.run.runId;
        try {
          await applyCompletedScreeningRun(created.run, payload);
        } catch (err) {
          resolvedRunIdRef.current = null;
          throw err;
        }
      }
    } catch (err) {
      setLoading(false);
      setError(getParsedApiError(err));
      setResponse(null);
      setDecision(null);
      setAggressiveResponse(null);
      setScreeningRun(null);
    }
  };

  const handleCancelScreeningRun = async () => {
    if (!screeningRun || (screeningRun.status !== 'queued' && screeningRun.status !== 'running')) {
      return;
    }

    try {
      const updated = await momentumScreenerApi.cancelRun(screeningRun.runId);
      setScreeningRun(updated);
      setScreeningRunMessage(
        updated.status === 'cancelled' ? '筛选任务已取消。' : '筛选任务取消请求已提交，当前阶段结束后会自动停止。',
      );
      if (updated.status === 'cancelled') {
        setLoading(false);
      }
      void refreshScreeningRunList({ silent: true });
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  useEffect(() => {
    if (!screeningRun) {
      return;
    }

    if (screeningRun.status === 'completed' && screeningRun.resultAvailable) {
      if (resolvedRunIdRef.current === screeningRun.runId) {
        return;
      }

      let cancelled = false;
      const payload = lastSubmittedPayload;
      if (!payload) {
        return;
      }
      resolvedRunIdRef.current = screeningRun.runId;

      void (async () => {
        try {
          await applyCompletedScreeningRun(screeningRun, payload);
        } catch (err) {
          if (cancelled) {
            return;
          }
          resolvedRunIdRef.current = null;
          setLoading(false);
          setError(getParsedApiError(err));
        }
      })();

      return () => {
        cancelled = true;
      };
    }

    if (screeningRun.status === 'failed' || screeningRun.status === 'cancelled') {
      setLoading(false);
      setScreeningRunMessage(
        screeningRun.status === 'cancelled'
          ? '筛选任务已取消。'
          : screeningRun.errorMessage ?? '筛选任务执行失败，请稍后重试。',
      );
      if (screeningRun.status === 'failed') {
        setError(
          createParsedApiError({
            title: '筛选任务失败',
            message: screeningRun.errorMessage ?? '筛选任务执行失败，请稍后重试。',
            rawMessage: screeningRun.errorMessage ?? '筛选任务执行失败',
            category: 'http_error',
          }),
        );
      }
      return;
    }

    if (screeningRun.status === 'completed') {
      setLoading(false);
      setScreeningRunMessage('筛选任务已完成，但结果尚未就绪，请稍后刷新任务状态。');
      return;
    }

    if (screeningRun.status !== 'queued' && screeningRun.status !== 'running') {
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const latest = await momentumScreenerApi.getRun(screeningRun.runId);
        if (!cancelled) {
          setScreeningRun(latest);
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        setLoading(false);
        setError(getParsedApiError(err));
      }
    }, SCREENING_RUN_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [applyCompletedScreeningRun, lastSubmittedPayload, screeningRun]);

  const handleRefreshDecision = async () => {
    if (!lastSubmittedPayload || !decision) {
      return;
    }

    setDecisionRefreshing(true);
    setError(null);

    try {
      const data = await momentumScreenerApi.screenWithDecision(lastSubmittedPayload, {
        waitForStrategyHealth: true,
      });
      setResponse(data.screening);
      setDecision(data.decision);
      setIntradaySignal(null);
      setSnapshotAssist(null);
      setIntradayError(null);
      void loadAggressiveSupplement(lastSubmittedPayload);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDecisionRefreshing(false);
    }
  };

  const handleRefreshIntradaySignal = async () => {
    if (!lastSubmittedPayload || !decision) {
      return;
    }

    setIntradayLoading(true);
    setIntradayError(null);

    try {
      const data = await momentumScreenerApi.fetchIntradaySignal(lastSubmittedPayload);
      setResponse(data.screening);
      setDecision(data.decision);
      setIntradaySignal(data.intradaySignal);
      setSnapshotAssist(data.snapshotAssist ?? null);
    } catch (err) {
      setIntradaySignal(null);
      setSnapshotAssist(null);
      setIntradayError(getParsedApiError(err));
    } finally {
      setIntradayLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const initialize = async () => {
      if (persisted.hasPersisted) {
        return;
      }

      try {
        await systemConfigApi.getConfig(false);
        if (cancelled) {
          return;
        }

        const nextForm = buildFormFromSystemConfig();
        setForm(nextForm);
      } catch {
        if (cancelled) {
          return;
        }
      }
    };

    void initialize();
    return () => {
      cancelled = true;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void refreshScreeningRunList({ resumeActive: true });
  }, [refreshScreeningRunList]);

  const sortedResults = useMemo(
    () => (response ? sortResults(response.results) : []),
    [response],
  );
  const candidateDiagnosticByCode = useMemo(() => {
    const diagnostics = new Map<string, MomentumDecisionCandidateDiagnostic>();
    for (const item of decision?.candidateDiagnostics ?? []) {
      diagnostics.set(item.tsCode, item);
    }
    return diagnostics;
  }, [decision?.candidateDiagnostics]);
  const topCapitalTheme = useMemo(() => {
    const item = decision?.mainlineRadar?.[0];
    if (!item) {
      return null;
    }
    return {
      item,
      display: formatMainlineThemeDisplay(item),
    };
  }, [decision?.mainlineRadar]);
  const aggressiveHighlights = useMemo(() => {
    if (!aggressiveResponse) {
      return [];
    }

    const officialTop3Codes = new Set((decision?.portfolio ?? []).map((item) => item.tsCode));

    return [...aggressiveResponse.results]
      .filter((item) => !officialTop3Codes.has(item.tsCode))
      .sort(
        (a, b) =>
          b.extensionScore - a.extensionScore ||
          (b.buyabilityScore ?? -1) - (a.buyabilityScore ?? -1) ||
          b.officialScore - a.officialScore ||
          b.finalScore - a.finalScore,
      )
      .slice(0, 2)
      .map((item, index) => ({ ...item, rank: index + 1 }));
  }, [aggressiveResponse, decision?.portfolio]);
  const selectedResultTsCode = selectedResult?.item.tsCode;
  const selectedResultSource = selectedResult?.source;
  const selectedResultDiagnostic =
    selectedResultSource === 'standard' && selectedResultTsCode
      ? candidateDiagnosticByCode.get(selectedResultTsCode) ?? null
      : null;

  useEffect(() => {
    if (!selectedResultSource) {
      return;
    }

    if (selectedResultSource === 'aggressive') {
      if (aggressiveHighlights.length === 0) {
        setSelectedResult(null);
        return;
      }

      if (!selectedResultTsCode) {
        return;
      }

      const matched = aggressiveHighlights.find((item) => item.tsCode === selectedResultTsCode);
      setSelectedResult(matched ? { source: 'aggressive', item: matched } : null);
      return;
    }

    if (sortedResults.length === 0) {
      setSelectedResult(null);
      return;
    }

    if (!selectedResultTsCode) {
      return;
    }

    const matched = sortedResults.find((item) => item.tsCode === selectedResultTsCode);
    setSelectedResult(matched ? { source: 'standard', item: matched } : null);
  }, [aggressiveHighlights, selectedResultSource, sortedResults, selectedResultTsCode]);

  const averageOfficialScore = sortedResults.length
    ? sortedResults.reduce((sum, item) => sum + item.officialScore, 0) / sortedResults.length
    : 0;
  const screeningRunProgressSummary = useMemo(
    () => (screeningRun ? buildScreeningRunProgressSummary(screeningRun) : null),
    [screeningRun],
  );
  const screeningRunStageHint = useMemo(
    () => (screeningRun ? buildScreeningRunStageHint(screeningRun) : null),
    [screeningRun],
  );
  const screeningRunProgressPct = screeningRun?.progress.progressPct ?? 0;
  const screeningRunCanCancel = screeningRun?.status === 'queued' || screeningRun?.status === 'running';
  const screeningRunStageLabel =
    screeningRun?.currentStageLabel ??
    (screeningRun?.status === 'completed'
      ? '结果落盘完成'
      : screeningRun?.status === 'cancelled'
        ? '任务已停止'
        : screeningRun?.status === 'failed'
          ? '任务执行失败'
          : screeningRun?.cancelRequested
            ? '取消请求处理中'
            : '等待任务进入下一阶段');
  const screeningRunHeartbeatLabel = screeningRun ? formatRunTimestamp(screeningRun.heartbeatAt) : null;
  const screeningRunDurationLabel = screeningRun
    ? formatDurationLabel(screeningRun.startedAt, screeningRun.finishedAt)
    : null;
  const visibleRunHistory = screeningRunHistory.slice(0, 4);
  const hasRunRecords = screeningQueuedRuns.length > 0 || visibleRunHistory.length > 0;
  const isBusy = loading || decisionRefreshing || intradayLoading;

  const buildAiTargetBase = (): Pick<
    MomentumScreenerAiReviewTarget,
    'payload' | 'screening' | 'decision' | 'intradaySignal' | 'snapshotAssist'
  > | null => {
    if (!lastSubmittedPayload || !response) {
      return null;
    }
    return {
      payload: lastSubmittedPayload,
      screening: response,
      decision,
      intradaySignal,
      snapshotAssist,
    };
  };

  const handleOpenCandidateAiReview = async (
    item: MomentumScreenerResult,
    source: MomentumProfile = 'standard',
  ) => {
    const base = buildAiTargetBase();
    if (!base) return;
    await openMomentumAiPanel({
      ...base,
      payload: source === 'aggressive' ? { ...base.payload, profile: 'aggressive' } : base.payload,
      screening: source === 'aggressive' && aggressiveResponse ? aggressiveResponse : base.screening,
      reviewType: 'candidate',
      reviewKey: item.tsCode,
      title: `候选股 AI 点评 · ${item.name}`,
    });
  };

  const handleOpenDecisionAiReview = async () => {
    const base = buildAiTargetBase();
    if (!base || !decision) return;
    await openMomentumAiPanel({
      ...base,
      reviewType: 'decision',
      reviewKey: 'summary',
      title: '二次决策 AI 综合建议',
    });
  };

  const handleOpenIntradayAiReview = async () => {
    const base = buildAiTargetBase();
    if (!base || !decision) return;
    await openMomentumAiPanel({
      ...base,
      reviewType: 'intraday',
      reviewKey: 'summary',
      title: '盘中信号 AI 解读',
    });
  };

  const handleOpenExcludedAiReview = async () => {
    const base = buildAiTargetBase();
    if (!base || !decision) return;
    await openMomentumAiPanel({
      ...base,
      reviewType: 'excluded',
      reviewKey: 'summary',
      title: '落选说明 AI 分析',
    });
  };

  const handleCopyResults = async () => {
    if (sortedResults.length === 0) {
      setCopyFeedback('\u6682\u65e0\u53ef\u590d\u5236\u7684\u7ed3\u679c');
      return;
    }

    const text = buildCopyText('standard', response?.tradeDate, sortedResults);
    try {
      await navigator.clipboard.writeText(text);
      setCopyFeedback('\u5df2\u590d\u5236\u5f53\u524d\u7b5b\u9009\u7ed3\u679c');
    } catch {
      setCopyFeedback('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6d4f\u89c8\u5668\u526a\u8d34\u677f\u6743\u9650');
    }
  };

  const handleCopySingleResult = async (item: MomentumScreenerResult) => {
    const text = buildSingleResultText('standard', response?.tradeDate, item);

    try {
      await navigator.clipboard.writeText(text);
      setCopyFeedback(`已复制 ${item.name} 的明细`);
    } catch {
      setCopyFeedback('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6d4f\u89c8\u5668\u526a\u8d34\u677f\u6743\u9650');
    }
  };

  const handleExportMarkdown = () => {
    if (sortedResults.length === 0) {
      setCopyFeedback('\u6682\u65e0\u53ef\u5bfc\u51fa\u7684\u7ed3\u679c');
      return;
    }

    const content = buildMarkdownText('standard', response?.tradeDate, sortedResults);
    const datePart = (response?.tradeDate ?? form.tradeDate ?? 'latest').replace(/-/g, '');
    const fileName = `momentum_screener_standard_${datePart}.md`;
    downloadTextFile(content, fileName, 'text/markdown;charset=utf-8');
    setCopyFeedback('\u5df2\u5bfc\u51fa Markdown');
  };

  const handleExportCsv = () => {
    if (sortedResults.length === 0) {
      setCopyFeedback('\u6682\u65e0\u53ef\u5bfc\u51fa\u7684\u7ed3\u679c');
      return;
    }

    const content = buildCsvText(sortedResults);
    const datePart = (response?.tradeDate ?? form.tradeDate ?? 'latest').replace(/-/g, '');
    const fileName = `momentum_screener_standard_${datePart}.csv`;
    downloadTextFile(content, fileName, 'text/csv;charset=utf-8');
    setCopyFeedback('\u5df2\u5bfc\u51fa CSV');
  };

  const handleExportSingleMarkdown = (item: MomentumScreenerResult) => {
    const content = buildSingleResultMarkdown('standard', response?.tradeDate, item);
    const datePart = (response?.tradeDate ?? form.tradeDate ?? 'latest').replace(/-/g, '');
    const fileName = `momentum_screener_${item.tsCode.replace('.', '_')}_${datePart}.md`;
    downloadTextFile(content, fileName, 'text/markdown;charset=utf-8');
    setCopyFeedback(`已导出 ${item.name} Markdown`);
  };

  const handleRestoreSystemDefaults = async () => {
    setError(null);

    try {
      await systemConfigApi.getConfig(false);
      const nextForm = buildFormFromSystemConfig();
      setForm(nextForm);
      await runScreening(nextForm);
      setCopyFeedback('已恢复系统默认参数');
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  useEffect(() => {
    if (!copyFeedback) {
      return;
    }
    const timer = window.setTimeout(() => setCopyFeedback(null), 2500);
    return () => window.clearTimeout(timer);
  }, [copyFeedback]);

  return (
    <div
      data-testid="momentum-screener-page"
      className="flex min-h-0 flex-col overflow-y-auto pb-6 pr-1"
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">强势筛选</h1>
          <p className="text-sm text-secondary-text">
            收盘后扫描全市场强势股；Standard 给官方主结论，Aggressive 只作进攻补充。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="default" size="md">
            Standard 官方主引擎
          </Badge>
          <Badge variant="warning" size="md">
            Aggressive 进攻补充
          </Badge>
          {response ? <Badge variant="default" size="md">{response.tradeDate}</Badge> : null}
        </div>
      </div>

      {error ? <ApiErrorAlert error={error} className="mb-4" onDismiss={() => setError(null)} /> : null}

      {response?.tradeDateNote ? (
        <div className="mb-4 rounded-3xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-secondary-text">
          {response.tradeDateNote}
        </div>
      ) : null}

      <div className="grid items-start gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="rounded-3xl border-border/60 bg-card/55 xl:sticky xl:top-0">
          <div className="mb-4">
            <p className="text-sm font-semibold text-foreground">筛选参数</p>
            <p className="mt-1 text-xs text-secondary-text">V1 主页面只保留官方生产入口，参数和输出口径都会自动保持统一。</p>
          </div>
          <div className="grid gap-3">
            <div className="rounded-2xl border border-border/50 bg-hover/10 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-foreground">页面输出关系</p>
                <Badge variant="default">Standard 官方主结论</Badge>
                <Badge variant="warning">Aggressive 进攻补充</Badge>
              </div>
              <div className="mt-2 space-y-2 text-sm leading-6 text-secondary-text">
                <p>官方今日出手级别、默认组合、行动清单和盘中权限都由 Standard 主引擎输出。</p>
                <p>Aggressive 只补充更高弹性候选，不单独形成新的官方组合，也不会推翻总闸门。</p>
              </div>
            </div>
            <div className="rounded-2xl border border-border/50 bg-hover/10 px-4 py-3">
              <p className="text-sm font-medium text-foreground">V1 统一入口基线</p>
              <div className="mt-2 grid gap-2 text-sm text-secondary-text sm:grid-cols-2">
                <p>最小涨幅 4%</p>
                <p>最小成交额 2 亿</p>
                <p>最小换手率 2%</p>
                <p>官方展示 Top30</p>
                <p>市场范围：主板 + 创业板 + 科创板</p>
              </div>
              <p className="mt-2 text-xs leading-6 text-secondary-text">
                V1 生产模式下候选池入口已固定，普通用户不再修改底层样本门槛。
              </p>
            </div>
            <Input
              label="交易日"
              type="date"
              value={form.tradeDate}
              onChange={(event) => setForm((prev) => ({ ...prev, tradeDate: event.target.value }))}
              hint="留空时优先使用当日收盘数据；若当天 EOD 数据未同步完成，则自动回退到上一交易日。"
            />
            <div className="mt-2 flex gap-2">
              <Button
                data-testid="momentum-screener-run"
                variant="home-action-ai"
                className="flex-1"
                disabled={isBusy}
                isLoading={loading}
                loadingText="任务执行中..."
                onClick={() => void runScreening()}
              >
                执行筛选
              </Button>
              <Button
                data-testid="momentum-screener-restore"
                variant="ghost"
                className="flex-1"
                disabled={isBusy}
                onClick={() => void handleRestoreSystemDefaults()}
              >
                恢复系统默认
              </Button>
              <Button
                data-testid="momentum-screener-reset"
                variant="ghost"
                className="flex-1"
                disabled={isBusy}
                onClick={() => {
                  setForm(DEFAULT_FORM);
                  void runScreening(DEFAULT_FORM);
                }}
              >
                重置
              </Button>
            </div>
            {screeningRun ? (
              <div
                data-testid="momentum-screening-run-panel"
                className="rounded-2xl border border-cyan/20 bg-cyan/5 px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-foreground">真实性优先任务</p>
                      <Badge variant={screeningRunBadgeVariant(screeningRun.status)}>
                        {screeningRunStatusLabel(screeningRun.status)}
                      </Badge>
                      <Badge variant="default">{screeningRun.truthMode === 'full' ? 'Full Truth' : 'Light'}</Badge>
                    </div>
                    <p className="mt-2 text-xs leading-6 text-secondary-text">{screeningRunStageLabel}</p>
                  </div>
                  {screeningRunCanCancel ? (
                    <Button
                      data-testid="momentum-screening-run-cancel"
                      variant="ghost"
                      size="sm"
                      onClick={() => void handleCancelScreeningRun()}
                    >
                      取消任务
                    </Button>
                  ) : null}
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-hover/40">
                  <div
                    data-testid="momentum-screening-run-progress-bar"
                    className="h-full rounded-full bg-cyan transition-all duration-300"
                    style={{ width: `${Math.max(6, Math.min(100, screeningRunProgressPct || 0))}%` }}
                  />
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <div className="rounded-2xl border border-border/40 bg-card/35 px-3 py-2">
                    <p className="text-[11px] uppercase tracking-wide text-tertiary-text">当前阶段</p>
                    <p className="mt-1 text-sm text-foreground">{screeningRunStageLabel}</p>
                  </div>
                  <div className="rounded-2xl border border-border/40 bg-card/35 px-3 py-2">
                    <p className="text-[11px] uppercase tracking-wide text-tertiary-text">完成度</p>
                    <p className="mt-1 text-sm text-foreground">{screeningRunProgressPct.toFixed(1)}%</p>
                  </div>
                  <div className="rounded-2xl border border-border/40 bg-card/35 px-3 py-2">
                    <p className="text-[11px] uppercase tracking-wide text-tertiary-text">最近心跳</p>
                    <p
                      data-testid="momentum-screening-run-heartbeat"
                      className="mt-1 text-sm text-foreground"
                    >
                      {screeningRunHeartbeatLabel ?? '--'}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-border/40 bg-card/35 px-3 py-2">
                    <p className="text-[11px] uppercase tracking-wide text-tertiary-text">已运行</p>
                    <p
                      data-testid="momentum-screening-run-duration"
                      className="mt-1 text-sm text-foreground"
                    >
                      {screeningRunDurationLabel ?? '--'}
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-secondary-text">
                  <span>任务号 {screeningRun.runId.slice(-8)}</span>
                  {screeningRun.requestedTradeDate ? <span>请求日期 {screeningRun.requestedTradeDate}</span> : null}
                  {screeningRun.tradeDate ? <span>实际交易日 {screeningRun.tradeDate}</span> : null}
                </div>
                {screeningRunProgressSummary ? (
                  <p className="mt-2 text-xs leading-6 text-secondary-text">{screeningRunProgressSummary}</p>
                ) : null}
                {screeningRunStageHint ? (
                  <p
                    data-testid="momentum-screening-run-stage-hint"
                    className="mt-2 text-xs leading-6 text-secondary-text"
                  >
                    {screeningRunStageHint}
                  </p>
                ) : null}
                {screeningRunMessage ? (
                  <p
                    data-testid="momentum-screening-run-message"
                    className="mt-2 text-xs leading-6 text-secondary-text"
                  >
                    {screeningRunMessage}
                  </p>
                ) : null}
              </div>
            ) : null}
            <div
              data-testid="momentum-screening-run-history"
              className="rounded-2xl border border-border/50 bg-hover/10 px-4 py-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-foreground">最近任务</p>
                  <p className="mt-1 text-xs leading-6 text-secondary-text">
                    页面重开后也能继续跟踪正在运行的筛选任务，并快速加载最近一次结果。
                  </p>
                </div>
                <Button
                  data-testid="momentum-screening-run-history-refresh"
                  variant="ghost"
                  size="sm"
                  disabled={screeningRunListLoading}
                  onClick={() => void refreshScreeningRunList()}
                >
                  <RefreshCw className="h-4 w-4" />
                  刷新
                </Button>
              </div>
              {!hasRunRecords ? (
                <p className="mt-3 text-xs leading-6 text-secondary-text">
                  暂无可恢复的筛选任务记录，执行一次真实性优先任务后会显示在这里。
                </p>
              ) : (
                <div className="mt-3 space-y-3">
                  {screeningQueuedRuns.map((run) => (
                    <div
                      key={run.runId}
                      className="rounded-2xl border border-border/50 bg-card/40 px-3 py-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={screeningRunBadgeVariant(run.status)}>
                            {screeningRunStatusLabel(run.status)}
                          </Badge>
                          <span className="text-xs text-secondary-text">{run.currentStageLabel ?? '等待调度'}</span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void restoreScreeningRun(run, { manual: true })}
                        >
                          继续跟踪
                        </Button>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-secondary-text">
                        {run.requestedTradeDate ? `请求日期 ${run.requestedTradeDate}` : '请求日期 latest'} ·
                        {' '}任务号 {run.runId.slice(-8)}
                      </p>
                      {buildScreeningRunProgressSummary(run) ? (
                        <p className="mt-1 text-xs leading-6 text-secondary-text">
                          {buildScreeningRunProgressSummary(run)}
                        </p>
                      ) : null}
                    </div>
                  ))}
                  {visibleRunHistory.map((run) => (
                    <div
                      key={run.runId}
                      className="rounded-2xl border border-border/50 bg-card/40 px-3 py-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={screeningRunBadgeVariant(run.status)}>
                            {screeningRunStatusLabel(run.status)}
                          </Badge>
                          {run.tradeDate ? <span className="text-xs text-secondary-text">交易日 {run.tradeDate}</span> : null}
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!run.resultAvailable && run.status !== 'failed' && run.status !== 'cancelled'}
                          onClick={() => void restoreScreeningRun(run, { manual: true })}
                        >
                          {run.status === 'completed' ? '加载结果' : run.status === 'failed' ? '查看失败' : '查看状态'}
                        </Button>
                      </div>
                      <p className="mt-2 text-xs leading-6 text-secondary-text">
                        {run.requestedTradeDate ? `请求日期 ${run.requestedTradeDate}` : '请求日期 latest'} ·
                        {' '}更新时间 {formatRunTimestamp(run.updatedAt) ?? '--'}
                      </p>
                      {run.errorMessage ? (
                        <p className="mt-1 text-xs leading-6 text-secondary-text">{run.errorMessage}</p>
                      ) : buildScreeningRunProgressSummary(run) ? (
                        <p className="mt-1 text-xs leading-6 text-secondary-text">
                          {buildScreeningRunProgressSummary(run)}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Card>

        <div className="flex min-h-0 flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <SummaryCard
              icon={Radar}
              label="候选池数量"
              value={response ? String(response.candidateCount) : '--'}
              subtext="通过硬过滤后进入评分池"
            />
            <SummaryCard
              icon={TrendingUp}
              label="结果数量"
              value={response ? String(sortedResults.length) : '--'}
              subtext="官方固定展示 Top30"
            />
            <SummaryCard
              icon={BarChart3}
              label="平均官方总分"
              value={response ? averageOfficialScore.toFixed(1) : '--'}
              subtext="当前结果列表的官方总分均值"
            />
            <SummaryCard
              icon={ShieldAlert}
              label="最高官方总分"
              value={sortedResults[0] ? sortedResults[0].officialScore.toFixed(1) : '--'}
              subtext={sortedResults[0] ? `${sortedResults[0].name} 排名第 1` : '等待筛选结果'}
            />
            <SummaryCard
              icon={Flame}
              label="资金主攻题材"
              value={topCapitalTheme ? topCapitalTheme.display.name : '--'}
              subtext={
                topCapitalTheme
                  ? `主力净额 ${formatCapitalAmount(topCapitalTheme.item.netAmount)} · ${
                      topCapitalTheme.item.boardRank != null ? `板块第 ${topCapitalTheme.item.boardRank}` : '板块排名待确认'
                    }`
                  : '等待 V1.3 资金题材雷达'
              }
            />
          </div>

          <SecondaryDecisionPanel
            decision={decision}
            onRefresh={() => void handleRefreshDecision()}
            refreshing={decisionRefreshing}
            refreshDisabled={!decision || !lastSubmittedPayload || loading || intradayLoading}
            onAiDecisionReview={() => void handleOpenDecisionAiReview()}
            onAiExcludedReview={() => void handleOpenExcludedAiReview()}
          />
          <AggressiveSupplementPanel
            officialActionLevel={decision?.action.level ?? null}
            tradeDate={aggressiveResponse?.tradeDate ?? response?.tradeDate}
            loading={aggressiveLoading}
            error={aggressiveError}
            items={aggressiveHighlights}
            onReview={(item) => void handleOpenCandidateAiReview(item, 'aggressive')}
            onOpenDetail={(item) => setSelectedResult({ source: 'aggressive', item })}
          />
          <IntradaySignalPanel
            decision={decision}
            intradaySignal={intradaySignal}
            snapshotAssist={snapshotAssist}
            loading={intradayLoading}
            error={intradayError}
            onRefresh={() => void handleRefreshIntradaySignal()}
            onDismissError={() => setIntradayError(null)}
            onAiReview={() => void handleOpenIntradayAiReview()}
          />

          <Card className="min-h-0 flex-1 overflow-hidden rounded-3xl border-border/60 bg-card/55">
            <div className="mb-4 flex items-center justify-between gap-3 border-b border-border/60 pb-4">
              <div>
                <p className="text-sm font-semibold text-foreground">Standard 官方筛选结果</p>
                <p className="mt-1 text-xs text-secondary-text">这里展示官方主路径结果；Aggressive 候选已经单独收进上方补充视图。</p>
              </div>
              <div className="flex items-end gap-2">
                <Button
                  data-testid="momentum-screener-copy-results"
                  variant="ghost"
                  className="mb-[2px]"
                  disabled={sortedResults.length === 0}
                  onClick={() => void handleCopyResults()}
                >
                  复制结果
                </Button>
                <Button
                  data-testid="momentum-screener-export-markdown"
                  variant="ghost"
                  className="mb-[2px]"
                  disabled={sortedResults.length === 0}
                  onClick={handleExportMarkdown}
                >
                  导出 Markdown
                </Button>
                <Button
                  data-testid="momentum-screener-export-csv"
                  variant="ghost"
                  className="mb-[2px]"
                  disabled={sortedResults.length === 0}
                  onClick={handleExportCsv}
                >
                  导出 CSV
                </Button>
              </div>
            </div>
            {copyFeedback ? (
              <div className="mb-4 rounded-2xl border border-border/60 bg-hover/30 px-4 py-3 text-sm text-secondary-text">
                {copyFeedback}
              </div>
            ) : null}

            {sortedResults.length === 0 ? (
              <EmptyState
                title="暂无筛选结果"
                description="先执行一次筛选；V1 候选池入口已经固定为全市场统一 4 / 2亿 / 2% 基线，并固定展示 Top30。"
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-border/60 text-xs uppercase tracking-[0.12em] text-secondary-text">
                    <tr>
                      <th className="px-3 py-3">排名</th>
                      <th className="px-3 py-3">股票</th>
                      <th className="px-3 py-3">涨幅</th>
                      <th className="px-3 py-3">官方总分</th>
                      <th className="px-3 py-3">延续分</th>
                      <th className="px-3 py-3">弹性分</th>
                      <th className="px-3 py-3">风险分</th>
                      <th className="px-3 py-3">可买分</th>
                      <th className="px-3 py-3">资金题材</th>
                      <th className="px-3 py-3">地位</th>
                      <th className="px-3 py-3">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedResults.map((item) => {
                      const diagnostic = candidateDiagnosticByCode.get(item.tsCode);
                      const capitalTheme = diagnostic?.theme || item.themes[0] || '--';
                      return (
                        <tr
                          key={item.tsCode}
                          data-testid={`momentum-screener-row-${item.tsCode}`}
                          className="cursor-pointer border-b border-border/40 transition-colors hover:bg-hover/40"
                          onClick={() => setSelectedResult({ source: 'standard', item })}
                        >
                          <td className="px-3 py-3 font-mono text-foreground">#{item.rank}</td>
                          <td className="px-3 py-3">
                            <div>
                              <p className="font-medium text-foreground">{item.name}</p>
                              <p className="mt-1 text-xs text-secondary-text">{item.tsCode} · {item.marketSegmentLabel}</p>
                            </div>
                          </td>
                          <td className="px-3 py-3 font-medium text-danger">+{item.pctChg.toFixed(2)}%</td>
                          <td className={`px-3 py-3 font-semibold ${scoreTone(item.officialScore)}`}>{item.officialScore.toFixed(1)}</td>
                          <td className="px-3 py-3 text-foreground">{item.continuationScore.toFixed(1)}</td>
                          <td className="px-3 py-3 text-foreground">{item.extensionScore.toFixed(1)}</td>
                          <td className="px-3 py-3 text-warning">{item.riskScore.toFixed(1)}</td>
                          <td className="px-3 py-3 text-cyan">{item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'}</td>
                          <td className="px-3 py-3">
                            <div className="min-w-[140px]">
                              <p className="font-medium text-foreground">{capitalTheme}</p>
                              {diagnostic ? (
                                <>
                                  <p className="mt-1 text-xs text-cyan">
                                    影子分 {formatOptionalScore(diagnostic.v13ShadowScore)}
                                  </p>
                                  <p className="mt-1 text-xs text-secondary-text">
                                    资金 {formatOptionalScore(diagnostic.v13FundSupportScore)} · 涨停 {formatOptionalScore(diagnostic.v13LimitStructureScore)}
                                  </p>
                                </>
                              ) : (
                                <p className="mt-1 text-xs text-secondary-text">原始分类</p>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-3">
                            <Badge variant={leaderBadgeVariant(item.leaderLevel)}>{translateLeaderLevel(item.leaderLevel)}</Badge>
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex gap-2">
                              <Button
                                data-testid={`momentum-screener-ai-${item.tsCode}`}
                                variant="ghost"
                                size="sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleOpenCandidateAiReview(item, 'standard');
                                }}
                              >
                                AI 点评
                              </Button>
                              <Button
                                data-testid={`momentum-screener-copy-${item.tsCode}`}
                                variant="ghost"
                                size="sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleCopySingleResult(item);
                                }}
                              >
                                复制明细
                              </Button>
                              <Button
                                data-testid={`momentum-screener-export-${item.tsCode}`}
                                variant="ghost"
                                size="sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleExportSingleMarkdown(item);
                                }}
                              >
                                导出 Markdown
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>

      <Drawer
        isOpen={selectedResult != null}
        onClose={() => setSelectedResult(null)}
        title={selectedResult ? `${selectedResult.item.name} · ${selectedResult.item.tsCode}` : undefined}
        width="max-w-3xl"
      >
        {selectedResult ? (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={selectedResult.source === 'aggressive' ? 'warning' : 'default'}>
                {selectedResult.source === 'aggressive' ? 'Aggressive 进攻补充' : 'Standard 官方结果'}
              </Badge>
              {response?.tradeDate ? <Badge variant="default">{response.tradeDate}</Badge> : null}
            </div>
            <div className="flex justify-end">
              <Button
                data-testid="momentum-screener-drawer-ai-review"
                variant="outline"
                size="sm"
                onClick={() => void handleOpenCandidateAiReview(selectedResult.item, selectedResult.source)}
              >
                <Sparkles className="h-4 w-4" />
                AI 点评这只票
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <SummaryCard icon={Flame} label="官方总分" value={selectedResult.item.officialScore.toFixed(1)} />
              <SummaryCard icon={TrendingUp} label="基础总分" value={selectedResult.item.finalScore.toFixed(1)} />
              <SummaryCard icon={Radar} label="延续分" value={selectedResult.item.continuationScore.toFixed(1)} />
              <SummaryCard icon={ShieldAlert} label="风险分" value={selectedResult.item.riskScore.toFixed(1)} />
            </div>

            {selectedResult.source === 'aggressive' ? (
              <div className="grid gap-3 md:grid-cols-3">
                <SummaryCard
                  icon={BarChart3}
                  label="可买分"
                  value={selectedResult.item.buyabilityScore != null ? selectedResult.item.buyabilityScore.toFixed(1) : '--'}
                />
                <SummaryCard
                  icon={TrendingUp}
                  label="机会标签"
                  value={selectedResult.item.opportunityTag ?? '--'}
                />
                <SummaryCard
                  icon={Radar}
                  label="建议区间"
                  value={formatEntryRange(selectedResult.item) || '--'}
                />
              </div>
            ) : null}

            {selectedResultDiagnostic ? (
              <Card className="rounded-2xl border-cyan/30 bg-cyan/5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">资金题材归因</p>
                    <p className="mt-2 text-sm leading-6 text-secondary-text">
                      归入 <span className="font-medium text-foreground">{selectedResultDiagnostic.theme}</span>
                      ，用于解释这只票跟随哪条真实强势题材，不直接改写官方排序。
                    </p>
                    {selectedResultDiagnostic.v13ShadowSummary ? (
                      <p className="mt-2 text-xs leading-5 text-secondary-text">{selectedResultDiagnostic.v13ShadowSummary}</p>
                    ) : null}
                  </div>
                  <Badge variant="info">影子分 {formatOptionalScore(selectedResultDiagnostic.v13ShadowScore)}</Badge>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 md:grid-cols-5">
                  {[
                    ['题材强弱', selectedResultDiagnostic.v13ThemeStrengthScore],
                    ['资金支撑', selectedResultDiagnostic.v13FundSupportScore],
                    ['涨停结构', selectedResultDiagnostic.v13LimitStructureScore],
                    ['买点可行', selectedResultDiagnostic.v13BuyabilityScore],
                    ['筹码风险', selectedResultDiagnostic.v13ChipRiskScore],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl border border-border/40 bg-card/55 px-3 py-2">
                      <p className="text-xs text-secondary-text">{label}</p>
                      <p className="mt-1 text-sm font-semibold text-foreground">{formatOptionalScore(value as number | null | undefined)}</p>
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}

            <Card className="rounded-2xl border-border/60 bg-card/45">
              <div className="flex flex-wrap gap-2">
                <Badge variant={leaderBadgeVariant(selectedResult.item.leaderLevel)}>{translateLeaderLevel(selectedResult.item.leaderLevel)}</Badge>
                {selectedResult.item.themes.map((theme) => (
                  <Badge key={theme} variant="default">{theme}</Badge>
                ))}
                {selectedResult.item.opportunityTag ? (
                  <Badge variant="warning">{selectedResult.item.opportunityTag}</Badge>
                ) : null}
                {selectedResult.item.topReasons.map((reason) => (
                  <Badge key={reason} variant="success">{reason}</Badge>
                ))}
                {selectedResult.item.riskTags.map((tag) => (
                  <Badge key={tag} variant="warning">{translateRiskTag(tag)}</Badge>
                ))}
              </div>
            </Card>

            <Card className="rounded-2xl border-border/60 bg-card/45">
              <p className="mb-3 text-sm font-semibold text-foreground">维度拆解</p>
              <div className="space-y-3">
                {Object.entries(selectedResult.item.scoreBreakdown).map(([key, value]) => (
                  <div key={key} className="rounded-2xl border border-border/50 bg-card/55 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-foreground">{translateDimensionKey(key)}</p>
                        <p className="mt-1 text-xs text-secondary-text">
                          {value.score.toFixed(1)} / {value.maxScore.toFixed(1)}
                        </p>
                      </div>
                      <div className={`text-lg font-semibold ${scoreTone((value.score / value.maxScore) * 100)}`}>
                        {((value.score / value.maxScore) * 100).toFixed(0)}
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      {Object.entries(value.items).map(([itemKey, itemValue]) => (
                        <div key={itemKey} className="rounded-xl border border-border/40 bg-hover/20 px-3 py-2">
                          <p className="text-xs text-secondary-text">
                            {translateItemKey(itemKey)}
                          </p>
                          <p className="mt-1 text-sm font-medium text-foreground">{String(itemValue)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        ) : null}
      </Drawer>
      <ScreenerAiDrawer />
    </div>
  );
};

export default MomentumScreenerPage;

