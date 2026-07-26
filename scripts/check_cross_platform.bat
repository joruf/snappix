@echo off
REM Cross-platform guard for Windows hosts.
setlocal
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\check_cross_platform.py"
) else (
  python "scripts\check_cross_platform.py"
)
exit /b %ERRORLEVEL%
