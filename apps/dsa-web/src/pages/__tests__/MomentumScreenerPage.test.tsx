import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MomentumScreenerPage from '../MomentumScreenerPage';
import type {
  MomentumScreenerDecisionResponse,
  MomentumScreenerIntradayResponse,
  MomentumScreenerResponse,
  MomentumScreenerResult,
} from '../../types/momentumScreener';

const { mockScreen } = vi.hoisted(() => ({
  mockScreen: vi.fn(),
}));

const { mockIntraday } = vi.hoisted(() => ({
  mockIntraday: vi.fn(),
}));

const { mockGetSystemConfig } = vi.hoisted(() => ({
  mockGetSystemConfig: vi.fn(),
}));

vi.mock('../../api/momentumScreener', () => ({
  momentumScreenerApi: {
    screen: mockScreen,
    screenWithDecision: mockScreen,
    fetchIntradaySignal: mockIntraday,
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: mockGetSystemConfig,
  },
}));

const standardResponse: MomentumScreenerResponse = {
  profile: 'standard' as const,
  tradeDate: '2026-04-10',
  candidateCount: 3,
  results: [
    {
      rank: 1,
      tsCode: '600001.SH',
      name: 'Alpha Leader',
      pctChg: 9.8,
      continuationScore: 88,
      extensionScore: 70,
      riskScore: 40,
      buyabilityScore: null,
      finalScore: 85,
      rankScore: 76,
      themes: ['Power Equipment'],
      leaderLevel: 'leader',
      topReasons: ['Strength Confirmed'],
      riskTags: ['risk-drift'],
      scoreBreakdown: {
        strength_confirmation: {
          score: 18,
          maxScore: 20,
          items: { pct_chg_strength: 6, close_position: 5 },
        },
      },
    },
    {
      rank: 2,
      tsCode: '600002.SH',
      name: 'Low Risk Runner',
      pctChg: 8.2,
      continuationScore: 72,
      extensionScore: 66,
      riskScore: 10,
      buyabilityScore: null,
      finalScore: 78,
      rankScore: 68,
      themes: ['Power Equipment'],
      leaderLevel: 'front',
      topReasons: ['Sector Resonance'],
      riskTags: [],
      scoreBreakdown: {
        sector_resonance: {
          score: 16,
          maxScore: 20,
          items: { sector_rank: 5, sector_leader: 4 },
        },
      },
    },
  ],
};

const aggressiveResponse: MomentumScreenerResponse = {
  profile: 'aggressive' as const,
  tradeDate: '2026-04-10',
  candidateCount: 2,
  results: [
    {
      rank: 1,
      tsCode: '600003.SH',
      name: 'Breakout One',
      pctChg: 10.0,
      continuationScore: 91,
      extensionScore: 84,
      riskScore: 18,
      buyabilityScore: 77,
      opportunityTag: 'Breakout Consensus',
      entryRangeLow: 10.34,
      entryRangeHigh: 10.66,
      finalScore: 92,
      rankScore: 82,
      themes: ['Robotics'],
      leaderLevel: 'leader',
      topReasons: ['Buyable Setup', 'Volume Track'],
      riskTags: ['risk-alert'],
      scoreBreakdown: {
        buyability: {
          score: 12,
          maxScore: 15,
          items: { amplitude_space: 6, amount_golden_zone: 4 },
        },
        volume_price_track: {
          score: 11,
          maxScore: 15,
          items: { healthy_turnover: 7 },
        },
      },
    },
  ],
};

