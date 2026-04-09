import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, List, RefreshCcw } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { marketReportsApi } from '../api/marketReports';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Button, EmptyState } from '../components/common';
import { markdownToPlainText } from '../utils/markdown';
import { cn } from '../utils/cn';
import type { MarketReportDetail, MarketReportItem } from '../types/marketReports';

const MarketReportsPage: React.FC = () => {
  const navigate = useNavigate();
  const { reportDate } = useParams();
  const [reports, setReports] = useState<MarketReportItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<MarketReportDetail | null>(null);
  const [listError, setListError] = useState<ParsedApiError | null>(null);
  const [detailError, setDetailError] = useState<ParsedApiError | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [copiedType, setCopiedType] = useState<'markdown' | 'text' | null>(null);

  const activeDate = reportDate ?? null;

  useEffect(() => {
    document.title = activeDate ? `大盘复盘报告 ${activeDate} - DSA` : '大盘复盘报告 - DSA';
  }, [activeDate]);

  const loadReports = useCallback(async () => {
    setIsLoadingList(true);
    setListError(null);
    try {
      const data = await marketReportsApi.getList();
      setReports(data.items);
    } catch (error) {
      setListError(getParsedApiError(error));
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  const loadReportDetail = useCallback(async (date: string) => {
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const data = await marketReportsApi.getDetail(date);
      setSelectedReport(data);
    } catch (error) {
      setSelectedReport(null);
      setDetailError(getParsedApiError(error));
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  useEffect(() => {
    if (!activeDate) {
      setSelectedReport(null);
      setDetailError(null);
      setIsLoadingDetail(false);
      return;
    }
    void loadReportDetail(activeDate);
  }, [activeDate, loadReportDetail]);

  const handleSelectReport = useCallback((date: string) => {
    navigate(`/market-reports/${date}`);
  }, [navigate]);

  const handleBackToList = useCallback(() => {
    navigate('/market-reports');
  }, [navigate]);

  const handleCopy = useCallback(async (copyType: 'markdown' | 'text') => {
    if (!selectedReport?.content) {
      return;
    }

    try {
      const content = copyType === 'markdown'
        ? selectedReport.content
        : markdownToPlainText(selectedReport.content);
      await navigator.clipboard.writeText(content);
      setCopiedType(copyType);
      window.setTimeout(() => setCopiedType(null), 2000);
    } catch {
      setCopiedType(null);
    }
  }, [selectedReport]);

  const listContent = useMemo(() => {
    if (isLoadingList) {
      return (
        <div className="flex h-full items-center justify-center py-10">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
        </div>
      );
    }

    if (reports.length === 0) {
      return (
        <EmptyState
          title="暂无大盘复盘报告"
          description="系统生成的每日大盘复盘报告会显示在这里。"
          className="border-none bg-transparent px-0 py-8 shadow-none"
          icon={<List className="h-6 w-6" />}
        />
      );
    }

    return (
      <div className="space-y-2">
        {reports.map((item) => {
          const isActive = item.date === activeDate;
          return (
            <button
              key={item.date}
              type="button"
              onClick={() => handleSelectReport(item.date)}
              className={cn(
                'w-full rounded-xl border px-4 py-3 text-left transition-all',
                isActive
                  ? 'border-cyan/40 bg-cyan/10 text-foreground shadow-soft-card'
                  : 'border-border/60 bg-card/55 text-secondary-text hover:border-cyan/20 hover:bg-hover hover:text-foreground',
              )}
              aria-label={item.title}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--home-action-report-bg)] text-[var(--home-action-report-text)]">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.title}</p>
                  <p className="mt-1 text-xs text-muted-text">
                    {item.updatedAt ? `更新时间 ${new Date(item.updatedAt).toLocaleString()}` : item.fileName}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    );
  }, [activeDate, handleSelectReport, isLoadingList, reports]);

  return (
    <div
      data-testid="market-reports-page"
      className="flex h-[calc(100vh-5rem)] flex-col overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">大盘复盘报告</h1>
          <p className="text-sm text-secondary-text">查看每天 18:00 生成的大盘复盘 Markdown 报告。</p>
        </div>
        <Button
          variant="home-action-ai"
          size="sm"
          isLoading={isLoadingList}
          loadingText="刷新中..."
          onClick={() => void loadReports()}
        >
          <RefreshCcw className="h-4 w-4" />
          刷新列表
        </Button>
      </div>

      {listError ? (
        <ApiErrorAlert
          error={listError}
          className="mb-4"
          actionLabel="重新加载"
          onAction={() => void loadReports()}
          onDismiss={() => setListError(null)}
        />
      ) : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="dashboard-card min-h-0 overflow-y-auto p-4">
          {listContent}
        </aside>

        <section className="dashboard-card min-h-0 overflow-hidden p-4">
          {!activeDate ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                title="选择一份报告查看详情"
                description="点击左侧任意一份大盘复盘报告，右侧会展示完整内容。"
                icon={<FileText className="h-6 w-6" />}
                className="max-w-xl"
              />
            </div>
          ) : isLoadingDetail ? (
            <div className="flex h-full items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
            </div>
          ) : detailError ? (
            <div className="flex h-full items-center justify-center">
              <ApiErrorAlert
                error={detailError}
                className="w-full max-w-2xl"
                actionLabel="重新加载"
                onAction={() => void loadReportDetail(activeDate)}
                onDismiss={() => setDetailError(null)}
              />
            </div>
          ) : selectedReport ? (
            <div className="flex h-full flex-col">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-4">
                <div>
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <Button variant="ghost" size="xsm" onClick={handleBackToList}>
                      返回列表
                    </Button>
                    <span className="rounded-full border border-cyan/20 bg-cyan/10 px-2 py-0.5 text-xs text-cyan">
                      {selectedReport.date}
                    </span>
                  </div>
                  <h2 className="text-base font-semibold text-foreground">{selectedReport.title}</h2>
                  <p className="text-xs text-secondary-text">{selectedReport.fileName}</p>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="home-action-report"
                    size="sm"
                    disabled={!selectedReport.content || copiedType !== null}
                    onClick={() => void handleCopy('markdown')}
                  >
                    {copiedType === 'markdown' ? '已复制 Markdown' : '复制 Markdown'}
                  </Button>
                  <Button
                    variant="home-action-ai"
                    size="sm"
                    disabled={!selectedReport.content || copiedType !== null}
                    onClick={() => void handleCopy('text')}
                  >
                    {copiedType === 'text' ? '已复制纯文本' : '复制纯文本'}
                  </Button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                <div
                  className="home-markdown-prose prose prose-invert prose-sm max-w-none
                    prose-headings:text-foreground prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
                    prose-h1:text-xl prose-h2:text-lg prose-h3:text-base
                    prose-p:leading-relaxed prose-p:mb-3 prose-p:last:mb-0
                    prose-strong:text-foreground prose-strong:font-semibold
                    prose-ul:my-2 prose-ol:my-2 prose-li:my-1
                    prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none
                    prose-pre:border prose-table:border-collapse prose-hr:my-4
                    prose-a:no-underline hover:prose-a:underline prose-blockquote:text-secondary-text
                    whitespace-pre-line break-words"
                >
                  <Markdown remarkPlugins={[remarkGfm]}>
                    {selectedReport.content}
                  </Markdown>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                title="未找到对应报告"
                description="请从左侧重新选择一份可用报告。"
                icon={<FileText className="h-6 w-6" />}
                className="max-w-xl"
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default MarketReportsPage;
