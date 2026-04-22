import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MomentumBacktestPanel } from '../MomentumBacktestPanel';

const {
  mockCreateRun,
  mockListRuns,
  mockGetRun,
  mockGetSummary,
  mockGetDaily,
  mockGetDailyDetail,
  mockGetIssues,
  mockCancelRun,
  mockDeleteRun,
} = vi.hoisted(() => ({
  mockCreateRun: vi.fn(),
  mockListRuns: vi.fn(),
  mockGetRun: vi.fn(),
  mockGetSummary: vi.fn(),
  mockGetDaily: vi.fn(),
  mockGetDailyDetail: vi.fn(),
  mockGetIssues: vi.fn(),
  mockCancelRun: vi.fn(),
  mockDeleteRun: vi.fn(),
}));

vi.mock('../../../api/momentumBacktest', () => ({
  momentumBacktestApi: {
    createRun: mockCreateRun,
    listRuns: mockListRuns,
    getRun: mockGetRun,
    getSummary: mockGetSummary,
    getDaily: mockGetDaily,
    getDailyDetail: mockGetDailyDetail,
    getIssues: mockGetIssues,
    cancelRun: mockCancelRun,
    deleteRun: mockDeleteRun,
  },
}));

const completedRun = {
  runId: 'momentum_bt_test',
  status: 'completed' as const,
  profile: 'standard' as const,
  engineVersion: 'momentum-v1',
  entryBaselineVersion: 'entry-5-3-3',
  marketScopeVersion: 'scope-all-market',
  topN: 30,
  startTradeDate: '2026-04-08',
  endTradeDate: '2026-04-10',
  totalTradeDates: 3,
  processedTradeDates: 3,
  failedTradeDates: 0,
  currentTradeDate: '2026-04-10',
  currentStageKey: 'completed',
  currentStageLabel: '任务已完成',
  heartbeatAt: '2026-04-17T08:01:00Z',
  startedAt: '2026-04-17T08:00:00Z',
  finishedAt: '2026-04-17T08:01:00Z',
  cancelRequested: false,
  summary: null,
  errorMessage: null,
  createdAt: '2026-04-17T08:00:00Z',
  updatedAt: '2026-04-17T08:01:00Z',
};

const runningRun = {
  ...completedRun,
  runId: 'momentum_bt_running',
  status: 'running' as const,
  processedTradeDates: 1,
  currentTradeDate: '2026-04-08',
  currentStageKey: 'candidate_pool',
  currentStageLabel: '候选池计算中',
  heartbeatAt: '2026-04-17T07:05:00Z',
  startedAt: '2026-04-17T07:00:00Z',
  finishedAt: null,
  createdAt: '2026-04-17T07:00:00Z',
  updatedAt: '2026-04-17T07:05:00Z',
};

const queuedRun = {
  ...completedRun,
  runId: 'momentum_bt_queued',
  status: 'queued' as const,
  processedTradeDates: 0,
  currentTradeDate: null,
  currentStageKey: 'queued',
  currentStageLabel: '等待后台调度',
  heartbeatAt: '2026-04-17T07:06:00Z',
  startedAt: null,
  finishedAt: null,
  createdAt: '2026-04-17T07:06:00Z',
  updatedAt: '2026-04-17T07:06:00Z',
};

const cancelledRun = {
  ...completedRun,
  runId: 'momentum_bt_cancelled',
  status: 'cancelled' as const,
  processedTradeDates: 1,
  currentTradeDate: '2026-04-09',
  currentStageKey: 'cancelled',
  currentStageLabel: '任务已取消',
  heartbeatAt: '2026-04-17T06:05:00Z',
  startedAt: '2026-04-17T06:00:00Z',
  finishedAt: '2026-04-17T06:05:00Z',
  createdAt: '2026-04-17T06:00:00Z',
  updatedAt: '2026-04-17T06:05:00Z',
};

