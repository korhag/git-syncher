@echo off
setlocal
cd /d "%~dp0"

set "NEED_INSTALL=0"
if not exist ".venv\Scripts\python.exe" set "NEED_INSTALL=1"
if "%NEED_INSTALL%"=="0" (
  ".venv\Scripts\python.exe" -c "import sys, flet as ft; raise SystemExit(0 if sys.version_info >= (3, 11) and hasattr(ft, 'run') else 1)" >nul 2>&1
  if errorlevel 1 set "NEED_INSTALL=1"
)

if "%NEED_INSTALL%"=="1" (
  echo Virtual environment missing or incompatible. Running install.bat...
  echo.
  call "%~dp0install.bat"
  if errorlevel 1 exit /b 1
  echo.
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" -m app.main
) else (
  start "" "%~dp0.venv\Scripts\python.exe" -m app.main
)
exit /b 0
