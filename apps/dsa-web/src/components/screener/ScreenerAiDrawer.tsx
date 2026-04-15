import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, RefreshCw, Send, Sparkles } from 'lucide-react';
import { ApiErrorAlert, Badge, Button, Drawer, EmptyState, InlineAlert, ScrollArea } from '../common';
import { useMomentumScreenerAiStore } from '../../stores/momentumScreenerAiStore';
import type { MomentumScreenerAiMessage, MomentumScreenerAiStageEvent, MomentumScreenerAiToolEvent } from '../../types/momentumScreenerAi';

const MarkdownContent = React.lazy(() => import('../markdown/MarkdownContent'));

function formatMetaTime(value?: string | null): string {
  if (!value) return '--';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

type ScreenerAiProgressEvent = MomentumScreenerAiStageEvent | MomentumScreenerAiToolEvent;

type ScreenerAiDrawerBodyProps = {
  messages: MomentumScreenerAiMessage[];
  progressEvents: ScreenerAiProgressEvent[];
  loadingSession: boolean;
  sending: boolean;
  error: ReturnType<typeof useMomentumScreenerAiStore.getState>['error'];
  sendMessage: ReturnType<typeof useMomentumScreenerAiStore.getState>['sendMessage'];
  rerunAnalysis: ReturnType<typeof useMomentumScreenerAiStore.getState>['rerunAnalysis'];
  clearError: ReturnType<typeof useMomentumScreenerAiStore.getState>['clearError'];
};

const ScreenerAiDrawerBody: React.FC<ScreenerAiDrawerBodyProps> = ({
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
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, progressEvents, sending]);

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant'),
    [messages],
  );

  const handleSend = async (override?: string) => {
    const next = (override ?? input).trim();
    if (!next || sending || loadingSession) return;
    setInput('');
    await sendMessage(next, 'resume');
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/50 bg-card/55 p-4">
          <div>
            <p className="text-sm font-semibold text-foreground">强势筛选 AI 点评</p>
            <p className="mt-1 text-xs leading-6 text-secondary-text">
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
          <div className="rounded-2xl border border-cyan/20 bg-cyan/5 p-4">
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
            {latestAssistantMessage.contextMeta.toolsUsed.length > 0 ? (
              <div className="mt-4">
                <p className="text-xs uppercase tracking-[0.12em] text-secondary-text">本轮用到的外部工具</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {latestAssistantMessage.contextMeta.toolsUsed.map((tool) => (
                    <Badge key={tool} variant="default">
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? <ApiErrorAlert error={error} onDismiss={clearError} /> : null}

        <ScrollArea className="flex-1 min-h-0 rounded-2xl border border-border/50 bg-card/45" viewportClassName="space-y-4 p-4">
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
                  className={`max-w-[min(100%,38rem)] rounded-2xl px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-cyan/10 text-foreground'
                      : 'border border-border/50 bg-card/80 text-foreground'
                  }`}
                >
                  {message.role === 'assistant' && message.contextMeta ? (
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <Badge variant="info">{message.contextMeta.reviewTypeLabel}</Badge>
                      <Badge variant="default">{message.contextMeta.ruleGuardrail}</Badge>
                    </div>
                  ) : null}
                  {message.role === 'assistant' ? (
                    <Suspense fallback={<div className="text-sm text-secondary-text">正在渲染 AI 点评...</div>}>
                      <MarkdownContent content={message.content} className="prose prose-sm max-w-none text-foreground" />
                    </Suspense>
                  ) : (
                    <p className="text-sm leading-7">{message.content}</p>
                  )}
                  {message.role === 'assistant' && message.suggestedQuestions.length > 0 ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {message.suggestedQuestions.map((question) => (
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
                  ) : null}
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
                      <div key={`${event.stage}-${index}`} className="rounded-xl border border-border/40 bg-hover/10 px-3 py-2 text-sm text-secondary-text">
                        <span className="font-medium text-foreground">{event.message}</span>
                      </div>
                    ) : (
                      <div key={`${event.tool}-${index}`} className="rounded-xl border border-border/40 bg-hover/10 px-3 py-2 text-sm text-secondary-text">
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

          <div ref={endRef} />
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
              className="min-h-[44px] flex-1 resize-none rounded-xl border border-border/60 bg-background/40 px-4 py-3 text-sm text-foreground transition-colors focus:border-cyan/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
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
      width="max-w-2xl"
      zIndex={80}
    >
      {isOpen ? (
        <ScreenerAiDrawerBody
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
