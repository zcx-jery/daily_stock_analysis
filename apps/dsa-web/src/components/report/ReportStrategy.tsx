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
                      <span className="font-mono text-cyan-300">{key}</span>
                      {section.key === 'mappedAliases' ? ' -> ' : ': '}
                      <span>{String(value)}</span>
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
