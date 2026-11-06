@echo off
cd /d "%~dp0.."
if not exist logs mkdir logs
".venv\Scripts\python.exe" -m price_tracker run >> logs\run.log 2>&1
