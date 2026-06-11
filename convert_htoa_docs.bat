@echo off
echo Starting HToA Documentation Converter...
cd /d "%~dp0"

IF NOT EXIST .venv\Scripts\python.exe (
    echo Error: Virtual environment not found. Please run install_dependencies.bat or setup venv first.
    pause
    exit /b
)

.\.venv\Scripts\python.exe scripts\python\rag\convert_htoa_docs.py
pause
