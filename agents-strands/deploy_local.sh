#!/bin/bash

set -e

echo "🔐 Validating AWS credentials..."

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "❌ Error: AWS credentials not found in environment variables"
    echo "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
    exit 1
fi

# Validate credentials are not expired by making a simple AWS call
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ Error: AWS credentials are invalid or expired"
    echo "Please refresh your credentials and try again"
    exit 1
fi

echo "✅ AWS credentials validated"

echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.local.yml down

echo "🔨 Building images..."

# Copy dependency files to .tmp directories for build
echo "📋 Copying dependency files to .tmp directories..."
mkdir -p src/flight-booking-agent/.tmp src/travel-assistant-agent/.tmp
cp pyproject.toml uv.lock src/flight-booking-agent/.tmp/
cp pyproject.toml uv.lock src/travel-assistant-agent/.tmp/

# Build images
docker-compose -f docker-compose.local.yml build --no-cache

# Clean up .tmp directories
echo "🧹 Cleaning up .tmp directories..."
rm -rf src/flight-booking-agent/.tmp
rm -rf src/travel-assistant-agent/.tmp

echo "🚀 Starting containers..."
docker-compose -f docker-compose.local.yml up -d

echo "✅ Deployment complete!"
echo "📊 Check status with: docker-compose -f docker-compose.local.yml ps"
echo "📝 View logs with: docker-compose -f docker-compose.local.yml logs -f"
