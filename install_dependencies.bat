@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================================
echo Installing Houdini-LLM Dependencies
echo ========================================================
echo.

echo [INFO] Auto-detecting Houdini installation...
set "HOUDINI_BASE=C:\Program Files\Side Effects Software"
set "HYTHON_CMD="

if exist "%HOUDINI_BASE%" (
    for /f "delims=" %%D in ('dir /b /ad /o-n "%HOUDINI_BASE%\Houdini *" 2^>nul') do (
        if exist "%HOUDINI_BASE%\%%D\bin\hython.exe" (
            set "HYTHON_CMD=%HOUDINI_BASE%\%%D\bin\hython.exe"
            echo [INFO] Found Houdini: %%D
            goto RUN_INSTALL
        )
    )
)

echo.
echo [ERROR] Could not find Houdini automatically.
echo Please run this script from the "Houdini Command Line Tools".
pause
exit /b 1

:RUN_INSTALL
echo.
echo Running dependency installation...
"%HYTHON_CMD%" -m pip install --upgrade -r requirements.txt --target=python_libs

if %ERRORLEVEL% GEQ 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
) else (
    echo.
    echo [SUCCESS] Dependencies installed into 'python_libs' successfully!
)

pause
