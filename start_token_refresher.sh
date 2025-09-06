#!/bin/bash

# Token Refresher Launcher Script
# This script starts the OAuth token refresher service in the background

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_REFRESHER_SCRIPT="$SCRIPT_DIR/credentials-provider/token_refresher.py"

# Configuration
CHECK_INTERVAL=${TOKEN_REFRESH_INTERVAL:-300}  # 5 minutes default
EXPIRY_BUFFER=${TOKEN_EXPIRY_BUFFER:-3600}     # 1 hour default

# Log file location
LOG_FILE="$SCRIPT_DIR/token_refresher.log"

echo "Starting OAuth Token Refresher Service..."
echo "Check interval: ${CHECK_INTERVAL} seconds"
echo "Expiry buffer: ${EXPIRY_BUFFER} seconds"
echo "Log file: ${LOG_FILE}"

# Check if token refresher is already running
if pgrep -f "token_refresher.py" > /dev/null; then
    echo "WARNING: Token refresher service appears to be already running"
    echo "Existing processes:"
    pgrep -fl "token_refresher.py"
    
    read -p "Kill existing processes and restart? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Killing existing token refresher processes..."
        pkill -f "token_refresher.py" || true
        sleep 2
    else
        echo "ERROR: Aborted - token refresher service already running"
        exit 1
    fi
fi

# Start the token refresher service in background
echo "Starting token refresher service..."
nohup uv run python "$TOKEN_REFRESHER_SCRIPT" \
    --interval "$CHECK_INTERVAL" \
    --buffer "$EXPIRY_BUFFER" \
    > "$LOG_FILE" 2>&1 &

TOKEN_REFRESHER_PID=$!
echo "Token refresher service started with PID: $TOKEN_REFRESHER_PID"

# Wait a moment and check if it's still running
sleep 2
if kill -0 "$TOKEN_REFRESHER_PID" 2>/dev/null; then
    echo "Service is running successfully"
    echo "Monitor logs with: tail -f $LOG_FILE"
    echo "Stop service with: pkill -f token_refresher.py"
else
    echo "ERROR: Service failed to start - check logs:"
    tail "$LOG_FILE"
    exit 1
fi

# Show first few lines of output
echo ""
echo "Recent log output:"
echo "===================="
tail -n 10 "$LOG_FILE" || echo "No log output yet"