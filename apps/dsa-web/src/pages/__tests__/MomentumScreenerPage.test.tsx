import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MomentumScreenerPage from '../MomentumScreenerPage';
import { useMomentumScreenerAiStore } from '../../stores/momentumScreenerAiStore';
import type {
  MomentumScreenerDecisionResponse,
  MomentumScreenerIntradayResponse,
  MomentumScreenerResponse,
  MomentumScreenerResult,
} from '../../types/momentumScreener';

const { mockScreen } = vi.hoisted(() => ({
  mockScreen: vi.fn(),
}));

const { mockScreenWithDecision } = vi.hoisted(() => ({
  mockScreenWithDecision: vi.fn(),
}));

const { mockIntraday } = vi.hoisted(() => ({
  mockIntraday: vi.fn(),
}));

const { mockGetSystemConfig } = vi.hoisted(() => ({
  mockGetSystemConfig: vi.fn(),
}));

const { mockLoadAiSession, mockStreamAiReview } = vi.hoisted(() => ({
  mockLoadAiSession: vi.fn(),
  mockStreamAiReview: vi.fn(),
}));

vi.mock('../../api/momentumScreener', () => ({
  momentumScreenerApi: {
    screen: mockScreen,
    screenWithDecision: mockScreenWithDecision,
    fetchIntradaySignal: mockIntraday,
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: mockGetSystemConfig,
  },
}));

vi.mock('../../api/momentumScreenerAi', () => ({
  momentumScreenerAiApi: {
    loadSession: mockLoadAiSession,
    streamReview: mockStreamAiReview,
  },
}));

vi.mock('../../components/markdown/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));

function createAiStreamResponse() {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'data: {"type":"stage","stage":"rules","message":"先复述规则结论"}',
            'data: {"type":"tool_start","tool":"market_snapshot","display_name":"行情快照"}',
            'data: {"type":"done","success":true,"content":"规则结论：今天先观察，不要追高。","session_id":"screener_ai:test","context_meta":{"review_type":"candidate","review_type_label":"候选股点评","review_target":"Alpha Leader","trade_date":"2026-04-10","profile":"standard","rule_conclusion":"今天先观察，不要追高。","rule_guardrail":"AI 不替代规则总闸门。","market_data_as_of":"2026-04-10T15:00:00","tools_used":["行情快照"]},"suggested_questions":["这只票最大风险是什么？"]}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
    },
  });
}

const standardResponse: MomentumScreenerResponse = {
  profile: 'standard' as const,
  tradeDate: '2026-04-10',
  entryBaselineVersion: 'v1_4_2_2',
  marketScopeVersion: 'v1_a_share_main_chinext_star',
  candidateCount: 3,
  results: [
    {
      rank: 1,
      tsCode: '600001.SH',
      name: 'Alpha Leader',
      marketSegment: 'main_board',
      marketSegmentLabel: '涓绘澘',
      pctChg: 9.8,
      continuationScore: 88,
      extensionScore: 70,
      riskScore: 40,
      buyabilityScore: null,
      finalScore: 85,
      rankScore: 76,
      themes: ['Power Equipment'],
      leaderLevel: 'leader',
      topReasons: ['Strength Confirmed'],
      riskTags: ['risk-drift'],
      scoreBreakdown: {
        strength_confirmation: {
          score: 18,
          maxScore: 20,
          items: { pct_chg_strength: 6, close_position: 5 },
        },
      },
    },
    {
      rank: 2,
      tsCode: '600002.SH',
      name: 'Low Risk Runner',
      marketSegment: 'main_board',
      marketSegmentLabel: '涓绘澘',
      pctChg: 8.2,
      continuationScore: 72,
      extensionScore: 66,
      riskScore: 10,
      buyabilityScore: null,
      finalScore: 78,
      rankScore: 68,
      themes: ['Power Equipment'],
      leaderLevel: 'front',
      topReasons: ['Sector Resonance'],
      riskTags: [],
      scoreBreakdown: {
        sector_resonance: {
          score: 16,
          maxScore: 20,
          items: { sector_rank: 5, sector_leader: 4 },
        },
      },
    },
  ],
};

const aggressiveResponse: MomentumScreenerResponse = {
  profile: 'aggressive' as const,
  tradeDate: '2026-04-10',
  entryBaselineVersion: 'v1_4_2_2',
  marketScopeVersion: 'v1_a_share_main_chinext_star',
  candidateCount: 2,
  results: [
    {
      rank: 1,
      tsCode: '600003.SH',
      name: 'Breakout One',
      marketSegment: 'main_board',
      marketSegmentLabel: '涓绘澘',
      pctChg: 10.0,
      continuationScore: 91,
      extensionScore: 84,
      riskScore: 18,
      buyabilityScore: 77,
      opportunityTag: 'Breakout Consensus',
      entryRangeLow: 10.34,
      entryRangeHigh: 10.66,
      finalScore: 92,
      rankScore: 82,
      themes: ['Robotics'],
      leaderLevel: 'leader',
      topReasons: ['Buyable Setup', 'Volume Track'],
      riskTags: ['risk-alert'],
      scoreBreakdown: {
        buyability: {
          score: 12,
          maxScore: 15,
          items: { amplitude_space: 6, amount_golden_zone: 4 },
        },
        volume_price_track: {
          score: 11,
          maxScore: 15,
          items: { healthy_turnover: 7 },
        },
      },
    },
  ],
};

