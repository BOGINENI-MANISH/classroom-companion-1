#!/usr/bin/env bash
# scripts/run_demo.sh
#
# One-shot demo runner.  Sets sensible defaults and starts the app
# without needing a fully-configured .env.
#
# Usage:
#   chmod +x scripts/run_demo.sh
#   ./scripts/run_demo.sh
#
# Optional environment overrides:
#   TELEGRAM_BOT_TOKEN=xxx ./scripts/run_demo.sh
#   LLM_PROVIDER=openai OPENAI_API_KEY=xxx ./scripts/run_demo.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Defaults (override via env vars or .env) ──────────────────────────────────
export APP_HOST="${APP_HOST:-0.0.0.0}"
export APP_PORT="${APP_PORT:-8000}"
export DEBUG="${DEBUG:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export LOCAL_DEV="${LOCAL_DEV:-true}"
export SEED_DB="${SEED_DB:-true}"
export LLM_PROVIDER="${LLM_PROVIDER:-grok}"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./classroom_companion.db}"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        Classroom Companion — Demo Run        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Host   : http://${APP_HOST}:${APP_PORT}"
echo "  Debug  : ${DEBUG}"
echo "  LLM    : ${LLM_PROVIDER}"
echo "  DB     : ${DATABASE_URL}"
echo "  Seed   : ${SEED_DB}"
echo ""

# ── Dependency check ──────────────────────────────────────────────────────────
if ! python -c "import fastapi" 2>/dev/null; then
    echo "[!] Dependencies not installed. Running: pip install -r requirements.txt"
    pip install -r requirements.txt
fi

# ── Run ───────────────────────────────────────────────────────────────────────
echo "[*] Starting Classroom Companion..."
echo "    Teacher dashboard : http://localhost:${APP_PORT}/static/teacher/"
echo "    Student dashboard : http://localhost:${APP_PORT}/static/student/"
echo "    API docs          : http://localhost:${APP_PORT}/docs"
echo "    Health check      : http://localhost:${APP_PORT}/health"
echo ""
exec python main.py
