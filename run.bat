@echo off
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.10 or later.
    pause
    exit /b 1
)

echo Checking dependencies...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo Failed to install dependencies. Check your Python/pip setup.
    pause
    exit /b 1
)

echo Starting Noc Clicker...
python main.py
if errorlevel 1 (
    echo.
    echo Noc Clicker exited with an error. See above for details.
    pause
)
