@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "BUILDER=%~dp0builder.py"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
set "RESULT=0"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo Project folder could not be opened: %PROJECT_DIR%
    set "RESULT=1"
    goto finish
)

if exist "%VENV_PYTHON%" goto run_venv

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%BUILDER%" %*
    set "RESULT=%ERRORLEVEL%"
    goto finish
)

where python >nul 2>nul
if errorlevel 1 (
    echo Python 3 was not found. Install Python or create the project .venv.
    set "RESULT=9009"
    goto finish
)

python "%BUILDER%" %*
set "RESULT=%ERRORLEVEL%"
goto finish

:run_venv
"%VENV_PYTHON%" "%BUILDER%" %*
set "RESULT=%ERRORLEVEL%"

:finish
if "%RESULT%"=="0" (
    echo KDP Builder completed successfully.
) else (
    echo KDP Builder failed with error code %RESULT%. Review the error above.
)
echo Press any key to close this window.
pause >nul
endlocal & exit /b %RESULT%