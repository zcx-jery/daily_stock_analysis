export type MomentumProfile = 'standard' | 'aggressive';

export interface MomentumScreenerRequest {
  topN: number;
  minChangePct: number;
  minAmount: number;
  minTurnover: number;
  excludeSt: boolean;
  mainBoardOnly: boolean;
  tradeDate?: string;
  profile: MomentumProfile;
}

export interface MomentumScoreBreakdown {
  score: number;
  maxScore: number;
  items: Record<string, number | string | null>;
}

export interface MomentumScreenerResult {
  rank: number;
  tsCode: string;
  name: string;
  pctChg: number;
  continuationScore: number;
  extensionScore: number;
  riskScore: number;
  buyabilityScore?: number | null;
  opportunityTag?: string | null;
  entryRangeLow?: number | null;
  entryRangeHigh?: number | null;
  finalScore: number;
  rankScore: number;
  themes: string[];
  leaderLevel: string;
  topReasons: string[];
  riskTags: string[];
  scoreBreakdown: Record<string, MomentumScoreBreakdown>;
}

export interface MomentumScreenerResponse {
  profile: MomentumProfile;
  tradeDate: string;
  candidateCount: number;
  results: MomentumScreenerResult[];
}
