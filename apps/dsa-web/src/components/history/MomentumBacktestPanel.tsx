import type React from 'react';
import { useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, Search } from 'lucide-react';
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
  MomentumBacktestRegimeBreakdownItem,
  MomentumBacktestRunResponse,
  MomentumBacktestSummary,
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
        <Badge variant="default">{pct(item.positiveT2RatePct)}</Badge>
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
        <DetailMetric label="T+2 正收益率" value={pct(item.decisionPositiveT2RatePct)} />
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

export const MomentumBacktestPanel: React.FC = () => {
  const [startTradeDate, setStartTradeDate] = useState('2026-04-08');
  const [endTradeDate, setEndTradeDate] = useState('2026-04-10');
  const [profile, setProfile] = useState<'standard' | 'aggressive'>('standard');
  const [topN, setTopN] = useState('30');
  const [runIdInput, setRunIdInput] = useState('');
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
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [isLoadingDaily, setIsLoadingDaily] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [panelError, setPanelError] = useState<ParsedApiError | null>(null);
  const [detailError, setDetailError] = useState<ParsedApiError | null>(null);

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
  ) => {
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
  };

  const handleCreateRun = async () => {
    setIsSubmitting(true);
    setPanelError(null);
    try {
      const created = await momentumBacktestApi.createRun({
        startTradeDate,
        endTradeDate,
        profile,
        topN: Number(topN) || 30,
      });
      await loadRunArtifacts(created.runId, DEFAULT_DAILY_FILTERS, created);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLoadRun = async () => {
    const runId = runIdInput.trim();
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
    setPanelError(null);
    try {
      await loadRunArtifacts(runId, dailyFilters);
    } catch (error) {
      setPanelError(getParsedApiError(error));
    } finally {
      setIsLoadingRun(false);
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

  return (
    <div className="space-y-4">
      <Card variant="gradient" padding="lg" className="animate-fade-in">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <span className="label-uppercase">Momentum Backtest V1</span>
              <h2 className="mt-1 text-xl font-semibold text-foreground">强势筛选回测结果页</h2>
              <p className="mt-2 max-w-3xl text-sm text-secondary-text">
                回放 V1 生产链路，冻结候选池 Top10、二次决策 Top3 与 T+1 / T+2 结果，并按“概览、基准、分层诊断、市场分桶、问题清单、日级回放”统一查看。
              </p>
            </div>
            <div className="flex items-center gap-2">
              {profileBadge(profile)}
              <Badge variant="default">统一入口 5 / 3 / 3</Badge>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1.2fr_0.8fr_0.8fr_auto]">
            <div>
              <div className="mb-1 text-xs text-muted-text">起始交易日</div>
              <input className={INPUT_CLASS} type="date" value={startTradeDate} onChange={(e) => setStartTradeDate(e.target.value)} />
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-text">结束交易日</div>
              <input className={INPUT_CLASS} type="date" value={endTradeDate} onChange={(e) => setEndTradeDate(e.target.value)} />
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-text">画像</div>
              <select className={INPUT_CLASS} value={profile} onChange={(e) => setProfile(e.target.value as 'standard' | 'aggressive')}>
                <option value="standard">Standard</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-text">展示数量</div>
              <input className={INPUT_CLASS} type="number" min={1} max={100} value={topN} onChange={(e) => setTopN(e.target.value)} />
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
              <button type="button" className="btn-secondary w-full gap-2" onClick={handleLoadRun} disabled={isLoadingRun}>
                {isLoadingRun ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                加载任务
              </button>
            </div>
          </div>
        </div>
      </Card>

      {panelError ? <ApiErrorAlert error={panelError} /> : null}

      {!run || !summary ? (
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
                  {profileBadge(run.profile)}
                  <Badge variant="default">{run.engineVersion}</Badge>
                  <Badge variant="default">{run.entryBaselineVersion}</Badge>
                  <Badge variant="default">{run.marketScopeVersion}</Badge>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-4">
                <DetailMetric label="回测区间" value={`${run.startTradeDate} → ${run.endTradeDate}`} />
                <DetailMetric label="已处理交易日" value={`${run.processedTradeDates} / ${run.totalTradeDates}`} />
                <DetailMetric label="触发率 / T+2 正收益率" value={issueTitle(summary)} />
                <DetailMetric label="T+2 平均回撤" value={pct(summary.decisionTop3AvgT2MaxDrawdownPct)} />
              </div>
              <div className="grid gap-3 md:grid-cols-4">
                <DetailMetric label="候选池均值" value={num(summary.avgCandidateCount)} />
                <DetailMetric label="默认组合均值" value={num(summary.avgSelectedCount)} />
                <DetailMetric label="Ready 数量均值" value={num(summary.avgBuyReadyCount)} />
                <DetailMetric label="问题总数" value={String(issues?.totalIssues ?? 0)} />
              </div>
              {run.errorMessage ? (
                <div className="rounded-xl border border-danger/30 bg-danger/8 px-4 py-3 text-sm text-danger">
                  {run.errorMessage}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.actionBreakdown).map(([key, count]) => (
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

          <Card padding="lg" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Benchmark Comparison</span>
                <h3 className="mt-1 text-lg font-semibold text-foreground">比较基准区</h3>
              </div>
              <div className="text-sm text-secondary-text">用官方 Top3 对比候选池 Top10、原始排序、主线龙头和空仓基准</div>
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              {summary.benchmarkComparison.map((item) => (
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
                {summary.layerDiagnostics.map((item) => (
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
                {summary.regimeBreakdown.map((item) => (
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
              {summary.gateModuleBreakdown.map((item) => (
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
                <DetailMetric label="候选池 T+2 正收益率" value={pct(selectedDetail.diagnosis.candidateMetrics.positiveT2RatePct)} />
                <DetailMetric label="默认组合 T+2 正收益率" value={pct(selectedDetail.diagnosis.decisionMetrics.positiveT2RatePct)} />
                <DetailMetric label="候选池 T+2 利润窗口" value={pct(selectedDetail.diagnosis.candidateMetrics.avgT2ProfitWindowPct)} />
                <DetailMetric label="默认组合 T+2 最大回撤" value={pct(selectedDetail.diagnosis.decisionMetrics.avgT2MaxDrawdownPct)} />
              </div>
            </Card>

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
                  <table className="min-w-[760px] w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/60 text-left text-xs uppercase tracking-[0.2em] text-muted-text">
                        <th className="px-3 py-3">排名</th>
                        <th className="px-3 py-3">股票</th>
                        <th className="px-3 py-3">主线 / 角色</th>
                        <th className="px-3 py-3">排序分</th>
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
                          <td className="px-3 py-3 text-secondary-text">{num(item.rankScore)}</td>
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
                      <div className="mt-3 grid gap-3 md:grid-cols-3">
                        <DetailMetric
                          label="买点区间"
                          value={item.entryRangeLow != null && item.entryRangeHigh != null ? `${item.entryRangeLow} - ${item.entryRangeHigh}` : '--'}
                        />
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
