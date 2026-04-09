import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { marketReportsApi } from '../../api/marketReports';
import MarketReportsPage from '../MarketReportsPage';

vi.mock('../../api/marketReports', () => ({
  marketReportsApi: {
    getList: vi.fn(),
    getDetail: vi.fn(),
  },
}));

describe('MarketReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the market report list workspace', async () => {
    vi.mocked(marketReportsApi.getList).mockResolvedValue({
      items: [
        {
          date: '2026-04-01',
          title: '大盘复盘报告 2026-04-01',
          fileName: 'market_review_20260401.md',
          updatedAt: '2026-04-01T18:00:00',
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/market-reports']}>
        <Routes>
          <Route path="/market-reports" element={<MarketReportsPage />} />
          <Route path="/market-reports/:reportDate" element={<MarketReportsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('大盘复盘报告')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '大盘复盘报告 2026-04-01' })).toBeInTheDocument();
    expect(screen.getByText('选择一份报告查看详情')).toBeInTheDocument();
  });

  it('loads detail content when entering a report route', async () => {
    vi.mocked(marketReportsApi.getList).mockResolvedValue({
      items: [
        {
          date: '2026-04-01',
          title: '大盘复盘报告 2026-04-01',
          fileName: 'market_review_20260401.md',
          updatedAt: '2026-04-01T18:00:00',
        },
      ],
    });
    vi.mocked(marketReportsApi.getDetail).mockResolvedValue({
      date: '2026-04-01',
      title: '大盘复盘报告 2026-04-01',
      fileName: 'market_review_20260401.md',
      updatedAt: '2026-04-01T18:00:00',
      content: '# 2026-04-01\n\n市场情绪回暖。',
    });

    render(
      <MemoryRouter initialEntries={['/market-reports/2026-04-01']}>
        <Routes>
          <Route path="/market-reports" element={<MarketReportsPage />} />
          <Route path="/market-reports/:reportDate" element={<MarketReportsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('市场情绪回暖。')).toBeInTheDocument();
    expect(marketReportsApi.getDetail).toHaveBeenCalledWith('2026-04-01');
  });

  it('navigates into detail when clicking a list item', async () => {
    vi.mocked(marketReportsApi.getList).mockResolvedValue({
      items: [
        {
          date: '2026-04-01',
          title: '大盘复盘报告 2026-04-01',
          fileName: 'market_review_20260401.md',
          updatedAt: '2026-04-01T18:00:00',
        },
      ],
    });
    vi.mocked(marketReportsApi.getDetail).mockResolvedValue({
      date: '2026-04-01',
      title: '大盘复盘报告 2026-04-01',
      fileName: 'market_review_20260401.md',
      updatedAt: '2026-04-01T18:00:00',
      content: '# 2026-04-01\n\n市场情绪回暖。',
    });

    render(
      <MemoryRouter initialEntries={['/market-reports']}>
        <Routes>
          <Route path="/market-reports" element={<MarketReportsPage />} />
          <Route path="/market-reports/:reportDate" element={<MarketReportsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '大盘复盘报告 2026-04-01' }));

    await waitFor(() => {
      expect(marketReportsApi.getDetail).toHaveBeenCalledWith('2026-04-01');
    });
    expect(await screen.findByText('市场情绪回暖。')).toBeInTheDocument();
  });
});
