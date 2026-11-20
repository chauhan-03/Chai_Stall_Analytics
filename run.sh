#!/usr/bin/env bash
# One command to set up and start the dashboard (macOS / Linux). Needs Python 3.11+.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "Setting up (first time only, a few minutes)..."
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
echo "Opening http://localhost:8501"
exec .venv/bin/streamlit run app.py