const mixedKeyResponse: MomentumScreenerResponse = {
  profile: 'aggressive' as const,
  tradeDate: '2026-04-10',
  candidateCount: 1,
  results: [
    {
      rank: 1,
      tsCode: '002733.SZ',
      name: '雄韬股份',
      pctChg: 10.0,
      continuationScore: 72,
      extensionScore: 68.3,
      riskScore: 0,
      buyabilityScore: 66,
      opportunityTag: '一致再加速',
      entryRangeLow: 16.8,
      entryRangeHigh: 17.2,
      finalScore: 69.8,
      rankScore: 69.8,
      themes: ['电力设备'],
      leaderLevel: 'leader',
      topReasons: ['强势确认', '资金承接'],
      riskTags: [],
      scoreBreakdown: {
        strengthConfirmation: {
          score: 21,
          maxScore: 30,
          items: {
            LIMITSTRENGTH: 10,
            GAPOPENSTRENGTH: 3,
            CLOSESTATUS: 6,
            ACCELERATIONCONFIRMATION: 2,
          },
        },
        capitalSupport: {
          score: 16,
          maxScore: 20,
          items: {
            MAININFLOWABS: 6,
            MAININFLOWRATIO: 6,
            PRICEFLOWALIGNMENT: 4,
            TOPLIST: 0,
          },
        },
        buyability: {
          score: 9,
          maxScore: 15,
          items: {
            AMPLITUDESPACE: 0,
            AMOUNTGOLDENZONE: 5,
            TURNOVERGOLDENZONE: 4,
          },
        },
        volumePriceTrack: {
          score: 10,
          maxScore: 15,
          items: {
            CONSENSUSLIMIT: 3,
            HEALTHYTURNOVER: 7,
          },
        },
        sectorResonance: {
          score: 8,
          maxScore: 12,
          items: {
            SECTORRANK: 2,
            SECTORBREADTH: 4,
            SECTORLEADER: 2,
          },
        },
        trendElasticity: {
          score: 6,
          maxScore: 8,
          items: {
            breakout: 4,
            CIRCMV: 0,
            HISTORICALACTIVITY: 2,
          },
        },
      },
    },
  ],
};

