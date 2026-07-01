@echo off
cd /d "%~dp0"

:: Detect System Python executable
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
    pause
    exit /b 1
)

echo Found Python executable: %PYTHON_CMD%

:: Create virtual environment
echo Creating virtual environment in .venv...
%PYTHON_CMD% -m venv .venv
if %errorlevel% neq 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
)

:: Activate virtual environment
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install requirements
if exist requirements.txt (
    echo Installing requirements from requirements.txt...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo Failed to install requirements.
        pause
        exit /b 1
    )
) else (
    echo WARNING: requirements.txt not found!
)

:: Copy .env.example to .env if .env does not exist
if not exist .env (
    if exist .env.example (
        echo Copying .env.example to .env...
        copy .env.example .env
        echo Please edit the .env file with your credentials before running the platform.
    )
)

:: Run check_system.py
if exist check_system.py (
    echo Running diagnostic script check_system.py...
    python check_system.py
    if %errorlevel% neq 0 (
        echo Diagnostic checks failed. Please resolve the errors above.
    )
)

echo.
echo ============================================================
echo Setup Completed Successfully
echo ============================================================
echo.
pause
