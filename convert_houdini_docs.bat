@echo off
echo Starting Houdini Native Docs conversion...
cd /d "%~dp0"

IF NOT EXIST .venv\Scripts\python.exe (
    echo Error: Virtual environment not found. Please run install_dependencies.bat or setup venv first.
    pause
    exit /b
)

.\.venv\Scripts\python.exe scripts\python\rag\convert_houdini_docs.py
echo Houdini docs conversion complete!
pause