const mixedKeyResponse: MomentumScreenerResponse = {
  profile: 'aggressive' as const,
  tradeDate: '2026-04-10',
  entryBaselineVersion: 'v1_4_2_2',
  marketScopeVersion: 'v1_a_share_main_chinext_star',
  candidateCount: 1,
  results: [
    {
      rank: 1,
      tsCode: '002733.SZ',
      name: '闆勯煬鑲′唤',
      marketSegment: 'main_board',
      marketSegmentLabel: '涓绘澘',
      pctChg: 10.0,
      continuationScore: 72,
      extensionScore: 68.3,
      riskScore: 0,
      buyabilityScore: 66,
      opportunityTag: '分歧再一致',
      entryRangeLow: 16.8,
      entryRangeHigh: 17.2,
      finalScore: 69.8,
      rankScore: 69.8,
      themes: ['鐢靛姏璁惧'],
      leaderLevel: 'leader',
      topReasons: ['寮哄娍纭', '璧勯噾鎵挎帴'],
      riskTags: [],
      scoreBreakdown: {
        strengthConfirmation: {
          score: 21,
          maxScore: 30,
          items: {
            LIMITSTRENGTH: 10,
            GAPOPENSTRENGTH: 3,
            CLOSESTATUS: 6,
            ACCELERATIONCONFIRMATION: 2,
          },
        },
        capitalSupport: {
          score: 16,
          maxScore: 20,
          items: {
            MAININFLOWABS: 6,
            MAININFLOWRATIO: 6,
            PRICEFLOWALIGNMENT: 4,
            TOPLIST: 0,
          },
        },
        buyability: {
          score: 9,
          maxScore: 15,
          items: {
            AMPLITUDESPACE: 0,
            AMOUNTGOLDENZONE: 5,
            TURNOVERGOLDENZONE: 4,
          },
        },
        volumePriceTrack: {
          score: 10,
          maxScore: 15,
          items: {
            CONSENSUSLIMIT: 3,
            HEALTHYTURNOVER: 7,
          },
        },
        sectorResonance: {
          score: 8,
          maxScore: 12,
          items: {
            SECTORRANK: 2,
            SECTORBREADTH: 4,
            SECTORLEADER: 2,
          },
        },
        trendElasticity: {
          score: 6,
          maxScore: 8,
          items: {
            breakout: 4,
            CIRCMV: 0,
            HISTORICALACTIVITY: 2,
          },
        },
      },
    },
  ],
};

