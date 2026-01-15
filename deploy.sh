#!/bin/bash

# Deployment script for gate.lexapp.co.ua
# This script builds and deploys the container on the remote server

set -e

SERVER="gate.lexapp.co.ua"
REMOTE_USER="${REMOTE_USER:-$(whoami)}"
REMOTE_DIR="${REMOTE_DIR:-~/court-registry-mcp}"
PROJECT_NAME="court-registry-mcp"

echo "=== Deploying to ${SERVER} ==="

# Check if SSH key is available
if [ -z "$SSH_KEY" ]; then
    echo "Using default SSH authentication"
    SSH_BASE="ssh"
    RSYNC_SSH_OPTS=""
else
    echo "Using SSH key: $SSH_KEY"
    SSH_BASE="ssh -i $SSH_KEY"
    RSYNC_SSH_OPTS="-e \"ssh -i $SSH_KEY\""
fi

# Create remote directory if it doesn't exist
echo "Creating remote directory..."
$SSH_BASE ${REMOTE_USER}@${SERVER} "mkdir -p ${REMOTE_DIR}"

# Copy files to server
echo "Copying files to server..."
if [ -z "$SSH_KEY" ]; then
    rsync -avz --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.env' \
        --exclude 'venv' \
        --exclude 'storage' \
        --exclude 'logs' \
        ./ ${REMOTE_USER}@${SERVER}:${REMOTE_DIR}/
else
    rsync -avz -e "ssh -i $SSH_KEY" --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.env' \
        --exclude 'venv' \
        --exclude 'storage' \
        --exclude 'logs' \
        ./ ${REMOTE_USER}@${SERVER}:${REMOTE_DIR}/
fi

# Build and start containers on remote server
echo "Building and starting containers..."
$SSH_BASE ${REMOTE_USER}@${SERVER} << EOF
    set -e
    cd ${REMOTE_DIR}
    
    # Detect docker compose command (docker compose or docker-compose)
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="sudo docker-compose"
    elif docker compose version &> /dev/null; then
        DOCKER_COMPOSE="sudo docker compose"
    else
        echo "Error: docker-compose or docker compose not found"
        exit 1
    fi
    
    # Check if .env exists, if not copy from .env.example
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            echo "Copying .env.example to .env"
            cp .env.example .env
        else
            echo "Warning: .env file not found and .env.example doesn't exist"
        fi
    fi
    
    # Create necessary directories
    mkdir -p storage logs
    
    # Stop existing containers
    echo "Stopping existing containers..."
    \$DOCKER_COMPOSE down --remove-orphans || true
    
    # Clean up outdated Docker resources
    echo "Cleaning up outdated Docker resources..."
    
    # Remove old/unused images (keep last 2 versions)
    echo "Removing old Docker images..."
    # Remove old images for this project
    OLD_IMAGES=\$(sudo docker images | grep ${PROJECT_NAME} | tail -n +3 | awk '{print \$3}')
    if [ ! -z "\$OLD_IMAGES" ]; then
        echo \$OLD_IMAGES | xargs sudo docker rmi -f || true
    fi
    # Also clean up old images by pattern
    DANGLING_IMAGES=\$(sudo docker images --filter "dangling=true" -q)
    if [ ! -z "\$DANGLING_IMAGES" ]; then
        echo \$DANGLING_IMAGES | xargs sudo docker rmi -f || true
    fi
    
    # Remove dangling images
    sudo docker image prune -f || true
    
    # Remove unused volumes (be careful with this - only remove truly unused)
    echo "Removing unused volumes..."
    sudo docker volume prune -f || true
    
    # Remove old containers
    echo "Removing stopped containers..."
    sudo docker container prune -f || true
    
    # Remove old build cache (optional - can be slow)
    # docker builder prune -af || true
    
    # Clean up old source files if needed
    echo "Cleaning up old source files..."
    find . -name "*.pyc" -delete || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.log" -mtime +7 -delete || true
    
    # Build and start containers
    echo "Building containers..."
    \$DOCKER_COMPOSE build --no-cache court-registry-mcp
    
    echo "Starting all containers..."
    \$DOCKER_COMPOSE up -d
    
    # Wait for database to be ready
    echo "Waiting for database to be ready..."
    sleep 10
    
    # Verify database schema
    echo "Verifying database schema..."
    \$DOCKER_COMPOSE exec -T court-registry-mcp python3 verify_db_schema.py || {
        echo "Warning: Database schema verification failed. This may be normal on first deployment."
        echo "The application will attempt to create missing tables on startup."
    }
    
    # Show status
    echo "Container status:"
    \$DOCKER_COMPOSE ps
    
    echo "=== Deployment completed ==="
EOF

echo "Deployment finished successfully!"
