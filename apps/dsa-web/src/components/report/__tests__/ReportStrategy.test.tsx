import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReportStrategy } from '../ReportStrategy';

describe('ReportStrategy', () => {
  it('formats plain numeric values for zh reports and shows pending for missing fields', () => {
    render(
      <ReportStrategy
        language="zh"
        strategy={{
          idealBuy: '254.0',
          secondaryBuy: undefined,
          stopLoss: '248.0',
          takeProfit: '269.9',
        }}
      />,
    );

    expect(screen.getByText('254.0元')).toBeInTheDocument();
    expect(screen.getByText('248.0元')).toBeInTheDocument();
    expect(screen.getByText('269.9元')).toBeInTheDocument();
    expect(screen.getByText('待补充')).toBeInTheDocument();
  });

  it('preserves descriptive sniper text when backend returns the original strings', () => {
    render(
      <ReportStrategy
        language="zh"
        strategy={{
          idealBuy: '理想买入点：254.0元（回踩承接）',
          secondaryBuy: '次优买入点：248.0元（前低支撑/整数关口）',
          stopLoss: '止损位：235.0元（跌破平台低点）',
          takeProfit: '目标位：269.9元（MA20压力位）',
        }}
      />,
    );

    expect(screen.getByText('理想买入点：254.0元（回踩承接）')).toBeInTheDocument();
    expect(screen.getByText('次优买入点：248.0元（前低支撑/整数关口）')).toBeInTheDocument();
    expect(screen.getByText('止损位：235.0元（跌破平台低点）')).toBeInTheDocument();
    expect(screen.getByText('目标位：269.9元（MA20压力位）')).toBeInTheDocument();
  });
});
