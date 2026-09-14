@echo off
chcp 65001 >nul 2>nul
title PyxiSUMO - Install
cd /d "%~dp0"

echo.
echo   PyxiSUMO installer starting...
echo.

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
  echo   [!!] Python not found.
  echo        Install Python 3.12 from https://www.python.org/downloads/
  echo        and check "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo   Creating a private Python folder for this app...
  %PYEXE% -m venv .venv
  if errorlevel 1 (
    echo   [!!] Could not create the virtual environment.
    pause
    exit /b 1
  )
)

set "VPY=.venv\Scripts\python.exe"

echo   Installing required packages...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VPY%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo   [!!] Package installation failed. Check your internet connection.
  pause
  exit /b 1
)

"%VPY%" tools\wizard.py install
exit /b %errorlevel%
