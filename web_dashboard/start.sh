#!/bin/bash
# Navigate to the script's directory
cd "$(dirname "$0")"

echo "🕷️ Starting Spooder Web Dashboard..."

# 1. Start the WebSocket hardware controller
python3 server.py &
BACKEND_PID=$!

# 2. Start the HTTP Web Server on port 8080
python3 -m http.server 8080 --directory public &
FRONTEND_PID=$!

echo "----------------------------------------"
echo "🚀 Dashboard is now running!"
echo "👉 Local UI: http://localhost:8080"
echo "👉 WebSocket Backend: ws://localhost:8765"
echo "----------------------------------------"
echo "Press [Ctrl+C] to stop both servers."

# Clean up processes on Ctrl+C
cleanup() {
    echo -e "\n🛑 Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "Goodbye!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for both processes to finish
wait
