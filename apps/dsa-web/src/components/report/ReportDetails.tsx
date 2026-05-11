import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import type { ReportDetails as ReportDetailsType, ReportLanguage } from '../../types/analysis';
import { Badge, Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportDetailsProps {
  details?: ReportDetailsType;
  recordId?: number;  // 分析历史记录主键 ID
  language?: ReportLanguage;
}

const isNonEmptyObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value) && Object.keys(value).length > 0;

const coerceNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === 'string') {
    const parsed = Number(value.trim().replace(/%$/, ''));
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const formatPercent = (value: unknown): string | undefined => {
  const numeric = coerceNumber(value);
  if (numeric === undefined) {
    return undefined;
  }
  const percent = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
  return `${percent.toFixed(1)}%`;
};

const formatNumber = (value: unknown, digits = 2): string | undefined => {
  const numeric = coerceNumber(value);
  if (numeric === undefined) {
    return undefined;
  }
  return numeric.toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
};

const PROVIDER_LABELS: Record<string, string> = {
  'tushare.daily_basic': 'Tushare 估值/交易指标',
  'tushare.fina_indicator': 'Tushare 财务指标',
  'tushare.dividend': 'Tushare 分红数据',
  'tushare.performance_events': 'Tushare 业绩预告/快报',
  'tushare.moneyflow_ths': '同花顺资金流',
  'tushare.moneyflow_dc': '东方财富资金流',
  'tushare.ths_member': '同花顺板块成分',
  'tushare.ths_index': '同花顺板块指数',
  'tushare.cyq_perf': 'Tushare 筹码表现',
  'tushare.cyq_chips': 'Tushare 筹码分布',
};

const formatProvider = (value: unknown): string | undefined => {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  if (PROVIDER_LABELS[trimmed]) {
    return PROVIDER_LABELS[trimmed];
  }
  const parts = trimmed.split('.');
  const compactProvider = parts.length > 1 ? parts.slice(-2).join('.') : trimmed;
  return PROVIDER_LABELS[compactProvider] || compactProvider;
};

const getStatusVariant = (status?: string): 'default' | 'success' | 'warning' | 'danger' | 'info' => {
  const normalized = (status || '').toLowerCase();
  if (['ok', 'complete', 'success', 'aligned', 'leading'].includes(normalized)) {
    return 'success';
  }
  if (['partial', 'fallback', 'stale', 'lagging'].includes(normalized)) {
    return 'warning';
  }
  if (['failed', 'error', 'missing', 'permission_denied'].includes(normalized)) {
    return 'danger';
  }
  if (['not_supported', 'isolated'].includes(normalized)) {
    return 'default';
  }
  return 'info';
};

const STATUS_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    ok: '正常',
    complete: '完整',
    success: '成功',
    partial: '部分可用',
    fallback: '降级',
    stale: '数据滞后',
    lagging: '板块偏弱',
    failed: '失败',
    error: '异常',
    missing: '缺失',
    permission_denied: '权限/积分不足',
    not_supported: '不支持',
    aligned: '强势联动',
    leading: '领先',
    isolated: '未联动',
  },
  en: {
    ok: 'OK',
    complete: 'Complete',
    success: 'Success',
    partial: 'Partial',
    fallback: 'Fallback',
    stale: 'Stale',
    lagging: 'Lagging',
    failed: 'Failed',
    error: 'Error',
    missing: 'Missing',
    permission_denied: 'Permission/points required',
    not_supported: 'Not supported',
    aligned: 'Aligned',
    leading: 'Leading',
    isolated: 'Isolated',
  },
};

const getStatusLabel = (status?: string, language: ReportLanguage = 'zh'): string | undefined => {
  if (!status) {
    return undefined;
  }
  const normalized = status.toLowerCase();
  return STATUS_LABELS[language][normalized] || status;
};

const BOARD_STATUS_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    aligned: '命中强势板块',
    leading: '板块共振偏强',
    lagging: '所属板块偏弱',
    isolated: '暂无板块共振',
    partial: '板块数据部分可用',
    failed: '板块数据不可用',
  },
  en: {
    aligned: 'Strong sector alignment',
    leading: 'Sector tailwind',
    lagging: 'Sector lagging',
    isolated: 'No clear sector linkage',
    partial: 'Partial sector data',
    failed: 'Sector data unavailable',
  },
};

