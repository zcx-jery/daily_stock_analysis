import type React from 'react';
import { useEffect, useState } from 'react';
import { marketReviewApi } from '../api/marketReview';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Badge, Button, Card, Drawer, Input } from '../components/common';
import {
  getSentimentBadgeVariant,
  getStrategyBadgeVariant,
  type MarketReviewItem,
  type MarketReviewListItem,
} from '../types/marketReview';

const NumberStat: React.FC<{
  label: string;
  value: number | string | null | undefined;
  tone?: 'default' | 'success' | 'danger';
}> = ({ label, value, tone = 'default' }) => {
  const toneClass = tone === 'success' ? 'text-success' : tone === 'danger' ? 'text-danger' : 'text-foreground';
  return (
    <div className="rounded-2xl border border-border/60 bg-card/55 p-4">
      <p className="text-xs text-secondary-text">{label}</p>
      <p className={`mt-2 text-xl font-semibold ${toneClass}`}>{value ?? '--'}</p>
    </div>
  );
};

const IndexCard: React.FC<{
  title: string;
  value?: number | null;
  change?: number | null;
}> = ({ title, value, change }) => (
  <div className="rounded-2xl border border-border/60 bg-card/55 p-4">
    <p className="text-xs text-secondary-text">{title}</p>
    <p className="mt-2 text-xl font-semibold text-foreground">
      {value != null ? value.toFixed(2) : '--'}
    </p>
    <p className={`mt-1 text-sm font-medium ${change != null && change < 0 ? 'text-danger' : 'text-success'}`}>
      {change != null ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : '--'}
    </p>
  </div>
);

