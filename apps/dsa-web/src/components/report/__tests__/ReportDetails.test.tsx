import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReportDetails } from '../ReportDetails';

describe('ReportDetails', () => {
  const writeTextMock = vi.fn().mockResolvedValue(undefined);
  let originalClipboard: Navigator['clipboard'] | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    writeTextMock.mockClear();
    originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: writeTextMock,
      },
    });
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: originalClipboard,
    });
    vi.useRealTimers();
  });

  it('keeps copied feedback scoped to the panel that was copied', async () => {
    const details = {
      rawResult: { score: 82 },
      contextSnapshot: { window: '30d' },
    };

    render(
      <ReportDetails
        recordId={7}
        details={details}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '原始分析结果' }));
    fireEvent.click(screen.getByRole('button', { name: '分析快照' }));

    const [rawCopyButton, snapshotCopyButton] = screen.getAllByRole('button', { name: '复制' });

    await act(async () => {
      fireEvent.click(rawCopyButton);
      await Promise.resolve();
    });

    expect(writeTextMock).toHaveBeenNthCalledWith(1, JSON.stringify(details.rawResult, null, 2));
    expect(screen.getByRole('button', { name: '已复制' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '复制' })).toHaveLength(1);

    await act(async () => {
      fireEvent.click(snapshotCopyButton);
      await Promise.resolve();
    });

    expect(writeTextMock).toHaveBeenNthCalledWith(2, JSON.stringify(details.contextSnapshot, null, 2));
    expect(screen.getAllByRole('button', { name: '已复制' })).toHaveLength(2);

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.getAllByRole('button', { name: '复制' })).toHaveLength(2);
  });

  it('does not render when details and record id are both absent', () => {
    const { container } = render(<ReportDetails />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders enhanced evidence metrics when available', () => {
    render(
      <ReportDetails
        details={{
          capitalFlowMetrics: {
            status: 'ok',
            signal: 'mixed_signal',
            tradeDate: '2026-05-07',
            sourceChain: [{ provider: 'tushare.moneyflow_ths', result: 'ok' }],
          },
          chipMetrics: {
            status: 'ok',
            chipSignal: 'supportive',
            source: 'tushare.cyq_chips',
            asOf: '2026-05-07',
            data: { profitRatio: 0.42 },
          },
          dataQuality: {
            status: 'partial',
            market: 'cn',
            coverage: {
              valuation: 'ok',
              capitalFlow: 'ok',
              chip: 'missing',
            },
            errors: ['capital_flow timeout'],
            sourceChain: [{ provider: 'tushare.daily_basic', result: 'ok' }],
          },
          tushareEnhancement: {
            enabled: true,
          },
        }}
      />,
    );

    expect(screen.getByText('增强证据')).toBeInTheDocument();
    expect(screen.getByText('Tushare 增强')).toBeInTheDocument();
    expect(screen.getByText('资金流')).toBeInTheDocument();
    expect(screen.getByText('资金信号分歧')).toBeInTheDocument();
    expect(screen.getByText('同花顺资金流')).toBeInTheDocument();
    expect(screen.getByText('筹码结构')).toBeInTheDocument();
    expect(screen.getByText('筹码支撑较好')).toBeInTheDocument();
    expect(screen.getByText('42.0%')).toBeInTheDocument();
    expect(screen.getByText('数据质量')).toBeInTheDocument();
    expect(screen.getByText('2/3')).toBeInTheDocument();
    expect(screen.getByText(/增强数据 2\/3 项可用/)).toBeInTheDocument();
  });

  it('renders fundamental and board linkage summaries when available', () => {
    render(
      <ReportDetails
        language="en"
        details={{
          financialReport: { reportDate: '2025-12-31' },
          dividendMetrics: {
            ttmDividendYieldPct: 2.6,
            ttmCashDividendPerShare: 1.3,
          },
          fundamentalMetrics: {
            valuation: { peTtm: 21.5, pbRatio: 7.8 },
            profitability: { roe: 31.2, grossMargin: 91.4 },
            statuses: { valuation: 'ok' },
          },
          belongBoards: [{ name: 'Baijiu', type: 'Industry' }],
          sectorRankings: {
            top: [{ name: 'Baijiu', changePct: 2.5 }],
            bottom: [{ name: 'Retail', changePct: -1.1 }],
          },
          boardLinkage: {
            status: 'aligned',
            matchedBoard: 'Baijiu',
            reason: 'belong board in top rankings',
          },
        }}
      />,
    );

    expect(screen.getByText('Fundamental Summary')).toBeInTheDocument();
    expect(screen.getByText('21.5')).toBeInTheDocument();
    expect(screen.getByText('31.2%')).toBeInTheDocument();
    expect(screen.getByText('2.6%')).toBeInTheDocument();
    expect(screen.getByText('Board Linkage')).toBeInTheDocument();
    expect(screen.getByText('Strong sector alignment')).toBeInTheDocument();
    expect(screen.queryByText('aligned')).not.toBeInTheDocument();
    expect(screen.getAllByText('Baijiu').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Retail')).toBeInTheDocument();
  });

  it('renders readable board linkage explanations instead of raw status codes', () => {
    render(
      <ReportDetails
        details={{
          belongBoards: [{ name: '化学制品(A股)', type: 'I' }],
          boardLinkage: {
            status: 'isolated',
            matchedBoard: null,
          },
        }}
      />,
    );

    expect(screen.getByText('暂无板块共振')).toBeInTheDocument();
    expect(screen.getByText(/更多看个股自身逻辑/)).toBeInTheDocument();
    expect(screen.getByText('化学制品(A股)')).toBeInTheDocument();
    expect(screen.queryByText('isolated')).not.toBeInTheDocument();
  });

  it('renders friendly labels for degraded evidence statuses', () => {
    render(
      <ReportDetails
        language="en"
        details={{
          fundamentalMetrics: {
            valuation: { peTtm: 21.5 },
            statuses: { valuation: 'stale' },
          },
          dataQuality: {
            status: 'permission_denied',
            market: 'cn',
            coverage: {
              valuation: 'stale',
              capitalFlow: 'permission_denied',
            },
            errors: ['permission denied'],
            sourceChain: [{ provider: 'tushare.daily_basic', result: 'permission_denied' }],
          },
          tushareEnhancement: {
            enabled: true,
          },
        }}
      />,
    );

    expect(screen.getByText('Stale')).toBeInTheDocument();
    expect(screen.getByText('Permission/points required')).toBeInTheDocument();
    expect(screen.queryByText('permission_denied')).not.toBeInTheDocument();
  });
});
