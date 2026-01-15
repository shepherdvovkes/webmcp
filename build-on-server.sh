#!/bin/bash

# Script to be run directly on the server
# Usage: Copy this file to the server and run it

set -e

REMOTE_DIR="${REMOTE_DIR:-/opt/court-registry-mcp}"

echo "=== Building container on server ==="

cd ${REMOTE_DIR} || {
    echo "Error: Directory ${REMOTE_DIR} not found"
    exit 1
}

# Check if .env exists
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Copying .env.example to .env"
        cp .env.example .env
        echo "Please edit .env file with your configuration"
    else
        echo "Error: .env file not found and .env.example doesn't exist"
        exit 1
    fi
fi

# Create necessary directories
mkdir -p storage logs

# Stop existing containers
echo "Stopping existing containers..."
docker-compose down || true

# Build containers
echo "Building containers..."
docker-compose build --no-cache

# Start containers
echo "Starting containers..."
docker-compose up -d

# Show status
echo ""
echo "=== Container status ==="
docker-compose ps

echo ""
echo "=== Logs (last 50 lines) ==="
docker-compose logs --tail=50

echo ""
echo "=== Build completed successfully ==="
