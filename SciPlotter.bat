@echo off
rem Launch SciPlotter using the project's virtual environment (no console window).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "main.py"
