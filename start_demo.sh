#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  PYTHON="$PWD/.venv/bin/python"
elif [[ -x .venv/Scripts/python.exe ]]; then
  PYTHON="$PWD/.venv/Scripts/python.exe"
else
  python3 -m venv .venv
  PYTHON="$PWD/.venv/bin/python"
fi
"$PYTHON" -m pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
if [[ ! -f backend/.env ]]; then export AWS_MODE="${AWS_MODE:-demo}"; fi
export PYTHONUNBUFFERED=1
(cd backend && exec "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!
(cd frontend && exec npm run start -- --port 3000) &
FRONTEND_PID=$!
cleanup() { kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
echo 'PulseContinuum: http://localhost:3000 | API: http://localhost:8000/docs'
wait -n "$BACKEND_PID" "$FRONTEND_PID"
