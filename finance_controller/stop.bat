@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Stopping AI Finance Controller processes...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo Killing process on port 8000 PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5173 .*LISTENING"') do (
  echo Killing process on port 5173 PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

echo Done. Close any leftover Ollama / cmd windows if still open.
pause
endlocal