const summaryResponse = {
  runId: 'momentum_bt_test',
  profile: 'standard' as const,
  engineVersion: 'momentum-v1',
  summary: {
    completedTradeDates: 3,
    actionBreakdown: {
      observe_only: 2,
      cautious_go: 1,
    },
    marketEnvironmentBreakdown: {
      strong: 1,
      general: 1,
      weak: 1,
    },
    opportunityQualityBreakdown: {
      strong: 1,
      general: 1,
      weak: 1,
    },
    historicalValidityBreakdown: {
      strong: 1,
      general: 1,
      weak: 1,
    },
    avgCandidateCount: 74,
    avgSelectedCount: 3,
    avgBuyReadyCount: 1.3,
    candidateTop10BuyTriggerRate: 46,
    candidateTop10PositiveT2Rate: 58,
    candidateTop10AvgT2ProfitWindowPct: 4.8,
    candidateTop10AvgT2MaxDrawdownPct: 2.6,
    decisionTop3BuyTriggerRate: 51,
    decisionTop3PositiveT1Rate: 47,
    decisionTop3PositiveT2Rate: 61,
    decisionTop3AvgT1ProfitWindowPct: 2.9,
    decisionTop3AvgT2ProfitWindowPct: 5.4,
    decisionTop3AvgT2MaxDrawdownPct: 2.2,
    benchmarkComparison: [
      {
        key: 'official_top3',
        label: '官方 Top3',
        sampleCount: 9,
        triggerRatePct: 51,
        positiveT2RatePct: 61,
        avgT2ProfitWindowPct: 5.4,
        avgT2MaxDrawdownPct: 2.2,
        alphaVsOfficialTop3Pct: 0,
        alphaVsCandidateTop10Pct: 0.6,
      },
    ],
    layerDiagnostics: [
      {
        key: 'gate',
        label: '总闸门',
        level: 'general' as const,
        score: 62,
        summary: '当前总闸门更多由机会质量和买点清晰度在收口。',
        metrics: {
          top_gate_blocker_days: 2,
        },
      },
    ],
    gateModuleBreakdown: [
      {
        key: 'sentiment',
        label: '市场情绪',
        groupKey: 'market_environment',
        groupLabel: '市场环境',
        sampleDays: 3,
        strongDays: 1,
        mediumDays: 1,
        weakDays: 1,
        blockerDays: 1,
        restrictedDays: 1,
        avgScore: 63.3,
        weakDayCandidatePositiveT2RatePct: 40,
        weakDayDecisionPositiveT2RatePct: 33.3,
        weakDayCandidateAvgT2ProfitWindowPct: 2.1,
        weakDayDecisionAvgT2ProfitWindowPct: 1.4,
        strongDayDecisionAvgT2ProfitWindowPct: 6.2,
        summary: '市场情绪转弱时，默认组合延续性明显下滑。',
      },
    ],
    regimeBreakdown: [
      {
        level: 'strong' as const,
        label: '强市',
        tradeDays: 1,
        decisionPositiveT2RatePct: 100,
        decisionAvgT2ProfitWindowPct: 7.5,
        decisionAvgT2MaxDrawdownPct: 1.8,
        missedOpportunityRatePct: 0,
        allowedTradePrecisionPct: 100,
        standAsideRatePct: 0,
      },
    ],
  },
};

const dailyResponse = {
  runId: 'momentum_bt_test',
  total: 1,
  page: 1,
  pageSize: 20,
  hasMore: false,
  items: [
    {
      tradeDate: '2026-04-09',
      actionLevel: 'observe_only',
      actionLabel: '仅观察',
      recommendationCap: '1-2 只',
      actionChecklistMode: 'observe',
      marketEnvironmentLevel: 'general',
      opportunityQualityLevel: 'weak',
      historicalValidityLevel: 'general',
      candidateCount: 76,
      resultCount: 30,
      selectedCount: 3,
      buyReadyCount: 1,
      mainTsCode: '002240.SZ',
      secondaryTsCode: '001896.SZ',
      watchTsCode: '603629.SH',
    },
  ],
};

const issuesResponse = {
  runId: 'momentum_bt_test',
  totalIssues: 1,
  severityBreakdown: {
    critical: 0,
    warning: 1,
    info: 0,
  },
  issueKeyBreakdown: {
    buy_point_unclear: 1,
  },
  items: [
    {
      tradeDate: '2026-04-09',
      issueKey: 'buy_point_unclear',
      severity: 'warning' as const,
      title: '买点不清晰导致收口',
      summary: '主仓虽然还在主线内，但回踩承接没有形成可执行结构。',
      affectedCodes: ['002240.SZ'],
      metrics: {
        buy_ready_count: 1,
      },
    },
  ],
};

