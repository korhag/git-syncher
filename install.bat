@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Git Syncher - Windows install
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo Make sure "Add python.exe to PATH" is checked.
  exit /b 1
)

python --version
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [WARN] Git was not found on PATH.
  echo Install Git from https://git-scm.com/download/win
  echo The app needs Git to sync projects.
  echo.
) else (
  git --version
  echo.
)

echo Creating virtual environment (.venv)...
if exist ".venv\Scripts\python.exe" (
  echo .venv already exists - reusing it.
) else (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    exit /b 1
  )
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip
  exit /b 1
)

echo Installing dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies
  exit /b 1
)

echo.
echo ========================================
echo  Install complete.
echo  Start the app with:  run.bat
echo ========================================
exit /b 0
