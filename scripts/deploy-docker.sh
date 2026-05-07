#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "Missing .env in $ROOT_DIR" >&2
  exit 1
fi

compose() {
  docker compose --env-file .env -f docker/docker-compose.yml "$@"
}

command_name="${1:-rebuild}"
shift || true

case "$command_name" in
  up)
    compose up -d "$@"
    ;;
  rebuild)
    compose build --no-cache "$@"
    compose up -d "$@"
    docker image prune -f >/dev/null || true
    ;;
  cleanup)
    bash scripts/docker-cleanup.sh
    ;;
  restart)
    compose restart "$@"
    ;;
  down)
    compose down "$@"
    ;;
  logs)
    compose logs -f "$@"
    ;;
  ps)
    compose ps "$@"
    ;;
  *)
    echo "Usage: scripts/deploy-docker.sh [up|rebuild|cleanup|restart|down|logs|ps] [service...]" >&2
    exit 1
    ;;
esac
