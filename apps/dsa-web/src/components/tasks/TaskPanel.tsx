import type React from 'react';
import { useMemo, useState } from 'react';
import { Badge, Card, Drawer, StatusDot } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import type { TaskInfo, TaskProgressEvent } from '../../types/analysis';

const TASK_EVENT_LABELS: Record<string, string> = {
  task_created: '任务已创建',
  task_started: '开始执行',
  task_progress: '进度更新',
  task_completed: '分析完成',
  task_failed: '分析失败',
};

function formatTaskEventTime(timestamp?: string): string {
  if (!timestamp) {
    return '';
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

interface TaskItemProps {
  task: TaskInfo;
  onOpenDetails: (task: TaskInfo) => void;
}

const TaskItem: React.FC<TaskItemProps> = ({ task, onOpenDetails }) => {
  const isPending = task.status === 'pending';
  const isProcessing = task.status === 'processing';
  const statusLabel = isProcessing ? '分析中' : '等待中';
  const statusVariant = isProcessing ? 'info' : 'default';
  const statusTone = isProcessing ? 'info' : 'neutral';
  const progress = Math.max(0, Math.min(100, task.progress || 0));
  const hasProgressDetails = (task.progressEvents?.length ?? 0) > 0;

  return (
    <div className="home-subpanel flex items-center gap-3 px-3 py-2.5">
      <div className="shrink-0">
        {isProcessing ? (
          <StatusDot tone="info" pulse className="h-2.5 w-2.5" aria-label="任务进行中" />
        ) : isPending ? (
          <StatusDot tone="neutral" className="h-2.5 w-2.5" aria-label="任务等待中" />
        ) : null}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {task.stockName || task.stockCode}
          </span>
          <span className="text-xs text-muted-text">
            {task.stockCode}
          </span>
        </div>
        {task.message && (
          <p className="mt-0.5 truncate text-xs text-secondary-text">
            {task.message}
          </p>
        )}
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-cyan transition-[width] duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-text">
            {progress}%
          </span>
        </div>
      </div>

      <div className="flex-shrink-0">
        {hasProgressDetails ? (
          <button
            type="button"
            onClick={() => onOpenDetails(task)}
            className="inline-flex"
            aria-label={`任务状态：${statusLabel}`}
          >
            <Badge
              variant={statusVariant}
              className="min-w-[4.75rem] justify-center gap-1.5 shadow-none transition-colors hover:bg-hover"
            >
              <StatusDot tone={statusTone} pulse={isProcessing} className="h-1.5 w-1.5" />
              {statusLabel}
            </Badge>
          </button>
        ) : (
          <Badge
            variant={statusVariant}
            className="min-w-[4.75rem] justify-center gap-1.5 shadow-none"
            aria-label={`任务状态：${statusLabel}`}
          >
            <StatusDot tone={statusTone} pulse={isProcessing} className="h-1.5 w-1.5" />
            {statusLabel}
          </Badge>
        )}
      </div>
    </div>
  );
};

interface TaskPanelProps {
  tasks: TaskInfo[];
  visible?: boolean;
  title?: string;
  className?: string;
}

export const TaskPanel: React.FC<TaskPanelProps> = ({
  tasks,
  visible = true,
  title = '分析任务',
  className = '',
}) => {
  const [selectedTask, setSelectedTask] = useState<TaskInfo | null>(null);
  const activeTasks = tasks.filter((task) => task.status === 'pending' || task.status === 'processing');
  const pendingCount = activeTasks.filter((task) => task.status === 'pending').length;
  const processingCount = activeTasks.filter((task) => task.status === 'processing').length;
  const selectedTaskLive = useMemo(
    () => activeTasks.find((task) => task.taskId === selectedTask?.taskId) ?? selectedTask,
    [activeTasks, selectedTask],
  );
  const progressEvents = selectedTaskLive?.progressEvents ?? [];

  if (!visible || activeTasks.length === 0) {
    return null;
  }

  return (
    <Card
      variant="bordered"
      padding="none"
      className={`home-panel-card overflow-hidden ${className}`}
    >
      <div className="border-b border-subtle px-3 py-3">
        <DashboardPanelHeader
          className="mb-0"
          title={title}
          titleClassName="text-sm font-medium"
          leading={(
            <svg className="h-4 w-4 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          )}
          headingClassName="items-center"
          actions={(
            <div className="flex items-center gap-2 text-xs text-muted-text">
              {processingCount > 0 && (
                <span className="flex items-center gap-1">
                  <StatusDot tone="info" pulse className="h-1.5 w-1.5" aria-label="进行中任务" />
                  {processingCount} 进行中
                </span>
              )}
              {pendingCount > 0 ? (
                <span className="flex items-center gap-1">
                  <StatusDot tone="neutral" className="h-1.5 w-1.5" aria-label="等待中任务" />
                  {pendingCount} 等待中
                </span>
              ) : null}
            </div>
          )}
        />
      </div>

      <div className="max-h-64 overflow-y-auto p-2">
        <div className="space-y-2">
          {activeTasks.map((task) => (
            <TaskItem key={task.taskId} task={task} onOpenDetails={setSelectedTask} />
          ))}
        </div>
      </div>

      <Drawer
        isOpen={selectedTaskLive !== null}
        onClose={() => setSelectedTask(null)}
        title={selectedTaskLive ? `${selectedTaskLive.stockName || selectedTaskLive.stockCode} 分析进度` : undefined}
        width="max-w-xl"
      >
        {selectedTaskLive && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-secondary-text">{selectedTaskLive.stockCode}</span>
                <span className="font-mono text-cyan">{selectedTaskLive.progress}%</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/8">
                <div
                  className="h-full rounded-full bg-cyan transition-[width] duration-300 ease-out"
                  style={{ width: `${Math.max(0, Math.min(100, selectedTaskLive.progress || 0))}%` }}
                />
              </div>
              {selectedTaskLive.message ? (
                <p className="mt-3 text-sm text-foreground/90">{selectedTaskLive.message}</p>
              ) : null}
            </div>

            <div className="space-y-3">
              {progressEvents.length > 0 ? (
                progressEvents.map((event: TaskProgressEvent, index) => (
                  <div key={`${event.timestamp}-${index}`} className="flex gap-3">
                    <div className="mt-1 flex flex-col items-center">
                      <span className="h-2.5 w-2.5 rounded-full bg-cyan shadow-[0_0_0_4px_rgba(34,211,238,0.12)]" />
                      {index < progressEvents.length - 1 ? (
                        <span className="mt-1 h-full w-px bg-white/10" />
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-secondary-text">
                        <span>{TASK_EVENT_LABELS[event.eventType] ?? '进度更新'}</span>
                        <span>{event.progress}%</span>
                        {event.timestamp ? <span>{formatTaskEventTime(event.timestamp)}</span> : null}
                      </div>
                      <div className="mt-1 break-words text-sm text-foreground/90">{event.message}</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-muted-text">
                  暂无详细进度
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </Card>
  );
};

export default TaskPanel;
