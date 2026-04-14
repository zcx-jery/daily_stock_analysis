import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Flame, ListChecks, Radar, RefreshCw, ShieldAlert, Target, TrendingUp } from 'lucide-react';
import { momentumScreenerApi } from '../api/momentumScreener';
import { systemConfigApi } from '../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Drawer, EmptyState, Input, Select } from '../components/common';
import type {
  MomentumActionLevel,
  MomentumBuyPointStatus,
  MomentumDecisionExcludedCandidate,
  MomentumDecisionPortfolioSlot,
  MomentumDecisionTheme,
  MomentumIntradayPortfolioItem,
  MomentumIntradaySignal,
  MomentumProfile,
  MomentumSecondaryDecision,
  MomentumScreenerRequest,
  MomentumScreenerResponse,
  MomentumScreenerResult,
} from '../types/momentumScreener';

type FormState = {
  profile: MomentumProfile;
  topN: string;
  minChangePct: string;
  minAmountYi: string;
  minTurnover: string;
  tradeDate: string;
};

type SortKey = 'rank_score' | 'continuation_score' | 'extension_score' | 'risk_score' | 'buyability_score';

const STORAGE_KEY = 'dsa.momentum-screener.page-state';

const PROFILE_OPTIONS = [
  { value: 'standard', label: 'Standard' },
  { value: 'aggressive', label: 'Aggressive' },
];

const SORT_OPTIONS = [
  { value: 'rank_score', label: '按排序分' },
  { value: 'continuation_score', label: '按延续分' },
  { value: 'extension_score', label: '按弹性分' },
  { value: 'risk_score', label: '按低风险优先' },
  { value: 'buyability_score', label: '按可买分' },
];

const DEFAULT_FORM: FormState = {
  profile: 'standard',
  topN: '10',
  minChangePct: '7',
  minAmountYi: '3',
  minTurnover: '3',
  tradeDate: '',
};

const DEFAULT_SORT: SortKey = 'rank_score';

function buildScreeningPayload(nextForm: FormState): MomentumScreenerRequest {
  return {
    profile: nextForm.profile,
    topN: Number.parseInt(nextForm.topN, 10) || 10,
    minChangePct: Number.parseFloat(nextForm.minChangePct) || 7,
    minAmount: (Number.parseFloat(nextForm.minAmountYi) || 3) * 1e8,
    minTurnover: Number.parseFloat(nextForm.minTurnover) || 3,
    excludeSt: true,
    mainBoardOnly: true,
    tradeDate: nextForm.tradeDate || undefined,
  };
}

type PersistedState = {
  form: FormState;
  sortBy: SortKey;
  hasPersisted: boolean;
};

type WatchlistThemeSummary = {
  name: string;
  count: number;
};

type WatchlistSummary = {
  profile: MomentumProfile;
  tradeDate?: string;
  primaryCandidates: MomentumScreenerResult[];
  headlineCandidate: MomentumScreenerResult;
  lowRiskCandidate: MomentumScreenerResult | null;
  buyableCandidate: MomentumScreenerResult | null;
  hotThemes: WatchlistThemeSummary[];
  riskWarnings: string[];
  overview: string;
  actionHint: string;
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

function loadPersistedState(): PersistedState {
  if (typeof window === 'undefined') {
    return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
    }

    const parsed = JSON.parse(raw) as Partial<{ form: FormState; sortBy: SortKey }>;
    return {
      form: { ...DEFAULT_FORM, ...(parsed.form ?? {}) },
      sortBy: parsed.sortBy ?? DEFAULT_SORT,
      hasPersisted: true,
    };
  } catch {
    return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
  }
}

function buildFormFromSystemConfig(
  items: Array<{ key: string; value: string }> | undefined,
): FormState {
  const itemMap = new Map((items ?? []).map((item) => [item.key, item.value]));
  const profile = itemMap.get('MOMENTUM_SCREENER_DEFAULT_PROFILE');

  return {
    profile: profile === 'aggressive' ? 'aggressive' : DEFAULT_FORM.profile,
    topN: itemMap.get('MOMENTUM_SCREENER_DEFAULT_TOP_N') || DEFAULT_FORM.topN,
    minChangePct: itemMap.get('MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT') || DEFAULT_FORM.minChangePct,
    minAmountYi: itemMap.get('MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI') || DEFAULT_FORM.minAmountYi,
    minTurnover: itemMap.get('MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER') || DEFAULT_FORM.minTurnover,
    tradeDate: DEFAULT_FORM.tradeDate,
  };
}

function persistState(form: FormState, sortBy: SortKey) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ form, sortBy }));
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

function translateDimensionKey(key: string): string {
  return dimensionLabelLookup[normalizeMetricLookupKey(key)] ?? key;
}

function translateItemKey(key: string): string {
  return itemLabelLookup[normalizeMetricLookupKey(key)] ?? key;
}

