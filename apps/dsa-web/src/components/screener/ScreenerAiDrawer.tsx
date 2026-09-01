import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bot, Maximize2, RefreshCw, Send, Sparkles, X } from 'lucide-react';
import { ApiErrorAlert, Badge, Button, Drawer, EmptyState, InlineAlert, ScrollArea } from '../common';
import { useMomentumScreenerAiStore } from '../../stores/momentumScreenerAiStore';
import type {
  MomentumScreenerAiMessage,
  MomentumScreenerAiStageEvent,
  MomentumScreenerAiToolEvent,
} from '../../types/momentumScreenerAi';

const MarkdownContent = React.lazy(() => import('../markdown/MarkdownContent'));

function formatMetaTime(value?: string | null): string {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

function buildMessagePreview(content?: string | null): string {
  const normalized = (content ?? '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[`#>*_-]/g, ' ')
    .replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();

  if (!normalized) {
    return '点击展开完整 AI 对话面板，查看完整点评、快捷追问和继续提问入口。';
  }

  return normalized.length > 180 ? `${normalized.slice(0, 180)}...` : normalized;
}

type ScreenerAiProgressEvent = MomentumScreenerAiStageEvent | MomentumScreenerAiToolEvent;

type ScreenerAiSharedProps = {
  messages: MomentumScreenerAiMessage[];
  progressEvents: ScreenerAiProgressEvent[];
  loadingSession: boolean;
  sending: boolean;
  error: ReturnType<typeof useMomentumScreenerAiStore.getState>['error'];
  sendMessage: ReturnType<typeof useMomentumScreenerAiStore.getState>['sendMessage'];
  rerunAnalysis: ReturnType<typeof useMomentumScreenerAiStore.getState>['rerunAnalysis'];
  clearError: ReturnType<typeof useMomentumScreenerAiStore.getState>['clearError'];
};

type ScreenerAiConversationModalProps = ScreenerAiSharedProps & {
  isOpen: boolean;
  title: string;
  onClose: () => void;
};

const ScreenerAiConversationModal: React.FC<ScreenerAiConversationModalProps> = ({
  isOpen,
  title,
  onClose,
  messages,
  progressEvents,
  loadingSession,
  sending,
  error,
  sendMessage,
  rerunAnalysis,
  clearError,
}) => {
  const [input, setInput] = useState('');
  const viewportRef = useRef<HTMLDivElement>(null);
  const hydratedRef = useRef(false);

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant'),
    [messages],
  );

  const scrollViewport = (top: number, behavior?: ScrollBehavior) => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }

    if (typeof viewport.scrollTo === 'function') {
      viewport.scrollTo({ top, ...(behavior ? { behavior } : {}) });
      return;
    }

    viewport.scrollTop = top;
  };

  useEffect(() => {
    if (!isOpen) {
      hydratedRef.current = false;
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen || loadingSession) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const viewport = viewportRef.current;
      if (!viewport) {
        return;
      }

      if (!hydratedRef.current) {
        hydratedRef.current = true;
        if (sending || progressEvents.length > 0) {
          scrollViewport(viewport.scrollHeight, 'smooth');
        } else {
          scrollViewport(0);
        }
        return;
      }

      if (sending || progressEvents.length > 0) {
        scrollViewport(viewport.scrollHeight, 'smooth');
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, [isOpen, loadingSession, messages.length, progressEvents.length, sending]);

  useEffect(() => {
    if (loadingSession || !isOpen) {
      hydratedRef.current = false;
    }
  }, [isOpen, loadingSession]);

  const handleSend = async (override?: string) => {
    const next = (override ?? input).trim();
    if (!next || sending || loadingSession) return;
    setInput('');
    await sendMessage(next, 'resume');
  };

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center bg-background/82 p-4 backdrop-blur-sm md:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${title} 对话面板`}
        className="flex h-[min(92vh,62rem)] w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border border-border/70 bg-card shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border/60 px-6 py-5">
          <div>
            <span className="label-uppercase">AI CONVERSATION</span>
            <h3 className="mt-1 text-2xl font-semibold text-foreground">{title}</h3>
            <p className="mt-2 text-sm text-secondary-text">
              这里专门承载完整 AI 点评、追问和输入，不再和上层规则卡共用同一块高度。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={loadingSession || sending}
              isLoading={sending}
              loadingText="重跑中..."
              onClick={() => void rerunAnalysis()}
            >
              <RefreshCw className="h-4 w-4" />
              基于最新数据重新分析
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border/70 bg-card/80 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
              aria-label="关闭 AI 对话面板"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4 px-6 py-5">
          {latestAssistantMessage?.contextMeta ? (
            <div className="rounded-2xl border border-cyan/20 bg-cyan/5 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">{latestAssistantMessage.contextMeta.reviewTypeLabel}</Badge>
                <Badge variant="default">{latestAssistantMessage.contextMeta.tradeDate}</Badge>
                <Badge variant="default">{latestAssistantMessage.contextMeta.ruleGuardrail}</Badge>
              </div>
              <p className="mt-3 text-sm leading-6 text-secondary-text">
                {latestAssistantMessage.contextMeta.reviewTarget} · {formatMetaTime(latestAssistantMessage.contextMeta.marketDataAsOf)}
              </p>
            </div>
          ) : null}

          {error ? <ApiErrorAlert error={error} onDismiss={clearError} /> : null}

          <ScrollArea
            className="min-h-0 flex-1 rounded-2xl border border-border/50 bg-card/45"
            viewportClassName="space-y-4 p-5"
            viewportRef={viewportRef}
          >
            {loadingSession ? (
              <EmptyState
                title="正在加载 AI 会话"
                description="系统正在恢复当前点评对象的历史结论和追问记录。"
                icon={<Sparkles className="h-8 w-8" />}
              />
            ) : messages.length === 0 && !sending ? (
              <EmptyState
                title="准备开始 AI 点评"
                description="首次打开会自动生成首条点评；之后你可以继续追问风险、触发条件和对比关系。"
                icon={<Bot className="h-8 w-8" />}
              />
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                      message.role === 'user'
                        ? 'bg-cyan text-background'
                        : 'border border-border/60 bg-card/80 text-cyan'
                    }`}
                  >
                    {message.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div
                    className={`rounded-2xl px-4 py-3 ${
                      message.role === 'user'
                        ? 'max-w-[min(100%,48rem)] bg-cyan/10 text-foreground'
                        : 'max-w-full flex-1 border border-border/50 bg-card/80 text-foreground'
                    }`}
                  >
                    {message.role === 'assistant' ? (
                      <Suspense fallback={<div className="text-sm text-secondary-text">正在渲染 AI 点评...</div>}>
                        <MarkdownContent
                          content={message.content}
                          className="prose prose-sm sm:prose-base max-w-none text-foreground"
                        />
                      </Suspense>
                    ) : (
                      <p className="text-sm leading-7">{message.content}</p>
                    )}
                  </div>
                </div>
              ))
            )}

            {sending ? (
              <div className="rounded-2xl border border-border/50 bg-card/60 p-4">
                <div className="flex items-center gap-2 text-sm text-secondary-text">
                  <div className="h-4 w-4 rounded-full border-2 border-cyan/20 border-t-cyan animate-spin" />
                  <span>AI 正在分析中...</span>
                </div>
                {progressEvents.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {progressEvents.map((event, index) =>
                      event.type === 'stage' ? (
                        <div
                          key={`${event.stage}-${index}`}
                          className="rounded-xl border border-border/40 bg-hover/10 px-3 py-2 text-sm text-secondary-text"
                        >
                          <span className="font-medium text-foreground">{event.message}</span>
                        </div>
                      ) : (
                        <div
                          key={`${event.tool}-${index}`}
                          className="rounded-xl border border-border/40 bg-hover/10 px-3 py-2 text-sm text-secondary-text"
                        >
                          {event.type === 'tool_start'
                            ? `正在调用 ${event.displayName || event.tool}`
                            : `${event.displayName || event.tool} ${event.success ? '完成' : '失败'}${event.duration != null ? ` · ${event.duration}s` : ''}`}
                        </div>
                      ),
                    )}
                  </div>
                ) : null}
              </div>
            ) : null}
          </ScrollArea>

          <div className="rounded-2xl border border-border/50 bg-card/55 p-4">
            {latestAssistantMessage?.suggestedQuestions?.length ? (
              <InlineAlert
                variant="info"
                title="快捷追问"
                message={
                  <div className="flex flex-wrap gap-2">
                    {latestAssistantMessage.suggestedQuestions.map((question) => (
                      <button
                        key={question}
                        type="button"
                        className="rounded-full border border-border/60 bg-hover/20 px-3 py-1.5 text-xs text-secondary-text transition-colors hover:border-cyan/40 hover:text-foreground"
                        onClick={() => void handleSend(question)}
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                }
                className="mb-4 shadow-none"
              />
            ) : null}

            <div className="flex items-end gap-3">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSend();
                  }
                }}
                rows={1}
                placeholder="继续追问风险、触发条件、和主仓对比、什么情况下直接放弃..."
                disabled={loadingSession || sending}
                className="min-h-[52px] flex-1 resize-none rounded-xl border border-border/60 bg-background/40 px-4 py-3 text-sm text-foreground transition-colors focus:border-cyan/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              />
              <Button
                variant="primary"
                disabled={!input.trim() || loadingSession || sending}
                onClick={() => void handleSend()}
              >
                <Send className="h-4 w-4" />
                继续追问
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};