const detailResponse = {
  runId: 'momentum_bt_test',
  tradeDate: '2026-04-09',
  dailyContext: dailyResponse.items[0],
  candidateTop10: [
    {
      rank: 1,
      tsCode: '002240.SZ',
      name: '盛新锂能',
      theme: '锂电',
      role: '龙头核心',
      marketSegment: '主板',
      rankScore: 68,
      finalScore: 67.7,
      continuationScore: 71.2,
      extensionScore: 69.5,
      riskScore: 18.1,
      buyabilityScore: 51,
      outcome: {
        viewScope: 'candidate_top10',
        slot: 'main',
        tsCode: '002240.SZ',
        name: '盛新锂能',
        buyTriggered: false,
        referenceEntryPrice: 44.86,
        triggerPrice: null,
        triggerTradeDate: null,
        t1TradeDate: '2026-04-10',
        t1CloseReturnPct: 1.3,
        t1ProfitWindowPct: 2.2,
        t1MaxDrawdownPct: 1.1,
        t2TradeDate: '2026-04-13',
        t2CloseReturnPct: 2.8,
        t2ProfitWindowPct: 4.5,
        t2MaxDrawdownPct: 2.0,
        realStrengthLabel: '强势延续',
      },
    },
  ],
  decisionTop3: [],
  slotView: [
    {
      slot: 'main',
      rank: 1,
      tsCode: '002240.SZ',
      name: '盛新锂能',
      theme: '锂电',
      role: '龙头核心',
      decisionScore: 67.7,
      rankScore: 68,
      riskScore: 18.1,
      buyPointStatus: '等待触发',
      suggestedAction: '继续观察',
      entryRangeLow: 44.4,
      entryRangeHigh: 45.3,
      opportunityTag: '主仓',
      outcome: {
        viewScope: 'decision_top3',
        slot: 'main',
        tsCode: '002240.SZ',
        name: '盛新锂能',
        buyTriggered: false,
        referenceEntryPrice: 44.86,
        triggerPrice: null,
        triggerTradeDate: null,
        t1TradeDate: '2026-04-10',
        t1CloseReturnPct: 1.3,
        t1ProfitWindowPct: 2.2,
        t1MaxDrawdownPct: 1.1,
        t2TradeDate: '2026-04-13',
        t2CloseReturnPct: 2.8,
        t2ProfitWindowPct: 4.5,
        t2MaxDrawdownPct: 2.0,
        realStrengthLabel: '强势延续',
      },
    },
  ],
  outcomes: {},
  diagnosis: {
    summaryLines: ['总闸门没有完全失效，但被市场情绪和买点清晰度同时压制。'],
    candidateMetrics: {
      sampleCount: 10,
      triggerRatePct: 46,
      positiveT1RatePct: 42,
      positiveT2RatePct: 58,
      avgT1ProfitWindowPct: 2.4,
      avgT2ProfitWindowPct: 4.8,
      avgT2MaxDrawdownPct: 2.6,
      bestT2ProfitWindowPct: 8.1,
    },
    decisionMetrics: {
      sampleCount: 3,
      triggerRatePct: 33.3,
      positiveT1RatePct: 33.3,
      positiveT2RatePct: 33.3,
      avgT1ProfitWindowPct: 1.5,
      avgT2ProfitWindowPct: 1.9,
      avgT2MaxDrawdownPct: 2.7,
      bestT2ProfitWindowPct: 4.5,
    },
    gateSnapshot: [
      {
        key: 'market_environment',
        label: '市场环境',
        level: 'general',
        levelLabel: '中',
        score: 63,
        reason: '指数没有转坏，但赚钱效应和情绪并不统一。',
        modules: [
          {
            key: 'sentiment',
            label: '市场情绪',
            groupKey: 'market_environment',
            groupLabel: '市场环境',
            level: 'weak',
            levelLabel: '弱',
            score: 45,
            summary: '昨日强势股承接不足，情绪对高位股不够友好。',
          },
        ],
      },
    ],
    gateBlockers: [
      {
        key: 'sentiment',
        label: '市场情绪',
        groupKey: 'market_environment',
        groupLabel: '市场环境',
        level: 'weak',
        levelLabel: '弱',
        score: 45,
        summary: '昨日强势股承接不足，情绪对高位股不够友好。',
      },
    ],
    issues: [
      {
        issueKey: 'buy_point_unclear',
        severity: 'warning' as const,
        title: '买点不清晰导致收口',
        summary: '龙头核心没有回踩承接，前排换手也没有给出分歧转一致。',
        affectedCodes: ['002240.SZ'],
        metrics: {
          buy_ready_count: 1,
        },
      },
    ],
  },
};

const recentRunsResponse = {
  currentRunning: runningRun,
  queued: {
    total: 1,
    items: [queuedRun],
  },
  history: {
    total: 2,
    limit: 20,
    items: [completedRun, cancelledRun],
  },
  refreshedAt: '2026-04-17T08:05:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockCreateRun.mockResolvedValue({
    createdNew: true,
    message: '已创建回测任务，正在后台计算',
    run: runningRun,
  });
  mockListRuns.mockResolvedValue(recentRunsResponse);
  mockGetRun.mockResolvedValue(completedRun);
  mockGetSummary.mockResolvedValue(summaryResponse);
  mockGetDaily.mockResolvedValue(dailyResponse);
  mockGetIssues.mockResolvedValue(issuesResponse);
  mockGetDailyDetail.mockResolvedValue(detailResponse);
  mockCancelRun.mockResolvedValue({
    ...runningRun,
    status: 'cancelled',
    currentStageKey: 'cancelled',
    currentStageLabel: '任务已取消',
    cancelRequested: false,
  });
  mockDeleteRun.mockResolvedValue({
    runId: 'momentum_bt_queued',
    deleted: true,
    message: '任务已删除',
  });
});

