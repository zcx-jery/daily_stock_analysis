import type React from 'react';
import { useEffect, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, RefreshCw, Search, Trash2, XCircle } from 'lucide-react';
import { momentumBacktestApi } from '../../api/momentumBacktest';
import type { MomentumBacktestDailyQuery } from '../../api/momentumBacktest';
import { getParsedApiError } from '../../api/error';
import type { ParsedApiError } from '../../api/error';
import type {
  MomentumBacktestBenchmarkItem,
  MomentumBacktestDailyDetailResponse,
  MomentumBacktestDailyItem,
  MomentumBacktestGateModuleBreakdownItem,
  MomentumBacktestGateSnapshotGroup,
  MomentumBacktestGateSnapshotModule,
  MomentumBacktestIssueListResponse,
  MomentumBacktestLayerDiagnostic,
  MomentumBacktestRunListResponse,
  MomentumBacktestRegimeBreakdownItem,
  MomentumBacktestRunResponse,
  MomentumBacktestSummary,
  MomentumBacktestV13DataStatus,
  MomentumBacktestV13Diagnostics,
  MomentumBacktestV13MainlineItem,
} from '../../types/momentumBacktest';
import { ApiErrorAlert, Badge, Card, Drawer, EmptyState } from '../common';

const INPUT_CLASS =
  'input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

const COMPACT_INPUT_CLASS =
  'input-surface input-focus-glow h-10 rounded-xl border bg-transparent px-3 py-2 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

type DailyFilters = {
  dateFrom: string;
  dateTo: string;
  marketRegime: string;
  actionLevel: string;
  slot: string;
  themeName: string;
};

const DEFAULT_DAILY_FILTERS: DailyFilters = {
  dateFrom: '',
  dateTo: '',
  marketRegime: '',
  actionLevel: '',
  slot: '',
  themeName: '',
};

const EMPTY_TASK_CENTER: MomentumBacktestRunListResponse = {
  currentRunning: null,
  queued: {
    total: 0,
    items: [],
  },
  history: {
    total: 0,
    limit: 20,
    items: [],
  },
  refreshedAt: null,
};

const EMPTY_SUMMARY: MomentumBacktestSummary = {
  completedTradeDates: 0,
  actionBreakdown: {},
  marketEnvironmentBreakdown: {},
  opportunityQualityBreakdown: {},
  historicalValidityBreakdown: {},
  avgCandidateCount: null,
  avgSelectedCount: null,
  avgBuyReadyCount: null,
  candidateTop10BuyTriggerRate: null,
  candidateTop10PositiveT2Rate: null,
  candidateTop10AvgT2ProfitWindowPct: null,
  candidateTop10AvgT2MaxDrawdownPct: null,
  decisionTop3BuyTriggerRate: null,
  decisionTop3PositiveT1Rate: null,
  decisionTop3PositiveT2Rate: null,
  decisionTop3AvgT1ProfitWindowPct: null,
  decisionTop3AvgT2ProfitWindowPct: null,
  decisionTop3AvgT2MaxDrawdownPct: null,
  benchmarkComparison: [],
  layerDiagnostics: [],
  gateModuleBreakdown: [],
  regimeBreakdown: [],
};

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(2)}%`;
}

function num(value?: number | null): string {
  if (value == null) return '--';
  return Number(value).toFixed(1);
}

function signedPct(value?: number | null): string {
  if (value == null) return '--';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

function amount(value?: number | null): string {
  if (value == null) return '--';
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

function formatDateTime(value?: string | null): string {
  if (!value) return '--';
  const normalized = value.replace('T', ' ');
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized;
}

function sentimentLabel(level?: string | null): string {
  switch (level) {
    case 'tradable':
      return '可做';
    case 'hot':
      return '偏热';
    case 'cold':
      return '偏冷';
    case 'weak':
      return '偏弱';
    case 'missing':
      return '缺失';
    default:
      return level ?? '--';
  }
}

function v13DataStatusBadge(status?: MomentumBacktestV13DataStatus | null) {
  const value = status?.status ?? 'missing';
  if (value === 'ok' && !status?.isDegraded) {
    return <Badge variant="success">数据完整</Badge>;
  }
  if (value === 'partial' || value === 'degraded' || status?.isDegraded) {
    return <Badge variant="warning">部分降级</Badge>;
  }
  if (value === 'failed' || value === 'missing') {
    return <Badge variant="danger">数据缺失</Badge>;
  }
  return <Badge variant="default">{value}</Badge>;
}

function actionBadge(level?: string | null) {
  switch (level) {
    case 'strong_go':
      return <Badge variant="success" glow>强烈可做</Badge>;
    case 'normal_go':
      return <Badge variant="success">可正常出手</Badge>;
    case 'cautious_go':
      return <Badge variant="warning">谨慎出手</Badge>;
    case 'observe_only':
      return <Badge variant="default">仅观察</Badge>;
    case 'stand_aside':
      return <Badge variant="danger">今日不做</Badge>;
    default:
      return <Badge variant="default">{level ?? '--'}</Badge>;
  }
}

function severityBadge(level?: string | null) {
  switch (level) {
    case 'critical':
      return <Badge variant="danger" glow>高优先</Badge>;
    case 'warning':
      return <Badge variant="warning">关注</Badge>;
    case 'info':
      return <Badge variant="info">提示</Badge>;
    default:
      return <Badge variant="default">{level ?? '--'}</Badge>;
  }
}

function profileBadge(profile?: string | null) {
  switch (profile) {
    case 'standard':
      return <Badge variant="info">Standard 主引擎</Badge>;
    case 'aggressive':
      return <Badge variant="warning">Aggressive 补充</Badge>;
    default:
      return <Badge variant="default">{profile ?? '--'}</Badge>;
  }
}

function runStatusBadge(status?: string | null) {
  switch (status) {
    case 'queued':
      return <Badge variant="default">排队中</Badge>;
    case 'running':
      return <Badge variant="warning" glow>后台计算中</Badge>;
    case 'completed':
      return <Badge variant="success">已完成</Badge>;
    case 'cancelled':
      return <Badge variant="default">已取消</Badge>;
    case 'failed':
      return <Badge variant="danger">已失败</Badge>;
    default:
      return <Badge variant="default">{status ?? '--'}</Badge>;
  }
}

function slotLabel(slot?: string | null) {
  switch (slot) {
    case 'main':
      return '主仓';
    case 'secondary':
      return '次仓';
    case 'watch':
      return '观察仓';
    default:
      return slot ?? '--';
  }
}

function levelBadge(level?: string | null) {
  switch (level) {
    case 'strong':
      return <Badge variant="success">强</Badge>;
    case 'general':
      return <Badge variant="warning">中</Badge>;
    case 'weak':
      return <Badge variant="danger">弱</Badge>;
    default:
      return <Badge variant="default">{level ?? '--'}</Badge>;
  }
}

function levelLabel(level?: string | null): string {
  switch (level) {
    case 'strong':
      return '强市';
    case 'general':
      return '中性市';
    case 'weak':
      return '弱市';
    default:
      return level ?? '--';
  }
}

function gateBadge(level?: string | null, label?: string | null) {
  switch (level) {
    case 'healthy':
    case 'strong':
      return <Badge variant="success">{label ?? '强'}</Badge>;
    case 'general':
    case 'medium':
      return <Badge variant="warning">{label ?? '中'}</Badge>;
    case 'weak':
      return <Badge variant="danger">{label ?? '弱'}</Badge>;
    default:
      return <Badge variant="default">{label ?? level ?? '--'}</Badge>;
  }
}

function formatRunStage(run?: MomentumBacktestRunResponse | null): string {
  if (!run?.currentStageLabel) {
    return '--';
  }
  if (run.currentTradeDate) {
    return `${run.currentTradeDate} ${run.currentStageLabel}`;
  }
  return run.currentStageLabel;
}

function runProgressPct(run?: MomentumBacktestRunResponse | null): number {
  const total = Math.max(Number(run?.totalTradeDates ?? 0), 0);
  const processed = Math.max(Number(run?.processedTradeDates ?? 0), 0);
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((processed / total) * 100)));
}

function runRemainingTradeDates(run?: MomentumBacktestRunResponse | null): number | null {
  const total = Number(run?.totalTradeDates ?? 0);
  const processed = Number(run?.processedTradeDates ?? 0);
  if (total <= 0) return null;
  return Math.max(total - processed, 0);
}

function runProgressBadge(run?: MomentumBacktestRunResponse | null): React.ReactNode {
  const remaining = runRemainingTradeDates(run);
  if (run?.status === 'completed') {
    return <Badge variant="success">已完成</Badge>;
  }
  if (run?.status === 'cancelled') {
    return <Badge variant="default">已取消</Badge>;
  }
  if (run?.status === 'failed') {
    return <Badge variant="danger">已失败</Badge>;
  }
  if (run?.status === 'queued') {
    return <Badge variant="default">等待执行</Badge>;
  }
  if (remaining == null) {
    return <Badge variant="warning">运行中</Badge>;
  }
  return <Badge variant="warning">剩余 {remaining} 天</Badge>;
}

function progressBarTone(status?: string | null): string {
  switch (status) {
    case 'completed':
      return 'from-emerald-400 via-emerald-500 to-cyan-400';
    case 'failed':
      return 'from-rose-500 via-rose-500 to-orange-400';
    case 'cancelled':
      return 'from-slate-400 via-slate-500 to-slate-400';
    case 'queued':
      return 'from-slate-500 via-cyan-500 to-slate-500';
    default:
      return 'from-cyan-400 via-sky-500 to-emerald-400';
  }
}

function buildRefreshNotice(
  run: MomentumBacktestRunResponse | null | undefined,
  refreshedAt?: string | null,
): string {
  const refreshedLabel = formatDateTime(refreshedAt ?? run?.heartbeatAt ?? run?.updatedAt);
  if (!run) {
    return `已刷新任务中心，最近更新时间 ${refreshedLabel}。`;
  }

  const progress = `${run.processedTradeDates} / ${run.totalTradeDates}`;
  const stage = run.currentStageLabel ?? '--';

  switch (run.status) {
    case 'running':
      return `已刷新：${run.runId} 正在执行，进度 ${progress}，当前处理 ${run.currentTradeDate ?? '--'}，阶段 ${stage}，最近心跳 ${refreshedLabel}。`;
    case 'queued':
      return `已刷新：${run.runId} 仍在排队中，当前阶段 ${stage}，最近更新时间 ${refreshedLabel}。`;
    case 'completed':
      return `已刷新：${run.runId} 已完成，最终进度 ${progress}，完成时间 ${formatDateTime(run.finishedAt ?? refreshedAt ?? run.updatedAt)}。`;
    case 'cancelled':
      return `已刷新：${run.runId} 已取消，保留已完成 ${progress} 的结果快照。`;
    case 'failed':
      return `已刷新：${run.runId} 已失败，阶段停留在 ${stage}。`;
    default:
      return `已刷新：${run.runId} 当前进度 ${progress}，阶段 ${stage}。`;
  }
}

function RunProgressPanel({
  run,
  title = '当前进度',
}: {
  run: MomentumBacktestRunResponse;
  title?: string;
}) {
  const progressPctValue = runProgressPct(run);
  const visualWidth = run.status === 'queued' ? Math.max(progressPctValue, 6) : progressPctValue;

  return (
    <div className="rounded-xl border border-info/20 bg-info/6 px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-info/80">{title}</div>
          <div className="mt-1 text-sm font-semibold text-foreground">
            {run.processedTradeDates} / {run.totalTradeDates} 个交易日
            <span className="ml-2 text-xs font-normal text-muted-text">{progressPctValue}%</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {runProgressBadge(run)}
        </div>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-background/70"
        role="progressbar"
        aria-label={`回测进度 ${run.runId}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progressPctValue}
      >
        <div
          className={`h-full rounded-full bg-gradient-to-r ${progressBarTone(run.status)} transition-all duration-500`}
          style={{ width: `${visualWidth}%` }}
        />
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted-text md:grid-cols-3">
        <span>当前交易日 {run.currentTradeDate ?? '--'}</span>
        <span>当前阶段 {run.currentStageLabel ?? '--'}</span>
        <span>最近心跳 {formatDateTime(run.heartbeatAt ?? run.updatedAt)}</span>
      </div>
    </div>
  );
}