function buildDecisionResponse(screening: MomentumScreenerResponse): MomentumScreenerDecisionResponse {
  const topThemeName = screening.results[0]?.themes[0] ?? '未分类';
  const topThemeCandidates = screening.results.filter((item: MomentumScreenerResult) => item.themes[0] === topThemeName);
  const portfolioSource = screening.results.slice(0, Math.min(3, screening.results.length));

  return {
    screening,
    decision: {
      profile: screening.profile,
      tradeDate: screening.tradeDate,
      action: {
        level: 'normal_go' as const,
        label: '可正常出手',
        reason: `${topThemeName} 主线已经比较清晰，当前默认组合里已有可继续跟踪的候选股。`,
        sourceProfile: screening.profile,
      },
      marketEnvironment: {
        level: 'strong' as const,
        label: '强',
        score: 78,
        reason: '指数趋势、赚钱效应与主线扩散都偏强，当前环境适合继续跟踪强势股。',
        modules: [
          { key: 'index_trend', label: '强', level: 'strong' as const, score: 80, summary: '指数趋势维持向上。' },
          { key: 'profitability', label: '强', level: 'strong' as const, score: 82, summary: '昨日强势股继续给出正反馈。' },
          { key: 'sentiment', label: '中', level: 'medium' as const, score: 60, summary: '短线情绪有分化，但未明显转弱。' },
          { key: 'theme_breadth', label: '强', level: 'strong' as const, score: 76, summary: '主线扩散度较好。' },
        ],
      },
      opportunityQuality: {
        level: 'strong' as const,
        label: '强',
        matrixLevel: 'strong' as const,
        matrixLabel: '强',
        score: 74,
        reason: '主线、默认组合和买点清晰度都支持继续跟踪，当日机会质量偏强。',
        modules: [
          { key: 'theme_clarity', label: '强', level: 'strong' as const, score: 80, summary: '至少有 1 条主线比较清晰。' },
          { key: 'portfolio_quality', label: '强', level: 'strong' as const, score: 78, summary: '默认组合里有 2-3 只可跟踪对象。' },
          { key: 'buy_point_clarity', label: '强', level: 'strong' as const, score: 76, summary: '主仓与次仓都保留了明确买点。' },
          { key: 'role_structure', label: '中', level: 'medium' as const, score: 60, summary: '主仓 / 次仓 / 观察仓结构基本成立。' },
          { key: 'risk_control', label: '中', level: 'medium' as const, score: 58, summary: '高位追涨风险需要继续控制。' },
        ],
      },
      historicalValidity: {
        level: 'healthy' as const,
        label: '健康',
        score: 80,
        reason: '20/60 日历史验证当前仍保持在健康区间。',
        maxActionLevel: 'strong_go' as const,
        recommendationCap: 'full' as const,
        attackPermissionStatus: 'open' as const,
        attackPermissionLabel: '可进攻',
      },
      strategyHealth: {
        status: 'healthy' as const,
        label: '正常',
        reason: '20 日可用性与 60 日结构可信度同时健康，允许维持完整推荐。',
        recommendationCap: 'full' as const,
        canFullRecommend: true,
        shortWindow: {
          window: 'short_20d' as const,
          windowLabel: '20 日当前可用性',
          status: 'healthy' as const,
          statusLabel: '健康',
          score: 82,
          threshold: 68,
          sampleCount: 20,
          successCount: 14,
          successRate: 70,
          avgProfitWindowPct: 2.6,
          avgMaxDrawdownPct: 2.1,
          avgSelectedCount: 2.1,
          summary: '20 日窗口当前可用性已达健康阈值，可继续支撑当前判断。',
        },
        longWindow: {
          window: 'long_60d' as const,
          windowLabel: '60 日结构可信度',
          status: 'healthy' as const,
          statusLabel: '健康',
          score: 78,
          threshold: 64,
          sampleCount: 60,
          successCount: 38,
          successRate: 63.3,
          avgProfitWindowPct: 2.2,
          avgMaxDrawdownPct: 2.8,
          avgSelectedCount: 2.0,
          summary: '60 日窗口结构可信度已达健康阈值，可继续支撑当前判断。',
        },
        blockers: [],
        recoveryConditions: [],
      },
      attackPermission: {
        status: 'open' as const,
        statusLabel: '可进攻',
        label: '可进攻',
        score: 80,
        window: 'short_20d' as const,
        windowLabel: '20 日进攻许可',
        validSampleCount: 14,
        hitRate: 70,
        avgProfitWindowPct: 2.6,
        avgMaxDrawdownPct: 2.1,
        reason: '最近 20 日里，系统仍能稳定打出可执行的核心票。',
        summary: '最近 20 日里，系统仍能稳定打出可执行的核心票。',
      },
      themeConfidence: {
        status: 'credible' as const,
        statusLabel: '可信',
        label: '可信',
        score: 78,
        window: 'long_60d' as const,
        windowLabel: '60 日主线可信度',
        validSampleCount: 38,
        coreHitRate: 63.3,
        reason: '最近 60 日主线识别整体仍稳定。',
        summary: '最近 60 日主线识别整体仍稳定。',
      },
      riskBanner: null,
        mainlineRadar: [
          {
            themeId: 'capital_theme:battery',
            themeName: '电池',
            score: 82.5,
            level: 'strong',
            levelLabel: '主线强',
            candidateCount: 5,
            top10Count: 2,
            limitUpCount: 3,
            brokenLimitCount: 0,
            hotRank: 5,
            boardRank: 1,
            netAmount: 10898035456,
            pctChange: 5.2,
            upNum: 58,
            downNum: 8,
            leaderStock: '多氟多',
            sourceThemeNames: ['电解液', '隔膜', '锂矿'],
            summary: '电池 聚集 5 只候选，Top10 有 2 只，主线强度为主线强。',
            evidence: [
              {
                key: 'candidate_density',
              label: '候选池密度',
              summary: '候选池密度贡献 30.0。',
            },
          ],
        },
      ],
      shortTermSentiment: {
        level: 'tradable',
        label: '可做',
        score: 70.6,
        summary: '短线情绪为可做，主要拖累来自炸板风险、昨日强势反馈。',
      },
      v13DataStatus: {
        enabled: true,
        status: 'ok',
        reason: 'V1.3 主线增强数据已接入二次决策。',
        mainlineCount: 1,
        shortTermSentimentLevel: 'tradable',
      },
      themes: [
        {
          name: topThemeName,
          score: screening.results[0]?.rankScore ?? 70,
          strengthLabel: '主线清晰',
          candidateCount: topThemeCandidates.length,
          clearBuyPointCount: Math.max(1, Math.min(2, topThemeCandidates.length)),
          leaderCount: topThemeCandidates.filter((item: MomentumScreenerResult) => item.leaderLevel === 'leader').length || 1,
          summary: `${topThemeName} 当前聚集了 ${topThemeCandidates.length || screening.results.length} 只强势候选。`,
          representatives: topThemeCandidates.slice(0, 3).map((item: MomentumScreenerResult) => ({
            rank: item.rank,
            tsCode: item.tsCode,
            name: item.name,
            role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
            buyPointLabel: item.buyabilityScore != null && item.buyabilityScore >= 70 ? '买点清晰' : '等待触发',
            rankScore: item.rankScore,
          })),
        },
      ],
      portfolio: portfolioSource.map((item: MomentumScreenerResult, index: number) => ({
        slot: index === 0 ? 'main' : index === 1 ? 'secondary' : 'watch',
        slotLabel: index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓',
        rank: item.rank,
        tsCode: item.tsCode,
        name: item.name,
        theme: item.themes[0] ?? '未分类',
        role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
        score: item.rankScore + 8 - index,
        rankScore: item.rankScore,
        riskScore: item.riskScore,
        buyPointStatus:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? 'clear'
            : item.rankScore >= 70
              ? 'waiting'
              : 'unclear',
        buyPointLabel:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? '买点清晰'
            : item.rankScore >= 70
              ? '等待触发'
              : '买点不清晰',
        suggestedAction:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? 'ready'
            : index < 2
              ? 'wait_for_trigger'
              : 'observe_only',
        suggestedActionLabel:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? '可准备执行'
            : index < 2
              ? '继续等触发'
              : '保留观察但不建议执行',
        primaryReason: item.topReasons[0] ?? '综合强度更优',
        roleReason: `${item.name} 在当前默认组合里承担 ${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'} 角色。`,
        executionPlan:
          item.entryRangeLow != null && item.entryRangeHigh != null
            ? `优先关注 ${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)} 区间确认。`
            : '优先等待分时承接与主线回流确认，不建议直接追高。',
        entryHint:
          item.entryRangeLow != null && item.entryRangeHigh != null
            ? `优先关注 ${item.entryRangeLow.toFixed(2)} - ${item.entryRangeHigh.toFixed(2)} 区间确认。`
            : null,
        opportunityTag: item.opportunityTag ?? null,
      })),
      candidateDiagnostics: screening.results.map((item: MomentumScreenerResult, index: number) => ({
        rank: item.rank,
        tsCode: item.tsCode,
        name: item.name,
        theme: index < 2 ? '电池' : item.themes[0] ?? '未分类',
        themeScore: 82.5,
        v13ThemeId: 'capital_theme:battery',
        v13MainlineScore: 82.5,
        v13MainlineLevel: 'strong',
        v13MainlineLevelLabel: '主线强',
        v13ThemeStrengthScore: 82.5,
        v13FundSupportScore: 88 - index,
        v13LimitStructureScore: 76 - index,
        v13BuyabilityScore: 70 - index,
        v13ChipRiskScore: 42 + index,
        v13ShadowScore: 78.5 - index,
        v13ShadowSummary: 'V1.3 影子分仅用于观察真实资金题材，不直接改写官方排序。',
        roleKey: item.leaderLevel,
        role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
        buyPointStatus:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? 'clear'
            : item.rankScore >= 70
              ? 'waiting'
              : 'unclear',
        buyPointLabel:
          item.buyabilityScore != null && item.buyabilityScore >= 70
            ? '买点清晰'
            : item.rankScore >= 70
              ? '等待触发'
              : '买点不清晰',
        rankScore: item.rankScore,
        continuationScore: item.continuationScore,
        extensionScore: item.extensionScore,
        extensionSignalScore: item.extensionScore,
        buyabilityScore: item.buyabilityScore ?? null,
        riskScore: item.riskScore,
        ruleBaseScore: item.rankScore,
        explainAdjustmentScore: 0,
        t1DirectionRiskAdjustment: 0,
        decisionScore: item.rankScore + 8 - index,
        forwardAlphaScore: 50,
        forwardAlphaAdjustment: 0,
        portfolioPriority: item.rankScore + 8 - index,
        selectedSlot: index === 0 ? 'main' : index === 1 ? 'secondary' : index === 2 ? 'watch' : null,
        isSelected: index < portfolioSource.length,
      })),
      excludedCandidates: screening.results.slice(3).map((item: MomentumScreenerResult) => ({
        rank: item.rank,
        tsCode: item.tsCode,
        name: item.name,
        theme: item.themes[0] ?? '未分类',
        role: item.leaderLevel === 'leader' ? '龙头核心' : item.leaderLevel === 'front' ? '前排换手' : '观察备选',
        reason: '主线内名次不够',
        rankScore: item.rankScore,
      })),
      evidence: {
        themeValidation: [`${topThemeName} 主线评分 ${(screening.results[0]?.rankScore ?? 70).toFixed(1)}。`],
        todayReasoning: ['系统已基于当前候选引擎重新收口默认组合与落选原因。'],
      },
      actionChecklist: {
        enabled: true,
        mode: 'full' as const,
        reason: '当前出手级别允许生成明日行动清单。',
        steps: [
          {
            phase: 'pre_open' as const,
            phaseLabel: '开盘前',
            objective: '先确认默认组合今天是否仍值得继续盯。',
            focusItems: portfolioSource.map(
              (item: MomentumScreenerResult, index: number) =>
                `${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'}：${item.name}`,
            ),
            tasks: ['先看竞价强弱。', '确认谁是开盘后第一跟踪对象。'],
            expectedOutcome: '明确开盘后优先盯主仓、次仓，其余继续观察。',
          },
          {
            phase: 'first_30m' as const,
            phaseLabel: '开盘后 30 分钟',
            objective: '识别谁掉队、谁还保留买点资格。',
            focusItems: portfolioSource
              .slice(0, 2)
              .map((item: MomentumScreenerResult, index: number) => `${index === 0 ? '主仓' : '次仓'}：${item.name}`),
            tasks: ['先排除明显不及预期的票。'],
            expectedOutcome: '只保留仍值得继续跟踪的核心票。',
          },
          {
            phase: 'first_60m' as const,
            phaseLabel: '开盘后 60 分钟内',
            objective: '必须收口成“建议买 / 不建议买”的明确结论。',
            focusItems: portfolioSource.map(
              (item: MomentumScreenerResult, index: number) =>
                `${index === 0 ? '主仓' : index === 1 ? '次仓' : '观察仓'}：${item.name}`,
            ),
            tasks: ['明确优先关注谁、次选谁，其余继续观察。'],
            expectedOutcome: '输出今天最终该不该买的结论。',
          },
        ],
      },
    },
  };
}