function buildDecisionResponse(screening: MomentumScreenerResponse): MomentumScreenerDecisionResponse {
  const topThemeName = screening.results[0]?.themes[0] ?? '未分类';
  const topThemeCandidates = screening.results.filter((item: MomentumScreenerResult) => item.themes[0] === topThemeName);
  const portfolioSource = screening.results.slice(0, Math.min(3, screening.results.length));

  return {
    screening,
    decision: {
      profile: screening.profile,
      tradeDate: screening.tradeDate,
      action: {
        level: 'normal_go' as const,
        label: '可正常出手',
        reason: `${topThemeName} 主线已经比较清晰，当前默认组合里已有可继续跟踪的候选股。`,
        sourceProfile: screening.profile,
      },
      strategyHealth: {
        status: 'healthy' as const,
        label: '正常',
        reason: '20 日可用性与 60 日结构可信度同时健康，允许维持完整强推荐。',
        recommendationCap: 'full' as const,
        canFullRecommend: true,
        shortWindow: {
          window: 'short_20d' as const,
          windowLabel: '20 日当前可用性',
          status: 'healthy' as const,
          statusLabel: '健康',
          score: 82,
          threshold: 68,
          sampleCount: 20,
          successCount: 14,
          successRate: 70,
          avgProfitWindowPct: 2.6,
          avgMaxDrawdownPct: 2.1,
          avgSelectedCount: 2.1,
          summary: '20 日窗口当前可用性已达健康阈值，可继续支撑当前判断。',
        },
        longWindow: {
          window: 'long_60d' as const,
          windowLabel: '60 日结构可信度',
          status: 'healthy' as const,
          statusLabel: '健康',
          score: 78,
          threshold: 64,
          sampleCount: 60,
          successCount: 38,
          successRate: 63.3,
          avgProfitWindowPct: 2.2,
          avgMaxDrawdownPct: 2.8,
          avgSelectedCount: 2.0,
          summary: '60 日窗口结构可信度已达健康阈值，可继续支撑当前判断。',
        },
        blockers: [],
        recoveryConditions: [],
      },
      themes: [
        {
          name: topThemeName,
          score: screening.results[0]?.rankScore ?? 70,
          strengthLabel: '主线清晰',
          candidateCount: topThemeCandidates.length,
          clearBuyPointCount: Math.max(1, Math.min(2, topThemeCandidates.length)),
          leaderCount: topThemeCandidates.filter((item: MomentumScreenerResult) => item.leaderLevel === 'leader').length || 1,
          summary: `${topThemeName} 当前聚集 ${topThemeCandidates.length || screening.results.length} 只强势候选。`,
          representatives: topThemeCandidates.slice(0, 3).map((item: MomentumScreenerResult) => ({
            rank: item.rank,
            tsCode: item.tsCode,
            name: item.name,
            role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
            buyPointLabel: item.buyabilityScore != null && item.buyabilityScore >= 70 ? '买点清晰' : '等待触发',
            rankScore: item.rankScore,
          })),
        },
      ],
      portfolio: portfolioSource.map((item: MomentumScreenerResult, index: number) => ({
        slot: index === 0 ? 'main' : index === 1 ? 'secondary' : 'watch',
        slotLabel: index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓',
        rank: item.rank,
        tsCode: item.tsCode,
        name: item.name,
        theme: item.themes[0] ?? '未分类',
        role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
        score: item.rankScore + 8 - index,
        rankScore: item.rankScore,
        riskScore: item.riskScore,
        buyPointStatus:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? 'clear'
            : item.rankScore >= 70
              ? 'waiting'
              : 'unclear',
        buyPointLabel:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? '买点清晰'
            : item.rankScore >= 70
              ? '等待触发'
              : '买点不清晰',
        suggestedAction:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? 'ready'
            : index < 2
              ? 'wait_for_trigger'
              : 'observe_only',
        suggestedActionLabel:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? '可准备执行'
            : index < 2
              ? '继续等触发'
              : '保留观察但不建议执行',
        primaryReason: item.topReasons[0] ?? '综合强度更优',
        roleReason: `${item.name} 在当前默认组合里承担 ${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'} 角色。`,
        executionPlan:
          item.entryRangeLow != null && item.entryRangeHigh != null
            ? `优先关注 ${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)} 区间确认。`
            : '优先等分时承接与主线回流确认，不建议直接追高。',
        entryHint:
          item.entryRangeLow != null && item.entryRangeHigh != null
            ? `优先关注 ${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)} 区间确认。`
            : null,
        opportunityTag: item.opportunityTag ?? null,
      })),
      excludedCandidates: screening.results.slice(3).map((item: MomentumScreenerResult) => ({
        rank: item.rank,
        tsCode: item.tsCode,
        name: item.name,
        theme: item.themes[0] ?? '未分类',
        role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
        reason: '主线内名次不够',
        rankScore: item.rankScore,
      })),
      evidence: {
        themeValidation: [`${topThemeName} 主线评分 ${(screening.results[0]?.rankScore ?? 70).toFixed(1)}。`],
        todayReasoning: ['系统已基于当前候选引擎重新收口默认组合与落选原因。'],
      },
      actionChecklist: {
        enabled: true,
        reason: '当前出手级别允许生成明日行动清单。',
        steps: [
          {
            phase: 'pre_open' as const,
            phaseLabel: '开盘前',
            objective: '先确认默认组合今天是否还值得继续盯。',
            focusItems: portfolioSource.map(
              (item: MomentumScreenerResult, index: number) =>
                `${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'}：${item.name}`,
            ),
            tasks: ['先看竞价强弱。', '确认谁是开盘后第一跟踪对象。'],
            expectedOutcome: '明确开盘后优先盯主仓、次仓，其余继续观察。',
          },
          {
            phase: 'first_30m' as const,
            phaseLabel: '开盘后 30 分钟',
            objective: '识别谁掉队、谁还保留买点资格。',
            focusItems: portfolioSource
              .slice(0, 2)
              .map((item: MomentumScreenerResult, index: number) => `${index === 0 ? '主仓' : '次仓'}：${item.name}`),
            tasks: ['先排除明显不及预期的票。'],
            expectedOutcome: '只保留仍值得继续跟踪的核心票。',
          },
          {
            phase: 'first_60m' as const,
            phaseLabel: '开盘后 60 分钟内',
            objective: '必须收口成“建议买 / 不建议买”的明确结论。',
            focusItems: portfolioSource.map(
              (item: MomentumScreenerResult, index: number) =>
                `${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'}：${item.name}`,
            ),
            tasks: ['明确优先关注谁、次选谁、其余继续观察。'],
            expectedOutcome: '输出今天最终该不该买的结论。',
          },
        ],
      },
    },
  };
}

