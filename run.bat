@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment missing. Running install.bat...
  echo.
  call "%~dp0install.bat"
  if errorlevel 1 exit /b 1
  echo.
)

".venv\Scripts\python.exe" -m app.main