function buildIntradayResponse(screening: MomentumScreenerResponse): MomentumScreenerIntradayResponse {
  const decisionResponse = buildDecisionResponse(screening);
  const [mainItem] = decisionResponse.decision.portfolio;

  return {
    ...decisionResponse,
    intradaySignal: {
      marketPhase: 'first_60m' as const,
      marketPhaseLabel: '开盘后 60 分钟内',
      confidenceLevel: 'low' as const,
      confidenceLabel: '低置信度',
      canEmitBuySignal: false,
      status: 'low_confidence' as const,
      statusLabel: '低置信度',
      reason: '主仓开盘后承接明显弱于预期，排序需要继续观察。',
      watchItems: ['主仓：等待分时重新站回开盘价上方。'],
      finalRecommendation: 'do_not_buy' as const,
      finalRecommendationLabel: '不建议买',
      closingNote: '今天结论是不建议买入；固定顺序仍按主仓、次仓、观察仓跟踪。',
      updatedAt: '2026-04-11T09:45:00',
      focusOrder: ['优先关注：主仓 Alpha Leader（不建议追入）'],
      portfolioItems: [
        {
          slot: mainItem.slot,
          slotLabel: mainItem.slotLabel,
          tsCode: mainItem.tsCode,
          name: mainItem.name,
          theme: mainItem.theme,
          role: mainItem.role,
          status: 'do_not_chase' as const,
          statusLabel: '不建议追入',
          reason: '当前价格已经明显偏离建议区间，不建议追入。',
          quoteAvailable: true,
          signalTriggered: false,
          doNotChase: true,
          currentPrice: 10.92,
          changePercent: 4.1,
          openPrice: 10.48,
          entryRangeLow: mainItem.entryRangeLow ?? 10.34,
          entryRangeHigh: mainItem.entryRangeHigh ?? 10.66,
          priceVsOpenPct: 4.2,
          priceVsEntryHighPct: 2.4,
          missingConditions: ['等待价格回到更合理的确认区间。'],
          updateTime: '2026-04-11T09:45:00',
        },
      ],
    },
  };
}

