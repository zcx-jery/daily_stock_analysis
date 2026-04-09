import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { marketReviewApi } from '../../api/marketReview';
import MarketReviewPage from '../MarketReviewPage';

vi.mock('../../api/marketReview', () => ({
  marketReviewApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
}));

describe('MarketReviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the structured review list', async () => {
    vi.mocked(marketReviewApi.list).mockResolvedValue({
      items: [
        {
          reportDate: '2026-04-09',
          title: '2026-04-09 大盘复盘',
          sentiment: '📉',
          sentimentLabel: '弱势调整',
          fileSize: 1024,
        },
      ],
      total: 1,
    });

    render(
      <MemoryRouter>
        <MarketReviewPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('大盘复盘')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /2026-04-09 大盘复盘/ })).toBeInTheDocument();
  });

  it('loads review detail when clicking a list item', async () => {
    vi.mocked(marketReviewApi.list).mockResolvedValue({
      items: [
        {
          reportDate: '2026-04-09',
          title: '2026-04-09 大盘复盘',
          sentiment: '📉',
          sentimentLabel: '弱势调整',
          fileSize: 1024,
        },
      ],
      total: 1,
    });
    vi.mocked(marketReviewApi.get).mockResolvedValue({
      item: {
        reportDate: '2026-04-09',
        title: '2026-04-09 大盘复盘',
        sentiment: '📉',
        sentimentLabel: '弱势调整',
        shanghaiIndex: 3966.17,
        shanghaiChange: -0.72,
        shenzhenIndex: 13996.27,
        shenzhenChange: -0.33,
        chiIndex: 3323.3,
        chiChange: -0.73,
        totalVolume: 21473,
        risingCount: 1140,
        fallingCount: 4299,
        limitUp: 64,
        limitDown: 14,
        topSectors: ['通信线缆及配套(+4.37%)'],
        bottomSectors: ['文字媒体(-5.22%)'],
        strategy: '均衡偏防守',
        content: '# 🎯 大盘复盘\n\n## 📉 2026-04-09 大盘复盘\n\n完整内容',
      },
    });

    render(
      <MemoryRouter>
        <MarketReviewPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /2026-04-09 大盘复盘/ }));

    await waitFor(() => {
      expect(marketReviewApi.get).toHaveBeenCalledWith('2026-04-09');
    });
    expect(await screen.findByText('完整报告')).toBeInTheDocument();
    expect(screen.getByText('均衡偏防守')).toBeInTheDocument();
    expect(screen.getByText('通信线缆及配套(+4.37%)')).toBeInTheDocument();
  });
});
