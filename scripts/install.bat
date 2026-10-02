@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo ========================================
echo  Git Syncher - Windows install
echo ========================================
echo.

set "NEED_PYTHON=0"
set "NEED_GIT=0"
set "INSTALLED_SOMETHING=0"

where python >nul 2>&1
if errorlevel 1 set "NEED_PYTHON=1"
if "%NEED_PYTHON%"=="0" (
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if errorlevel 1 set "NEED_PYTHON=1"
)

where git >nul 2>&1
if errorlevel 1 set "NEED_GIT=1"

if "%NEED_PYTHON%"=="1" (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.11+ was not found, and winget is not available.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure "Add python.exe to PATH" is checked, then re-run scripts\install.bat
    exit /b 1
  )
  echo Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERROR] winget failed to install Python 3.12
    echo Install it from https://www.python.org/downloads/ then re-run scripts\install.bat
    exit /b 1
  )
  set "INSTALLED_SOMETHING=1"
)

if "%NEED_GIT%"=="1" (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo [WARN] Git was not found on PATH, and winget is not available.
    echo Install Git from https://git-scm.com/download/win
    echo The app needs Git to sync projects.
    echo.
  ) else (
    echo Installing Git with winget...
    winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
      echo [WARN] winget failed to install Git.
      echo Install it from https://git-scm.com/download/win
      echo The app needs Git to sync projects.
      echo.
    ) else (
      set "INSTALLED_SOMETHING=1"
    )
  )
)

if "%INSTALLED_SOMETHING%"=="1" (
  echo.
  echo Close this window and run scripts\install.bat again so PATH picks up the new programs.
  exit /b 0
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
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo Existing .venv is too old. Removing it...
    rmdir /s /q .venv
  )
)
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
