#!/usr/bin/env bash
# One-command launcher: sets up the backend venv (first run only), installs
# dependencies, starts the API, serves the frontend, and opens it in your
# browser. Works with zero configuration — no API key required to try it,
# since the app auto-falls-back to a local rule-based engine until you add
# one to backend/.env.
set -e
cd "$(dirname "$0")"

echo "== WeatherGPT setup =="

if [ ! -d "backend/venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv backend/venv
fi

echo "Installing backend dependencies..."
backend/venv/bin/pip install -q -r backend/requirements.txt

if [ ! -f "backend/.env" ]; then
  cp backend/.env.example backend/.env
  echo "No backend/.env found — created one from the template."
  echo "(The app will run in local/no-AI mode until you paste a real ANTHROPIC_API_KEY into backend/.env)"
fi

echo "Starting backend on http://localhost:8000 ..."
(cd backend && ../backend/venv/bin/python run.py) &
BACKEND_PID=$!

sleep 2

echo "Starting frontend on http://localhost:5500 ..."
(cd frontend && python3 -m http.server 5500) &
FRONTEND_PID=$!

sleep 1
URL="http://localhost:5500"
if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
fi

echo ""
echo "WeatherGPT is running:"
echo "  Frontend: $URL"
echo "  Backend:  http://localhost:8000"
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID" INT TERM
wait