const ScreenerAiDrawerBody: React.FC<ScreenerAiSharedProps & { title: string }> = ({
  title,
  messages,
  progressEvents,
  loadingSession,
  sending,
  error,
  sendMessage,
  rerunAnalysis,
  clearError,
}) => {
  const [conversationOpen, setConversationOpen] = useState(false);

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant'),
    [messages],
  );

  const previewText = useMemo(
    () => buildMessagePreview(latestAssistantMessage?.content),
    [latestAssistantMessage?.content],
  );

  const previewStatus = useMemo(() => {
    if (loadingSession) {
      return '正在恢复 AI 会话';
    }
    if (sending) {
      return 'AI 正在分析中';
    }
    if (latestAssistantMessage) {
      return '点击展开完整 AI 对话';
    }
    return '点击开始查看完整 AI 对话';
  }, [latestAssistantMessage, loadingSession, sending]);

  const previewDescription = useMemo(() => {
    if (loadingSession) {
      return '系统正在恢复当前点评对象的历史结论和追问记录。';
    }

    if (sending && progressEvents.length > 0) {
      return progressEvents
        .slice(-2)
        .map((event) =>
          event.type === 'stage'
            ? event.message
            : event.type === 'tool_start'
              ? `正在调用 ${event.displayName || event.tool}`
              : `${event.displayName || event.tool} ${event.success ? '完成' : '失败'}`,
        )
        .join(' ');
    }

    return previewText;
  }, [loadingSession, previewText, progressEvents, sending]);

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/50 bg-card/55 px-4 py-3">
          <div>
            <p className="text-sm font-semibold text-foreground">强势筛选 AI 点评</p>
            <p className="mt-1 text-xs leading-5 text-secondary-text">
              规则结论先行，AI 只负责解释、补充和追问，不替代规则层做最终决策。
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={loadingSession || sending}
            isLoading={sending}
            loadingText="重跑中..."
            onClick={() => void rerunAnalysis()}
          >
            <RefreshCw className="h-4 w-4" />
            基于最新数据重新分析
          </Button>
        </div>

        {latestAssistantMessage?.contextMeta ? (
          <div className="rounded-2xl border border-cyan/20 bg-cyan/5 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{latestAssistantMessage.contextMeta.reviewTypeLabel}</Badge>
              <Badge variant="default">{latestAssistantMessage.contextMeta.tradeDate}</Badge>
              <Badge variant={latestAssistantMessage.contextMeta.profile === 'aggressive' ? 'warning' : 'default'}>
                {latestAssistantMessage.contextMeta.profile === 'aggressive' ? 'Aggressive' : 'Standard'}
              </Badge>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">规则结论</p>
                <p className="mt-2 text-sm leading-6 text-foreground">
                  {latestAssistantMessage.contextMeta.ruleConclusion}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">规则边界</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">
                  {latestAssistantMessage.contextMeta.ruleGuardrail}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">点评对象</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">
                  {latestAssistantMessage.contextMeta.reviewTarget}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">数据时间</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">
                  {formatMetaTime(latestAssistantMessage.contextMeta.marketDataAsOf)}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {error ? <ApiErrorAlert error={error} onDismiss={clearError} /> : null}

        <button
          type="button"
          data-testid="momentum-ai-open-conversation"
          onClick={() => setConversationOpen(true)}
          className="group rounded-2xl border border-border/50 bg-card/45 p-5 text-left transition-colors hover:border-cyan/30 hover:bg-card/55"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-base font-semibold text-foreground">AI 对话面板</p>
              <p className="mt-1 text-sm text-secondary-text">
                把完整 AI 点评、快捷追问和输入框放到二级弹层里，避免和规则卡共用同一段高度。
              </p>
            </div>
            <Badge variant="info">{previewStatus}</Badge>
          </div>

          <div className="mt-4 rounded-2xl border border-border/50 bg-card/70 p-4">
            {loadingSession ? (
              <div className="flex items-center gap-3 text-sm text-secondary-text">
                <Sparkles className="h-4 w-4 text-cyan" />
                <span>{previewDescription}</span>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm text-cyan">
                    <Bot className="h-4 w-4" />
                    <span className="font-medium">预览当前 AI 输出</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-secondary-text transition-colors group-hover:text-foreground">
                    <Maximize2 className="h-4 w-4" />
                    <span>展开完整页面</span>
                  </div>
                </div>
                <p className="mt-3 line-clamp-4 text-sm leading-7 text-secondary-text">
                  {previewDescription}
                </p>
              </>
            )}
          </div>
        </button>
      </div>

      <ScreenerAiConversationModal
        isOpen={conversationOpen}
        title={title}
        onClose={() => setConversationOpen(false)}
        messages={messages}
        progressEvents={progressEvents}
        loadingSession={loadingSession}
        sending={sending}
        error={error}
        sendMessage={sendMessage}
        rerunAnalysis={rerunAnalysis}
        clearError={clearError}
      />
    </>
  );
};

export const ScreenerAiDrawer: React.FC = () => {
  const {
    isOpen,
    title,
    messages,
    progressEvents,
    loadingSession,
    sending,
    error,
    closePanel,
    sendMessage,
    rerunAnalysis,
    clearError,
  } = useMomentumScreenerAiStore();

  return (
    <Drawer
      isOpen={isOpen}
      onClose={closePanel}
      title={title || 'AI 点评'}
      width="max-w-4xl"
      contentClassName="flex min-h-0 flex-col overflow-hidden"
      zIndex={80}
    >
      {isOpen ? (
        <ScreenerAiDrawerBody
          title={title || 'AI 点评'}
          messages={messages}
          progressEvents={progressEvents}
          loadingSession={loadingSession}
          sending={sending}
          error={error}
          sendMessage={sendMessage}
          rerunAnalysis={rerunAnalysis}
          clearError={clearError}
        />
      ) : null}
    </Drawer>
  );
};

export default ScreenerAiDrawer;
