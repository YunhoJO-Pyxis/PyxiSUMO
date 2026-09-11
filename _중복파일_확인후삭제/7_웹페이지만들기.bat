@echo off
chcp 65001 >nul 2>nul
title PyxiSumo
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   [!!] Not installed yet.
  echo        Please run the install file first ^(the one starting with 1_^).
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\wizard.py site
exit /b %errorlevel%