const CAPITAL_SIGNAL_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    inflow_confirmed: '资金流入确认',
    outflow_confirmed: '资金流出确认',
    mixed_signal: '资金信号分歧',
    neutral: '资金中性',
    missing: '暂无资金信号',
  },
  en: {
    inflow_confirmed: 'Confirmed inflow',
    outflow_confirmed: 'Confirmed outflow',
    mixed_signal: 'Mixed flow signal',
    neutral: 'Neutral flow',
    missing: 'No flow signal',
  },
};

const CHIP_SIGNAL_LABELS: Record<ReportLanguage, Record<string, string>> = {
  zh: {
    supportive: '筹码支撑较好',
    neutral: '筹码中性',
    overheated: '获利盘偏高',
    weak: '筹码支撑不足',
    missing: '暂无筹码信号',
  },
  en: {
    supportive: 'Supportive chip profile',
    neutral: 'Neutral chip profile',
    overheated: 'Profit-taking pressure elevated',
    weak: 'Weak chip support',
    missing: 'No chip signal',
  },
};

const getMappedLabel = (
  mapping: Record<ReportLanguage, Record<string, string>>,
  value?: string,
  language: ReportLanguage = 'zh',
): string | undefined => {
  if (!value) {
    return undefined;
  }
  const normalized = value.toLowerCase();
  return mapping[language][normalized] || getStatusLabel(value, language) || value;
};

const getCoverageSummary = (coverage?: Record<string, string>): string | undefined => {
  if (!coverage) {
    return undefined;
  }
  const entries = Object.values(coverage);
  if (!entries.length) {
    return undefined;
  }
  const okCount = entries.filter((status) => ['ok', 'complete', 'partial'].includes(String(status).toLowerCase())).length;
  return `${okCount}/${entries.length}`;
};

const pickRecordValue = (record: Record<string, unknown>, keys: string[]): unknown => {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== '') {
      return value;
    }
  }
  return undefined;
};

const joinBoardNames = (boards?: Array<{ name?: string }>, limit = 2): string | undefined => {
  if (!boards?.length) {
    return undefined;
  }
  const names = boards
    .map((board) => board.name?.trim())
    .filter((name): name is string => Boolean(name))
    .slice(0, limit);
  return names.length ? names.join(' / ') : undefined;
};

const pickBoardNames = (boards?: Array<{ name?: string }>, limit = 4): string[] =>
  boards
    ?.map((board) => board.name?.trim())
    .filter((name): name is string => Boolean(name))
    .slice(0, limit) ?? [];

/**
 * 透明度与追溯区组件 - 终端风格
 */
