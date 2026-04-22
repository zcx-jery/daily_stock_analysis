# Momentum Backtest Task Heartbeat Note

## Purpose

This note supplements the V1 momentum backtest task-center design.
It documents how long-running stages should expose liveness and progress.

## Scope

Applies to the V1 momentum backtest task lifecycle, especially the `secondary_decision` stage.

## Rules

1. When a run stays in `secondary_decision` for a long time, the backend must keep refreshing `heartbeat_at`.
2. `current_stage_label` may carry fine-grained progress, for example:
   - `二次决策回放中（样本 15/60）`
   - `二次决策回放中（扫描 24/72）`
3. The task center should use the refreshed `heartbeat_at` to show that the task is still alive, not frozen.
4. This heartbeat refresh is only a progress-observability improvement. It does not change the decision algorithm or replay outcome.

## Why

Without continuous heartbeat updates, users may see an old timestamp for many minutes and incorrectly assume the service is hung.
This is especially likely during historical strategy-health validation, where a single trade date can take a long time to finish.

## API / UI Impact

- `heartbeat_at` is expected to move forward while the run is still progressing inside `secondary_decision`.
- `current_stage_label` can temporarily become a progress-aware label instead of a fixed stage name.
- Once the run moves to the next stage, the normal stage label takes over again.
