import type React from 'react';
import { Pie, PieChart, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { Card, EmptyState } from '../common';

const PIE_COLORS = ['#00d4ff', '#00ff88', '#ffaa00', '#ff7a45', '#7f8cff', '#ff4466'];

type ChartDatum = {
  name: string;
  value: number;
};

type PortfolioConcentrationChartProps = {
  concentrationMode: 'sector' | 'position';
  concentrationPieData: ChartDatum[];
  sectorAlert: boolean;
};

const PortfolioConcentrationChart: React.FC<PortfolioConcentrationChartProps> = ({
  concentrationMode,
  concentrationPieData,
  sectorAlert,
}) => {
  return (
    <Card padding="md">
      <h2 className="mb-3 text-sm font-semibold text-foreground">
        {concentrationMode === 'sector' ? '琛屼笟闆嗕腑搴﹀垎甯?' : '琛屼笟鏁版嵁鏆備笉鍙敤锛屽綋鍓嶅睍绀轰釜鑲￠泦涓害'}
      </h2>
      {concentrationPieData.length > 0 ? (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={concentrationPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                {concentrationPieData.map((entry, index) => (
                  <Cell key={`cell-${entry.name}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState
          title="鏆傛棤闆嗕腑搴︽暟鎹?"
          description="椋庨櫓妯″潡瀹屾垚璁＄畻鍚庯紝杩欓噷浼氬睍绀鸿涓氭垨涓偂缁村害鐨勯泦涓害鍒嗗竷銆?"
          className="border-none bg-transparent px-4 py-10 shadow-none"
        />
      )}
      <div className="mt-3 space-y-1 text-xs text-secondary">
        <div>灞曠ず鍙ｅ緞: {concentrationMode === 'sector' ? '琛屼笟缁村害' : '涓偂缁村害锛堥檷绾ф樉绀猴級'}</div>
        <div>鏉垮潡闆嗕腑搴﹀憡璀? {sectorAlert ? '鏄?' : '鍚?'}</div>
      </div>
    </Card>
  );
};

export default PortfolioConcentrationChart;
