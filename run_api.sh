#!/bin/bash

# run_api.sh - Simple script to run the Social Media Recommendation API

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "╔════════════════════════════════════════════════════════╗"
echo "║   Social Media API - Posts & Reels Recommendations    ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Check if .env exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠ Warning: .env file not found!"
    echo "Creating .env file..."
    cat > "$PROJECT_DIR/.env" << 'EOF'
# Database Configuration
DB_HOST=36.253.137.34
DB_PORT=5436
DB_NAME=social_db
DB_USER=innovator_user
DB_PASSWORD=Nep@tronix9335%

# ====================== MEDIA ======================
MEDIA_BASE_URL=http://36.253.137.34:8006

# ====================== OPTIONAL (defaults are fine) ======================
EMBED_MODEL=sentence-transformers/paraphrase-MiniLM-L3-v2
W_CONTENT=0.30
W_TRENDING=0.20
W_RANDOM=0.10
W_COLLABORATIVE=0.40
EOF
    echo "✓ .env file created"
fi

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "✗ Python not found. Please install Python 3.8+"
    exit 1
fi

PYTHON_CMD=$(command -v python3 || command -v python)
echo "✓ Using Python: $PYTHON_CMD"

# Check if virtual env exists
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$PROJECT_DIR/venv"
    source "$PROJECT_DIR/venv/bin/activate"
    echo "✓ Virtual environment created"
    
    echo ""
    echo "Installing dependencies (this may take a few minutes)..."
    pip install -q -r "$PROJECT_DIR/requirements.txt"
    echo "✓ Dependencies installed"
else
    source "$PROJECT_DIR/venv/bin/activate"
    echo "✓ Virtual environment activated"
fi

echo ""
echo "────────────────────────────────────────────────────────"
echo ""

# Parse command line arguments
MODE="${1:-dev}"
PORT="${2:-8000}"

if [ "$MODE" = "prod" ]; then
    echo "Starting API in PRODUCTION mode on port $PORT..."
    echo ""
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:$PORT \
        --access-logfile - \
        --error-logfile - \
        main:app
elif [ "$MODE" = "test" ]; then
    echo "Running tests..."
    $PYTHON_CMD test_api.py "${3:-}"
elif [ "$MODE" = "debug" ]; then
    echo "Starting API in DEBUG mode on port $PORT..."
    echo ""
    uvicorn main:app --host 0.0.0.0 --port $PORT --reload --log-level debug
else
    echo "Starting API in DEVELOPMENT mode on port $PORT..."
    echo ""
    echo "API Documentation: http://localhost:$PORT/docs"
    echo "Health Check: http://localhost:$PORT/health"
    echo ""
    echo "To get recommendations, use:"
    echo "  curl \"http://localhost:$PORT/suggestions/<user_id>?top_n=10\""
    echo ""
    echo "Stop the server with Ctrl+C"
    echo ""
    
    uvicorn main:app --host 0.0.0.0 --port $PORT --reload
fi
