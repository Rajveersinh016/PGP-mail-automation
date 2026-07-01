@echo off

:: 1. Locate project directory and change to it
cd /d "%~dp0"

:: 2. Check if virtual environment is present and activate it
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

:: 3. Detect Python executable
set PYTHON_CMD=

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto python_found
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto python_found
)

where python3 >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python3
    goto python_found
)

:python_found
if "%PYTHON_CMD%"=="" (
    echo Python is not installed.
    echo Please install Python 3.11 or later.
    
    :: Pause if double-clicked (launched manually from explorer)
    echo %CMDCMDLINE% | findstr /i "explorer.exe" >nul
    if %errorlevel% equ 0 (
        pause
    )
    exit /b 1
)

:: 4. Execute main.py
echo Executing Container Glass Intelligence Platform...
%PYTHON_CMD% main.py
set EXIT_CODE=%errorlevel%

:: 5. Display success/failure message
if %EXIT_CODE% equ 0 (
    echo.
    echo ============================================================
    echo SUCCESS: Platform execution completed successfully.
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo FAILURE: Platform execution failed with exit code %EXIT_CODE%.
    echo ============================================================
)

:: 6. Pause before closing if launched manually (double-clicked)
echo %CMDCMDLINE% | findstr /i "explorer.exe" >nul
if %errorlevel% equ 0 (
    echo Press any key to exit...
    pause >nul
)

exit /b %EXIT_CODE%
