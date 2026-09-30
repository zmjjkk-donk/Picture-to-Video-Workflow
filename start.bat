@echo off
cd /d "%~dp0"
"D:\anaconda\envs\interview-agent\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

