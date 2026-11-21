@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem UTF-8 output first: the python path can contain Korean (user folder name)
set "PYTHONIOENCODING=utf-8"
rem Fast check: run.py --check-deps only looks up installed packages (no import, ~0.3s)
rem and prints the python path, or MISSING. Importing anthropic here used to take 10+ seconds.
set "PYEXE="
for /f "delims=" %%i in ('python run.py --check-deps 2^>nul') do set "PYEXE=%%i"
if not defined PYEXE (echo Python is not installed. Install Python 3.10+ from python.org & pause & exit /b 1)
if /i "%PYEXE%"=="MISSING" (
  python -m pip install --user -r requirements.txt
  for /f "delims=" %%i in ('python run.py --check-deps 2^>nul') do set "PYEXE=%%i"
)
rem Run without a console window. Stop the app with the [App exit] button at the bottom left.
rem To keep this window with logs instead, run this file with the argument: console
if /i "%~1"=="console" goto console
for %%i in ("%PYEXE%") do set "PYW=%%~dpipythonw.exe"
if exist "%PYW%" (
  start "" "%PYW%" run.py
  exit /b 0
)
:console
title Gian Learner - close this window to stop
python run.py
if errorlevel 1 pause
