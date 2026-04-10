import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TaskPanel } from '../TaskPanel';
import type { TaskInfo } from '../../../types/analysis';

const baseTask: TaskInfo = {
  taskId: 'task-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  status: 'processing',
  progress: 40,
  message: '正在抓取最新行情',
  reportType: 'detailed',
  createdAt: '2026-03-21T08:00:00Z',
  progressEvents: [
    {
      progress: 0,
      message: '任务已加入队列',
      eventType: 'task_created',
      timestamp: '2026-03-21T08:00:00Z',
    },
    {
      progress: 40,
      message: '正在抓取最新行情',
      eventType: 'task_progress',
      timestamp: '2026-03-21T08:00:05Z',
    },
  ],
};

describe('TaskPanel', () => {
  it('renders active tasks with preserved dashboard panel styling', () => {
    const { container } = render(
      <TaskPanel
        tasks={[
          baseTask,
          {
            ...baseTask,
            taskId: 'task-2',
            stockCode: 'AAPL',
            stockName: 'Apple',
            status: 'pending',
            message: '等待分析队列',
          },
        ]}
      />,
    );

    expect(screen.getByText('分析任务')).toBeInTheDocument();
    expect(screen.getByText('1 进行中')).toBeInTheDocument();
    expect(screen.getByText('1 等待中')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：分析中')).toBeInTheDocument();
    expect(container.querySelector('.home-panel-card')).toBeTruthy();
    expect(container.querySelector('.home-subpanel')).toBeTruthy();
  });

  it('opens a progress drawer when clicking the processing badge', () => {
    render(<TaskPanel tasks={[baseTask]} />);

    fireEvent.click(screen.getByLabelText('任务状态：分析中'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台 分析进度')).toBeInTheDocument();
    expect(screen.getByText('任务已创建')).toBeInTheDocument();
    expect(screen.getByText('任务已加入队列')).toBeInTheDocument();
    expect(screen.getByText('进度更新')).toBeInTheDocument();
    expect(screen.getAllByText('正在抓取最新行情')).toHaveLength(3);
  });

  it('does not render when there are no active tasks', () => {
    const { container } = render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'completed',
          },
        ]}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
