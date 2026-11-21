@echo off
chcp 65001 > nul
cd /d "%~dp0"
where python > nul 2>&1 || (echo Python is not installed. Install Python 3.10+ from python.org & pause & exit /b 1)
python -c "import fastapi, uvicorn, lxml, multipart, pypdf, anthropic, webview" > nul 2>&1 || python -m pip install --user -r requirements.txt
rem Run without a console window. Stop the app with the [App exit] button at the bottom left.
rem To keep this window with logs instead, run this file with the argument: console
if /i "%~1"=="console" goto console
set "PYTHONIOENCODING=utf-8"
for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)"') do set "PYW=%%~dpipythonw.exe"
if exist "%PYW%" (
  start "" "%PYW%" run.py
  exit /b 0
)
:console
title Gian Learner - close this window to stop
python run.py
if errorlevel 1 pause
