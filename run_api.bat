@echo off
REM run_api.bat - Simple script to run the Social Media Recommendation API on Windows

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
set "MODE=%1"
set "PORT=%2"

if "%MODE%"=="" (
    set "MODE=dev"
)
if "%PORT%"=="" (
    set "PORT=8000"
)

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║   Social Media API - Posts ^& Reels Recommendations    ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Check if .env exists
if not exist "%PROJECT_DIR%.env" (
    echo ⚠ Warning: .env file not found!
    echo Creating .env file...
    (
        echo # Database Configuration
        echo DB_HOST=36.253.137.34
        echo DB_PORT=5436
        echo DB_NAME=social_db
        echo DB_USER=innovator_user
        echo DB_PASSWORD=Nep@tronix9335%%
        echo.
        echo # ====================== MEDIA ======================
        echo MEDIA_BASE_URL=http://36.253.137.34:8006
        echo.
        echo # ====================== OPTIONAL (defaults are fine) ======================
        echo EMBED_MODEL=sentence-transformers/paraphrase-MiniLM-L3-v2
        echo W_CONTENT=0.30
        echo W_TRENDING=0.20
        echo W_RANDOM=0.10
        echo W_COLLABORATIVE=0.40
    ) > "%PROJECT_DIR%.env"
    echo ✓ .env file created
)

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ✗ Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set "PYTHON_VER=%%i"
echo ✓ Using Python: %PYTHON_VER%

REM Check if virtual env exists
if not exist "%PROJECT_DIR%venv" (
    echo Creating virtual environment...
    python -m venv "%PROJECT_DIR%venv"
    call "%PROJECT_DIR%venv\Scripts\activate.bat"
    echo ✓ Virtual environment created
    
    echo.
    echo Installing dependencies (this may take a few minutes)...
    pip install -q -r "%PROJECT_DIR%requirements.txt"
    if errorlevel 1 (
        echo ✗ Failed to install dependencies
        pause
        exit /b 1
    )
    echo ✓ Dependencies installed
) else (
    call "%PROJECT_DIR%venv\Scripts\activate.bat"
    echo ✓ Virtual environment activated
)

echo.
echo ────────────────────────────────────────────────────────
echo.

if "%MODE%"=="prod" (
    echo Starting API in PRODUCTION mode on port %PORT%...
    echo.
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker ^
        --bind 0.0.0.0:%PORT% ^
        --access-logfile - ^
        --error-logfile - ^
        main:app
) else if "%MODE%"=="test" (
    echo Running tests...
    python test_api.py %3
) else if "%MODE%"=="debug" (
    echo Starting API in DEBUG mode on port %PORT%...
    echo.
    uvicorn main:app --host 0.0.0.0 --port %PORT% --reload --log-level debug
) else (
    echo Starting API in DEVELOPMENT mode on port %PORT%...
    echo.
    echo API Documentation: http://localhost:%PORT%/docs
    echo Health Check: http://localhost:%PORT%/health
    echo.
    echo To get recommendations, use:
    echo   curl "http://localhost:%PORT%/suggestions/^<user_id^>?top_n=10"
    echo.
    echo Stop the server with Ctrl+C
    echo.
    
    uvicorn main:app --host 0.0.0.0 --port %PORT% --reload
)

endlocal
