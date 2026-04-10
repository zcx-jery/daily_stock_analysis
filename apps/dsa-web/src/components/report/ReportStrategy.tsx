import type React from 'react';
import type {
  ReportFieldDrift,
  ReportLanguage,
  ReportStrategy as ReportStrategyType,
} from '../../types/analysis';
import { Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportStrategyProps {
  strategy?: ReportStrategyType;
  fieldDrift?: ReportFieldDrift;
  language?: ReportLanguage;
}

interface StrategyItemProps {
  label: string;
  value?: string;
  tone: string;
}

const PLACEHOLDER_VALUES = new Set(['', '-', '—', 'N/A', 'n/a', 'null', 'undefined', '待补充']);

const DRIFT_FIELD_LABELS: Record<string, { zh: string; en: string }> = {
  ideal_buy: { zh: '理想买入点', en: 'Ideal Entry' },
  ideal_buy_if_valuation_improves: { zh: '估值改善理想买点', en: 'Ideal Buy If Valuation Improves' },
  buy_zone: { zh: '买入区间', en: 'Buy Zone' },
  entry_zone: { zh: '入场区间', en: 'Entry Zone' },
  idealEntry: { zh: '理想入场区间', en: 'Ideal Entry Range' },
  secondary_buy: { zh: '次优买入点', en: 'Secondary Entry' },
  secondary_entry: { zh: '次级入场位', en: 'Secondary Entry Level' },
  add_on_breakout: { zh: '突破加仓位', en: 'Add-on Breakout Level' },
  next_buy: { zh: '下一买点', en: 'Next Buy Level' },
  support: { zh: '支撑位', en: 'Support Level' },
  support_level: { zh: '支撑位', en: 'Support Level' },
  immediate_support: { zh: '当前支撑位', en: 'Immediate Support' },
  resistance: { zh: '阻力位', en: 'Resistance Level' },
  current_resistance: { zh: '当前阻力位', en: 'Current Resistance' },
  resistance_1: { zh: '一级阻力位', en: 'Primary Resistance' },
  resistance_2: { zh: '二级阻力位', en: 'Secondary Resistance' },
  target_price: { zh: '目标价', en: 'Target Price' },
  take_profit: { zh: '止盈目标', en: 'Take Profit' },
  next_breakout_target: { zh: '突破后目标位', en: 'Next Breakout Target' },
  stop_loss: { zh: '止损位', en: 'Stop Loss' },
  stopLoss: { zh: '止损位', en: 'Stop Loss' },
  strong_support_stop_loss: { zh: '强支撑止损位', en: 'Strong Support Stop Loss' },
  pressure_band: { zh: '压力区间', en: 'Pressure Band' },
  trend_alignment: { zh: '趋势排列', en: 'Trend Alignment' },
  volume_signal: { zh: '量价信号', en: 'Volume Signal' },
};

function formatStrategyValue(value: string | undefined, language: ReportLanguage): string | undefined {
  const text = (value ?? '').trim();
  if (!text || PLACEHOLDER_VALUES.has(text)) {
    return undefined;
  }

  if (language === 'zh') {
    if (/^\d+(?:\.\d+)?$/.test(text)) {
      return `${text}元`;
    }
    if (/^\d+(?:\.\d+)?\s*[-~至]\s*\d+(?:\.\d+)?$/.test(text)) {
      return `${text}元`;
    }
  }

  return text;
}

function getDriftFieldLabel(key: string, language: ReportLanguage): string {
  const predefined = DRIFT_FIELD_LABELS[key];
  if (predefined) {
    return language === 'zh' ? predefined.zh : predefined.en;
  }
  return key;
}

const StrategyItem: React.FC<StrategyItemProps> = ({
  label,
  value,
  tone,
}) => (
  <div className="home-subpanel home-strategy-card p-3" style={{ ['--home-strategy-tone' as string]: `var(${tone})` }}>
    <div className="flex flex-col">
      <span className="home-strategy-label mb-0.5 text-xs">{label}</span>
      <span className="home-strategy-value text-lg font-bold font-mono" style={!value ? { color: 'var(--text-muted-text)' } : undefined}>
        {value || '—'}
      </span>
    </div>
    <div
      className="absolute bottom-0 left-0 right-0 h-0.5"
      style={{ background: `linear-gradient(90deg, transparent, var(${tone}), transparent)` }}
    />
  </div>
);

/**
 * 策略点位区组件 - 终端风格
 */
export const ReportStrategy: React.FC<ReportStrategyProps> = ({
  strategy,
  fieldDrift,
  language = 'zh',
}) => {
  if (!strategy) {
    return null;
  }

  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const emptyText = reportLanguage === 'zh' ? '待补充' : 'Pending';
  const driftSections = [
    {
      key: 'mappedAliases',
      label: text.mappedAliases,
      entries: Object.entries(fieldDrift?.mappedAliases ?? {}),
    },
    {
      key: 'rawKeyLevels',
      label: text.rawKeyLevels,
      entries: Object.entries(fieldDrift?.rawKeyLevels ?? {}),
    },
    {
      key: 'unmappedKeyLevels',
      label: text.unmappedKeyLevels,
      entries: Object.entries(fieldDrift?.unmappedKeyLevels ?? {}),
    },
    {
      key: 'dashboardExtra',
      label: text.dashboardExtra,
      entries: Object.entries(fieldDrift?.dashboardExtra ?? {}),
    },
  ].filter((section) => section.entries.length > 0);

  const strategyItems = [
    {
      label: text.idealBuy,
      value: formatStrategyValue(strategy.idealBuy, reportLanguage),
      tone: '--home-strategy-buy',
    },
    {
      label: text.secondaryBuy,
      value: formatStrategyValue(strategy.secondaryBuy, reportLanguage),
      tone: '--home-strategy-secondary',
    },
    {
      label: text.stopLoss,
      value: formatStrategyValue(strategy.stopLoss, reportLanguage),
      tone: '--home-strategy-stop',
    },
    {
      label: text.takeProfit,
      value: formatStrategyValue(strategy.takeProfit, reportLanguage),
      tone: '--home-strategy-take',
    },
  ];

  return (
    <Card variant="bordered" padding="md" className="home-panel-card">
      <DashboardPanelHeader
        eyebrow={text.strategyPoints}
        title={text.sniperLevels}
        className="mb-3"
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {strategyItems.map((item) => (
          <StrategyItem key={item.label} {...item} value={item.value ?? emptyText} />
        ))}
      </div>
      {driftSections.length > 0 && (
        <details className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-muted-text">
          <summary className="cursor-pointer select-none font-medium text-foreground">
            {text.driftFields}
          </summary>
          <div className="mt-3 space-y-3">
            {driftSections.map((section) => (
              <div key={section.key}>
                <div className="mb-1 text-xs uppercase tracking-[0.18em] text-muted-text/80">
                  {section.label}
                </div>
                <div className="space-y-1">
                  {section.entries.map(([key, value]) => (
                    <div key={`${section.key}-${key}`} className="break-words text-foreground/90">
                      <span className="text-foreground">{getDriftFieldLabel(key, reportLanguage)}</span>{' '}
                      <span className="font-mono text-cyan-300">({key})</span>
                      {section.key === 'mappedAliases' ? ' -> ' : ': '}
                      <span>
                        {section.key === 'mappedAliases'
                          ? `${getDriftFieldLabel(String(value), reportLanguage)} (${String(value)})`
                          : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </Card>
  );
};
