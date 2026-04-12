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

const aggressiveResponse = {
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
    mockScreen.mockResolvedValue(standardResponse);
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
    mockScreen.mockResolvedValue(aggressiveResponse);

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
    mockScreen.mockResolvedValue(aggressiveResponse);

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
    mockScreen.mockResolvedValue(aggressiveResponse);

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