export const ReportDetails: React.FC<ReportDetailsProps> = ({
  details,
  recordId,
  language = 'zh',
}) => {
  type JsonPanel = 'raw' | 'snapshot';
  type CopiedPanelState = Record<JsonPanel, boolean>;

  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const [showRaw, setShowRaw] = useState(false);
  const [showSnapshot, setShowSnapshot] = useState(false);
  const [copiedPanels, setCopiedPanels] = useState<CopiedPanelState>({
    raw: false,
    snapshot: false,
  });
  const copyResetTimerRef = useRef<Partial<Record<JsonPanel, number>>>({});
  const financialReport = isNonEmptyObject(details?.financialReport) ? details.financialReport : {};
  const dividendMetrics = isNonEmptyObject(details?.dividendMetrics) ? details.dividendMetrics : {};
  const fundamentalMetrics = details?.fundamentalMetrics;
  const valuationMetrics = isNonEmptyObject(fundamentalMetrics?.valuation) ? fundamentalMetrics.valuation : {};
  const profitabilityMetrics = isNonEmptyObject(fundamentalMetrics?.profitability) ? fundamentalMetrics.profitability : {};
  const growthMetrics = isNonEmptyObject(fundamentalMetrics?.growth) ? fundamentalMetrics.growth : {};
  const hasFundamentalSummary = Boolean(
    isNonEmptyObject(financialReport)
    || isNonEmptyObject(dividendMetrics)
    || isNonEmptyObject(valuationMetrics)
    || isNonEmptyObject(profitabilityMetrics)
    || isNonEmptyObject(growthMetrics),
  );
  const hasBoardSummary = Boolean(
    details?.boardLinkage
    || details?.belongBoards?.length
    || details?.sectorRankings?.top?.length
    || details?.sectorRankings?.bottom?.length,
  );
  const hasEvidenceDetails = Boolean(
    hasFundamentalSummary
    || hasBoardSummary
    || details?.capitalFlowMetrics
    || details?.chipMetrics
    || details?.dataQuality
    || details?.tushareEnhancement,
  );

  useEffect(() => {
    return () => {
      Object.values(copyResetTimerRef.current).forEach((timerId) => {
        if (timerId !== undefined) {
          window.clearTimeout(timerId);
        }
      });
      copyResetTimerRef.current = {};
    };
  }, []);

  if (!details?.rawResult && !details?.contextSnapshot && !recordId && !hasEvidenceDetails) {
    return null;
  }

  const copyToClipboard = async (content: string, panel: JsonPanel) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedPanels((prev) => ({
        ...prev,
        [panel]: true,
      }));
      const existingTimer = copyResetTimerRef.current[panel];
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }
      copyResetTimerRef.current[panel] = window.setTimeout(() => {
        setCopiedPanels((prev) => ({
          ...prev,
          [panel]: false,
        }));
        delete copyResetTimerRef.current[panel];
      }, 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  const renderJson = (data: unknown, panel: JsonPanel) => {
    const jsonStr = JSON.stringify(data, null, 2);
    return (
      <div className="relative overflow-hidden">
        <span className="absolute top-2 right-2 z-10 inline-flex">
          <button
            type="button"
            onClick={() => copyToClipboard(jsonStr, panel)}
            className="home-accent-link text-xs text-muted-text"
            aria-label={copiedPanels[panel] ? text.copied : text.copy}
          >
            {copiedPanels[panel] ? text.copied : text.copy}
          </button>
        </span>
        <pre className="home-trace-pre home-trace-pre-content text-xs text-foreground font-mono overflow-x-auto p-3 bg-base rounded-lg max-h-80 overflow-y-auto text-left w-0 min-w-full">
          {jsonStr}
        </pre>
      </div>
    );
  };

  const renderEvidenceItem = (label: string, value?: string | number | null) => {
    if (value === undefined || value === null || value === '') {
      return null;
    }
    return (
      <div className="min-w-0">
        <dt className="text-[10px] uppercase tracking-[0.14em] text-muted-text">{label}</dt>
        <dd className="mt-1 truncate text-xs font-medium text-foreground">{value}</dd>
      </div>
    );
  };

  const renderEvidenceSummary = (summary?: string) => {
    if (!summary) {
      return null;
    }
    return (
      <p className="mb-3 rounded-md border border-border/60 bg-base/40 px-2.5 py-2 text-xs leading-5 text-foreground">
        {summary}
      </p>
    );
  };

  const renderNameChips = (names: string[]) => {
    if (!names.length) {
      return null;
    }
    return (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {names.map((name) => (
          <span
            key={name}
            className="max-w-full rounded border border-border/70 px-2 py-1 text-[11px] leading-none text-muted-text"
            title={name}
          >
            {name}
          </span>
        ))}
      </div>
    );
  };

  const capitalFlow = details?.capitalFlowMetrics;
  const chipMetrics = details?.chipMetrics;
  const chipData = isNonEmptyObject(chipMetrics?.data) ? chipMetrics.data : {};
  const chipProfitRatio = chipData.profitRatio ?? chipData.profit_ratio;
  const flowSource = capitalFlow?.sourceChain?.map((source) => formatProvider(source.provider)).find(Boolean);
  const chipSource = formatProvider(chipMetrics?.source) || chipMetrics?.sourceChain?.map((source) => formatProvider(source.provider)).find(Boolean);
  const coverageSummary = getCoverageSummary(details?.dataQuality?.coverage);
  const fundamentalStatus = fundamentalMetrics?.statuses?.valuation
    || fundamentalMetrics?.statuses?.profitability
    || fundamentalMetrics?.statuses?.growth;
  const reportPeriod = pickRecordValue(financialReport, ['reportDate', 'reportPeriod', 'endDate', 'annDate'])
    || pickRecordValue(profitabilityMetrics, ['reportPeriod', 'endDate', 'annDate', 'dataAsOf']);
  const dividendYield = pickRecordValue(dividendMetrics, ['ttmDividendYieldPct', 'dividendYieldPct'])
    || pickRecordValue(valuationMetrics, ['dividendYieldPct', 'dividendYieldStaticPct']);
  const cashDividend = pickRecordValue(dividendMetrics, ['ttmCashDividendPerShare', 'cashDividendPerShare', 'latestCashDividendPerShare']);
  const topBoardNames = joinBoardNames(details?.sectorRankings?.top);
  const bottomBoardNames = joinBoardNames(details?.sectorRankings?.bottom);
  const relatedBoardNames = pickBoardNames(details?.belongBoards, 5);
  const boardStatusLabel = getMappedLabel(BOARD_STATUS_LABELS, details?.boardLinkage?.status, reportLanguage);
  const capitalSignalLabel = getMappedLabel(CAPITAL_SIGNAL_LABELS, capitalFlow?.signal, reportLanguage);
  const chipSignalValue = chipMetrics?.chipSignal || chipMetrics?.chipStatus;
  const chipSignalLabel = getMappedLabel(CHIP_SIGNAL_LABELS, chipSignalValue, reportLanguage);
  const marketLabel = details?.dataQuality?.market === 'cn' && reportLanguage === 'zh'
    ? 'A 股'
    : details?.dataQuality?.market;
  const dataQualityErrors = details?.dataQuality?.errors?.length ?? 0;
  const dataQualitySourceCount = details?.dataQuality?.sourceChain?.length ?? 0;

  const boardSummary = (() => {
    const status = details?.boardLinkage?.status?.toLowerCase();
    const matchedBoard = details?.boardLinkage?.matchedBoard || undefined;
    if (status === 'aligned' || status === 'leading') {
      return reportLanguage === 'zh'
        ? `当前命中${matchedBoard || '强势'}板块，板块共振可作为趋势判断的加分项。`
        : `The stock is aligned with ${matchedBoard || 'a strong'} sector, adding a sector tailwind to the read.`;
    }
    if (status === 'lagging') {
      return reportLanguage === 'zh'
        ? '所属板块偏弱，短线追高需要更谨慎。'
        : 'The related sector is lagging, so chasing strength needs extra caution.';
    }
    if (status === 'isolated') {
      return reportLanguage === 'zh'
        ? '暂时没有命中当日强势或弱势板块，更多看个股自身逻辑。'
        : 'No clear leading or lagging sector linkage; this read leans more on stock-specific evidence.';
    }
    if (status === 'partial') {
      return reportLanguage === 'zh'
        ? '只拿到部分板块数据，板块结论先作为参考。'
        : 'Only partial sector data is available, so treat the sector read as directional context.';
    }
    return reportLanguage === 'zh' ? '展示该股所属板块及是否与当日强弱板块形成共振。' : 'Shows related sectors and whether they align with daily sector strength.';
  })();

  const capitalFlowSummary = (() => {
    const signal = capitalFlow?.signal?.toLowerCase();
    if (signal === 'inflow_confirmed') {
      return reportLanguage === 'zh'
        ? '资金流偏强，可作为趋势延续的确认信号。'
        : 'Capital flow is supportive and can confirm trend continuation.';
    }
    if (signal === 'outflow_confirmed') {
      return reportLanguage === 'zh'
        ? '资金流偏弱，短线追买需要收紧条件。'
        : 'Capital flow is weak, so short-term entries need tighter confirmation.';
    }
    if (signal === 'mixed_signal') {
      return reportLanguage === 'zh'
        ? '不同资金口径有分歧，先看价格和成交量是否继续确认。'
        : 'Flow sources disagree; wait for price and volume confirmation.';
    }
    if (signal === 'neutral') {
      return reportLanguage === 'zh'
        ? '资金信号中性，暂时不是主要加分或扣分项。'
        : 'Capital flow is neutral and is not a primary positive or negative driver.';
    }
    return reportLanguage === 'zh' ? '用同花顺/东方财富资金流辅助判断短线强弱。' : 'Uses THS/DC flow data to judge short-term strength.';
  })();

  const chipSummary = (() => {
    const signal = chipSignalValue?.toLowerCase();
    const profitRatioText = formatPercent(chipProfitRatio);
    if (signal === 'supportive') {
      return reportLanguage === 'zh'
        ? `筹码结构偏支撑${profitRatioText ? `，当前获利盘约 ${profitRatioText}` : ''}。`
        : `Chip profile is supportive${profitRatioText ? `, with profit ratio around ${profitRatioText}` : ''}.`;
    }
    if (signal === 'overheated') {
      return reportLanguage === 'zh'
        ? `获利盘偏高${profitRatioText ? `（约 ${profitRatioText}）` : ''}，冲高后更容易有兑现压力。`
        : `Profit-taking pressure is elevated${profitRatioText ? ` at around ${profitRatioText}` : ''}.`;
    }
    if (signal === 'weak') {
      return reportLanguage === 'zh'
        ? '筹码支撑不足，价格回落时承接需要继续观察。'
        : 'Chip support is weak; watch whether buyers step in on pullbacks.';
    }
    return reportLanguage === 'zh'
      ? `筹码信号中性${profitRatioText ? `，获利盘约 ${profitRatioText}` : ''}。`
      : `Chip signal is neutral${profitRatioText ? `, with profit ratio around ${profitRatioText}` : ''}.`;
  })();

  const dataQualitySummary = (() => {
    if (!details?.dataQuality) {
      return undefined;
    }
    if (reportLanguage === 'zh') {
      const coverageText = coverageSummary ? `增强数据 ${coverageSummary} 项可用` : '增强数据已接入';
      return dataQualityErrors > 0
        ? `${coverageText}，有 ${dataQualityErrors} 项降级或超时，相关结论需结合卡片状态看。`
        : `${coverageText}，数据完整度较好。`;
    }
    const coverageText = coverageSummary ? `${coverageSummary} enhanced blocks available` : 'Enhanced data is connected';
    return dataQualityErrors > 0
      ? `${coverageText}, with ${dataQualityErrors} degraded or timed-out item(s).`
      : `${coverageText}, with good coverage.`;
  })();

  return (
    <Card variant="bordered" padding="md" className="home-panel-card text-left">
      <DashboardPanelHeader
        eyebrow={text.transparency}
        title={text.traceability}
        className="mb-3"
      />

      {/* Record ID */}
      {recordId && (
        <div className="home-divider mb-3 flex items-center gap-2 border-b pb-3 text-xs text-muted-text">
          <span>{text.recordId}:</span>
          <code className="home-accent-chip px-1.5 py-0.5 font-mono text-xs">
            {recordId}
          </code>
        </div>
      )}

      {hasEvidenceDetails && (
        <div className="home-divider mb-3 border-b pb-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="label-uppercase">{text.enhancedEvidence}</span>
            <Badge
              variant={details?.tushareEnhancement?.enabled ? 'success' : 'default'}
              className="shadow-none"
            >
              {details?.tushareEnhancement?.enabled ? text.tushareEnhanced : text.basicMode}
            </Badge>
          </div>
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
            {hasFundamentalSummary && (
              <div className="home-surface-button rounded-lg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{text.fundamentalSummary}</span>
                  {fundamentalStatus && (
                    <Badge variant={getStatusVariant(fundamentalStatus)} className="shadow-none">
                      {getStatusLabel(fundamentalStatus, reportLanguage)}
                    </Badge>
                  )}
                </div>
                {renderEvidenceSummary(
                  reportLanguage === 'zh'
                    ? '估值、盈利和分红用于判断中线质量，不直接等同短线买卖点。'
                    : 'Valuation, profitability, and dividends help judge medium-term quality, not direct short-term entries.',
                )}
                <dl className="grid grid-cols-2 gap-2">
                  {renderEvidenceItem(text.peTtm, formatNumber(pickRecordValue(valuationMetrics, ['peTtm', 'peRatio'])))}
                  {renderEvidenceItem(text.pbRatio, formatNumber(pickRecordValue(valuationMetrics, ['pbRatio'])))}
                  {renderEvidenceItem(text.roe, formatPercent(pickRecordValue(profitabilityMetrics, ['roe', 'roeDt'])))}
                  {renderEvidenceItem(text.grossMargin, formatPercent(pickRecordValue(profitabilityMetrics, ['grossMargin'])))}
                  {renderEvidenceItem(text.dividendYield, formatPercent(dividendYield))}
                  {renderEvidenceItem(text.cashDividend, formatNumber(cashDividend, 4))}
                  {renderEvidenceItem(text.reportPeriod, typeof reportPeriod === 'string' || typeof reportPeriod === 'number' ? reportPeriod : undefined)}
                </dl>
              </div>
            )}

            {hasBoardSummary && (
              <div className="home-surface-button rounded-lg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{text.boardLinkageSummary}</span>
                  {details?.boardLinkage?.status && (
                    <Badge variant={getStatusVariant(details.boardLinkage.status)} className="shadow-none">
                      {boardStatusLabel || getStatusLabel(details.boardLinkage.status, reportLanguage)}
                    </Badge>
                  )}
                </div>
                {renderEvidenceSummary(boardSummary)}
                <dl className="grid grid-cols-2 gap-2">
                  {renderEvidenceItem(text.matchedBoard, details?.boardLinkage?.matchedBoard || undefined)}
                  {renderEvidenceItem(text.relatedBoardsCount, details?.belongBoards?.length)}
                  {renderEvidenceItem(text.topBoards, topBoardNames)}
                  {renderEvidenceItem(text.bottomBoards, bottomBoardNames)}
                </dl>
                {renderNameChips(relatedBoardNames)}
              </div>
            )}

            {capitalFlow && (
              <div className="home-surface-button rounded-lg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{text.capitalFlow}</span>
                  {capitalFlow.status && (
                    <Badge variant={getStatusVariant(capitalFlow.status)} className="shadow-none">
                      {getStatusLabel(capitalFlow.status, reportLanguage)}
                    </Badge>
                  )}
                </div>
                {renderEvidenceSummary(capitalFlowSummary)}
                <dl className="grid grid-cols-2 gap-2">
                  {renderEvidenceItem(text.flowSignal, capitalSignalLabel || text.unavailable)}
                  {renderEvidenceItem(text.dataDate, capitalFlow.tradeDate)}
                  {renderEvidenceItem(text.dataSource, flowSource)}
                </dl>
              </div>
            )}

            {chipMetrics && (
              <div className="home-surface-button rounded-lg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{text.chipStructure}</span>
                  {chipMetrics.status && (
                    <Badge variant={getStatusVariant(chipMetrics.status)} className="shadow-none">
                      {getStatusLabel(chipMetrics.status, reportLanguage)}
                    </Badge>
                  )}
                </div>
                {renderEvidenceSummary(chipSummary)}
                <dl className="grid grid-cols-2 gap-2">
                  {renderEvidenceItem(text.chipSignal, chipSignalLabel || text.unavailable)}
                  {renderEvidenceItem(text.dataDate, chipMetrics.asOf)}
                  {renderEvidenceItem(text.profitRatio, formatPercent(chipProfitRatio))}
                  {renderEvidenceItem(text.dataSource, chipSource)}
                </dl>
              </div>
            )}

            {details?.dataQuality && (
              <div className="home-surface-button rounded-lg p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{text.dataQuality}</span>
                  {details.dataQuality.status && (
                    <Badge variant={getStatusVariant(details.dataQuality.status)} className="shadow-none">
                      {getStatusLabel(details.dataQuality.status, reportLanguage)}
                    </Badge>
                  )}
                </div>
                {renderEvidenceSummary(dataQualitySummary)}
                <dl className="grid grid-cols-2 gap-2">
                  {renderEvidenceItem(text.coverage, coverageSummary)}
                  {renderEvidenceItem(text.market, marketLabel)}
                  {renderEvidenceItem(text.errors, dataQualityErrors)}
                  {renderEvidenceItem(text.sources, dataQualitySourceCount)}
                </dl>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 折叠区域 */}
      <div className="space-y-2">
        {/* 原始分析结果 */}
        {details?.rawResult && (
          <div>
            <button
              type="button"
              onClick={() => setShowRaw(!showRaw)}
              className="home-surface-button home-trace-toggle flex w-full items-center justify-between rounded-lg p-2.5"
            >
              <span className="text-xs text-foreground">{text.rawResult}</span>
              <svg
                className={`w-3.5 h-3.5 text-muted-text transition-transform ${showRaw ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showRaw && (
              <div className="mt-2 animate-fade-in min-w-0 overflow-hidden">
                {renderJson(details.rawResult, 'raw')}
              </div>
            )}
          </div>
        )}

        {/* 分析快照 */}
        {details?.contextSnapshot && (
          <div>
            <button
              type="button"
              onClick={() => setShowSnapshot(!showSnapshot)}
              className="home-surface-button home-trace-toggle flex w-full items-center justify-between rounded-lg p-2.5"
            >
              <span className="text-xs text-foreground">{text.analysisSnapshot}</span>
              <svg
                className={`w-3.5 h-3.5 text-muted-text transition-transform ${showSnapshot ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showSnapshot && (
              <div className="mt-2 animate-fade-in min-w-0 overflow-hidden">
                {renderJson(details.contextSnapshot, 'snapshot')}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