function buildDailyQuery(filters: DailyFilters, page: number, pageSize: number): MomentumBacktestDailyQuery {
  return {
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    marketRegime: filters.marketRegime || undefined,
    actionLevel: filters.actionLevel || undefined,
    slot: filters.slot || undefined,
    themeName: filters.themeName || undefined,
    page,
    pageSize,
  };
}

function issueTitle(summary?: MomentumBacktestSummary | null): string {
  if (!summary) return '--';
  return `${pct(summary.decisionTop3BuyTriggerRate)} / ${pct(summary.decisionTop3PositiveT2Rate)}`;
}

function DetailMetric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-card/60 px-4 py-3">
      <div className="text-xs text-muted-text">{label}</div>
      <div className="mt-1 text-base font-semibold text-foreground">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted-text">{hint}</div> : null}
    </div>
  );
}

function BenchmarkCard({ item }: { item: MomentumBacktestBenchmarkItem }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{item.label}</div>
          <div className="mt-1 text-xs text-muted-text">样本 {item.sampleCount}</div>
        </div>
        <Badge variant="default">{pct(item.settlementPassRatePct ?? item.positiveT2RatePct)}</Badge>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <DetailMetric label="T+2 利润窗口" value={pct(item.avgT2ProfitWindowPct)} />
        <DetailMetric label="T+2 平均回撤" value={pct(item.avgT2MaxDrawdownPct)} />
        <DetailMetric label="买点触发率" value={pct(item.triggerRatePct)} />
        <DetailMetric label="相对官方 Top3" value={signedPct(item.alphaVsOfficialTop3Pct)} hint="按 T+2 利润窗口比较" />
      </div>
    </div>
  );
}

function LayerCard({ item }: { item: MomentumBacktestLayerDiagnostic }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{item.label}</div>
          <div className="mt-1 text-xs text-muted-text">评分 {item.score.toFixed(0)}</div>
        </div>
        {levelBadge(item.level)}
      </div>
      <p className="mt-3 text-sm leading-6 text-secondary-text">{item.summary}</p>
    </div>
  );
}

function RegimeCard({ item }: { item: MomentumBacktestRegimeBreakdownItem }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{item.label}</div>
          <div className="mt-1 text-xs text-muted-text">{item.tradeDays} 个交易日</div>
        </div>
        {levelBadge(item.level)}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <DetailMetric label="延续合格率" value={pct(item.decisionPositiveT2RatePct)} />
        <DetailMetric label="T+2 利润窗口" value={pct(item.decisionAvgT2ProfitWindowPct)} />
        <DetailMetric label="放行准确率" value={pct(item.allowedTradePrecisionPct)} />
        <DetailMetric label="错杀率" value={pct(item.missedOpportunityRatePct)} />
      </div>
    </div>
  );
}

function GateModuleBreakdownCard({ item }: { item: MomentumBacktestGateModuleBreakdownItem }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{item.label}</div>
          <div className="mt-1 text-xs text-muted-text">{item.groupLabel} · 样本 {item.sampleDays} 天</div>
        </div>
        <Badge variant={item.blockerDays > 0 ? 'warning' : 'default'}>{item.blockerDays} 天弱项</Badge>
      </div>
      <p className="mt-3 text-sm leading-6 text-secondary-text">{item.summary}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <DetailMetric label="平均分" value={num(item.avgScore)} />
        <DetailMetric label="限制出手日" value={String(item.restrictedDays)} />
        <DetailMetric label="弱项日组合 T+2" value={pct(item.weakDayDecisionAvgT2ProfitWindowPct)} />
        <DetailMetric label="强项日组合 T+2" value={pct(item.strongDayDecisionAvgT2ProfitWindowPct)} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge variant="success">强 {item.strongDays}</Badge>
        <Badge variant="warning">中 {item.mediumDays}</Badge>
        <Badge variant="danger">弱 {item.weakDays}</Badge>
      </div>
    </div>
  );
}

