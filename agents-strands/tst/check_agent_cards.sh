#!/bin/bash

# Check agent cards for local deployments

set -e

echo "🔍 Checking Agent Cards..."
echo "================================"

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "⚠️  Warning: jq not installed. Output will not be formatted."
    JQ_CMD="cat"
else
    JQ_CMD="jq ."
fi

echo ""
echo "📋 Travel Assistant Agent Card:"
echo "--------------------------------"
if curl -s http://localhost:9001/.well-known/agent-card.json | $JQ_CMD; then
    echo "✅ Travel Assistant agent card retrieved"
else
    echo "❌ Failed to retrieve Travel Assistant agent card"
    echo "   Is the agent running on port 9001?"
fi

echo ""
echo "📋 Flight Booking Agent Card:"
echo "--------------------------------"
if curl -s http://localhost:9002/.well-known/agent-card.json | $JQ_CMD; then
    echo "✅ Flight Booking agent card retrieved"
else
    echo "❌ Failed to retrieve Flight Booking agent card"
    echo "   Is the agent running on port 9002?"
fi

echo ""
echo "================================"
