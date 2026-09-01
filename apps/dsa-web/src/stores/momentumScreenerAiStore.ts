import { create } from 'zustand';
import { momentumScreenerAiApi } from '../api/momentumScreenerAi';
import { getParsedApiError, isApiRequestError, isParsedApiError, type ParsedApiError } from '../api/error';
import { toCamelCase } from '../api/utils';
import type {
  MomentumScreenerAiDoneEvent,
  MomentumScreenerAiMessage,
  MomentumScreenerAiReviewTarget,
  MomentumScreenerAiStageEvent,
  MomentumScreenerAiStreamEvent,
  MomentumScreenerAiToolEvent,
} from '../types/momentumScreenerAi';

type MomentumScreenerAiProgressEvent = MomentumScreenerAiStageEvent | MomentumScreenerAiToolEvent;

interface MomentumScreenerAiState {
  isOpen: boolean;
  title: string;
  target: MomentumScreenerAiReviewTarget | null;
  sessionId: string;
  messages: MomentumScreenerAiMessage[];
  progressEvents: MomentumScreenerAiProgressEvent[];
  loadingSession: boolean;
  sending: boolean;
  error: ParsedApiError | null;
  abortController: AbortController | null;
}

interface MomentumScreenerAiActions {
  openPanel: (target: MomentumScreenerAiReviewTarget) => Promise<void>;
  closePanel: () => void;
  sendMessage: (message?: string, refreshMode?: 'resume' | 'rerun') => Promise<void>;
  rerunAnalysis: () => Promise<void>;
  clearError: () => void;
}

function buildAutoPrompt(target: MomentumScreenerAiReviewTarget): string {
  if (target.reviewType === 'candidate') {
    return `请点评 ${target.title}，告诉我它为什么入选、最大风险是什么、明天什么情况下考虑、什么情况下直接放弃。`;
  }
  if (target.reviewType === 'decision') {
    return '请综合点评当前二次决策，先告诉我今天做不做，再解释为什么是这 1-3 只。';
  }
  if (target.reviewType === 'intraday') {
    return '请解读当前盘中信号，说明主仓、次仓、观察仓分别是什么状态。';
  }
  return '请解释当前最可惜落选的股票，分别说明它们为什么没进默认组合。';
}

export const useMomentumScreenerAiStore = create<
  MomentumScreenerAiState & MomentumScreenerAiActions
>((set, get) => ({
  isOpen: false,
  title: '',
  target: null,
  sessionId: '',
  messages: [],
  progressEvents: [],
  loadingSession: false,
  sending: false,
  error: null,
  abortController: null,

  clearError: () => set({ error: null }),

  closePanel: () => {
    get().abortController?.abort();
    set({
      isOpen: false,
      progressEvents: [],
      loadingSession: false,
      sending: false,
      abortController: null,
      error: null,
    });
  },

  openPanel: async (target) => {
    get().abortController?.abort();
    set({
      isOpen: true,
      title: target.title,
      target,
      loadingSession: true,
      sending: false,
      error: null,
      progressEvents: [],
      abortController: null,
    });

    try {
      const session = await momentumScreenerAiApi.loadSession({
        reviewType: target.reviewType,
        reviewKey: target.reviewKey,
        refreshMode: 'resume',
        payload: target.payload,
        screening: target.screening,
        decision: target.decision ?? undefined,
        intradaySignal: target.intradaySignal ?? undefined,
      });

      const current = get().target;
      if (!current || current.reviewType !== target.reviewType || current.reviewKey !== target.reviewKey) {
        return;
      }

      set({
        sessionId: session.sessionId,
        messages: session.messages,
        loadingSession: false,
      });

      if (session.messages.length === 0) {
        await get().sendMessage(undefined, 'rerun');
      }
    } catch (error: unknown) {
      set({
        loadingSession: false,
        error: getParsedApiError(error),
      });
    }
  },

  sendMessage: async (message, refreshMode = 'resume') => {
    const state = get();
    if (state.sending || !state.target) {
      return;
    }

    state.abortController?.abort();
    const ac = new AbortController();

    const userMessage = (message || '').trim() || buildAutoPrompt(state.target);
    const optimisticUserMessage: MomentumScreenerAiMessage = {
      id: `optimistic-user-${Date.now()}`,
      role: 'user',
      content: userMessage,
      suggestedQuestions: [],
    };

    set((current) => ({
      sending: true,
      error: null,
      progressEvents: [],
      abortController: ac,
      messages: [...current.messages, optimisticUserMessage],
    }));

    try {
      const response = await momentumScreenerAiApi.streamReview(
        {
          reviewType: state.target.reviewType,
          reviewKey: state.target.reviewKey,
          refreshMode,
          sessionId: state.sessionId || undefined,
          message,
          payload: state.target.payload,
          screening: state.target.screening,
          decision: state.target.decision ?? undefined,
          intradaySignal: state.target.intradaySignal ?? undefined,
        },
        { signal: ac.signal },
      );

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let doneEvent: MomentumScreenerAiDoneEvent | null = null;

      const processLine = (line: string) => {
        if (!line.startsWith('data: ')) return;
        const parsed = toCamelCase<MomentumScreenerAiStreamEvent>(JSON.parse(line.slice(6)));
        if (parsed.type === 'done') {
          doneEvent = parsed;
          return;
        }
        if (parsed.type === 'error') {
          throw getParsedApiError(parsed.message || 'AI 点评失败');
        }
        set((current) => ({
          progressEvents: [...current.progressEvents, parsed],
        }));
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          processLine(line);
        }
      }

      if (buffer.trim().startsWith('data: ')) {
        processLine(buffer.trim());
      }

      if (!doneEvent) {
        throw getParsedApiError('AI 点评未返回最终内容');
      }
      const finalEvent = doneEvent as MomentumScreenerAiDoneEvent;

      const assistantMessage: MomentumScreenerAiMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: finalEvent.content || '',
        contextMeta: finalEvent.contextMeta ?? null,
        suggestedQuestions: finalEvent.suggestedQuestions ?? [],
      };

      set((current) => ({
        sessionId: finalEvent.sessionId || current.sessionId,
        messages: [...current.messages, assistantMessage],
      }));
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // silent abort
      } else if (isParsedApiError(error) || isApiRequestError(error)) {
        set({ error: getParsedApiError(error) });
      } else {
        set({ error: getParsedApiError(error) });
      }
    } finally {
      const currentAbort = get().abortController;
      if (currentAbort === ac) {
        set({
          sending: false,
          progressEvents: [],
          abortController: null,
        });
      }
    }
  },

  rerunAnalysis: async () => {
    const state = get();
    if (!state.target) return;
    await get().sendMessage(undefined, 'rerun');
  },
}));
