@echo off
REM One-command launcher for Windows: sets up the backend venv (first run
REM only), installs dependencies, starts the API, serves the frontend, and
REM opens it in your browser. No API key required to try it -- the app
REM auto-falls-back to a local rule-based engine until you add one to
REM backend\.env.

cd /d "%~dp0"

echo == WeatherGPT setup ==

if not exist "backend\venv" (
    echo Creating Python virtual environment...
    python -m venv backend\venv
)

echo Installing backend dependencies...
backend\venv\Scripts\pip install -q -r backend\requirements.txt

if not exist "backend\.env" (
    copy backend\.env.example backend\.env
    echo No backend\.env found -- created one from the template.
    echo (The app will run in local/no-AI mode until you paste a real ANTHROPIC_API_KEY into backend\.env)
)

echo Starting backend on http://localhost:8000 ...
start "WeatherGPT backend" cmd /k "cd backend && ..\backend\venv\Scripts\python run.py"

timeout /t 2 /nobreak >nul

echo Starting frontend on http://localhost:5500 ...
start "WeatherGPT frontend" cmd /k "cd frontend && python -m http.server 5500"

timeout /t 1 /nobreak >nul
start http://localhost:5500

echo.
echo WeatherGPT is running in two new terminal windows.
echo   Frontend: http://localhost:5500
echo   Backend:  http://localhost:8000
echo Close those windows to stop the servers.
