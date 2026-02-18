#!/bin/bash
# Run the Personal Assistant backend API and macOS menu bar app together
# Usage: ./run-dev.sh

set -e

echo "🚀 Starting Personal Assistant (API + macOS Menu Bar)"
echo "=================================================="

# Kill any existing processes on cleanup
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    pkill -f "pa server" 2>/dev/null || true
    pkill -f "pa macos-menu" 2>/dev/null || true
    wait
}

trap cleanup EXIT INT TERM

# Start API server in background
echo "Starting API server on http://localhost:8000..."
pa server &
API_PID=$!
echo "API server PID: $API_PID"

# Wait for API to be ready
echo "Waiting for API to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✓ API server is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "✗ API server failed to start"
        exit 1
    fi
    sleep 1
done

# Start macOS menu bar app in background
echo ""
echo "Starting macOS menu bar application..."
pa macos-menu &
MENU_PID=$!
echo "Menu app PID: $MENU_PID"

echo ""
echo "✓ All services started!"
echo ""
echo "Endpoints:"
echo "  API Dashboard: http://localhost:8000/docs"
echo "  API Health: http://localhost:8000/api/health"
echo ""
echo "Running processes:"
echo "  API Server (PID: $API_PID)"
echo "  Menu App (PID: $MENU_PID)"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for both processes
wait
