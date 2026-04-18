@echo off
rem Aether CLI — Windows entry point
rem Invokes bin\aether.py with whatever Python is on PATH.

set SCRIPT_DIR=%~dp0

where py >nul 2>&1
if %ERRORLEVEL% == 0 (
  py -3 "%SCRIPT_DIR%aether.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL% == 0 (
  python "%SCRIPT_DIR%aether.py" %*
  exit /b %ERRORLEVEL%
)

echo [aether] Python 3 is not on PATH. Install from https://python.org and retry.
exit /b 127
