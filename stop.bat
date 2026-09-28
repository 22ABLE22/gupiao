@echo off
setlocal
title Gupiao Stop
echo Stopping gupiao...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
exit /b 0