function buildIntradayResponse(screening: MomentumScreenerResponse): MomentumScreenerIntradayResponse {
  const decisionResponse = buildDecisionResponse(screening);
  const [mainItem] = decisionResponse.decision.portfolio;

  return {
    ...decisionResponse,
    intradaySignal: {
      marketPhase: 'first_60m' as const,
      marketPhaseLabel: '开盘后 60 分钟内',
      confidenceLevel: 'low' as const,
      confidenceLabel: '低置信度',
      canEmitBuySignal: false,
      status: 'low_confidence' as const,
      statusLabel: '低置信度',
      reason: '主仓开盘后承接明显弱于预期，排序需要继续观察。',
      watchItems: ['主仓：等待分时重新站回开盘价上方。'],
      finalRecommendation: 'do_not_buy' as const,
      finalRecommendationLabel: '不建议买',
      closingNote: '今天结论是不建议买入；固定顺序仍按主仓、次仓、观察仓跟踪。',
      updatedAt: '2026-04-11T09:45:00',
      focusOrder: ['优先关注：主仓 Alpha Leader（不建议追入）'],
      portfolioItems: [
        {
          slot: mainItem.slot,
          slotLabel: mainItem.slotLabel,
          tsCode: mainItem.tsCode,
          name: mainItem.name,
          theme: mainItem.theme,
          role: mainItem.role,
          status: 'do_not_chase' as const,
          statusLabel: '不建议追入',
          reason: '当前价格已经明显偏离建议区间，不建议追入。',
          quoteAvailable: true,
          signalTriggered: false,
          doNotChase: true,
          currentPrice: 10.92,
          changePercent: 4.1,
          openPrice: 10.48,
          entryRangeLow: mainItem.entryRangeLow ?? 10.34,
          entryRangeHigh: mainItem.entryRangeHigh ?? 10.66,
          priceVsOpenPct: 4.2,
          priceVsEntryHighPct: 2.4,
          missingConditions: ['等待价格回到更合理的确认区间。'],
          updateTime: '2026-04-11T09:45:00',
        },
      ],
    },
  };
}

async function clickRunButton() {
  fireEvent.click(screen.getByTestId('momentum-screener-run'));
  await waitFor(() => {
    expect(mockScreen).toHaveBeenCalled();
  });
}

function getProfileSelect() {
  return document.getElementById('momentum-screener-profile') as HTMLSelectElement;
}

function getSortSelect() {
  return document.getElementById('momentum-screener-sort') as HTMLSelectElement;
}

function getResultRows() {
  return screen.getAllByTestId(/^momentum-screener-row-/);
}

