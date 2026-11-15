@echo off
rem Start PsyPull on Windows: double-click this file, then open http://127.0.0.1:8000
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if not exist config.yaml copy config.example.yaml config.yaml >nul
echo PsyPull is starting: open http://127.0.0.1:8000
start "" http://127.0.0.1:8000
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
