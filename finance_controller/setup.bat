@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  AI Finance Controller - First-time setup
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.10+ and try again.
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js was not found on PATH.
  echo Install Node.js 18+ and try again.
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm was not found on PATH.
  exit /b 1
)

echo [1/4] Creating Python virtual environment...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    exit /b 1
  )
) else (
  echo       .venv already exists
)

echo [2/4] Installing Python packages...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed
  exit /b 1
)

echo [3/4] Installing frontend packages...
pushd frontend
call npm install
if errorlevel 1 (
  popd
  echo [ERROR] npm install failed
  exit /b 1
)
popd

echo [4/4] Checking Ollama / AI model...
where ollama >nul 2>&1
if errorlevel 1 (
  echo [WARN] Ollama was not found on PATH.
  echo       Install from https://ollama.com then run:
  echo       ollama pull qwen2.5:3b
) else (
  echo       Pulling qwen2.5:3b if needed...
  ollama pull qwen2.5:3b
)

echo.
echo Setup complete.
echo Next: run start.bat
echo.
pause
endlocal
