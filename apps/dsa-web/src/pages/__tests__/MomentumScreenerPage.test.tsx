import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MomentumScreenerPage from '../MomentumScreenerPage';

const { mockScreen } = vi.hoisted(() => ({
  mockScreen: vi.fn(),
}));

const { mockGetSystemConfig } = vi.hoisted(() => ({
  mockGetSystemConfig: vi.fn(),
}));

vi.mock('../../api/momentumScreener', () => ({
  momentumScreenerApi: {
    screen: mockScreen,
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: mockGetSystemConfig,
  },
}));

const standardResponse = {
  profile: 'standard' as const,
  tradeDate: '2026-04-10',
  candidateCount: 3,
  results: [
    {
      rank: 1,
      tsCode: '600001.SH',
      name: '龙头一号',
      pctChg: 9.8,
      continuationScore: 88,
      extensionScore: 70,
      riskScore: 40,
      buyabilityScore: null,
      finalScore: 85,
      rankScore: 76,
      themes: ['电力设备'],
      leaderLevel: '龙头',
      topReasons: ['强势确认'],
      riskTags: ['upper_shadow'],
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
      name: '低风险二号',
      pctChg: 8.2,
      continuationScore: 72,
      extensionScore: 66,
      riskScore: 10,
      buyabilityScore: null,
      finalScore: 78,
      rankScore: 68,
      themes: ['电力设备'],
      leaderLevel: '前排',
      topReasons: ['板块共振'],
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

const aggressiveResponse = {
  profile: 'aggressive' as const,
  tradeDate: '2026-04-10',
  candidateCount: 2,
  results: [
    {
      rank: 1,
      tsCode: '600003.SH',
      name: '进攻一号',
      pctChg: 10.0,
      continuationScore: 91,
      extensionScore: 84,
      riskScore: 18,
      buyabilityScore: 77,
      opportunityTag: '分歧转一致',
      entryRangeLow: 10.34,
      entryRangeHigh: 10.66,
      finalScore: 92,
      rankScore: 82,
      themes: ['机器人'],
      leaderLevel: 'leader',
      topReasons: ['买入可行性', '量价双轨'],
      riskTags: ['price_flow_divergence'],
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
    mockScreen.mockResolvedValue(standardResponse);
  });

  it('loads default form values from system config when no local state exists', async () => {
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
    mockScreen.mockResolvedValue(aggressiveResponse);

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(mockScreen).toHaveBeenCalledWith({
        profile: 'aggressive',
        topN: 12,
        minChangePct: 8.5,
        minAmount: 4.5e8,
        minTurnover: 6,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: undefined,
      });
    });

    expect(screen.getByDisplayValue('12')).toBeInTheDocument();
    expect(screen.getByDisplayValue('8.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('4.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('6')).toBeInTheDocument();
    expect(screen.getAllByText('Aggressive').length).toBeGreaterThan(0);
  });

  it('loads persisted form state and uses it on initial screening', async () => {
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
    mockScreen.mockResolvedValue(aggressiveResponse);

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(mockScreen).toHaveBeenCalledWith({
        profile: 'aggressive',
        topN: 12,
        minChangePct: 8,
        minAmount: 5e8,
        minTurnover: 4,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: '2026-04-09',
      });
    });

    expect(screen.getByDisplayValue('12')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2026-04-09')).toBeInTheDocument();
    expect(screen.getAllByText('Aggressive').length).toBeGreaterThan(0);
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

    mockScreen
      .mockResolvedValueOnce(aggressiveResponse)
      .mockResolvedValueOnce(standardResponse);
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
      expect(mockScreen).toHaveBeenCalledWith({
        profile: 'aggressive',
        topN: 12,
        minChangePct: 8,
        minAmount: 5e8,
        minTurnover: 4,
        excludeSt: true,
        mainBoardOnly: true,
        tradeDate: '2026-04-09',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: '恢复系统默认' }));

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

    expect(screen.getByDisplayValue('9')).toBeInTheDocument();
    expect(screen.getByDisplayValue('6.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2.5')).toBeInTheDocument();
    expect(screen.getByDisplayValue('2')).toBeInTheDocument();
    expect(screen.getAllByText('Standard').length).toBeGreaterThan(0);
    expect(await screen.findByText('已恢复系统默认参数')).toBeInTheDocument();
  });

  it('re-sorts the list when switching sort mode', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    const rowsBefore = screen.getAllByRole('row');
    expect(within(rowsBefore[1]).getByText('龙头一号')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('排序方式'), { target: { value: 'risk_score' } });

    await waitFor(() => {
      const rowsAfter = screen.getAllByRole('row');
      expect(within(rowsAfter[1]).getByText('低风险二号')).toBeInTheDocument();
    });
  });

  it('supports aggressive profile rerun and shows translated drawer details', async () => {
    mockScreen
      .mockResolvedValueOnce(standardResponse)
      .mockResolvedValueOnce(aggressiveResponse);

    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.change(screen.getByLabelText('评分画像'), { target: { value: 'aggressive' } });
    fireEvent.click(screen.getByRole('button', { name: '执行筛选' }));

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

    expect(await screen.findByText('进攻一号')).toBeInTheDocument();
    expect(screen.getAllByText('77.0').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText('进攻一号'));

    expect((await screen.findAllByText('买入可行性')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('分歧转一致').length).toBeGreaterThan(0);
    expect(screen.getByText('10.34 - 10.66')).toBeInTheDocument();
    expect(screen.getByText('价资背离')).toBeInTheDocument();
    expect(screen.getByText('日内振幅')).toBeInTheDocument();
  });

  it('copies the current sorted result list to clipboard', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.click(screen.getByRole('button', { name: '复制结果' }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('已复制当前筛选结果')).toBeInTheDocument();
    expect(String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain('龙头一号');
  });

  it('exports the current result list as markdown', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.click(screen.getAllByRole('button', { name: '导出 Markdown' })[0]);

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });

    expect(await screen.findByText('已导出 Markdown')).toBeInTheDocument();
  });

  it('exports the current result list as csv', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.click(screen.getByRole('button', { name: '导出 CSV' }));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });

    expect(await screen.findByText('已导出 CSV')).toBeInTheDocument();
  });

  it('copies a single stock detail from the result row', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.click(screen.getAllByRole('button', { name: '复制明细' })[0]);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('强势筛选个股明细');
    expect(copiedText).toContain('600001.SH');
    expect(copiedText).toContain('排序分');
    expect(await screen.findByText('已复制 龙头一号 的明细')).toBeInTheDocument();
  });

  it('copies aggressive single stock detail with opportunity tag and entry range', async () => {
    mockScreen.mockResolvedValue(aggressiveResponse);

    render(<MomentumScreenerPage />);

    await screen.findByText('进攻一号');

    fireEvent.click(screen.getByRole('button', { name: '复制明细' }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('分歧转一致');
    expect(copiedText).toContain('10.34 - 10.66');
  });

  it('exports a single stock detail as markdown from the result row', async () => {
    render(<MomentumScreenerPage />);

    await screen.findByText('龙头一号');

    fireEvent.click(screen.getAllByRole('button', { name: '导出 Markdown' })[1]);

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });

    expect(await screen.findByText('已导出 龙头一号 Markdown')).toBeInTheDocument();
  });
});