function profileBadgeVariant(profile: MomentumProfile): 'default' | 'warning' {
  return profile === 'aggressive' ? 'warning' : 'default';
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

function strategyHealthBadgeVariant(
  status: MomentumSecondaryDecision['strategyHealth']['status'],
): 'success' | 'info' | 'warning' | 'danger' {
  if (status === 'healthy') return 'success';
  if (status === 'recovery_mode') return 'info';
  if (status === 'partial_healthy') return 'warning';
  return 'danger';
}

function strategyHealthWindowBadgeVariant(
  status: MomentumSecondaryDecision['strategyHealth']['shortWindow']['status'],
): 'success' | 'warning' | 'danger' {
  if (status === 'healthy') return 'success';
  if (status === 'recovering') return 'warning';
  return 'danger';
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

function intradayFinalRecommendationBadgeVariant(
  recommendation: MomentumIntradaySignal['finalRecommendation'],
): 'success' | 'warning' | 'danger' {
  if (recommendation === 'buy') return 'success';
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

function sortResults(results: MomentumScreenerResult[], sortBy: SortKey): MomentumScreenerResult[] {
  const sorted = [...results];
  sorted.sort((a, b) => {
    if (sortBy === 'risk_score') {
      return a.riskScore - b.riskScore || b.rankScore - a.rankScore;
    }

    if (sortBy === 'buyability_score') {
      return (b.buyabilityScore ?? -1) - (a.buyabilityScore ?? -1) || b.rankScore - a.rankScore;
    }

    if (sortBy === 'continuation_score') {
      return b.continuationScore - a.continuationScore || b.rankScore - a.rankScore;
    }

    if (sortBy === 'extension_score') {
      return b.extensionScore - a.extensionScore || b.rankScore - a.rankScore;
    }

    return b.rankScore - a.rankScore || b.finalScore - a.finalScore;
  });

  return sorted.map((item, index) => ({ ...item, rank: index + 1 }));
}

function buildCopyText(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  sortBy: SortKey,
  results: MomentumScreenerResult[],
): string {
  const sortLabel = SORT_OPTIONS.find((item) => item.value === sortBy)?.label ?? sortBy;
  const header = [
    '\u5f3a\u52bf\u7b5b\u9009\u7ed3\u679c',
    `\u753b\u50cf\uff1a${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    tradeDate ? `\u4ea4\u6613\u65e5\uff1a${tradeDate}` : null,
    `\u6392\u5e8f\u65b9\u5f0f\uff1a${sortLabel}`,
  ].filter(Boolean);

  const lines = results.map((item) => {
    const parts = [
      `#${item.rank}`,
      `${item.name}(${item.tsCode})`,
      `\u6da8\u5e45 ${item.pctChg.toFixed(2)}%`,
      `\u6392\u5e8f\u5206 ${item.rankScore.toFixed(1)}`,
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
    `排序分：${item.rankScore.toFixed(1)}`,
    `延续分：${item.continuationScore.toFixed(1)}`,
    `弹性分：${item.extensionScore.toFixed(1)}`,
    `风险分：${item.riskScore.toFixed(1)}`,
    item.buyabilityScore != null ? `可买分：${item.buyabilityScore.toFixed(1)}` : null,
    item.opportunityTag ? `机会标签：${item.opportunityTag}` : null,
    item.entryRangeLow != null && item.entryRangeHigh != null
      ? `建议区间：${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}`
      : null,
    `最终分：${item.finalScore.toFixed(1)}`,
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
    `- 排序分：${item.rankScore.toFixed(1)}`,
    `- 延续分：${item.continuationScore.toFixed(1)}`,
    `- 弹性分：${item.extensionScore.toFixed(1)}`,
    `- 风险分：${item.riskScore.toFixed(1)}`,
    `- 可买分：${item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'}`,
    `- 机会标签：${item.opportunityTag ?? '--'}`,
    `- 建议区间：${item.entryRangeLow != null && item.entryRangeHigh != null ? `${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)}` : '--'}`,
    `- 最终分：${item.finalScore.toFixed(1)}`,
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
  sortBy: SortKey,
  results: MomentumScreenerResult[],
): string {
  const sortLabel = SORT_OPTIONS.find((item) => item.value === sortBy)?.label ?? sortBy;
  const lines: string[] = [
    '# 强势筛选结果',
    '',
    `- 画像：${profile === 'aggressive' ? 'Aggressive' : 'Standard'}`,
    `- 交易日：${tradeDate ?? '--'}`,
    `- 排序方式：${sortLabel}`,
    `- 结果数量：${results.length}`,
    '',
    '| 排名 | 股票 | 涨幅 | 排序分 | 延续分 | 弹性分 | 风险分 | 可买分 | 板块 | 地位 |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |',
  ];

  for (const item of results) {
    lines.push(
      `| ${item.rank} | ${item.name} (${item.tsCode}) | ${item.pctChg.toFixed(2)}% | ${item.rankScore.toFixed(1)} | ${item.continuationScore.toFixed(1)} | ${item.extensionScore.toFixed(1)} | ${item.riskScore.toFixed(1)} | ${item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'} | ${item.themes[0] ?? '--'} | ${translateLeaderLevel(item.leaderLevel)} |`,
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
    'rank_score',
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
    item.rankScore.toFixed(1),
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

function getUniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function buildWatchlistSummary(
  profile: MomentumProfile,
  tradeDate: string | undefined,
  results: MomentumScreenerResult[],
): WatchlistSummary | null {
  if (results.length === 0) {
    return null;
  }

  const primaryCandidates = results.slice(0, Math.min(results.length, 3));
  const headlineCandidate = primaryCandidates[0];
  const lowRiskCandidate =
    [...results].sort((a, b) => a.riskScore - b.riskScore || b.rankScore - a.rankScore)[0] ?? null;
  const buyableCandidate =
    profile === 'aggressive'
      ? [...results]
          .filter((item) => item.buyabilityScore != null)
          .sort(
            (a, b) =>
              (b.buyabilityScore ?? -1) - (a.buyabilityScore ?? -1) || b.rankScore - a.rankScore,
          )[0] ?? null
      : null;

  const themeOrder: string[] = [];
  const themeCounts = new Map<string, number>();
  for (const item of results.slice(0, Math.min(results.length, 5))) {
    const theme = item.themes[0];
    if (!theme) {
      continue;
    }
    if (!themeCounts.has(theme)) {
      themeOrder.push(theme);
    }
    themeCounts.set(theme, (themeCounts.get(theme) ?? 0) + 1);
  }
  const hotThemes = [...themeCounts.entries()]
    .sort((a, b) => {
      if (b[1] !== a[1]) {
        return b[1] - a[1];
      }
      return themeOrder.indexOf(a[0]) - themeOrder.indexOf(b[0]);
    })
    .slice(0, 2)
    .map(([name, count]) => ({ name, count }));

  const riskWarnings = getUniqueValues(
    results
      .slice(0, Math.min(results.length, 5))
      .flatMap((item) => item.riskTags.map((tag) => translateRiskTag(tag))),
  ).slice(0, 3);

  const topNames = primaryCandidates.map((item) => `${item.name}(${item.tsCode})`).join('、');
  const leadingTheme = hotThemes[0]?.name;
  const overviewParts = [
    leadingTheme ? `当前强势方向集中在 ${leadingTheme}` : '当前题材分布偏分散',
    `优先观察 ${topNames}`,
  ];

  if (profile === 'aggressive' && buyableCandidate) {
    overviewParts.push(`进攻上优先看 ${buyableCandidate.name}`);
  } else if (lowRiskCandidate && lowRiskCandidate.tsCode !== headlineCandidate.tsCode) {
    overviewParts.push(`低风险跟踪可保留 ${lowRiskCandidate.name}`);
  }

  const actionHint =
    profile === 'aggressive'
      ? '先看龙头和前排的承接，再结合可买分与建议区间确认是否参与，不追高。'
      : '先看延续分与低风险的交集，优先保留量价结构更稳定、板块地位更靠前的标的。';

  return {
    profile,
    tradeDate,
    primaryCandidates,
    headlineCandidate,
    lowRiskCandidate,
    buyableCandidate,
    hotThemes,
    riskWarnings,
    overview: `${overviewParts.join('；')}。`,
    actionHint,
  };
}

function buildWatchlistSummaryText(summary: WatchlistSummary): string {
  const profileLabel = summary.profile === 'aggressive' ? 'Aggressive' : 'Standard';
  const lines = [
    '明日观察池摘要',
    `画像：${profileLabel}`,
    summary.tradeDate ? `交易日：${summary.tradeDate}` : null,
    '',
    `优先关注：${summary.primaryCandidates
      .map(
        (item) =>
          `#${item.rank} ${item.name}(${item.tsCode}) 排序分 ${item.rankScore.toFixed(1)} / 亮点 ${item.topReasons.slice(0, 2).join('、') || '--'}`,
      )
      .join('；')}`,
    summary.buyableCandidate
      ? `进攻首选：${summary.buyableCandidate.name}(${summary.buyableCandidate.tsCode}) 可买分 ${(summary.buyableCandidate.buyabilityScore ?? 0).toFixed(1)}`
      : null,
    summary.lowRiskCandidate
      ? `低风险优先：${summary.lowRiskCandidate.name}(${summary.lowRiskCandidate.tsCode}) 风险分 ${summary.lowRiskCandidate.riskScore.toFixed(1)}`
      : null,
    summary.hotThemes.length > 0
      ? `题材聚焦：${summary.hotThemes.map((item) => `${item.name} x${item.count}`).join('、')}`
      : '题材聚焦：当前结果更偏个股强度，暂无集中题材',
    summary.riskWarnings.length > 0
      ? `风险提醒：${summary.riskWarnings.join('、')}`
      : '风险提醒：Top 结果暂无明显共性风险标签，仍需盘中确认承接',
    `执行建议：${summary.actionHint}`,
  ].filter(Boolean);

  return lines.join('\n');
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
      </div>
    </div>
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
            <p className="mt-1 text-xs text-secondary-text">排序分 {item.rankScore.toFixed(1)}</p>
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
          <Badge variant="default">#{item.rank}</Badge>
          <Badge variant={buyPointBadgeVariant(item.buyPointStatus)}>{item.buyPointLabel}</Badge>
        </div>
        <p className="mt-3 text-base font-semibold text-foreground">{item.name}</p>
        <p className="mt-1 text-sm text-secondary-text">
          {item.tsCode} · {item.theme} · {item.role}
        </p>
      </div>
      <div className="text-right">
        <p className={`text-lg font-semibold ${scoreTone(item.score)}`}>{item.score.toFixed(1)}</p>
        <p className="mt-1 text-xs text-secondary-text">组合优先级</p>
      </div>
    </div>

    <div className="mt-4 flex flex-wrap gap-2">
      <Badge variant={decisionActionBadgeVariant(item.suggestedAction)}>{item.suggestedActionLabel}</Badge>
      <Badge variant="info">排序分 {item.rankScore.toFixed(1)}</Badge>
      <Badge variant="warning">风险分 {item.riskScore.toFixed(1)}</Badge>
      {item.opportunityTag ? <Badge variant="warning">{item.opportunityTag}</Badge> : null}
    </div>

    <div className="mt-4 space-y-3 text-sm leading-6 text-secondary-text">
      <p>
        <span className="font-medium text-foreground">主因：</span>
        {item.primaryReason}
      </p>
      <p>
        <span className="font-medium text-foreground">仓位理由：</span>
        {item.roleReason}
      </p>
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
            <Badge variant="default">{item.rankScore.toFixed(1)}</Badge>
          </div>
          <p className="mt-3 text-sm leading-6 text-secondary-text">
            <span className="font-medium text-foreground">主淘汰原因：</span>
            {item.reason}
          </p>
        </div>
      ))}
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
        <p className="text-sm font-semibold text-foreground">明日行动清单</p>
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

const StrategyHealthPanel: React.FC<{
  health: MomentumSecondaryDecision['strategyHealth'];
  onRefresh: () => void;
  refreshing: boolean;
  refreshDisabled: boolean;
}> = ({ health, onRefresh, refreshing, refreshDisabled }) => {
  const validationStatus = resolveStrategyHealthValidationStatus(health);
  const showRefresh = shouldShowStrategyHealthRefresh(health);
  const healthDataSourceLabel = buildStrategyHealthDataSourceLabel(health);
  const progressSummary = buildStrategyHealthProgressSummary(health);
  const capLabel =
    health.recommendationCap === 'full'
      ? '完整推荐'
      : health.recommendationCap === 'limited'
        ? '有限推荐'
        : '停用';
  const dataSourceLabel =
    health.dataSource === 'proxy'
      ? health.isWarming
        ? '历史验证计算中'
        : '代理结果'
      : '历史验证';

  return (
    <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/60 bg-hover/30 text-cyan">
          <Radar className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">策略健康</p>
            <Badge variant={strategyHealthBadgeVariant(health.status)}>{health.label}</Badge>
            <Badge variant="default">{capLabel}</Badge>
            <Badge variant={validationStatus === 'final' ? 'success' : 'warning'}>
              {healthDataSourceLabel || dataSourceLabel}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{health.reason}</p>
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
              首轮请求已切换为后台预热模式，页面先给你代理健康度，等真实 20/60 日历史结果算完后，点击下方“刷新真实 20/60 结果”即可看到正式结论。
            </p>
          ) : null}
        </div>
      </div>

      {showRefresh ? (
        <div className="mt-4 rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">真实 20/60 结果刷新</p>
              <p className="mt-1 text-xs leading-6 text-secondary-text">
                {health.isWarming
                  ? '后台正在计算真实历史验证；点击后会直接等待正式结果返回，不再只看代理健康度。'
                  : '当前仍是代理健康度；点击后会优先尝试返回真实 20/60 历史验证结果。'}
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
              刷新真实 20/60 结果
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {[health.shortWindow, health.longWindow].map((window) => (
          <div key={window.window} className="rounded-2xl border border-border/40 bg-hover/10 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-foreground">{window.windowLabel}</p>
              <Badge variant={strategyHealthWindowBadgeVariant(window.status)}>{window.statusLabel}</Badge>
            </div>
            <p className={`mt-3 text-lg font-semibold ${scoreTone(window.score)}`}>{window.score.toFixed(1)}</p>
            <p className="mt-1 text-xs text-secondary-text">健康阈值 {window.threshold.toFixed(1)}</p>
            <div className="mt-3 grid gap-2 text-xs text-secondary-text sm:grid-cols-2">
              <p>样本 {window.sampleCount} / 成功 {window.successCount}</p>
              <p>成功率 {window.successRate.toFixed(1)}%</p>
              <p>利润窗口 {window.avgProfitWindowPct.toFixed(2)}%</p>
              <p>平均回撤 {window.avgMaxDrawdownPct.toFixed(2)}%</p>
            </div>
            <p className="mt-3 text-sm leading-6 text-secondary-text">{window.summary}</p>
          </div>
        ))}
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
};

const SecondaryDecisionPanel: React.FC<SecondaryDecisionPanelProps> = ({
  decision,
  onRefresh,
  refreshing,
  refreshDisabled,
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
          <Badge variant="info">
            {decision.action.sourceProfile === 'aggressive' ? 'Aggressive 引擎' : 'Standard 引擎'}
          </Badge>
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
                <p className="mt-2 text-base leading-7 text-foreground">{decision.action.reason}</p>
              </div>
            </div>
          </div>

          <StrategyHealthPanel
            health={decision.strategyHealth}
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
            <div className="mb-3 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-cyan" />
              <p className="text-sm font-semibold text-foreground">落选说明</p>
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

type IntradaySignalPanelProps = {
  decision: MomentumSecondaryDecision | null;
  intradaySignal: MomentumIntradaySignal | null;
  loading: boolean;
  error: ParsedApiError | null;
  onRefresh: () => void;
  onDismissError: () => void;
};

const IntradaySignalPanel: React.FC<IntradaySignalPanelProps> = ({
  decision,
  intradaySignal,
  loading,
  error,
  onRefresh,
  onDismissError,
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
  const [sortBy, setSortBy] = useState<SortKey>(persisted.sortBy);
  const [response, setResponse] = useState<MomentumScreenerResponse | null>(null);
  const [decision, setDecision] = useState<MomentumSecondaryDecision | null>(null);
  const [intradaySignal, setIntradaySignal] = useState<MomentumIntradaySignal | null>(null);
  const [lastSubmittedPayload, setLastSubmittedPayload] = useState<MomentumScreenerRequest | null>(null);
  const [selectedResult, setSelectedResult] = useState<MomentumScreenerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [decisionRefreshing, setDecisionRefreshing] = useState(false);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [intradayError, setIntradayError] = useState<ParsedApiError | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  useEffect(() => {
    document.title = '强势筛选 - DSA';
  }, []);

  useEffect(() => {
    persistState(form, sortBy);
  }, [form, sortBy]);

  const runScreening = async (nextForm = form) => {
    setLoading(true);
    setError(null);
    setDecision(null);
    setIntradaySignal(null);
    setIntradayError(null);
    setSelectedResult(null);

    const payload = buildScreeningPayload(nextForm);
    setLastSubmittedPayload(payload);

    try {
      const data = await momentumScreenerApi.screenWithDecision(payload);
      setResponse(data.screening);
      setDecision(data.decision);
    } catch (err) {
      setError(getParsedApiError(err));
      setResponse(null);
      setDecision(null);
    } finally {
      setLoading(false);
    }
  };

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
      setIntradayError(null);
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
    } catch (err) {
      setIntradaySignal(null);
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
        const config = await systemConfigApi.getConfig(false);
        if (cancelled) {
          return;
        }

        const nextForm = buildFormFromSystemConfig(config.items);
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

  const sortedResults = useMemo(
    () => (response ? sortResults(response.results, sortBy) : []),
    [response, sortBy],
  );
  const selectedResultTsCode = selectedResult?.tsCode;

  useEffect(() => {
    if (sortedResults.length === 0) {
      setSelectedResult(null);
      return;
    }

    if (!selectedResultTsCode) {
      return;
    }

    const matched = sortedResults.find((item) => item.tsCode === selectedResultTsCode);
    setSelectedResult(matched ?? null);
  }, [sortedResults, selectedResultTsCode]);

  const averageRankScore = sortedResults.length
    ? sortedResults.reduce((sum, item) => sum + item.rankScore, 0) / sortedResults.length
    : 0;
  const watchlistSummary = useMemo(
    () => buildWatchlistSummary(response?.profile ?? form.profile, response?.tradeDate, sortedResults),
    [form.profile, response?.profile, response?.tradeDate, sortedResults],
  );
  const isBusy = loading || decisionRefreshing || intradayLoading;

  const handleCopyResults = async () => {
    if (sortedResults.length === 0) {
      setCopyFeedback('\u6682\u65e0\u53ef\u590d\u5236\u7684\u7ed3\u679c');
      return;
    }

    const text = buildCopyText(response?.profile ?? form.profile, response?.tradeDate, sortBy, sortedResults);
    try {
      await navigator.clipboard.writeText(text);
      setCopyFeedback('\u5df2\u590d\u5236\u5f53\u524d\u7b5b\u9009\u7ed3\u679c');
    } catch {
      setCopyFeedback('\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6d4f\u89c8\u5668\u526a\u8d34\u677f\u6743\u9650');
    }
  };

  const handleCopySingleResult = async (item: MomentumScreenerResult) => {
    const text = buildSingleResultText(response?.profile ?? form.profile, response?.tradeDate, item);

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

    const content = buildMarkdownText(response?.profile ?? form.profile, response?.tradeDate, sortBy, sortedResults);
    const datePart = (response?.tradeDate ?? form.tradeDate ?? 'latest').replace(/-/g, '');
    const fileName = `momentum_screener_${form.profile}_${datePart}.md`;
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
    const fileName = `momentum_screener_${form.profile}_${datePart}.csv`;
    downloadTextFile(content, fileName, 'text/csv;charset=utf-8');
    setCopyFeedback('\u5df2\u5bfc\u51fa CSV');
  };

  const handleExportSingleMarkdown = (item: MomentumScreenerResult) => {
    const content = buildSingleResultMarkdown(response?.profile ?? form.profile, response?.tradeDate, item);
    const datePart = (response?.tradeDate ?? form.tradeDate ?? 'latest').replace(/-/g, '');
    const fileName = `momentum_screener_${item.tsCode.replace('.', '_')}_${datePart}.md`;
    downloadTextFile(content, fileName, 'text/markdown;charset=utf-8');
    setCopyFeedback(`已导出 ${item.name} Markdown`);
  };

  const handleCopyWatchlistSummary = async () => {
    if (!watchlistSummary) {
      setCopyFeedback('暂无可复制的观察池摘要');
      return;
    }

    try {
      await navigator.clipboard.writeText(buildWatchlistSummaryText(watchlistSummary));
      setCopyFeedback('已复制明日观察池摘要');
    } catch {
      setCopyFeedback('复制失败，请检查浏览器剪贴板权限');
    }
  };

  const handleRestoreSystemDefaults = async () => {
    setLoading(true);
    setError(null);

    try {
      const config = await systemConfigApi.getConfig(false);
      const nextForm = buildFormFromSystemConfig(config.items);
      setForm(nextForm);
      setSortBy(DEFAULT_SORT);
      await runScreening(nextForm);
      setCopyFeedback('已恢复系统默认参数');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
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
            收盘后扫描今日强势股，按 Standard / Aggressive 两套画像输出次日候选。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={profileBadgeVariant(form.profile)} size="md">
            {form.profile === 'aggressive' ? 'Aggressive' : 'Standard'}
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
            <p className="mt-1 text-xs text-secondary-text">本页会自动记住上次使用的参数和排序方式。</p>
          </div>
          <div className="grid gap-3">
            <Select
              label="评分画像"
              id="momentum-screener-profile"
              value={form.profile}
              onChange={(value) => setForm((prev) => ({ ...prev, profile: value as MomentumProfile }))}
              options={PROFILE_OPTIONS}
            />
            <Input
              label="返回数量"
              type="number"
              min={1}
              max={100}
              value={form.topN}
              onChange={(event) => setForm((prev) => ({ ...prev, topN: event.target.value }))}
            />
            <Input
              label="最小涨幅 (%)"
              type="number"
              min={0}
              max={20}
              step="0.1"
              value={form.minChangePct}
              onChange={(event) => setForm((prev) => ({ ...prev, minChangePct: event.target.value }))}
            />
            <Input
              label="最小成交额 (亿)"
              type="number"
              min={0}
              step="0.5"
              value={form.minAmountYi}
              onChange={(event) => setForm((prev) => ({ ...prev, minAmountYi: event.target.value }))}
            />
            <Input
              label="最小换手率 (%)"
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={form.minTurnover}
              onChange={(event) => setForm((prev) => ({ ...prev, minTurnover: event.target.value }))}
            />
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
                loadingText="筛选中..."
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
                  setSortBy(DEFAULT_SORT);
                  void runScreening(DEFAULT_FORM);
                }}
              >
                重置
              </Button>
            </div>
          </div>
        </Card>

        <div className="flex min-h-0 flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
              subtext="当前页面展示的 TopN"
            />
            <SummaryCard
              icon={BarChart3}
              label="平均排序分"
              value={response ? averageRankScore.toFixed(1) : '--'}
              subtext="当前结果列表的 rank score 均值"
            />
            <SummaryCard
              icon={ShieldAlert}
              label="最高排序分"
              value={sortedResults[0] ? sortedResults[0].rankScore.toFixed(1) : '--'}
              subtext={sortedResults[0] ? `${sortedResults[0].name} 排名第 1` : '等待筛选结果'}
            />
          </div>

          <SecondaryDecisionPanel
            decision={decision}
            onRefresh={() => void handleRefreshDecision()}
            refreshing={decisionRefreshing}
            refreshDisabled={!decision || !lastSubmittedPayload || loading || intradayLoading}
          />
          <IntradaySignalPanel
            decision={decision}
            intradaySignal={intradaySignal}
            loading={intradayLoading}
            error={intradayError}
            onRefresh={() => void handleRefreshIntradaySignal()}
            onDismissError={() => setIntradayError(null)}
          />

          <Card className="rounded-3xl border-border/60 bg-card/55">
            <div data-testid="momentum-screener-watchlist-summary">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-4">
                <div>
                  <p className="text-sm font-semibold text-foreground">明日观察池摘要</p>
                  <p className="mt-1 text-xs text-secondary-text">
                    把排序结果压缩成可直接复盘和分享的观察清单，减少手工整理。
                  </p>
                </div>
                <Button
                  data-testid="momentum-screener-copy-watchlist-summary"
                  variant="ghost"
                  disabled={!watchlistSummary}
                  onClick={() => void handleCopyWatchlistSummary()}
                >
                  复制观察池摘要
                </Button>
              </div>

              {!watchlistSummary ? (
                <div className="pt-4">
                  <EmptyState
                    title="暂无观察池摘要"
                    description="先执行一次筛选，系统会自动帮你整理出明日优先关注列表。"
                  />
                </div>
              ) : (
                <div className="grid gap-4 pt-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
                  <div className="rounded-2xl border border-border/60 bg-hover/20 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="info">自动整理</Badge>
                      <Badge variant={profileBadgeVariant(watchlistSummary.profile)}>
                        {watchlistSummary.profile === 'aggressive' ? 'Aggressive' : 'Standard'}
                      </Badge>
                      {watchlistSummary.tradeDate ? (
                        <Badge variant="default">{watchlistSummary.tradeDate}</Badge>
                      ) : null}
                    </div>
                    <p className="mt-3 text-sm leading-7 text-foreground">{watchlistSummary.overview}</p>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      {watchlistSummary.primaryCandidates.map((item) => (
                        <div
                          key={item.tsCode}
                          className="rounded-2xl border border-border/50 bg-card/55 p-4"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <Badge variant="default">#{item.rank}</Badge>
                            <Badge variant={leaderBadgeVariant(item.leaderLevel)}>
                              {translateLeaderLevel(item.leaderLevel)}
                            </Badge>
                          </div>
                          <p className="mt-3 text-sm font-semibold text-foreground">
                            {item.name}
                          </p>
                          <p className="mt-1 text-xs text-secondary-text">{item.tsCode}</p>
                          <p className={`mt-3 text-lg font-semibold ${scoreTone(item.rankScore)}`}>
                            {item.rankScore.toFixed(1)}
                          </p>
                          <p className="mt-1 text-xs text-secondary-text">
                            排序分 · {item.themes[0] ?? '未标记题材'}
                          </p>
                          <p className="mt-3 text-xs leading-6 text-secondary-text">
                            {item.topReasons.slice(0, 2).join('、') || '等待亮点标签'}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-3">
                    <div className="rounded-2xl border border-border/60 bg-card/45 p-4">
                      <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">
                        {watchlistSummary.profile === 'aggressive' ? '进攻首选' : '低风险优先'}
                      </p>
                      <p className="mt-2 text-base font-semibold text-foreground">
                        {(watchlistSummary.profile === 'aggressive'
                          ? watchlistSummary.buyableCandidate?.name
                          : watchlistSummary.lowRiskCandidate?.name) ?? watchlistSummary.headlineCandidate.name}
                      </p>
                      <p className="mt-1 text-sm text-secondary-text">
                        {(watchlistSummary.profile === 'aggressive'
                          ? watchlistSummary.buyableCandidate?.tsCode
                          : watchlistSummary.lowRiskCandidate?.tsCode) ?? watchlistSummary.headlineCandidate.tsCode}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-secondary-text">
                        {watchlistSummary.profile === 'aggressive'
                          ? `可买分 ${(
                              watchlistSummary.buyableCandidate?.buyabilityScore ??
                              watchlistSummary.headlineCandidate.buyabilityScore ??
                              0
                            ).toFixed(1)}，优先配合承接和区间确认。`
                          : `风险分 ${(
                              watchlistSummary.lowRiskCandidate?.riskScore ??
                              watchlistSummary.headlineCandidate.riskScore
                            ).toFixed(1)}，更适合保守观察和次日跟踪。`}
                      </p>
                    </div>

                    <div className="rounded-2xl border border-border/60 bg-card/45 p-4">
                      <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">题材聚焦</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {watchlistSummary.hotThemes.length > 0 ? (
                          watchlistSummary.hotThemes.map((theme) => (
                            <Badge key={theme.name} variant="info">
                              {theme.name} x{theme.count}
                            </Badge>
                          ))
                        ) : (
                          <Badge variant="default">暂无集中题材</Badge>
                        )}
                      </div>
                    </div>

                    <div className="rounded-2xl border border-border/60 bg-card/45 p-4">
                      <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">风险提醒</p>
                      <p className="mt-3 text-sm leading-6 text-secondary-text">
                        {watchlistSummary.riskWarnings.length > 0
                          ? watchlistSummary.riskWarnings.join('、')
                          : 'Top 结果暂无明显共性风险标签，仍需盘中确认承接。'}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-secondary-text">
                        {watchlistSummary.actionHint}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card className="min-h-0 flex-1 overflow-hidden rounded-3xl border-border/60 bg-card/55">
            <div className="mb-4 flex items-center justify-between gap-3 border-b border-border/60 pb-4">
              <div>
                <p className="text-sm font-semibold text-foreground">筛选结果</p>
                <p className="mt-1 text-xs text-secondary-text">支持按不同指标重新排序，点击行可查看维度拆解。</p>
              </div>
              <div className="flex items-end gap-2">
                <div className="w-[180px]">
                  <Select
                    label="排序方式"
                    id="momentum-screener-sort"
                    value={sortBy}
                    onChange={(value) => setSortBy(value as SortKey)}
                    options={SORT_OPTIONS}
                  />
                </div>
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
                description="先执行一次筛选，或调整涨幅、成交额和换手率参数。"
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-border/60 text-xs uppercase tracking-[0.12em] text-secondary-text">
                    <tr>
                      <th className="px-3 py-3">排名</th>
                      <th className="px-3 py-3">股票</th>
                      <th className="px-3 py-3">涨幅</th>
                      <th className="px-3 py-3">排序分</th>
                      <th className="px-3 py-3">延续分</th>
                      <th className="px-3 py-3">弹性分</th>
                      <th className="px-3 py-3">风险分</th>
                      <th className="px-3 py-3">可买分</th>
                      <th className="px-3 py-3">板块</th>
                      <th className="px-3 py-3">地位</th>
                      <th className="px-3 py-3">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedResults.map((item) => (
                      <tr
                        key={item.tsCode}
                        data-testid={`momentum-screener-row-${item.tsCode}`}
                        className="cursor-pointer border-b border-border/40 transition-colors hover:bg-hover/40"
                        onClick={() => setSelectedResult(item)}
                      >
                        <td className="px-3 py-3 font-mono text-foreground">#{item.rank}</td>
                        <td className="px-3 py-3">
                          <div>
                            <p className="font-medium text-foreground">{item.name}</p>
                            <p className="mt-1 text-xs text-secondary-text">{item.tsCode}</p>
                          </div>
                        </td>
                        <td className="px-3 py-3 font-medium text-danger">+{item.pctChg.toFixed(2)}%</td>
                        <td className={`px-3 py-3 font-semibold ${scoreTone(item.rankScore)}`}>{item.rankScore.toFixed(1)}</td>
                        <td className="px-3 py-3 text-foreground">{item.continuationScore.toFixed(1)}</td>
                        <td className="px-3 py-3 text-foreground">{item.extensionScore.toFixed(1)}</td>
                        <td className="px-3 py-3 text-warning">{item.riskScore.toFixed(1)}</td>
                        <td className="px-3 py-3 text-cyan">{item.buyabilityScore != null ? item.buyabilityScore.toFixed(1) : '--'}</td>
                        <td className="px-3 py-3 text-secondary-text">{item.themes[0] ?? '--'}</td>
                        <td className="px-3 py-3">
                          <Badge variant={leaderBadgeVariant(item.leaderLevel)}>{translateLeaderLevel(item.leaderLevel)}</Badge>
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex gap-2">
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
                    ))}
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
        title={selectedResult ? `${selectedResult.name} · ${selectedResult.tsCode}` : undefined}
        width="max-w-3xl"
      >
        {selectedResult ? (
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-4">
              <SummaryCard icon={Flame} label="最终总分" value={selectedResult.finalScore.toFixed(1)} />
              <SummaryCard icon={TrendingUp} label="排序分" value={selectedResult.rankScore.toFixed(1)} />
              <SummaryCard icon={Radar} label="延续分" value={selectedResult.continuationScore.toFixed(1)} />
              <SummaryCard icon={ShieldAlert} label="风险分" value={selectedResult.riskScore.toFixed(1)} />
            </div>

            {response?.profile === 'aggressive' ? (
              <div className="grid gap-3 md:grid-cols-3">
                <SummaryCard
                  icon={BarChart3}
                  label="可买分"
                  value={selectedResult.buyabilityScore != null ? selectedResult.buyabilityScore.toFixed(1) : '--'}
                />
                <SummaryCard
                  icon={TrendingUp}
                  label="机会标签"
                  value={selectedResult.opportunityTag ?? '--'}
                />
                <SummaryCard
                  icon={Radar}
                  label="建议区间"
                  value={formatEntryRange(selectedResult) || '--'}
                />
              </div>
            ) : null}

            <Card className="rounded-2xl border-border/60 bg-card/45">
              <div className="flex flex-wrap gap-2">
                <Badge variant={leaderBadgeVariant(selectedResult.leaderLevel)}>{translateLeaderLevel(selectedResult.leaderLevel)}</Badge>
                {selectedResult.themes.map((theme) => (
                  <Badge key={theme} variant="default">{theme}</Badge>
                ))}
                {selectedResult.opportunityTag ? (
                  <Badge variant="warning">{selectedResult.opportunityTag}</Badge>
                ) : null}
                {selectedResult.topReasons.map((reason) => (
                  <Badge key={reason} variant="success">{reason}</Badge>
                ))}
                {selectedResult.riskTags.map((tag) => (
                  <Badge key={tag} variant="warning">{translateRiskTag(tag)}</Badge>
                ))}
              </div>
            </Card>

            <Card className="rounded-2xl border-border/60 bg-card/45">
              <p className="mb-3 text-sm font-semibold text-foreground">维度拆解</p>
              <div className="space-y-3">
                {Object.entries(selectedResult.scoreBreakdown).map(([key, value]) => (
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
    </div>
  );
};

export default MomentumScreenerPage;