async function clickRunButton() {
  fireEvent.click(screen.getByTestId('momentum-screener-run'));
  await waitFor(() => {
    expect(mockScreenWithDecision).toHaveBeenCalled();
  });
  await waitFor(() => {
    expect(mockScreen).toHaveBeenCalled();
  });
}

function getSortSelect() {
  return document.getElementById('momentum-screener-sort') as HTMLSelectElement;
}

function getResultRows() {
  return screen.getAllByTestId(/^momentum-screener-row-/);
}

describe('MomentumScreenerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useMomentumScreenerAiStore.getState().closePanel();
    useMomentumScreenerAiStore.setState({
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
    });
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:momentum-export');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [],
    });
    mockLoadAiSession.mockResolvedValue({
      sessionId: 'screener_ai:test',
      reviewType: 'candidate',
      reviewTypeLabel: '候选股点评',
      sessionTitle: '候选股 AI 点评 · Alpha Leader',
      messages: [],
    });
    mockStreamAiReview.mockResolvedValue(createAiStreamResponse());
    mockScreenWithDecision.mockResolvedValue(buildDecisionResponse(standardResponse));
    mockScreen.mockResolvedValue(aggressiveResponse);
    mockIntraday.mockResolvedValue(buildIntradayResponse(standardResponse));
  });

  it('loads default form values from system config without auto-running screening', async () => {
    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'aggressive' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '12' },
      ],
    });

    render(<MomentumScreenerPage />);

    await waitFor(() => {
      expect(mockGetSystemConfig).toHaveBeenCalledWith(false);
      expect(screen.getByText('官方展示 Top30')).toBeInTheDocument();
    });

    expect(screen.getByText('Standard 官方主引擎')).toBeInTheDocument();
    expect(screen.getAllByText('Aggressive 进攻补充').length).toBeGreaterThan(0);
    expect(screen.getByText('最小涨幅 4%')).toBeInTheDocument();
    expect(screen.getByText('最小成交额 2 亿')).toBeInTheDocument();
    expect(screen.getByText('最小换手率 2%')).toBeInTheDocument();
    expect(screen.getByText('市场范围：主板 + 创业板 + 科创板')).toBeInTheDocument();
    expect(mockScreen).not.toHaveBeenCalled();
    expect(mockScreenWithDecision).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('uses a scrollable page container so action buttons are reachable on smaller viewports', () => {
    render(<MomentumScreenerPage />);

    const page = screen.getByTestId('momentum-screener-page');
    expect(page.className).toContain('overflow-y-auto');
    expect(page.className).not.toContain('overflow-hidden');
  });

  it('loads persisted form state without auto-running screening', async () => {
    window.localStorage.setItem(
      'dsa.momentum-screener.page-state',
      JSON.stringify({
        form: {
          profile: 'aggressive',
          topN: '12',
          tradeDate: '2026-04-09',
        },
        sortBy: 'buyability_score',
      }),
    );

    render(<MomentumScreenerPage />);

    expect(screen.getByDisplayValue('2026-04-09')).toBeInTheDocument();
    expect(mockGetSystemConfig).not.toHaveBeenCalled();
    expect(mockScreen).not.toHaveBeenCalled();
    expect(mockScreenWithDecision).not.toHaveBeenCalled();
  });

  it('restores system defaults and reruns screening from the current page state', async () => {
    window.localStorage.setItem(
      'dsa.momentum-screener.page-state',
      JSON.stringify({
        form: {
          profile: 'aggressive',
          topN: '12',
          tradeDate: '2026-04-09',
        },
        sortBy: 'buyability_score',
      }),
    );

    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'test-version',
      maskToken: '******',
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'standard' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '9' },
      ],
    });

    render(<MomentumScreenerPage />);

    expect(screen.getByDisplayValue('2026-04-09')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-screener-restore'));

    await waitFor(() => {
      expect(mockScreenWithDecision).toHaveBeenLastCalledWith({
        profile: 'standard',
        topN: 30,
        tradeDate: undefined,
      });
    });
  });

  it('re-sorts the list when switching sort mode', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    expect(within(getResultRows()[0]).getByText('Alpha Leader')).toBeInTheDocument();

    fireEvent.change(getSortSelect(), { target: { value: 'risk_score' } });

    await waitFor(() => {
      expect(within(getResultRows()[0]).getByText('Low Risk Runner')).toBeInTheDocument();
    });
  });

  it('opens drawer only after clicking an official result row and allows closing it', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();

    expect(await screen.findByTestId('momentum-screener-row-600001.SH')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-screener-row-600001.SH'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Alpha Leader · 600001.SH')).toBeInTheDocument();
    expect(within(dialog).getByText('Standard 官方结果')).toBeInTheDocument();
    expect(within(dialog).getByText('资金题材归因')).toBeInTheDocument();
    expect(within(dialog).getByText('电池')).toBeInTheDocument();
    expect(within(dialog).getByText('Strength Confirmed')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '关闭抽屉' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('copies the current sorted result list to clipboard', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-copy-results'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('Alpha Leader');
    expect(copiedText).toContain('Low Risk Runner');
  });

  it('does not render the legacy watchlist summary card', async () => {
    render(<MomentumScreenerPage />);

    expect(screen.queryByText('暂无观察池摘要')).not.toBeInTheDocument();

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    expect(screen.queryByTestId('momentum-screener-watchlist-summary')).not.toBeInTheDocument();
    expect(screen.queryByText('官方明日观察池摘要')).not.toBeInTheDocument();
    expect(screen.queryByTestId('momentum-screener-copy-watchlist-summary')).not.toBeInTheDocument();
  });

  it('shows the aggressive supplement panel as a secondary view instead of replacing the official summary', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    expect(await screen.findByText('Aggressive 进攻补充视图')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/发现 1 只额外进攻补充标的/));
    expect(screen.getAllByText('Breakout One').length).toBeGreaterThan(0);
    expect(screen.getByText('Breakout Consensus')).toBeInTheDocument();
    expect(screen.getByText('10.34 - 10.66')).toBeInTheDocument();
  });

  it('translates mixed-case score breakdown keys into readable Chinese labels in the aggressive supplement detail drawer', async () => {
    mockScreen.mockResolvedValue(mixedKeyResponse);

    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    await screen.findByText('Aggressive 进攻补充视图');
    fireEvent.click(screen.getByText(/发现 1 只额外进攻补充标的/));
    fireEvent.click(screen.getAllByRole('button', { name: '查看详情' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Aggressive 进攻补充')).toBeInTheDocument();
    expect(within(dialog).getAllByText('强势确认').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('资金承接').length).toBeGreaterThan(0);
    expect(within(dialog).getByText('量价双轨')).toBeInTheDocument();
    expect(within(dialog).getByText('板块共振')).toBeInTheDocument();
    expect(within(dialog).getByText('趋势位置与弹性')).toBeInTheDocument();
    expect(within(dialog).getByText('近涨停强度')).toBeInTheDocument();
    expect(within(dialog).getByText('跳空高开')).toBeInTheDocument();
    expect(within(dialog).getByText('收盘地位')).toBeInTheDocument();
    expect(within(dialog).getByText('主力净流入')).toBeInTheDocument();
    expect(within(dialog).getByText('成交额黄金区')).toBeInTheDocument();
    expect(within(dialog).getByText('健康换手')).toBeInTheDocument();
    expect(within(dialog).getByText('板块强度')).toBeInTheDocument();
    expect(within(dialog).getByText('历史股性')).toBeInTheDocument();
    expect(within(dialog).queryByText('strengthConfirmation')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('SECTORRANK')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('MAININFLOWABS')).not.toBeInTheDocument();
  });

  it('exports the current result list as markdown', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-markdown'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });

  it('exports the current result list as csv', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-csv'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });

  it('copies a single stock detail from the result row', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-copy-600001.SH'));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    });

    const copiedText = String((navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(copiedText).toContain('Alpha Leader');
    expect(copiedText).toContain('600001.SH');
    expect(copiedText).toContain('Strength Confirmed');
  });

  it('opens aggressive supplement detail without replacing the official result list', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    await screen.findByText('Aggressive 进攻补充视图');
    fireEvent.click(screen.getByText(/发现 1 只额外进攻补充标的/));
    fireEvent.click(screen.getAllByRole('button', { name: '查看详情' })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Aggressive 进攻补充')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Breakout Consensus').length).toBeGreaterThan(0);
    expect(screen.getByTestId('momentum-screener-row-600001.SH')).toBeInTheDocument();
  });

  it('renders the secondary decision panel alongside the original screening results', async () => {
    render(<MomentumScreenerPage />);

    expect(screen.getByText('暂无二次决策结果')).toBeInTheDocument();

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    const panel = screen.getByTestId('momentum-secondary-decision');
    expect(within(panel).getByTestId('momentum-secondary-action-level')).toHaveTextContent('可正常出手');
    expect(within(panel).getByText('市场环境')).toBeInTheDocument();
    expect(within(panel).getByText('当日机会质量')).toBeInTheDocument();
    expect(within(panel).getByText('进攻许可与主线可信度')).toBeInTheDocument();
    expect(within(panel).getByText('20日进攻许可')).toBeInTheDocument();
    expect(within(panel).getByText('60日主线可信度')).toBeInTheDocument();
    expect(screen.getByText('资金主攻题材')).toBeInTheDocument();
    expect(screen.getByText('资金题材')).toBeInTheDocument();
    expect(screen.getAllByText('影子分 78.5').length).toBeGreaterThan(0);
    expect(within(panel).getByText('资金题材雷达')).toBeInTheDocument();
    expect(within(panel).getByText('电池')).toBeInTheDocument();
    expect(within(panel).getByText('板块第 1')).toBeInTheDocument();
    expect(within(panel).getByText('题材强')).toBeInTheDocument();
    expect(within(panel).getByText('强弱分 82.5')).toBeInTheDocument();
    expect(within(panel).getByText('候选股 5 只')).toBeInTheDocument();
    expect(within(panel).getByText('主力净额 +108.98亿')).toBeInTheDocument();
    expect(within(panel).getByText('板块涨跌 +5.20%')).toBeInTheDocument();
    expect(within(panel).getByText('上涨家数 58 / 下跌家数 8')).toBeInTheDocument();
    expect(within(panel).getByText('领涨股 多氟多')).toBeInTheDocument();
    expect(within(panel).getByText('覆盖子题材：电解液、隔膜、锂矿')).toBeInTheDocument();
    expect(within(panel).getByText('默认 1-3 票组合')).toBeInTheDocument();
    expect(within(panel).getByText('明日行动清单')).toBeInTheDocument();
    expect(within(panel).getByText('开盘后 60 分钟内')).toBeInTheDocument();
    expect(within(panel).getAllByText('Alpha Leader').length).toBeGreaterThan(0);
    expect(within(panel).getByText('Standard 官方主引擎')).toBeInTheDocument();
    expect(screen.queryByTestId('momentum-screener-watchlist-summary')).not.toBeInTheDocument();
    expect(screen.getByText('Standard 官方筛选结果')).toBeInTheDocument();
    expect(screen.getByText('Aggressive 进攻补充视图')).toBeInTheDocument();
  });

  it('shows a visible secondary decision refresh button and warming guidance', async () => {
    const warmingResponse = buildDecisionResponse(standardResponse);
    warmingResponse.decision.strategyHealth.dataSource = 'proxy';
    warmingResponse.decision.strategyHealth.isWarming = true;
    mockScreenWithDecision.mockResolvedValue(warmingResponse);

    render(<MomentumScreenerPage />);

    await clickRunButton();
    const panel = await screen.findByTestId('momentum-secondary-decision');

    expect(within(panel).getByTestId('momentum-secondary-refresh')).toBeInTheDocument();
    expect(within(panel).getByTestId('momentum-secondary-refresh-inline')).toBeInTheDocument();
    expect(within(panel).getAllByText('刷新 20/60 结果').length).toBeGreaterThan(0);
    expect(
      within(panel).getByText('首轮请求已切换为后台预热模式，页面先给你代理结果；等真实 20/60 日历史结果算完后，点击下方刷新即可看到正式结论。'),
    ).toBeInTheDocument();
  });

  it('reuses the last submitted payload when refreshing the secondary decision', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    mockScreenWithDecision.mockClear();
    fireEvent.click(screen.getByTestId('momentum-secondary-refresh'));

    await waitFor(() => {
      expect(mockScreenWithDecision).toHaveBeenCalledWith(
        {
          profile: 'standard',
          topN: 30,
          tradeDate: undefined,
        },
        { waitForStrategyHealth: true },
      );
    });
  });

  it('refreshes intraday signal only after manual action and renders do-not-chase guidance', async () => {
    mockScreenWithDecision.mockResolvedValue(buildDecisionResponse(standardResponse));
    mockIntraday.mockResolvedValue(buildIntradayResponse(standardResponse));

    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    expect(mockIntraday).not.toHaveBeenCalled();
    expect(screen.getByText('盘中信号尚未刷新')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('momentum-intraday-refresh'));

    await waitFor(() => {
      expect(mockIntraday).toHaveBeenCalledWith({
        profile: 'standard',
        topN: 30,
        tradeDate: undefined,
      });
    });

    const panel = screen.getByTestId('momentum-intraday-signal');
    expect(within(panel).getAllByText('低置信度').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('不建议买').length).toBeGreaterThan(0);
    expect(within(panel).getAllByText('不建议追入').length).toBeGreaterThan(0);
    expect(within(panel).getByText('优先关注顺序')).toBeInTheDocument();
    expect(within(panel).getByText('今天结论是不建议买入；固定顺序仍按主仓、次仓、观察仓跟踪。')).toBeInTheDocument();
    expect(within(panel).getByText('等待价格回到更合理的确认区间。')).toBeInTheDocument();
  });

  it('opens candidate AI review drawer and auto-generates the first commentary', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-ai-600001.SH'));

    const dialog = await screen.findByRole('dialog', { name: /候选股 AI 点评 .*Alpha Leader/ });

    await waitFor(() => {
      expect(mockLoadAiSession).toHaveBeenCalledWith(
        expect.objectContaining({
          reviewType: 'candidate',
          reviewKey: '600001.SH',
        }),
      );
      expect(mockStreamAiReview).toHaveBeenCalledWith(
        expect.objectContaining({
          reviewType: 'candidate',
          reviewKey: '600001.SH',
          refreshMode: 'rerun',
        }),
        expect.any(Object),
      );
    });

    await waitFor(() => {
      expect(within(dialog).getByText('规则结论')).toBeInTheDocument();
    });
    expect(within(dialog).getAllByText('AI 不替代规则总闸门。').length).toBeGreaterThan(0);
    expect(within(dialog).getByTestId('momentum-ai-open-conversation')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByTestId('momentum-ai-open-conversation'));

    const conversationDialog = await screen.findByRole('dialog', {
      name: /候选股 AI 点评 .*Alpha Leader 对话面板/,
    });

    expect(within(conversationDialog).getByText('AI CONVERSATION')).toBeInTheDocument();
    await waitFor(() => {
      expect(conversationDialog.textContent).toContain('今天先观察，不要追高。');
    });
    expect(within(conversationDialog).getAllByText('这只票最大风险是什么？').length).toBeGreaterThan(0);
  });

  it('opens decision AI review drawer from the secondary decision panel', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    mockLoadAiSession.mockResolvedValueOnce({
      sessionId: 'screener_ai:decision',
      reviewType: 'decision',
      reviewTypeLabel: '二次决策建议',
      sessionTitle: '二次决策 AI 综合建议',
      messages: [],
    });

    fireEvent.click(screen.getByTestId('momentum-secondary-ai-review'));

    await screen.findByRole('dialog', { name: /二次决策 AI 综合建议/ });

    await waitFor(() => {
      expect(mockLoadAiSession).toHaveBeenCalledWith(
        expect.objectContaining({
          reviewType: 'decision',
          reviewKey: 'summary',
        }),
      );
      expect(mockStreamAiReview).toHaveBeenCalledWith(
        expect.objectContaining({
          reviewType: 'decision',
          reviewKey: 'summary',
          refreshMode: 'rerun',
        }),
        expect.any(Object),
      );
    });
  });

  it('exports a single stock detail as markdown from the result row', async () => {
    render(<MomentumScreenerPage />);

    await clickRunButton();
    await screen.findByTestId('momentum-screener-row-600001.SH');

    fireEvent.click(screen.getByTestId('momentum-screener-export-600001.SH'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:momentum-export');
    });
  });
});
