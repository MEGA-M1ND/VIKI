#!/usr/bin/env bash
# Start the Company Brain API server (dev mode with auto-reload).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

export CB_APP_ENV="${CB_APP_ENV:-local}"
export CB_LOG_JSON="${CB_LOG_JSON:-false}"

echo "==> Starting Company Brain API on http://0.0.0.0:${CB_APP_PORT:-8000} ..."
exec uvicorn app.main:app \
  --host "${CB_APP_HOST:-0.0.0.0}" \
  --port "${CB_APP_PORT:-8000}" \
  --reload
