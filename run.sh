#!/bin/bash

# AI Trading System - Run Script

echo "=================================="
echo "AI Trading System"
echo "=================================="

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Start the FastAPI server
echo "Starting server..."
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

