#!/usr/bin/env bash
# Start backend (:8000) and frontend (:5173) in one terminal; Ctrl+C stops both.
# Run from anywhere:   ./scripts/dev.sh
cd "$(dirname "$0")/.."

(cd backend && uv run uvicorn main:app --reload) &
# kill 0 = the whole process group, so uvicorn's reload child dies too
trap 'kill 0 2>/dev/null' EXIT

cd frontend && npm run dev
