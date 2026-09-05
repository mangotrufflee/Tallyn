@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  AI Finance Controller - Starting
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found.
  echo Run setup.bat once first.
  pause
  exit /b 1
)

if not exist "frontend\node_modules\" (
  echo [ERROR] Frontend dependencies not installed.
  echo Run setup.bat once first.
  pause
  exit /b 1
)

where ollama >nul 2>&1
if not errorlevel 1 (
  echo Starting Ollama in a new window...
  start "Finance Controller - Ollama" cmd /k ollama serve
) else (
  echo [WARN] Ollama not found. AI review steps may fail.
  echo        Install Ollama and run: ollama pull qwen2.5:3b
)

timeout /t 2 /nobreak >nul

echo Starting backend API on http://127.0.0.1:8000 ...
start "Finance Controller - Backend" cmd /k "cd /d %~dp0 && set PYTHONPATH=. && .venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo Starting frontend on http://127.0.0.1:5173 ...
start "Finance Controller - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo --------------------------------------------
echo Backend:  http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
echo Frontend: http://127.0.0.1:5173
echo --------------------------------------------
echo.
echo Opened windows: Ollama (if installed), Backend, Frontend.
echo Close those windows to stop the services, or run stop.bat.
echo.
timeout /t 5 /nobreak >nul
start "" http://localhost:5173
endlocal
