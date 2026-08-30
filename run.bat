@echo off
rem Launcher: uses the project venv python (system "python" is the Store stub, silent no-op)
cd /d %~dp0
.venv\Scripts\python.exe planner.py %*
if errorlevel 1 pause
