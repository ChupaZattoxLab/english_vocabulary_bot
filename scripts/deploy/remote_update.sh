#!/usr/bin/env bash
# Apply deploy artefacts on the server (called over SSH from GitHub Actions).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/english_vocabulary_bot}"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/chupazattoxlab/english_vocabulary_bot}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-300}"
cd "$APP_DIR"

if [[ -z "${BOT_IMAGE:-}" ]]; then
  echo "BOT_IMAGE is required" >&2
  exit 1
fi

if [[ -z "${DEPLOY_ENV_FILE:-}" || ! -f "$DEPLOY_ENV_FILE" ]]; then
  echo "DEPLOY_ENV_FILE must point to a generated .env payload" >&2
  exit 1
fi

: "${GHCR_TOKEN:?GHCR_TOKEN is required}"
: "${GHCR_USER:?GHCR_USER is required}"
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

install -m 600 "$DEPLOY_ENV_FILE" "$APP_DIR/.env"
export BOT_IMAGE

# Prefer Docker Compose bot over a leftover host systemd unit.
if command -v systemctl >/dev/null 2>&1; then
  systemctl stop vocabulary-bot 2>/dev/null || true
  systemctl disable vocabulary-bot 2>/dev/null || true
fi

docker compose pull bot
# Block until postgres is healthy and bot healthcheck passes (migrate + tgbot up).
docker compose up -d --wait --wait-timeout "$WAIT_TIMEOUT_SECONDS" postgres bot
docker compose ps

echo "Pruning unused ${IMAGE_REPO} images (keeps the one in use by bot)..."
docker image prune -af --filter "reference=${IMAGE_REPO}" || true
docker image prune -f || true

echo "Deploy finished: BOT_IMAGE=$BOT_IMAGE"