describe('MomentumBacktestPanel', () => {
  it('shows the empty state before any run is loaded', () => {
    render(<MomentumBacktestPanel />);

    expect(screen.getByText('还没有 V1 回测结果')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '创建回测' })).toBeInTheDocument();
  });

  it('loads the three-section task center and supports loading a queued task', async () => {
    render(<MomentumBacktestPanel />);

    expect(await screen.findByText('回测任务中心')).toBeInTheDocument();
    expect(screen.getByText('当前运行任务')).toBeInTheDocument();
    expect(screen.getByText('排队中任务')).toBeInTheDocument();
    expect(screen.getByText('历史任务')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /momentum_bt_running/ })).toBeInTheDocument();

    const queuedRunCode = await screen.findByText('momentum_bt_queued');
    const queuedRunRow = queuedRunCode.closest('.rounded-xl');
    expect(queuedRunRow).not.toBeNull();

    fireEvent.click(within(queuedRunRow as HTMLElement).getByRole('button', { name: '加载任务' }));

    await waitFor(() => {
      expect(mockGetSummary).toHaveBeenLastCalledWith('momentum_bt_queued');
      expect(mockGetDaily).toHaveBeenLastCalledWith('momentum_bt_queued', {
        dateFrom: undefined,
        dateTo: undefined,
        marketRegime: undefined,
        actionLevel: undefined,
        slot: undefined,
        themeName: undefined,
        page: 1,
        pageSize: 20,
      });
      expect(mockGetIssues).toHaveBeenLastCalledWith('momentum_bt_queued');
    });
  });

  it('shows a manual refresh notice for the current running task', async () => {
    render(<MomentumBacktestPanel />);

    expect(await screen.findByText('回测任务中心')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '刷新进度' }));

    await waitFor(() => {
      expect(mockListRuns).toHaveBeenCalledTimes(2);
    });

    expect(
      await screen.findByText((content) => content.includes('momentum_bt_running') && content.includes('已刷新')),
    ).toBeInTheDocument();
  });

  it('creates a run, shows task feedback, and renders gate diagnostics', async () => {
    render(<MomentumBacktestPanel />);

    fireEvent.click(screen.getByRole('button', { name: '创建回测' }));

    await waitFor(() => {
      expect(mockCreateRun).toHaveBeenCalledWith({
        startTradeDate: '2026-04-08',
        endTradeDate: '2026-04-10',
        profile: 'standard',
        topN: 30,
      });
    });

    expect(await screen.findByText('已创建回测任务，正在后台计算')).toBeInTheDocument();
    expect(await screen.findByText('总闸门细分模块复盘')).toBeInTheDocument();
    expect(screen.getAllByText('市场情绪').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: '查看' }));

    await waitFor(() => {
      expect(mockGetDailyDetail).toHaveBeenCalledWith('momentum_bt_running', '2026-04-09');
    });

    expect(await screen.findByText('当日总闸门快照')).toBeInTheDocument();
    expect(screen.getByText('拖后腿：市场情绪')).toBeInTheDocument();
  }, 10000);

  it('supports cancelling the running task and deleting a queued task', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<MomentumBacktestPanel />);

    expect(await screen.findByText('回测任务中心')).toBeInTheDocument();
    const runningRunCode = await screen.findByText('momentum_bt_running');
    const queuedRunCode = await screen.findByText('momentum_bt_queued');
    const runningRunRow = runningRunCode.closest('.rounded-xl');
    const queuedRunRow = queuedRunCode.closest('.rounded-xl');
    expect(runningRunRow).not.toBeNull();
    expect(queuedRunRow).not.toBeNull();

    fireEvent.click(within(runningRunRow as HTMLElement).getByRole('button', { name: '取消任务' }));
    await waitFor(() => {
      expect(mockCancelRun).toHaveBeenCalledWith('momentum_bt_running');
    });

    fireEvent.click(within(queuedRunRow as HTMLElement).getByRole('button', { name: '删除任务' }));
    await waitFor(() => {
      expect(mockDeleteRun).toHaveBeenCalledWith('momentum_bt_queued');
    });

    confirmSpy.mockRestore();
  });
});
