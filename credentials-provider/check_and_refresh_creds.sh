#!/bin/bash

# Script to check JWT token validity and refresh credentials only if needed
# Usage: ./scripts/check_and_refresh_creds.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if token is valid using Python
echo "Checking token validity..."
TOKEN_VALID=$(cd "$PROJECT_ROOT" && python3 -c "
import sys
import os
sys.path.append('cli')
from mcp_utils import _load_oauth_token_from_file
import time

try:
    token_data = _load_oauth_token_from_file()
    if token_data and 'expires_at' in token_data:
        current_time = time.time()
        expires_at = token_data['expires_at']
        # Add 60 second buffer to avoid edge cases
        if current_time < (expires_at - 60):
            print('valid')
        else:
            print('expired')
    else:
        print('missing')
except Exception:
    print('missing')
")

if [ "$TOKEN_VALID" = "valid" ]; then
    echo "Token is still valid, skipping credential generation"
    exit 0
elif [ "$TOKEN_VALID" = "expired" ]; then
    echo "Token has expired, generating fresh credentials..."
else
    echo "No valid token found, generating fresh credentials..."
fi

# Generate fresh credentials
echo "Running credential generation..."
cd "$PROJECT_ROOT"
./credentials-provider/generate_creds.sh

echo "Credentials refreshed successfully"
