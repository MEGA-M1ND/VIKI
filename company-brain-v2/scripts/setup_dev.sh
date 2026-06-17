#!/usr/bin/env bash
# Setup the development environment from scratch.
# Run once after cloning: bash scripts/setup_dev.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Checking Python version..."
python_cmd=$(command -v python3.11 || command -v python3 || command -v python)
python_version=$("$python_cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo "    Found Python $python_version via $python_cmd"

echo "==> Creating virtual environment at .venv ..."
"$python_cmd" -m venv .venv

# Activate
source .venv/bin/activate

echo "==> Upgrading pip & wheel..."
pip install --quiet --upgrade pip wheel

echo "==> Installing project with dev extras..."
pip install --quiet -e ".[dev]"

echo "==> Copying .env.example -> .env (if not already present)..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    Created .env — fill in credentials before running connectors."
else
  echo "    .env already exists, skipping."
fi

echo ""
echo "✓ Dev setup complete."
echo "  Activate with:  source .venv/bin/activate"
echo "  Run API with:   bash scripts/run_api.sh"
echo "  Run smoke test: python scripts/smoke.py"
