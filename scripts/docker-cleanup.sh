#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="/tmp/dsa-docker-cleanup.lock"
LOG_FILE="/var/log/dsa-docker-cleanup.log"
APP_ROOT="/opt/daily_stock_analysis"
CACHE_DIR="$APP_ROOT/data/cache"

CONTAINER_KEEP_AGE="24h"
IMAGE_KEEP_AGE="72h"
BUILDER_KEEP_AGE="${DSA_DOCKER_BUILDER_KEEP_AGE:-24h}"
BUILDER_MAX_USED_SPACE="${DSA_DOCKER_BUILDER_MAX_USED_SPACE:-2gb}"
BUILDER_MIN_FREE_SPACE="${DSA_DOCKER_BUILDER_MIN_FREE_SPACE:-8gb}"
IMAGE_FORCE_PRUNE_THRESHOLD=80
VOLUME_PRUNE_THRESHOLD=90
CACHE_KEEP_DAYS=30

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T %Z') cleanup already running"
  exit 0
fi

if ! touch "$LOG_FILE" >/dev/null 2>&1; then
  LOG_FILE=""
fi

log() {
  local message
  message="$(date '+%F %T %Z') $*"
  if [[ -n "$LOG_FILE" ]]; then
    echo "$message" | tee -a "$LOG_FILE"
  else
    echo "$message"
  fi
}

run() {
  log "+ $*"
  "$@" 2>&1 | while IFS= read -r line; do
    log "  $line"
  done
}

disk_usage_percent() {
  df -P / | awk 'NR == 2 {gsub("%", "", $5); print $5}'
}

builder_prune_supports_budget() {
  docker builder prune --help 2>&1 | grep -q -- "--max-used-space"
}

prune_builder_cache_budget() {
  if builder_prune_supports_budget; then
    run docker builder prune -af \
      --max-used-space "$BUILDER_MAX_USED_SPACE" \
      --min-free-space "$BUILDER_MIN_FREE_SPACE"
  else
    log "Docker builder prune does not support cache budget flags; skipping budgeted build-cache prune"
  fi
}

log "DSA cleanup started"
run df -h /

if command -v docker >/dev/null 2>&1; then
  run docker system df

  run docker container prune -f --filter "until=$CONTAINER_KEEP_AGE"
  run docker image prune -af --filter "until=$IMAGE_KEEP_AGE"
  run docker builder prune -af --filter "until=$BUILDER_KEEP_AGE"
  prune_builder_cache_budget

  current_usage="$(disk_usage_percent)"
  if [[ "$current_usage" =~ ^[0-9]+$ ]] && (( current_usage >= IMAGE_FORCE_PRUNE_THRESHOLD )); then
    log "Disk usage ${current_usage}% >= ${IMAGE_FORCE_PRUNE_THRESHOLD}%; pruning all unused images and build cache"
    run docker image prune -af
    run docker builder prune -af
  fi

  current_usage="$(disk_usage_percent)"
  if [[ "$current_usage" =~ ^[0-9]+$ ]] && (( current_usage >= VOLUME_PRUNE_THRESHOLD )); then
    log "Disk usage ${current_usage}% >= ${VOLUME_PRUNE_THRESHOLD}%; pruning unused Docker volumes"
    run docker volume prune -f
  else
    log "Skipping Docker volume prune; disk usage is ${current_usage}%"
  fi

  run docker system df
else
  log "Docker command not found; skipping Docker cleanup"
fi

if [[ -d "$CACHE_DIR" ]]; then
  log "Cleaning cache files older than ${CACHE_KEEP_DAYS} days under $CACHE_DIR"
  find "$CACHE_DIR" -type f -mtime "+$CACHE_KEEP_DAYS" -print -delete 2>&1 | while IFS= read -r line; do
    log "  $line"
  done
  find "$CACHE_DIR" -type d -empty -print -delete 2>&1 | while IFS= read -r line; do
    log "  removed empty dir $line"
  done
fi

run df -h /
log "DSA cleanup finished"
