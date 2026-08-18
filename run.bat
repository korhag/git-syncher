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

if exist ".venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" -m app.main
) else (
  start "" "%~dp0.venv\Scripts\python.exe" -m app.main
)
exit /b 0