function GateSnapshotGroupCard({ group }: { group: MomentumBacktestGateSnapshotGroup }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{group.label}</div>
          <p className="mt-2 text-sm leading-6 text-secondary-text">{group.reason || '暂无补充说明。'}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {gateBadge(group.level, group.levelLabel)}
          <Badge variant="default">评分 {num(group.score)}</Badge>
        </div>
      </div>
      {group.modules.length > 0 ? (
        <div className="mt-4 space-y-3">
          {group.modules.map((module: MomentumBacktestGateSnapshotModule) => (
            <div key={`${group.key}-${module.key}`} className="rounded-xl border border-border/50 bg-background/40 px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">{module.label}</div>
                  <p className="mt-1 text-xs leading-5 text-muted-text">{module.summary}</p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  {gateBadge(module.level, module.levelLabel)}
                  <span className="text-xs text-muted-text">评分 {num(module.score)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function V13TopMainlineCard({
  item,
  compact = false,
}: {
  item: MomentumBacktestV13MainlineItem;
  compact?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-foreground">{item.themeName ?? item.themeId ?? '未命名主线'}</div>
          <div className="mt-1 text-xs text-muted-text">
            主线分 {num(item.score)}{item.levelLabel ? ` · ${item.levelLabel}` : ''}
          </div>
        </div>
        {item.level ? levelBadge(item.level) : <Badge variant="default">主线快照</Badge>}
      </div>
      {item.summary ? <p className="mt-3 text-sm leading-6 text-secondary-text">{item.summary}</p> : null}
      <div className={`mt-4 grid gap-3 ${compact ? 'md:grid-cols-2' : 'md:grid-cols-3'}`}>
        <DetailMetric label="候选股" value={item.candidateCount != null ? String(item.candidateCount) : '--'} />
        <DetailMetric label="Top10 占位" value={item.top10Count != null ? String(item.top10Count) : '--'} />
        <DetailMetric label="涨停数" value={item.limitUpCount != null ? String(item.limitUpCount) : '--'} />
        {!compact ? <DetailMetric label="炸板数" value={item.brokenLimitCount != null ? String(item.brokenLimitCount) : '--'} /> : null}
        {!compact ? <DetailMetric label="主力净额" value={amount(item.netAmount)} /> : null}
        {!compact ? <DetailMetric label="板块涨跌" value={signedPct(item.pctChange)} /> : null}
      </div>
      {item.leaderStock || item.sourceThemeNames?.length ? (
        <div className="mt-3 space-y-2 text-xs text-secondary-text">
          {item.leaderStock ? <p>领涨股：{item.leaderStock}</p> : null}
          {item.sourceThemeNames?.length ? <p>覆盖子题材：{item.sourceThemeNames.join('、')}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function V13RunDiagnosticsSection({ diagnostics }: { diagnostics?: MomentumBacktestV13Diagnostics | null }) {
  if (!diagnostics) {
    return null;
  }

  return (
    <Card padding="lg" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="label-uppercase">V1.3 Diagnostics</span>
          <h3 className="mt-1 text-lg font-semibold text-foreground">主线与情绪诊断</h3>
        </div>
        {v13DataStatusBadge(diagnostics.v13DataStatus)}
      </div>
      {diagnostics.summary ? (
        <div className="rounded-xl border border-info/20 bg-info/6 px-4 py-3 text-sm text-secondary-text">
          {diagnostics.summary}
        </div>
      ) : null}
      <div className="grid gap-3 md:grid-cols-4">
        <DetailMetric label="主线雷达覆盖" value={`${diagnostics.radarAvailableDays ?? 0} / ${diagnostics.evaluatedTradeDates ?? 0}`} />
        <DetailMetric label="覆盖率" value={pct(diagnostics.radarCoveragePct)} />
        <DetailMetric label="Top 主线均分" value={num(diagnostics.avgTopMainlineScore)} />
        <DetailMetric label="降级天数" value={String(diagnostics.degradedDays ?? 0)} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4">
          {diagnostics.topMainline ? <V13TopMainlineCard item={diagnostics.topMainline} /> : null}
          {diagnostics.shortTermSentiment ? (
            <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-foreground">短线情绪</div>
                  <div className="mt-1 text-xs text-muted-text">
                    {diagnostics.shortTermSentiment.levelLabel ?? sentimentLabel(diagnostics.shortTermSentiment.level)} ·
                    {' '}分数 {num(diagnostics.shortTermSentiment.score)}
                  </div>
                </div>
                <Badge variant="default">{diagnostics.shortTermSentiment.levelLabel ?? sentimentLabel(diagnostics.shortTermSentiment.level)}</Badge>
              </div>
              {diagnostics.shortTermSentiment.summary ? (
                <p className="mt-3 text-sm leading-6 text-secondary-text">{diagnostics.shortTermSentiment.summary}</p>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="space-y-4">
          <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
            <div className="text-sm font-medium text-foreground">Top 主线分布</div>
            <div className="mt-3 space-y-2">
              {(diagnostics.topThemeBreakdown ?? []).length > 0 ? (
                diagnostics.topThemeBreakdown?.map((item) => (
                  <div key={item.theme} className="flex items-center justify-between rounded-xl border border-border/50 bg-background/40 px-3 py-2 text-sm">
                    <span className="text-secondary-text">{item.theme}</span>
                    <Badge variant="default">{item.days} 天</Badge>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-border/60 border-dashed px-4 py-6 text-sm text-muted-text">
                  当前没有可用的 Top 主线分布统计。
                </div>
              )}
            </div>
          </div>
          <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
            <div className="text-sm font-medium text-foreground">短线情绪分布</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(diagnostics.sentimentBreakdown ?? {}).map(([key, count]) => (
                <Badge key={key} variant="default">{sentimentLabel(key)}: {count}</Badge>
              ))}
              {Object.keys(diagnostics.sentimentBreakdown ?? {}).length === 0 ? (
                <span className="text-sm text-muted-text">暂无短线情绪分布。</span>
              ) : null}
            </div>
            <div className="mt-4 text-sm font-medium text-foreground">数据状态分布</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(diagnostics.dataStatusBreakdown ?? {}).map(([key, count]) => (
                <Badge key={key} variant="default">{key}: {count}</Badge>
              ))}
              {Object.keys(diagnostics.dataStatusBreakdown ?? {}).length === 0 ? (
                <span className="text-sm text-muted-text">暂无数据状态分布。</span>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function V13DailyDiagnosticsSection({ diagnostics }: { diagnostics?: MomentumBacktestV13Diagnostics | null }) {
  if (!diagnostics) {
    return null;
  }

  return (
    <Card padding="lg" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="label-uppercase">V1.3 Snapshot</span>
          <h3 className="mt-1 text-lg font-semibold text-foreground">当日主线与情绪诊断</h3>
        </div>
        {v13DataStatusBadge(diagnostics.v13DataStatus)}
      </div>
      <div className="space-y-2">
        {(diagnostics.summaryLines ?? []).map((line, index) => (
          <p key={index} className="text-sm text-secondary-text">{line}</p>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <DetailMetric label="主线条数" value={String(diagnostics.mainlineCount ?? 0)} />
        <DetailMetric label="Top 主线分" value={num(diagnostics.topMainline?.score)} />
        <DetailMetric
          label="短线情绪"
          value={diagnostics.shortTermSentiment?.levelLabel ?? sentimentLabel(diagnostics.shortTermSentiment?.level)}
        />
        <DetailMetric label="数据状态" value={diagnostics.v13DataStatus?.status ?? '--'} />
      </div>
      {diagnostics.topMainline ? <V13TopMainlineCard item={diagnostics.topMainline} compact /> : null}
    </Card>
  );
}

export const MomentumBacktestPanel: React.FC = () => {
  const [startTradeDate, setStartTradeDate] = useState('2026-04-08');
  const [endTradeDate, setEndTradeDate] = useState('2026-04-10');
  const [runIdInput, setRunIdInput] = useState('');
  const [taskCenter, setTaskCenter] = useState<MomentumBacktestRunListResponse>(EMPTY_TASK_CENTER);
  const [dailyFilters, setDailyFilters] = useState<DailyFilters>(DEFAULT_DAILY_FILTERS);
  const [dailyPage, setDailyPage] = useState(1);
  const [run, setRun] = useState<MomentumBacktestRunResponse | null>(null);
  const [summary, setSummary] = useState<MomentumBacktestSummary | null>(null);
  const [dailyItems, setDailyItems] = useState<MomentumBacktestDailyItem[]>([]);
  const [dailyTotal, setDailyTotal] = useState(0);
  const [dailyPageSize, setDailyPageSize] = useState(20);
  const [dailyHasMore, setDailyHasMore] = useState(false);
  const [issues, setIssues] = useState<MomentumBacktestIssueListResponse | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<MomentumBacktestDailyDetailResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingRecentRuns, setIsLoadingRecentRuns] = useState(false);
  const [isRefreshingProgress, setIsRefreshingProgress] = useState(false);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);
  const [isLoadingDaily, setIsLoadingDaily] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [mutatingRunId, setMutatingRunId] = useState<string | null>(null);
  const [panelError, setPanelError] = useState<ParsedApiError | null>(null);
  const [detailError, setDetailError] = useState<ParsedApiError | null>(null);
  const [recentRunsError, setRecentRunsError] = useState<string | null>(null);
  const [taskNotice, setTaskNotice] = useState<string | null>(null);

  const loadRecentRuns = async (): Promise<MomentumBacktestRunListResponse> => {
    setIsLoadingRecentRuns(true);
    setRecentRunsError(null);
    try {
      const response = await momentumBacktestApi.listRuns({ limit: 20 });
      setTaskCenter(response);
      return response;
    } catch (error) {
      const parsed = getParsedApiError(error);
      setRecentRunsError(parsed.message);
      throw error;
    } finally {
      setIsLoadingRecentRuns(false);
    }
  };

  const loadDailySlice = async (runId: string, nextFilters: DailyFilters, nextPage = 1, pageSize = dailyPageSize) => {
    setIsLoadingDaily(true);
    try {
      const response = await momentumBacktestApi.getDaily(runId, buildDailyQuery(nextFilters, nextPage, pageSize));
      setDailyItems(response.items);
      setDailyTotal(response.total);
      setDailyPage(response.page);
      setDailyPageSize(response.pageSize);
      setDailyHasMore(response.hasMore);
    } finally {
      setIsLoadingDaily(false);
    }
  };

  const loadRunArtifacts = async (
    runId: string,
    nextFilters: DailyFilters = DEFAULT_DAILY_FILTERS,
    runPayload?: MomentumBacktestRunResponse,
  ): Promise<MomentumBacktestRunResponse> => {
    const [resolvedRun, summaryResponse, dailyResponse, issuesResponse] = await Promise.all([
      runPayload ? Promise.resolve(runPayload) : momentumBacktestApi.getRun(runId),
      momentumBacktestApi.getSummary(runId),
      momentumBacktestApi.getDaily(runId, buildDailyQuery(nextFilters, 1, dailyPageSize)),
      momentumBacktestApi.getIssues(runId),
    ]);
    setRun(resolvedRun);
    setSummary(summaryResponse.summary);
    setDailyItems(dailyResponse.items);
    setDailyTotal(dailyResponse.total);
    setDailyPage(dailyResponse.page);
    setDailyPageSize(dailyResponse.pageSize);
    setDailyHasMore(dailyResponse.hasMore);
    setIssues(issuesResponse);
    setRunIdInput(runId);
    setDailyFilters(nextFilters);
    return resolvedRun;
  };

  const handleCreateRun = async () => {
    setIsSubmitting(true);
    setPanelError(null);
    setTaskNotice(null);
    try {
      const created = await momentumBacktestApi.createRun({
        startTradeDate,
        endTradeDate,
      });
      setTaskNotice(created.message);
      await loadRunArtifacts(created.run.runId, DEFAULT_DAILY_FILTERS, created.run);
      await loadRecentRuns();
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLoadRun = async (targetRunId?: string, runPayload?: MomentumBacktestRunResponse) => {
    const runId = (targetRunId ?? runIdInput).trim();
    if (!runId) {
      setPanelError({
        title: '缺少回测任务 ID',
        message: '请先输入已创建的回测任务 ID。',
        rawMessage: 'missing run id',
        category: 'missing_params',
      });
      return;
    }
    setIsLoadingRun(true);
    setLoadingRunId(runId);
    setPanelError(null);
    setTaskNotice(null);
    try {
      await loadRunArtifacts(runId, dailyFilters, runPayload);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setIsLoadingRun(false);
      setLoadingRunId(null);
    }
  };

  const handleApplyFilters = async () => {
    if (!run?.runId) return;
    setPanelError(null);
    try {
      await loadDailySlice(run.runId, dailyFilters, 1);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    }
  };

  const handleResetFilters = async () => {
    if (!run?.runId) {
      setDailyFilters(DEFAULT_DAILY_FILTERS);
      return;
    }
    setDailyFilters(DEFAULT_DAILY_FILTERS);
    setPanelError(null);
    try {
      await loadDailySlice(run.runId, DEFAULT_DAILY_FILTERS, 1);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    }
  };

  const handlePageChange = async (nextPage: number) => {
    if (!run?.runId || nextPage < 1) return;
    setPanelError(null);
    try {
      await loadDailySlice(run.runId, dailyFilters, nextPage);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    }
  };

  const handleOpenDetail = async (tradeDate: string) => {
    if (!run?.runId) return;
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const detail = await momentumBacktestApi.getDailyDetail(run.runId, tradeDate);
      setSelectedDetail(detail);
    } catch (error) {
      setDetailError(getParsedApiError(error));
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const handleRefreshProgress = async () => {
    setIsRefreshingProgress(true);
    setPanelError(null);
    try {
      const refreshedTaskCenter = await loadRecentRuns();
      let focusRun =
        refreshedTaskCenter.currentRunning
        ?? (run?.runId
          ? refreshedTaskCenter.history.items.find((item) => item.runId === run.runId)
            ?? refreshedTaskCenter.queued.items.find((item) => item.runId === run.runId)
            ?? null
          : null);
      if (run?.runId) {
        focusRun = await loadRunArtifacts(run.runId, dailyFilters);
      }
      setTaskNotice(buildRefreshNotice(focusRun, refreshedTaskCenter.refreshedAt));
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setIsRefreshingProgress(false);
    }
  };

  const handleCancelRun = async (targetRunId: string) => {
    setMutatingRunId(targetRunId);
    setPanelError(null);
    setTaskNotice(null);
    try {
      const updated = await momentumBacktestApi.cancelRun(targetRunId);
      setTaskNotice('任务已取消，已保留已完成部分');
      await loadRecentRuns();
      if (run?.runId === targetRunId) {
        await loadRunArtifacts(targetRunId, dailyFilters, updated);
      }
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setMutatingRunId(null);
    }
  };

  const handleDeleteRun = async (targetRunId: string) => {
    const confirmed = window.confirm('确认彻底删除这条回测任务及其已冻结结果吗？删除后不可恢复。');
    if (!confirmed) {
      return;
    }
    setMutatingRunId(targetRunId);
    setPanelError(null);
    setTaskNotice(null);
    try {
      const result = await momentumBacktestApi.deleteRun(targetRunId);
      setTaskNotice(result.message);
      if (run?.runId === targetRunId) {
        setRun(null);
        setSummary(null);
        setDailyItems([]);
        setDailyTotal(0);
        setDailyHasMore(false);
        setIssues(null);
        setSelectedDetail(null);
        setRunIdInput('');
      }
      await loadRecentRuns();
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setMutatingRunId(null);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setIsLoadingRecentRuns(true);
      setRecentRunsError(null);
      try {
        const response = await momentumBacktestApi.listRuns({ limit: 20 });
        setTaskCenter(response);
      } catch (error) {
        const parsed = getParsedApiError(error);
        setRecentRunsError(parsed.message);
      } finally {
        setIsLoadingRecentRuns(false);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!run?.runId || run.status !== 'running') {
      return;
    }
    const nextFilters = {
      dateFrom: dailyFilters.dateFrom,
      dateTo: dailyFilters.dateTo,
      marketRegime: dailyFilters.marketRegime,
      actionLevel: dailyFilters.actionLevel,
      slot: dailyFilters.slot,
      themeName: dailyFilters.themeName,
    };
    const timer = window.setTimeout(async () => {
      try {
        const [resolvedRun, summaryResponse, dailyResponse, issuesResponse, recentRunsResponse] = await Promise.all([
          momentumBacktestApi.getRun(run.runId),
          momentumBacktestApi.getSummary(run.runId),
          momentumBacktestApi.getDaily(run.runId, buildDailyQuery(nextFilters, 1, dailyPageSize)),
          momentumBacktestApi.getIssues(run.runId),
          momentumBacktestApi.listRuns({ limit: 20 }),
        ]);
        setRun(resolvedRun);
        setSummary(summaryResponse.summary);
        setDailyItems(dailyResponse.items);
        setDailyTotal(dailyResponse.total);
        setDailyPage(dailyResponse.page);
        setDailyPageSize(dailyResponse.pageSize);
        setDailyHasMore(dailyResponse.hasMore);
        setIssues(issuesResponse);
        setTaskCenter(recentRunsResponse);
      } catch {
        // Keep the last visible snapshot and let manual refresh/load recover.
      }
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [
    run?.runId,
    run?.status,
    run?.processedTradeDates,
    dailyFilters.dateFrom,
    dailyFilters.dateTo,
    dailyFilters.marketRegime,
    dailyFilters.actionLevel,
    dailyFilters.slot,
    dailyFilters.themeName,
    dailyPageSize,
  ]);

  const summaryView = summary ?? EMPTY_SUMMARY;

  return (
    <div className="space-y-4">
      <Card variant="gradient" padding="lg" className="animate-fade-in">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <span className="label-uppercase">Momentum Backtest V1</span>
              <h2 className="mt-1 text-xl font-semibold text-foreground">强势筛选回测结果页</h2>
              <p className="mt-2 max-w-3xl text-sm text-secondary-text">
                回放 V1 生产链路，固定 Standard 主引擎、官方 Top30、二次决策 Top3 与 T+1 / T+2 结果，并按“概览、基准、分层诊断、市场分桶、问题清单、日级回放”统一查看。
              </p>
            </div>
            <div className="flex items-center gap-2">
              {profileBadge('standard')}
              <Badge variant="default">统一入口 4 / 2亿 / 2%</Badge>
              <Badge variant="default">官方 Top30</Badge>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1.2fr_1fr_auto]">
            <div>
              <div className="mb-1 text-xs text-muted-text">起始交易日</div>
              <input className={INPUT_CLASS} type="date" value={startTradeDate} onChange={(e) => setStartTradeDate(e.target.value)} />
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-text">结束交易日</div>
              <input className={INPUT_CLASS} type="date" value={endTradeDate} onChange={(e) => setEndTradeDate(e.target.value)} />
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-text">官方回测口径</div>
              <div className={`${INPUT_CLASS} flex items-center text-secondary-text`}>
                Standard / Top30 / 4-2-2
              </div>
            </div>
            <div className="flex items-end">
              <button type="button" className="btn-primary w-full" onClick={handleCreateRun} disabled={isSubmitting}>
                {isSubmitting ? '回放中...' : '创建回测'}
              </button>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
            <div>
              <div className="mb-1 text-xs text-muted-text">加载已有任务</div>
              <input
                className={COMPACT_INPUT_CLASS + ' w-full'}
                value={runIdInput}
                onChange={(e) => setRunIdInput(e.target.value)}
                placeholder="输入 run_id，例如 momentum_bt_xxx"
              />
            </div>
            <div className="flex items-end">
              <button type="button" className="btn-secondary w-full gap-2" onClick={() => void handleLoadRun()} disabled={isLoadingRun}>
                {isLoadingRun ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                加载任务
              </button>
            </div>
          </div>
          <div className="rounded-2xl border border-border/60 bg-card/40 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-foreground">回测任务中心</div>
                <div className="mt-1 text-xs text-muted-text">
                  任务会持久化到服务器。这里按“当前运行 / 排队中 / 历史任务”三段展示，并支持刷新、取消、删除和继续加载。
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-text">
                  <span>最近刷新时间 {formatDateTime(taskCenter.refreshedAt)}</span>
                  {isRefreshingProgress ? <Badge variant="info">正在刷新后台进度</Badge> : null}
                </div>
              </div>
              <button
                type="button"
                className="btn-secondary gap-2"
                onClick={() => void handleRefreshProgress()}
                disabled={isLoadingRecentRuns || isRefreshingProgress}
              >
                {isLoadingRecentRuns || isRefreshingProgress ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                {isLoadingRecentRuns || isRefreshingProgress ? '刷新中...' : '刷新进度'}
              </button>
            </div>
            {recentRunsError ? (
              <div className="mt-4 rounded-xl border border-warning/30 bg-warning/8 px-4 py-3 text-sm text-warning">
                回测任务列表加载失败：{recentRunsError}
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-border/60 bg-background/30 px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">当前运行任务</div>
                      <div className="mt-1 text-xs text-muted-text">同一时间只允许 1 个任务后台计算；服务重启后会自动回到排队状态。</div>
                    </div>
                    {taskCenter.currentRunning ? <Badge variant="warning">正在执行</Badge> : <Badge variant="default">空闲</Badge>}
                  </div>
                  {!taskCenter.currentRunning ? (
                    <div className="mt-3 rounded-xl border border-dashed border-border/60 px-4 py-5 text-sm text-muted-text">
                      当前没有正在运行的回测任务。
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-border/60 bg-card/60 px-4 py-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <code className="rounded bg-background/60 px-2 py-1 text-xs text-foreground">{taskCenter.currentRunning.runId}</code>
                            {runStatusBadge(taskCenter.currentRunning.status)}
                            {profileBadge(taskCenter.currentRunning.profile)}
                            {run?.runId === taskCenter.currentRunning.runId ? <Badge variant="success">当前查看</Badge> : null}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-text">
                            <span>区间 {taskCenter.currentRunning.startTradeDate} → {taskCenter.currentRunning.endTradeDate}</span>
                            <span>进度 {taskCenter.currentRunning.processedTradeDates} / {taskCenter.currentRunning.totalTradeDates}</span>
                            <span>阶段 {formatRunStage(taskCenter.currentRunning)}</span>
                            <span>最近更新时间 {formatDateTime(taskCenter.currentRunning.heartbeatAt ?? taskCenter.currentRunning.updatedAt)}</span>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className="btn-secondary gap-2"
                            onClick={() => void handleLoadRun(taskCenter.currentRunning?.runId, taskCenter.currentRunning ?? undefined)}
                            disabled={isLoadingRun}
                          >
                            {isLoadingRun && loadingRunId === taskCenter.currentRunning.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                            加载任务
                          </button>
                          <button
                            type="button"
                            className="btn-secondary gap-2"
                            onClick={() => void handleCancelRun(taskCenter.currentRunning!.runId)}
                            disabled={mutatingRunId === taskCenter.currentRunning.runId}
                          >
                            {mutatingRunId === taskCenter.currentRunning.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                            取消任务
                          </button>
                        </div>
                      </div>
                      <div className="mt-4">
                        <RunProgressPanel run={taskCenter.currentRunning} title="后台执行进度" />
                      </div>
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-border/60 bg-background/30 px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">排队中任务</div>
                      <div className="mt-1 text-xs text-muted-text">按 FIFO 顺序串行执行；相同参数任务会直接复用，不会重复创建。</div>
                    </div>
                    <Badge variant="default">共 {taskCenter.queued.total} 条</Badge>
                  </div>
                  {taskCenter.queued.items.length === 0 ? (
                    <div className="mt-3 rounded-xl border border-dashed border-border/60 px-4 py-5 text-sm text-muted-text">
                      当前没有排队中的任务。
                    </div>
                  ) : (
                    <div className="mt-3 space-y-3">
                      {taskCenter.queued.items.map((item, index) => (
                        <div key={item.runId} className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card/60 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <code className="rounded bg-background/60 px-2 py-1 text-xs text-foreground">{item.runId}</code>
                              {runStatusBadge(item.status)}
                              {profileBadge(item.profile)}
                              <Badge variant="default">队列 #{index + 1}</Badge>
                              {run?.runId === item.runId ? <Badge variant="success">当前查看</Badge> : null}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-text">
                              <span>区间 {item.startTradeDate} → {item.endTradeDate}</span>
                              <span>阶段 {formatRunStage(item)}</span>
                              <span>最近更新时间 {formatDateTime(item.heartbeatAt ?? item.updatedAt)}</span>
                              <span>创建于 {formatDateTime(item.createdAt)}</span>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              className="btn-secondary gap-2"
                              onClick={() => void handleLoadRun(item.runId, item)}
                              disabled={isLoadingRun}
                            >
                              {isLoadingRun && loadingRunId === item.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                              加载任务
                            </button>
                            <button
                              type="button"
                              className="btn-secondary gap-2"
                              onClick={() => void handleDeleteRun(item.runId)}
                              disabled={mutatingRunId === item.runId}
                            >
                              {mutatingRunId === item.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                              删除任务
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-border/60 bg-background/30 px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">历史任务</div>
                      <div className="mt-1 text-xs text-muted-text">默认只展示最近 {taskCenter.history.limit ?? 20} 条历史任务，包含已完成 / 已失败 / 已取消。</div>
                    </div>
                    <Badge variant="default">共 {taskCenter.history.total} 条</Badge>
                  </div>
                  {taskCenter.history.items.length === 0 ? (
                    <div className="mt-3 rounded-xl border border-dashed border-border/60 px-4 py-5 text-sm text-muted-text">
                      当前还没有可回看历史任务。
                    </div>
                  ) : (
                    <div className="mt-3 space-y-3">
                      {taskCenter.history.items.map((item) => (
                        <div key={item.runId} className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card/60 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <code className="rounded bg-background/60 px-2 py-1 text-xs text-foreground">{item.runId}</code>
                              {runStatusBadge(item.status)}
                              {profileBadge(item.profile)}
                              {run?.runId === item.runId ? <Badge variant="success">当前查看</Badge> : null}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-text">
                              <span>区间 {item.startTradeDate} → {item.endTradeDate}</span>
                              <span>进度 {item.processedTradeDates} / {item.totalTradeDates}</span>
                              <span>阶段 {formatRunStage(item)}</span>
                              <span>最近更新时间 {formatDateTime(item.finishedAt ?? item.updatedAt)}</span>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              className="btn-secondary gap-2"
                              onClick={() => void handleLoadRun(item.runId, item)}
                              disabled={isLoadingRun}
                            >
                              {isLoadingRun && loadingRunId === item.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                              加载任务
                            </button>
                            <button
                              type="button"
                              className="btn-secondary gap-2"
                              onClick={() => void handleDeleteRun(item.runId)}
                              disabled={mutatingRunId === item.runId}
                            >
                              {mutatingRunId === item.runId ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                              删除任务
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </Card>

      {panelError ? <ApiErrorAlert error={panelError} /> : null}
      {taskNotice ? (
        <div className="rounded-xl border border-info/30 bg-info/8 px-4 py-3 text-sm text-info">
          {taskNotice}
        </div>
      ) : null}

      {!run ? (
        <EmptyState
          title="还没有 V1 回测结果"
          description="先创建一个强势筛选回测 run，或加载已有 run_id，再查看区间摘要、问题清单和单日详情。"
          className="border-dashed"
        />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <Card padding="lg" className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="label-uppercase">Overview</span>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">{run.runId}</h3>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {runStatusBadge(run.status)}
                  {profileBadge(run.profile)}
                  <Badge variant="default">{run.engineVersion}</Badge>
                  <Badge variant="default">{run.entryBaselineVersion}</Badge>
                  <Badge variant="default">{run.marketScopeVersion}</Badge>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-4">
                <DetailMetric label="回测区间" value={`${run.startTradeDate} → ${run.endTradeDate}`} />
                <DetailMetric label="已处理交易日" value={`${run.processedTradeDates} / ${run.totalTradeDates}`} />
                <DetailMetric label="触发率 / 延续合格率" value={issueTitle(summaryView)} />
                <DetailMetric label="T+2 平均回撤" value={pct(summaryView.decisionTop3AvgT2MaxDrawdownPct)} />
              </div>
              <RunProgressPanel run={run} title="当前任务快照" />
              {run.status === 'running' || run.status === 'queued' ? (
                <div className="rounded-xl border border-info/30 bg-info/8 px-4 py-3 text-sm text-info">
                  {run.status === 'queued'
                    ? '回测任务正在队列中等待执行。点击上方“刷新进度”可以看到它是否已经开始跑。'
                    : '回测任务已转入后台计算，页面会每 4 秒自动刷新一次进度。你也可以点击上方“刷新进度”手动确认它是否还在继续推进。'}
                </div>
              ) : null}
              <div className="grid gap-3 md:grid-cols-4">
                <DetailMetric label="候选池均值" value={num(summaryView.avgCandidateCount)} />
                <DetailMetric label="默认组合均值" value={num(summaryView.avgSelectedCount)} />
                <DetailMetric label="Ready 数量均值" value={num(summaryView.avgBuyReadyCount)} />
                <DetailMetric label="问题总数" value={String(issues?.totalIssues ?? 0)} />
              </div>
              {run.errorMessage ? (
                <div className="rounded-xl border border-danger/30 bg-danger/8 px-4 py-3 text-sm text-danger">
                  {run.errorMessage}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {Object.entries(summaryView.actionBreakdown).map(([key, count]) => (
                  <Badge key={key} variant="default">{key}: {count}</Badge>
                ))}
              </div>
            </Card>

            <Card padding="lg" className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="label-uppercase">Issue Radar</span>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">区间问题清单</h3>
                </div>
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-warning" />
                  <span className="text-sm text-secondary-text">{issues?.totalIssues ?? 0} 项</span>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <DetailMetric label="高优先" value={String(issues?.severityBreakdown?.critical ?? 0)} />
                <DetailMetric label="关注" value={String(issues?.severityBreakdown?.warning ?? 0)} />
                <DetailMetric label="提示" value={String(issues?.severityBreakdown?.info ?? 0)} />
              </div>
              <div className="space-y-3">
                {(issues?.items ?? []).slice(0, 4).map((issue) => (
                  <div key={`${issue.tradeDate}-${issue.issueKey}`} className="rounded-xl border border-border/60 bg-card/60 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-foreground">{issue.title}</div>
                        <div className="mt-1 text-xs text-secondary-text">{issue.tradeDate} · {issue.actionLabel}</div>
                      </div>
                      {severityBadge(issue.severity)}
                    </div>
                    <p className="mt-2 text-sm text-secondary-text">{issue.summary}</p>
                  </div>
                ))}
                {!issues?.items?.length ? (
                  <div className="rounded-xl border border-border/60 border-dashed px-4 py-6 text-sm text-muted-text">
                    当前区间暂未识别出明显问题。
                  </div>
                ) : null}
              </div>
            </Card>
          </div>

          <V13RunDiagnosticsSection diagnostics={summaryView.v13Diagnostics} />

          <Card padding="lg" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Benchmark Comparison</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">比较基准区</h3>
              </div>
              <div className="text-sm text-secondary-text">用官方 Top3 对比候选池 Top10、原始排序、主线龙头和空仓基准</div>
            </div>
              <div className="grid gap-4 xl:grid-cols-3">
                {summaryView.benchmarkComparison.map((item) => (
                  <BenchmarkCard key={item.key} item={item} />
                ))}
              </div>
          </Card>

          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <Card padding="lg" className="space-y-4">
              <div>
                <span className="label-uppercase">Layer Diagnostics</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">分层诊断区</h3>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
                {summaryView.layerDiagnostics.map((item) => (
                  <LayerCard key={item.key} item={item} />
                ))}
              </div>
            </Card>

            <Card padding="lg" className="space-y-4">
              <div>
                <span className="label-uppercase">Market Regime</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">市场分桶区</h3>
              </div>
              <div className="space-y-4">
                {summaryView.regimeBreakdown.map((item) => (
                  <RegimeCard key={item.level} item={item} />
                ))}
              </div>
            </Card>
          </div>

          <Card padding="lg" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Gate Modules</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">总闸门细分模块复盘</h3>
              </div>
              <div className="text-sm text-secondary-text">按模块统计哪些地方最常拖后腿，以及这些弱项日的真实结果表现。</div>
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              {summaryView.gateModuleBreakdown.map((item) => (
                <GateModuleBreakdownCard key={item.key} item={item} />
              ))}
            </div>
          </Card>

          <Card padding="lg" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Issues</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">完整问题清单</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(issues?.issueKeyBreakdown ?? {}).slice(0, 6).map(([key, count]) => (
                  <Badge key={key} variant="default">{key}: {count}</Badge>
                ))}
              </div>
            </div>
            {!issues?.items?.length ? (
              <EmptyState
                title="当前没有结构化问题"
                description="这轮回测里暂未识别到需要收口的问题项。"
                className="border-dashed"
              />
            ) : (
              <div className="space-y-3">
                {issues.items.map((issue) => (
                  <div key={`${issue.tradeDate}-${issue.issueKey}`} className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-foreground">{issue.title}</div>
                        <div className="mt-1 text-xs text-secondary-text">{issue.tradeDate} · {issue.actionLabel}</div>
                        <p className="mt-2 text-sm leading-6 text-secondary-text">{issue.summary}</p>
                      </div>
                      {severityBadge(issue.severity)}
                    </div>
                    {issue.affectedCodes.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {issue.affectedCodes.map((code) => (
                          <Badge key={code} variant="default">{code}</Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card padding="lg" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Daily Replay</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">日级回放区</h3>
              </div>
              <div className="text-sm text-secondary-text">当前共 {dailyTotal} 条，页码 {dailyPage}</div>
            </div>

            <div className="grid gap-3 xl:grid-cols-[1fr_1fr_0.8fr_0.8fr_0.8fr_auto]">
              <div>
                <div className="mb-1 text-xs text-muted-text">日期起点</div>
                <input
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  type="date"
                  value={dailyFilters.dateFrom}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, dateFrom: e.target.value }))}
                />
              </div>
              <div>
                <div className="mb-1 text-xs text-muted-text">日期终点</div>
                <input
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  type="date"
                  value={dailyFilters.dateTo}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, dateTo: e.target.value }))}
                />
              </div>
              <div>
                <div className="mb-1 text-xs text-muted-text">市场分桶</div>
                <select
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  value={dailyFilters.marketRegime}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, marketRegime: e.target.value }))}
                >
                  <option value="">全部</option>
                  <option value="strong">强市</option>
                  <option value="general">中性市</option>
                  <option value="weak">弱市</option>
                </select>
              </div>
              <div>
                <div className="mb-1 text-xs text-muted-text">总闸门级别</div>
                <select
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  value={dailyFilters.actionLevel}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, actionLevel: e.target.value }))}
                >
                  <option value="">全部</option>
                  <option value="strong_go">强烈可做</option>
                  <option value="normal_go">可正常出手</option>
                  <option value="cautious_go">谨慎出手</option>
                  <option value="observe_only">仅观察</option>
                  <option value="stand_aside">今日不做</option>
                </select>
              </div>
              <div>
                <div className="mb-1 text-xs text-muted-text">槽位</div>
                <select
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  value={dailyFilters.slot}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, slot: e.target.value }))}
                >
                  <option value="">全部</option>
                  <option value="main">主仓</option>
                  <option value="secondary">次仓</option>
                  <option value="watch">观察仓</option>
                </select>
              </div>
              <div className="flex items-end gap-2">
                <button type="button" className="btn-primary" onClick={() => void handleApplyFilters()} disabled={isLoadingDaily}>
                  {isLoadingDaily ? '筛选中...' : '应用筛选'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => void handleResetFilters()} disabled={isLoadingDaily}>
                  重置
                </button>
              </div>
            </div>

            <div className="grid gap-3 xl:grid-cols-[1fr_auto]">
              <div>
                <div className="mb-1 text-xs text-muted-text">主线主题</div>
                <input
                  className={COMPACT_INPUT_CLASS + ' w-full'}
                  value={dailyFilters.themeName}
                  onChange={(e) => setDailyFilters((prev) => ({ ...prev, themeName: e.target.value }))}
                  placeholder="输入主线关键字，例如 锂电 / 机器人"
                />
              </div>
              <div className="flex items-end text-xs text-muted-text">
                页面按单个 run 展示，版本筛选以当前 run 的引擎 / 入口 / 市场范围版本为准。
              </div>
            </div>

            {dailyItems.length === 0 ? (
              <EmptyState
                title="当前筛选条件下没有日级结果"
                description="可以放宽市场分桶、总闸门级别或主线关键字后再试。"
                className="border-dashed"
              />
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-[1120px] w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/60 text-left text-xs uppercase tracking-[0.2em] text-muted-text">
                        <th className="px-3 py-3">交易日</th>
                        <th className="px-3 py-3">出手级别</th>
                        <th className="px-3 py-3">市场分桶</th>
                        <th className="px-3 py-3">机会 / 历史</th>
                        <th className="px-3 py-3">候选池 / 排序集</th>
                        <th className="px-3 py-3">默认组合</th>
                        <th className="px-3 py-3">Ready</th>
                        <th className="px-3 py-3">主仓 / 次仓 / 观察仓</th>
                        <th className="px-3 py-3 text-right">详情</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyItems.map((item) => (
                        <tr key={item.tradeDate} className="border-b border-border/40">
                          <td className="px-3 py-3 text-foreground">{item.tradeDate}</td>
                          <td className="px-3 py-3">{actionBadge(item.actionLevel)}</td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-2">
                              {levelBadge(item.marketEnvironmentLevel)}
                              <span className="text-secondary-text">{levelLabel(item.marketEnvironmentLevel)}</span>
                            </div>
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex flex-wrap gap-2">
                              <Badge variant="default">{item.opportunityQualityLevel}</Badge>
                              <Badge variant="default">{item.historicalValidityLevel}</Badge>
                            </div>
                          </td>
                          <td className="px-3 py-3 text-secondary-text">{item.candidateCount} / {item.resultCount}</td>
                          <td className="px-3 py-3 text-secondary-text">{item.selectedCount}</td>
                          <td className="px-3 py-3 text-secondary-text">{item.buyReadyCount}</td>
                          <td className="px-3 py-3 text-secondary-text">
                            {item.mainTsCode ?? '--'} / {item.secondaryTsCode ?? '--'} / {item.watchTsCode ?? '--'}
                          </td>
                          <td className="px-3 py-3 text-right">
                            <button type="button" className="btn-secondary gap-2" onClick={() => void handleOpenDetail(item.tradeDate)}>
                              查看
                              <ChevronRight className="h-4 w-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/40 pt-3">
                  <div className="text-sm text-secondary-text">本页 {dailyItems.length} 条，累计 {dailyTotal} 条</div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="btn-secondary gap-2"
                      disabled={dailyPage <= 1 || isLoadingDaily}
                      onClick={() => void handlePageChange(dailyPage - 1)}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      上一页
                    </button>
                    <div className="rounded-xl border border-border/60 px-3 py-2 text-sm text-secondary-text">第 {dailyPage} 页</div>
                    <button
                      type="button"
                      className="btn-secondary gap-2"
                      disabled={!dailyHasMore || isLoadingDaily}
                      onClick={() => void handlePageChange(dailyPage + 1)}
                    >
                      下一页
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </Card>
        </>
      )}

      <Drawer
        isOpen={Boolean(selectedDetail) || isLoadingDetail}
        onClose={() => {
          setSelectedDetail(null);
          setDetailError(null);
        }}
        title={selectedDetail ? `V1 回测单日详情 · ${selectedDetail.tradeDate}` : '加载单日详情'}
        width="max-w-6xl"
      >
        {isLoadingDetail ? (
          <div className="flex min-h-[20rem] items-center justify-center">
            <Loader2 className="h-7 w-7 animate-spin text-cyan" />
          </div>
        ) : detailError ? (
          <ApiErrorAlert error={detailError} />
        ) : selectedDetail ? (
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-4">
              <DetailMetric label="官方结论" value={selectedDetail.dailyContext.actionLabel} />
              <DetailMetric label="推荐上限" value={selectedDetail.dailyContext.recommendationCap} />
              <DetailMetric label="行动清单模式" value={selectedDetail.dailyContext.actionChecklistMode} />
              <DetailMetric label="Ready 数量" value={String(selectedDetail.dailyContext.buyReadyCount)} />
            </div>

            <Card padding="lg" className="space-y-3">
              <div>
                <span className="label-uppercase">Diagnosis Summary</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">问题诊断摘要</h3>
              </div>
              <div className="space-y-2">
                {selectedDetail.diagnosis.summaryLines.map((line, index) => (
                  <p key={index} className="text-sm text-secondary-text">{line}</p>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <DetailMetric label="候选池延续合格率" value={pct(selectedDetail.diagnosis.candidateMetrics.positiveT2RatePct)} />
                <DetailMetric label="默认组合延续合格率" value={pct(selectedDetail.diagnosis.decisionMetrics.positiveT2RatePct)} />
                <DetailMetric label="候选池 T+2 利润窗口" value={pct(selectedDetail.diagnosis.candidateMetrics.avgT2ProfitWindowPct)} />
                <DetailMetric label="默认组合 T+2 最大回撤" value={pct(selectedDetail.diagnosis.decisionMetrics.avgT2MaxDrawdownPct)} />
              </div>
            </Card>

            <V13DailyDiagnosticsSection diagnostics={selectedDetail.v13Diagnostics} />

            <Card padding="lg" className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="label-uppercase">Gate Snapshot</span>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">当日总闸门快照</h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedDetail.diagnosis.gateBlockers.length > 0 ? (
                    selectedDetail.diagnosis.gateBlockers.map((item) => (
                      <Badge key={`${item.groupKey}-${item.key}`} variant="warning">
                        拖后腿：{item.label}
                      </Badge>
                    ))
                  ) : (
                    <Badge variant="success">当日无明显拖后腿模块</Badge>
                  )}
                </div>
              </div>
              <div className="grid gap-4 xl:grid-cols-3">
                {selectedDetail.diagnosis.gateSnapshot.map((group) => (
                  <GateSnapshotGroupCard key={group.key} group={group} />
                ))}
              </div>
            </Card>

            <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
              <Card padding="lg" className="space-y-4">
                <div>
                  <span className="label-uppercase">Candidate Top10</span>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">候选池 Top10 回放</h3>
                </div>
                <div className="overflow-x-auto">
                      <table className="min-w-[860px] w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/60 text-left text-xs uppercase tracking-[0.2em] text-muted-text">
                        <th className="px-3 py-3">排名</th>
                        <th className="px-3 py-3">股票</th>
                        <th className="px-3 py-3">主线 / 角色</th>
                        <th className="px-3 py-3">官方总分</th>
                        <th className="px-3 py-3">延续合格</th>
                        <th className="px-3 py-3">T+2 利润窗口</th>
                        <th className="px-3 py-3">T+2 回撤</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedDetail.candidateTop10.map((item) => (
                        <tr key={item.tsCode} className="border-b border-border/40">
                          <td className="px-3 py-3">{item.rank}</td>
                          <td className="px-3 py-3">
                            <div className="font-medium text-foreground">{item.name}</div>
                            <div className="text-xs text-muted-text">{item.tsCode}</div>
                          </td>
                          <td className="px-3 py-3 text-secondary-text">{item.theme ?? '--'} / {item.role ?? '--'}</td>
                          <td className="px-3 py-3 text-secondary-text">
                            {num(item.officialScore ?? item.rankScore)}
                          </td>
                          <td className="px-3 py-3 text-secondary-text">{item.outcome?.settlementPass ? '是' : '否'}</td>
                          <td className="px-3 py-3 text-secondary-text">{pct(item.outcome?.t2ProfitWindowPct)}</td>
                          <td className="px-3 py-3 text-secondary-text">{pct(item.outcome?.t2MaxDrawdownPct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card padding="lg" className="space-y-4">
                <div>
                  <span className="label-uppercase">Decision Top3</span>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">默认组合回放</h3>
                </div>
                <div className="space-y-3">
                  {selectedDetail.slotView.map((item) => (
                    <div key={`${item.slot}-${item.tsCode}`} className="rounded-xl border border-border/60 bg-card/60 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge variant="info">{slotLabel(item.slot)}</Badge>
                            <span className="font-medium text-foreground">{item.name}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-text">{item.tsCode} · {item.theme ?? '--'} / {item.role ?? '--'}</div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="default">{item.buyPointStatus ?? '--'}</Badge>
                          <Badge variant="default">{item.suggestedAction ?? '--'}</Badge>
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-4">
                        <DetailMetric
                          label="买点区间"
                          value={item.entryRangeLow != null && item.entryRangeHigh != null ? `${item.entryRangeLow} - ${item.entryRangeHigh}` : '--'}
                        />
                        <DetailMetric label="延续合格" value={item.outcome?.settlementPass ? '是' : '否'} />
                        <DetailMetric label="T+2 利润窗口" value={pct(item.outcome?.t2ProfitWindowPct)} />
                        <DetailMetric label="T+2 回撤" value={pct(item.outcome?.t2MaxDrawdownPct)} />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            <Card padding="lg" className="space-y-4">
              <div>
                <span className="label-uppercase">Issue List</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">单日问题列表</h3>
              </div>
              {selectedDetail.diagnosis.issues.length === 0 ? (
                <div className="rounded-xl border border-border/60 border-dashed px-4 py-6 text-sm text-muted-text">
                  本日未识别出明显的候选池、排序、买点或总闸门问题。
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedDetail.diagnosis.issues.map((issue) => (
                    <div key={issue.issueKey} className="rounded-xl border border-border/60 bg-card/60 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-foreground">{issue.title}</div>
                          <p className="mt-1 text-sm text-secondary-text">{issue.summary}</p>
                        </div>
                        {severityBadge(issue.severity)}
                      </div>
                      {issue.affectedCodes.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {issue.affectedCodes.map((code) => (
                            <Badge key={code} variant="default">{code}</Badge>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
};
