@echo off
chcp 65001 > nul
cd /d "%~dp0"
where python > nul 2>&1 || (echo Python is not installed. Install Python 3.10+ from python.org & pause & exit /b 1)
python -c "import fastapi, uvicorn, lxml, multipart" > nul 2>&1 || python -m pip install --user -r requirements.txt
title Gian Learner - close this window to stop
python run.py
if errorlevel 1 pause
