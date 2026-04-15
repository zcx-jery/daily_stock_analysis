import type {
  MomentumIntradaySignal,
  MomentumProfile,
  MomentumScreenerDecisionResponse,
  MomentumScreenerIntradayResponse,
  MomentumScreenerRequest,
  MomentumScreenerResponse,
  MomentumSecondaryDecision,
} from './momentumScreener';

export type MomentumScreenerAiReviewType = 'candidate' | 'decision' | 'intraday' | 'excluded';
export type MomentumScreenerAiRefreshMode = 'resume' | 'rerun';

export interface MomentumScreenerAiContextMeta {
  reviewType: MomentumScreenerAiReviewType;
  reviewTypeLabel: string;
  reviewTarget: string;
  tradeDate: string;
  profile: MomentumProfile;
  ruleConclusion: string;
  ruleGuardrail: string;
  marketDataAsOf?: string | null;
  toolsUsed: string[];
}

export interface MomentumScreenerAiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt?: string | null;
  contextMeta?: MomentumScreenerAiContextMeta | null;
  suggestedQuestions: string[];
}

export interface MomentumScreenerAiSessionResponse {
  sessionId: string;
  reviewType: MomentumScreenerAiReviewType;
  reviewTypeLabel: string;
  sessionTitle: string;
  messages: MomentumScreenerAiMessage[];
}

export interface MomentumScreenerAiReviewRequest {
  reviewType: MomentumScreenerAiReviewType;
  reviewKey: string;
  refreshMode?: MomentumScreenerAiRefreshMode;
  sessionId?: string;
  message?: string;
  payload: MomentumScreenerRequest;
  screening: MomentumScreenerResponse;
  decision?: MomentumSecondaryDecision | null;
  intradaySignal?: MomentumIntradaySignal | null;
}

export interface MomentumScreenerAiStageEvent {
  type: 'stage';
  stage: 'context' | 'rules' | 'external' | 'synthesis' | 'drafting';
  message: string;
}

export interface MomentumScreenerAiToolEvent {
  type: 'tool_start' | 'tool_done';
  tool: string;
  displayName?: string;
  success?: boolean;
  duration?: number;
}

export interface MomentumScreenerAiDoneEvent {
  type: 'done';
  success: boolean;
  content: string;
  sessionId: string;
  contextMeta?: MomentumScreenerAiContextMeta;
  suggestedQuestions?: string[];
}

export interface MomentumScreenerAiErrorEvent {
  type: 'error';
  message: string;
}

export type MomentumScreenerAiStreamEvent =
  | MomentumScreenerAiStageEvent
  | MomentumScreenerAiToolEvent
  | MomentumScreenerAiDoneEvent
  | MomentumScreenerAiErrorEvent;

export interface MomentumScreenerAiReviewTarget {
  reviewType: MomentumScreenerAiReviewType;
  reviewKey: string;
  title: string;
  payload: MomentumScreenerRequest;
  screening: MomentumScreenerResponse;
  decision?: MomentumSecondaryDecision | null;
  intradaySignal?: MomentumIntradaySignal | null;
}

export type MomentumScreenerPageSnapshot =
  | MomentumScreenerResponse
  | MomentumScreenerDecisionResponse
  | MomentumScreenerIntradayResponse;