describe('MomentumScreenerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:momentum-export');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [],
    });
    mockScreen.mockResolvedValue(buildDecisionResponse(standardResponse));
    mockIntraday.mockResolvedValue(buildIntradayResponse(standardResponse));
  });

  it('loads default form values from system config without auto-running screening', async () => {
    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'aggressive' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '12' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT', value: '8.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI', value: '4.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER', value: '6' },
      ],
    });

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(mockGetSystemConfig).toHaveBeenCalledWith(false);
      expect(screen.getByDisplayValue('12')).toBeInTheDocument();
    });

    expect(getProfileSelect().value).toBe('aggressive');
    expect(screen.getByDisplayValue('8.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('4.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('6')).toBeInTheDocument();
    expect(mockScreen).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('uses a scrollable page container so action buttons are reachable on smaller viewports', () => {
    render(<MomentumScreenerPage />);

    const page = screen.getByTestId('momentum-screener-page');
    expect(page.className).toContain('overflow-y-auto');
    expect(page.className).not.toContain('overflow-hidden');
  });

  it('loads persisted form state without auto-running screening', async () => {
    window.localStorage.setItem(
      'dsa.momentum-screener.page-state',
      JSON.stringify({
        form: {
          profile: 'aggressive',
          topN: '12',
          minChangePct: '8',
          minAmountYi: '5',
          minTurnover: '4',
          tradeDate: '2026-04-09',
        },
        sortBy: 'buyability_score',
      }),
    );

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('12')).toBeInTheDocument();
    });

    expect(getProfileSelect().value).toBe('aggressive');
    expect(screen.getByDisplayValue('2026-04-09')).toBeInTheDocument();
    expect(mockGetSystemConfig).not.toHaveBeenCalled();
    expect(mockScreen).not.toHaveBeenCalled();
  });

  it('restores system defaults and reruns screening from the current page state', async () => {
    window.localStorage.setItem(
      'dsa.momentum-screener.page-state',
      JSON.stringify({
        form: {
          profile: 'aggressive',
          topN: '12',
          minChangePct: '8',
          minAmountYi: '5',
          minTurnover: '4',
          tradeDate: '2026-04-09',
        },
        sortBy: 'buyability_score',
      }),
    );

    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'standard' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '9' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT', value: '6.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI', value: '2.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER', value: '2' },
      ],
    });

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('12')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('momentum-screener-restore'));

    await waitFor(() => {
      expect(mockScreen).toHaveBeenLastCalledWith({
        profile: 'standard',
        topN: 9,
        minChangePct: 6.5,
        minAmount: 2.5e8,
        minTurnover: 2,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: undefined,
      });
    });

    expect(getProfileSelect().value).toBe('standard');
    expect(screen.getByDisplayValue('9')).toBeInTheDocument();
    expect(screen.getByDisplayValue('6.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2')).toBeInTheDocument();
  });

  it('re-sorts the list when switching sort mode', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    expect(within(getResultRows()[0]).getByText('Alpha Leader')).toBeInTheDocument();

    fireEvent.change(getSortSelect(), { target: { value: 'risk_score' } });

    await waitFor(() => {
      expect(within(getResultRows()[0]).getByText('Low Risk Runner')).toBeInTheDocument();
    });
  });

  it('opens drawer only after clicking a result row and allows closing it', async () => {
    mockScreen.mockResolvedValue(buildDecisionResponse(aggressiveResponse));

    render(<MomentumScreenerPage />);

    fireEvent.change(getProfileSelect(), { target: { value: 'aggressive' } });
    await clickRunButton();

    await waitFor(() => {
      expect(mockScreen).toHaveBeenLastCalledWith({
        profile: 'aggressive',
        topN: 10,
        minChangePct: 7,
        minAmount: 3e8,
        minTurnover: 3,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: undefined,
      });
    });

    expect(await screen.findByTestId('momentum-screener-row-600003.SH')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-screener-row-600003.SH'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Breakout One · 600003.SH')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Breakout Consensus').length).toBeGreaterThan(0);
    expect(within(dialog).getByText('10.34 - 10.66')).toBeInTheDocument();
    expect(within(dialog).getByText('Volume Track')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button'));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('copies the current sorted result list to clipboard', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-copy-results'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('Alpha Leader');
    expect(copiedText).toContain('Low Risk Runner');
  });

  it('builds a watchlist summary from screening results and copies it', async () => {
    render(<MomentumScreenerPage />);

    expect(screen.getByText('暂无观察池摘要')).toBeInTheDocument();
    expect(screen.getByTestId('momentum-screener-copy-watchlist-summary')).toBeDisabled();

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    const summaryCard = screen.getByTestId('momentum-screener-watchlist-summary');
    expect(within(summaryCard).getByText('明日观察池摘要')).toBeInTheDocument();
    expect(within(summaryCard).getAllByText('Alpha Leader').length).toBeGreaterThan(0);
    expect(within(summaryCard).getAllByText('Low Risk Runner').length).toBeGreaterThan(0);
    expect(within(summaryCard).getByText('Power Equipment x2')).toBeInTheDocument();
    expect(within(summaryCard).getByText('风险漂移')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-screener-copy-watchlist-summary'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('明日观察池摘要');
    expect(copiedText).toContain('Alpha Leader');
    expect(copiedText).toContain('Power Equipment x2');
    expect(copiedText).toContain('风险漂移');
  });

  it('shows buyability-first guidance in the watchlist summary for aggressive mode', async () => {
    mockScreen.mockResolvedValue(buildDecisionResponse(aggressiveResponse));

    render(<MomentumScreenerPage />);

    fireEvent.change(getProfileSelect(), { target: { value: 'aggressive' } });
    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600003.SH');

    const summaryCard = screen.getByTestId('momentum-screener-watchlist-summary');
    expect(within(summaryCard).getByText('进攻首选')).toBeInTheDocument();
    expect(within(summaryCard).getAllByText('Breakout One').length).toBeGreaterThan(0);
    expect(within(summaryCard).getByText('可买分 77.0，优先配合承接和区间确认。')).toBeInTheDocument();
    expect(within(summaryCard).getByText('Robotics x1')).toBeInTheDocument();
  });

  it('translates mixed-case score breakdown keys into readable Chinese labels in the detail drawer', async () => {
    mockScreen.mockResolvedValue(buildDecisionResponse(mixedKeyResponse));

    render(<MomentumScreenerPage />);

    fireEvent.change(getProfileSelect(), { target: { value: 'aggressive' } });
    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-002733.SZ');

    fireEvent.click(screen.getByTestId('momentum-screener-row-002733.SZ'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getAllByText('强势确认').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('资金承接').length).toBeGreaterThan(0);
    expect(within(dialog).getByText('量价双轨')).toBeInTheDocument();
    expect(within(dialog).getByText('板块共振')).toBeInTheDocument();
    expect(within(dialog).getByText('趋势位置与弹性')).toBeInTheDocument();
    expect(within(dialog).getByText('近涨停强度')).toBeInTheDocument();
    expect(within(dialog).getByText('跳空高开')).toBeInTheDocument();
    expect(within(dialog).getByText('收盘地位')).toBeInTheDocument();
    expect(within(dialog).getByText('主力净流入')).toBeInTheDocument();
    expect(within(dialog).getByText('成交额黄金区')).toBeInTheDocument();
    expect(within(dialog).getByText('健康换手')).toBeInTheDocument();
    expect(within(dialog).getByText('板块强度')).toBeInTheDocument();
    expect(within(dialog).getByText('历史股性')).toBeInTheDocument();
    expect(within(dialog).queryByText('strengthConfirmation')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('SECTORRANK')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('MAININFLOWABS')).not.toBeInTheDocument();
  });

  it('exports the current result list as markdown', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-markdown'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });

  it('exports the current result list as csv', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-csv'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });

  it('copies a single stock detail from the result row', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-copy-600001.SH'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('Alpha Leader');
    expect(copiedText).toContain('600001.SH');
    expect(copiedText).toContain('Strength Confirmed');
  });

  it('copies aggressive single stock detail with opportunity tag and entry range', async () => {
    mockScreen.mockResolvedValue(buildDecisionResponse(aggressiveResponse));

    render(<MomentumScreenerPage />);

    fireEvent.change(getProfileSelect(), { target: { value: 'aggressive' } });
    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600003.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-copy-600003.SH'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('Breakout Consensus');
    expect(copiedText).toContain('10.34 - 10.66');
  });

  it('renders the secondary decision panel alongside the original screening results', async () => {
    render(<MomentumScreenerPage />);

    expect(screen.getByText('暂无二次决策结果')).toBeInTheDocument();

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    const panel = screen.getByTestId('momentum-secondary-decision');
    expect(within(panel).getByTestId('momentum-secondary-action-level')).toHaveTextContent('可正常出手');
    expect(within(panel).getByText('策略健康')).toBeInTheDocument();
    expect(within(panel).getByText('20 日当前可用性')).toBeInTheDocument();
    expect(within(panel).getByText('默认 1-3 票组合')).toBeInTheDocument();
    expect(within(panel).getByText('明日行动清单')).toBeInTheDocument();
    expect(within(panel).getByText('开盘后 60 分钟内')).toBeInTheDocument();
    expect(within(panel).getAllByText('Alpha Leader').length).toBeGreaterThan(0);
    expect(screen.getByTestId('momentum-screener-watchlist-summary')).toBeInTheDocument();
    expect(screen.getByText('筛选结果')).toBeInTheDocument();
  });

  it('shows a visible secondary decision refresh button and warming guidance', async () => {
    const warmingResponse = buildDecisionResponse(standardResponse);
    warmingResponse.decision.strategyHealth.dataSource = 'proxy';
    warmingResponse.decision.strategyHealth.isWarming = true;
    mockScreen.mockResolvedValue(warmingResponse);

    render(<MomentumScreenerPage />);

    await clickRunButton();
    const panel = await screen.findByTestId('momentum-secondary-decision');

    expect(within(panel).getByTestId('momentum-secondary-refresh')).toBeInTheDocument();
    expect(within(panel).getByTestId('momentum-secondary-refresh-inline')).toBeInTheDocument();
    expect(within(panel).getByText('真实 20/60 结果刷新')).toBeInTheDocument();
    expect(
      within(panel).getByText('首轮请求已切换为后台预热模式，页面先给你代理健康度，等真实 20/60 日历史结果算完后，点击下方“刷新真实 20/60 结果”即可看到正式结论。'),
    ).toBeInTheDocument();
  });

  it('reuses the last submitted payload when refreshing the secondary decision', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    mockScreen.mockClear();
    fireEvent.click(screen.getByTestId('momentum-secondary-refresh'));

    await waitFor(() => {
      expect(mockScreen).toHaveBeenCalledWith(
        {
          profile: 'standard',
          topN: 10,
          minChangePct: 7,
          minAmount: 3e8,
          minTurnover: 3,
          excludeSt: true,
          mainBoardOnly: true,
          tradeDate: undefined,
        },
        { waitForStrategyHealth: true },
      );
    });
  });

  it('refreshes intraday signal only after manual action and renders do-not-chase guidance', async () => {
    mockScreen.mockResolvedValue(buildDecisionResponse(aggressiveResponse));
    mockIntraday.mockResolvedValue(buildIntradayResponse(aggressiveResponse));

    render(<MomentumScreenerPage />);

    fireEvent.change(getProfileSelect(), { target: { value: 'aggressive' } });
    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600003.SH');

    expect(mockIntraday).not.toHaveBeenCalled();
    expect(screen.getByText('盘中信号尚未刷新')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-intraday-refresh'));

    await waitFor(() => {
      expect(mockIntraday).toHaveBeenCalledWith({
        profile: 'aggressive',
        topN: 10,
        minChangePct: 7,
        minAmount: 3e8,
        minTurnover: 3,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: undefined,
      });
    });

    const panel = screen.getByTestId('momentum-intraday-signal');
    expect(within(panel).getAllByText('低置信度').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('不建议买').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('不建议追入').length).toBeGreaterThan(0);
    expect(within(panel).getByText('优先关注顺序')).toBeInTheDocument();
    expect(within(panel).getByText('今天结论是不建议买入；固定顺序仍按主仓、次仓、观察仓跟踪。')).toBeInTheDocument();
    expect(within(panel).getByText('等待价格回到更合理的确认区间。')).toBeInTheDocument();
  });

  it('exports a single stock detail as markdown from the result row', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-600001.SH'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });
});
