@echo off
echo =======================================================
echo Houdini-LLM RAG Vector Database Builder
echo =======================================================
echo.
echo Launching Knowledge Base Ingestion Pipeline...
echo This process will generate vector embeddings for the 
echo official Houdini documentation.
echo.

set PYTHONUNBUFFERED=1
".venv\Scripts\python.exe" "scripts\python\rag\ingest.py"

echo.
echo =======================================================
echo Task complete.
echo If you saw no errors, the database is successfully built!
echo =======================================================
pause
