#!/usr/bin/env bash
# Full end-to-end demo: smoke test + API boot + context query.
# Requires no external credentials — uses the in-memory store and fake extractor.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

echo "===================================================================="
echo "  Company Brain — full local demo"
echo "===================================================================="
echo ""

echo "--- Step 1: Run smoke test (fake extractor → in-memory store) ---"
python scripts/smoke.py
echo ""

echo "--- Step 2: Run tests ---"
pytest tests/ -q --tb=short
echo ""

echo "--- Step 3: Start API in background and query context ---"
uvicorn app.main:app --host 127.0.0.1 --port 8765 --log-level warning &
API_PID=$!
sleep 2

echo "  Health check:"
curl -s http://127.0.0.1:8765/health | python -m json.tool

echo ""
echo "  Readiness check:"
curl -s http://127.0.0.1:8765/ready | python -m json.tool

echo ""
echo "  Context query (empty store — expected empty context):"
curl -s -X POST http://127.0.0.1:8765/context/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Q2 budget approval"}' | python -m json.tool

kill $API_PID 2>/dev/null || true

echo ""
echo "===================================================================="
echo "  Demo complete."
echo "===================================================================="
