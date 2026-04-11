import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Flame, Radar, ShieldAlert, TrendingUp } from 'lucide-react';
import { momentumScreenerApi } from '../api/momentumScreener';
import { systemConfigApi } from '../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Drawer, EmptyState, Input, Select } from '../components/common';
import type {
  MomentumProfile,
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

const riskTagLabelMap: Record<string, string> = {
  upper_shadow: '长上影/冲高回落',
  blowoff_volume: '爆量滞涨',
  late_session_weakness: '尾盘走弱',
  high_acceleration: '高位连续加速',
  price_flow_divergence: '价资背离',
  sector_fade: '板块退潮',
  top_list_distribution: '龙虎榜偏兑现',
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

function translateItemKey(key: string): string {
  return itemLabelMap[key] ?? key;
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

const MomentumScreenerPage: React.FC = () => {
  const persisted = useMemo(() => loadPersistedState(), []);
  const [form, setForm] = useState<FormState>(persisted.form);
  const [sortBy, setSortBy] = useState<SortKey>(persisted.sortBy);
  const [response, setResponse] = useState<MomentumScreenerResponse | null>(null);
  const [selectedResult, setSelectedResult] = useState<MomentumScreenerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
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

    const payload: MomentumScreenerRequest = {
      profile: nextForm.profile,
      topN: Number.parseInt(nextForm.topN, 10) || 10,
      minChangePct: Number.parseFloat(nextForm.minChangePct) || 7,
      minAmount: (Number.parseFloat(nextForm.minAmountYi) || 3) * 1e8,
      minTurnover: Number.parseFloat(nextForm.minTurnover) || 3,
      excludeSt: true,
      mainBoardOnly: true,
      tradeDate: nextForm.tradeDate || undefined,
    };

    try {
      const data = await momentumScreenerApi.screen(payload);
      setResponse(data);
    } catch (err) {
      setError(getParsedApiError(err));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const initialize = async () => {
      if (persisted.hasPersisted) {
        await runScreening(persisted.form);
        return;
      }

      try {
        const config = await systemConfigApi.getConfig(false);
        if (cancelled) {
          return;
        }

        const nextForm = buildFormFromSystemConfig(config.items);
        setForm(nextForm);
        await runScreening(nextForm);
      } catch {
        if (cancelled) {
          return;
        }
        await runScreening(DEFAULT_FORM);
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

  useEffect(() => {
    if (sortedResults.length === 0) {
      setSelectedResult(null);
      return;
    }

    if (!selectedResult) {
      setSelectedResult(sortedResults[0]);
      return;
    }

    const matched = sortedResults.find((item) => item.tsCode === selectedResult.tsCode);
    setSelectedResult(matched ?? sortedResults[0]);
  }, [sortedResults, selectedResult?.tsCode]);

  const averageRankScore = sortedResults.length
    ? sortedResults.reduce((sum, item) => sum + item.rankScore, 0) / sortedResults.length
    : 0;

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
    <div className="flex h-[calc(100vh-5rem)] flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
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

      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="rounded-3xl border-border/60 bg-card/55">
          <div className="mb-4">
            <p className="text-sm font-semibold text-foreground">筛选参数</p>
            <p className="mt-1 text-xs text-secondary-text">本页会自动记住上次使用的参数和排序方式。</p>
          </div>
          <div className="grid gap-3">
            <Select
              label="评分画像"
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
              hint="留空时默认使用最近一个有效交易日。"
            />
            <div className="mt-2 flex gap-2">
              <Button
                variant="home-action-ai"
                className="flex-1"
                isLoading={loading}
                loadingText="筛选中..."
                onClick={() => void runScreening()}
              >
                执行筛选
              </Button>
              <Button
                variant="ghost"
                className="flex-1"
                disabled={loading}
                onClick={() => void handleRestoreSystemDefaults()}
              >
                恢复系统默认
              </Button>
              <Button
                variant="ghost"
                className="flex-1"
                disabled={loading}
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
                    value={sortBy}
                    onChange={(value) => setSortBy(value as SortKey)}
                    options={SORT_OPTIONS}
                  />
                </div>
                <Button
                  variant="ghost"
                  className="mb-[2px]"
                  disabled={sortedResults.length === 0}
                  onClick={() => void handleCopyResults()}
                >
                  复制结果
                </Button>
                <Button
                  variant="ghost"
                  className="mb-[2px]"
                  disabled={sortedResults.length === 0}
                  onClick={handleExportMarkdown}
                >
                  导出 Markdown
                </Button>
                <Button
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
                        <p className="text-sm font-medium text-foreground">{dimensionLabelMap[key] ?? key}</p>
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
                          <p className="text-[11px] uppercase tracking-[0.12em] text-secondary-text">
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
