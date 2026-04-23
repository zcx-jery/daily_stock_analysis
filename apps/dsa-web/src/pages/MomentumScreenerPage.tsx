import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Flame, ListChecks, Radar, RefreshCw, ShieldAlert, Sparkles, Target, TrendingUp } from 'lucide-react';
import { momentumScreenerApi } from '../api/momentumScreener';
import { systemConfigApi } from '../api/systemConfig';
import ScreenerAiDrawer from '../components/screener/ScreenerAiDrawer';
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
import type { MomentumScreenerAiReviewTarget } from '../types/momentumScreenerAi';
import { useMomentumScreenerAiStore } from '../stores/momentumScreenerAiStore';

type FormState = {
  tradeDate: string;
};

type SelectedResultState = {
  source: MomentumProfile;
  item: MomentumScreenerResult;
};

type SortKey = 'rank_score' | 'continuation_score' | 'extension_score' | 'risk_score' | 'buyability_score';

const STORAGE_KEY = 'dsa.momentum-screener.page-state';
const OFFICIAL_TOP_N = 30;

const SORT_OPTIONS = [
  { value: 'rank_score', label: '按排序分' },
  { value: 'continuation_score', label: '按延续分' },
  { value: 'extension_score', label: '按弹性分' },
  { value: 'risk_score', label: '按低风险优先' },
  { value: 'buyability_score', label: '按可买分' },
];

const DEFAULT_FORM: FormState = {
  tradeDate: '',
};

const DEFAULT_SORT: SortKey = 'rank_score';

function buildScreeningPayload(nextForm: FormState): MomentumScreenerRequest {
  return {
    profile: 'standard',
    topN: OFFICIAL_TOP_N,
    tradeDate: nextForm.tradeDate || undefined,
  };
}

type PersistedState = {
  form: FormState;
  sortBy: SortKey;
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
    return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
    }

    const parsed = JSON.parse(raw) as Partial<{ form: Partial<FormState>; sortBy: SortKey }>;
    const parsedForm = parsed.form;
    return {
      form: { tradeDate: parsedForm?.tradeDate ?? DEFAULT_FORM.tradeDate },
      sortBy: parsed.sortBy ?? DEFAULT_SORT,
      hasPersisted: true,
    };
  } catch {
    return { form: DEFAULT_FORM, sortBy: DEFAULT_SORT, hasPersisted: false };
  }
}

function buildFormFromSystemConfig(): FormState {
  return {
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
                    <p className={`text-lg font-semibold ${scoreTone(item.rankScore)}`}>
                      {item.rankScore.toFixed(1)}
                    </p>
                    <p className="mt-1 text-xs text-secondary-text">进攻排序分</p>
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

type IntradaySignalPanelProps = {
  decision: MomentumSecondaryDecision | null;
  intradaySignal: MomentumIntradaySignal | null;
  loading: boolean;
  error: ParsedApiError | null;
  onRefresh: () => void;
  onDismissError: () => void;
  onAiReview: () => void;
};

const IntradaySignalPanel: React.FC<IntradaySignalPanelProps> = ({
  decision,
  intradaySignal,
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
  const [aggressiveResponse, setAggressiveResponse] = useState<MomentumScreenerResponse | null>(null);
  const [decision, setDecision] = useState<MomentumSecondaryDecision | null>(null);
  const [intradaySignal, setIntradaySignal] = useState<MomentumIntradaySignal | null>(null);
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

  useEffect(() => {
    document.title = '强势筛选 - DSA';
  }, []);

  useEffect(() => {
    persistState(form, sortBy);
  }, [form, sortBy]);

  const openMomentumAiPanel = async (target: MomentumScreenerAiReviewTarget) => {
    await openAiPanel(target);
  };

  const loadAggressiveSupplement = async (payload: MomentumScreenerRequest) => {
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
  };

  const runScreening = async (nextForm = form) => {
    setLoading(true);
    setError(null);
    setDecision(null);
    setIntradaySignal(null);
    setIntradayError(null);
    setSelectedResult(null);
    setAggressiveResponse(null);
    setAggressiveError(null);

    const payload = buildScreeningPayload(nextForm);
    setLastSubmittedPayload(payload);

    try {
      const data = await momentumScreenerApi.screenWithDecision(payload);
      setResponse(data.screening);
      setDecision(data.decision);
      void loadAggressiveSupplement(payload);
    } catch (err) {
      setError(getParsedApiError(err));
      setResponse(null);
      setDecision(null);
      setAggressiveResponse(null);
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

  const sortedResults = useMemo(
    () => (response ? sortResults(response.results, sortBy) : []),
    [response, sortBy],
  );
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
          b.rankScore - a.rankScore ||
          b.finalScore - a.finalScore,
      )
      .slice(0, 2)
      .map((item, index) => ({ ...item, rank: index + 1 }));
  }, [aggressiveResponse, decision?.portfolio]);
  const selectedResultTsCode = selectedResult?.item.tsCode;
  const selectedResultSource = selectedResult?.source;

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

  const averageRankScore = sortedResults.length
    ? sortedResults.reduce((sum, item) => sum + item.rankScore, 0) / sortedResults.length
    : 0;
  const isBusy = loading || decisionRefreshing || intradayLoading;

  const buildAiTargetBase = (): Pick<
    MomentumScreenerAiReviewTarget,
    'payload' | 'screening' | 'decision' | 'intradaySignal'
  > | null => {
    if (!lastSubmittedPayload || !response) {
      return null;
    }
    return {
      payload: lastSubmittedPayload,
      screening: response,
      decision,
      intradaySignal,
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

    const text = buildCopyText('standard', response?.tradeDate, sortBy, sortedResults);
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

    const content = buildMarkdownText('standard', response?.tradeDate, sortBy, sortedResults);
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
    setLoading(true);
    setError(null);

    try {
      await systemConfigApi.getConfig(false);
      const nextForm = buildFormFromSystemConfig();
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
              subtext="官方固定展示 Top30"
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
              <SummaryCard icon={Flame} label="最终总分" value={selectedResult.item.finalScore.toFixed(1)} />
              <SummaryCard icon={TrendingUp} label="排序分" value={selectedResult.item.rankScore.toFixed(1)} />
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