const MarketReviewPage: React.FC = () => {
  const [reviews, setReviews] = useState<MarketReviewListItem[]>([]);
  const [selectedReview, setSelectedReview] = useState<MarketReviewItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false);

  useEffect(() => {
    document.title = '大盘复盘 - DSA';
    void loadReviews();
  }, []);

  const loadReviews = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await marketReviewApi.list({
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        limit: 30,
      });
      setReviews(response.items);
      if (response.items.length === 0) {
        setSelectedReview(null);
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const loadReviewDetail = async (date: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const response = await marketReviewApi.get(date);
      setSelectedReview(response.item);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">大盘复盘</h1>
          <p className="text-sm text-secondary-text">按日期筛选复盘报告，并用结构化指标查看当天市场状态。</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Input
            type="date"
            label="开始日期"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="w-[180px]"
            disabled={loading}
          />
          <Input
            type="date"
            label="结束日期"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="w-[180px]"
            disabled={loading}
          />
          <Button
            variant="home-action-ai"
            isLoading={loading}
            loadingText="查询中..."
            onClick={() => void loadReviews()}
            className="mb-[2px]"
          >
            查询
          </Button>
        </div>
      </div>

      {error ? (
        <ApiErrorAlert error={error} className="mb-4" onDismiss={() => setError(null)} />
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card padding="none" className="min-h-0 overflow-hidden">
          <div className="border-b border-border/60 px-4 py-3">
            <p className="text-sm font-medium text-foreground">复盘列表</p>
            <p className="text-xs text-secondary-text">共 {reviews.length} 份</p>
          </div>
          <div className="max-h-full overflow-y-auto">
            {loading ? (
              <div className="flex h-40 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
              </div>
            ) : reviews.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-secondary-text">
                暂无匹配的复盘报告
              </div>
            ) : (
              reviews.map((item) => (
                <button
                  key={item.reportDate}
                  type="button"
                  onClick={() => void loadReviewDetail(item.reportDate)}
                  className="flex w-full items-center justify-between gap-3 border-b border-border/50 px-4 py-3 text-left transition-colors hover:bg-hover"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
                    <p className="mt-1 text-xs text-secondary-text">{item.reportDate}</p>
                  </div>
                  <Badge variant={getSentimentBadgeVariant(item.sentiment)}>
                    <span>{item.sentiment}</span>
                    <span>{item.sentimentLabel}</span>
                  </Badge>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card className="min-h-0 overflow-hidden">
          {detailLoading ? (
            <div className="flex h-full items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
            </div>
          ) : selectedReview ? (
            <div className="flex h-full flex-col">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-4">
                <div>
                  <h2 className="text-base font-semibold text-foreground">{selectedReview.title}</h2>
                  <p className="mt-1 text-sm text-secondary-text">{selectedReview.reportDate}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={getSentimentBadgeVariant(selectedReview.sentiment)} size="md">
                    <span>{selectedReview.sentiment}</span>
                    <span>{selectedReview.sentimentLabel}</span>
                  </Badge>
                  {selectedReview.strategy ? (
                    <Badge variant={getStrategyBadgeVariant(selectedReview.strategy)} size="md">
                      {selectedReview.strategy}
                    </Badge>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <IndexCard
                  title="上证指数"
                  value={selectedReview.shanghaiIndex}
                  change={selectedReview.shanghaiChange}
                />
                <IndexCard
                  title="深证成指"
                  value={selectedReview.shenzhenIndex}
                  change={selectedReview.shenzhenChange}
                />
                <IndexCard
                  title="创业板指"
                  value={selectedReview.chiIndex}
                  change={selectedReview.chiChange}
                />
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-5">
                <NumberStat label="成交额(亿)" value={selectedReview.totalVolume?.toFixed(0)} />
                <NumberStat label="上涨家数" value={selectedReview.risingCount} tone="success" />
                <NumberStat label="下跌家数" value={selectedReview.fallingCount} tone="danger" />
                <NumberStat label="涨停家数" value={selectedReview.limitUp} tone="success" />
                <NumberStat label="跌停家数" value={selectedReview.limitDown} tone="danger" />
              </div>

              {(selectedReview.topSectors.length > 0 || selectedReview.bottomSectors.length > 0) ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <Card title="领涨板块" padding="sm" className="bg-card/40">
                    <div className="flex flex-wrap gap-2">
                      {selectedReview.topSectors.map((sector) => (
                        <Badge key={sector} variant="success">{sector}</Badge>
                      ))}
                    </div>
                  </Card>
                  <Card title="领跌板块" padding="sm" className="bg-card/40">
                    <div className="flex flex-wrap gap-2">
                      {selectedReview.bottomSectors.map((sector) => (
                        <Badge key={sector} variant="danger">{sector}</Badge>
                      ))}
                    </div>
                  </Card>
                </div>
              ) : null}

              <div className="mt-4 min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/60 bg-card/40 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-medium text-foreground">完整报告</h3>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setReportDrawerOpen(true)}
                  >
                    放大查看
                  </Button>
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  aria-label="打开完整报告"
                  onClick={() => setReportDrawerOpen(true)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      setReportDrawerOpen(true);
                    }
                  }}
                  className="flex h-full min-h-[240px] cursor-pointer flex-col overflow-hidden rounded-2xl border border-border/50 bg-background/20 transition-colors hover:bg-hover/60 focus:outline-none focus:ring-2 focus:ring-cyan/30"
                >
                  <div className="border-b border-border/40 px-4 py-3 text-xs text-secondary-text">
                    点击预览区域，在弹窗中查看完整内容
                  </div>
                  <div className="min-h-0 flex-1 overflow-hidden px-4 py-4">
                    <pre className="max-h-full overflow-hidden whitespace-pre-wrap text-sm leading-7 text-secondary-text">
                      {selectedReview.content.replace(/^# .*\n+/, '').trim()}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <p className="text-base font-medium text-foreground">选择一份复盘报告</p>
                <p className="mt-2 text-sm text-secondary-text">左侧会展示最近的结构化复盘列表。</p>
              </div>
            </div>
          )}
        </Card>
      </div>

      <Drawer
        isOpen={reportDrawerOpen && Boolean(selectedReview)}
        onClose={() => setReportDrawerOpen(false)}
        title={selectedReview ? `${selectedReview.reportDate} 完整报告` : '完整报告'}
        width="max-w-[min(96vw,1200px)]"
        zIndex={90}
        backdropClassName="bg-background/84 backdrop-blur-sm"
      >
        <div className="flex h-full flex-col">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-foreground">{selectedReview?.title}</p>
              <p className="mt-1 text-xs text-secondary-text">弹窗内支持更大阅读区域和独立滚动</p>
            </div>
            {selectedReview?.strategy ? (
              <Badge variant={getStrategyBadgeVariant(selectedReview.strategy)} size="md">
                {selectedReview.strategy}
              </Badge>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-border/60 bg-card/40 p-5">
            <pre className="whitespace-pre-wrap text-[15px] leading-8 text-secondary-text">
              {selectedReview?.content.replace(/^# .*\n+/, '').trim()}
            </pre>
          </div>
        </div>
      </Drawer>
    </div>
  );
};

export default MarketReviewPage;
