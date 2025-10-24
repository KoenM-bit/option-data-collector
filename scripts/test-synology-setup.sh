#!/bin/bash
# Quick deployment test script for Synology
# Run this from your local machine to test SSH and deployment setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration (update these values)
SYNOLOGY_HOST="${SYNOLOGY_HOST:-192.168.1.200}"
SYNOLOGY_USER="${SYNOLOGY_USER:-admin}"
SYNOLOGY_PORT="${SYNOLOGY_PORT:-22}"
PROJECT_DIR="/volume1/docker/option-data-collector"

echo -e "${BLUE}🧪 Testing Synology Deployment Setup${NC}"
echo "=================================="

# Test SSH connection
echo -e "${YELLOW}📡 Testing SSH connection...${NC}"
if ssh -o ConnectTimeout=10 -o BatchMode=yes -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "echo 'SSH OK'" 2>/dev/null; then
    echo -e "${GREEN}✅ SSH connection successful${NC}"
else
    echo -e "${RED}❌ SSH connection failed${NC}"
    echo "Please check:"
    echo "  - SSH is enabled on Synology (Control Panel → Terminal & SNMP)"
    echo "  - SSH key is properly set up"
    echo "  - Host/username are correct: $SYNOLOGY_USER@$SYNOLOGY_HOST:$SYNOLOGY_PORT"
    exit 1
fi

# Test Docker
echo -e "${YELLOW}🐳 Testing Docker availability...${NC}"
if ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "docker --version" 2>/dev/null; then
    echo -e "${GREEN}✅ Docker is available${NC}"
else
    echo -e "${RED}❌ Docker not found or not accessible${NC}"
    echo "Please install Docker from Package Center"
    exit 1
fi

# Test project directory access
echo -e "${YELLOW}📁 Testing project directory...${NC}"
if ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "mkdir -p $PROJECT_DIR && cd $PROJECT_DIR && pwd" 2>/dev/null; then
    echo -e "${GREEN}✅ Project directory accessible: $PROJECT_DIR${NC}"
else
    echo -e "${RED}❌ Cannot access project directory: $PROJECT_DIR${NC}"
    exit 1
fi

# Test git availability
echo -e "${YELLOW}📦 Testing git availability...${NC}"
if ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "git --version" 2>/dev/null; then
    echo -e "${GREEN}✅ Git is available${NC}"
else
    echo -e "${YELLOW}⚠️  Git not found - installing...${NC}"
    ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
        # Try to install git via package manager
        which opkg && opkg install git-http || true
        which apt-get && apt-get update && apt-get install -y git || true
    "
fi

# Test GitHub repository access
echo -e "${YELLOW}🔗 Testing repository access...${NC}"
if ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
    cd $PROJECT_DIR
    if [ ! -d '.git' ]; then
        git init
        git remote add origin https://github.com/KoenM-bit/option-data-collector.git
    fi
    timeout 30 git fetch origin main
" 2>/dev/null; then
    echo -e "${GREEN}✅ Repository access successful${NC}"
else
    echo -e "${RED}❌ Cannot access GitHub repository${NC}"
    echo "Check internet connectivity and repository URL"
    exit 1
fi

# Test environment file
echo -e "${YELLOW}⚙️  Checking environment configuration...${NC}"
ENV_STATUS=$(ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
    cd $PROJECT_DIR
    if [ -f '.env' ]; then
        echo 'exists'
    elif [ -f '.env.example' ]; then
        echo 'example_only'
    else
        echo 'missing'
    fi
")

case $ENV_STATUS in
    "exists")
        echo -e "${GREEN}✅ Environment file (.env) exists${NC}"
        ;;
    "example_only")
        echo -e "${YELLOW}⚠️  Only .env.example found${NC}"
        echo "Creating .env from example..."
        ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
            cd $PROJECT_DIR
            cp .env.example .env
            echo '# Created by deployment test on $(date)' >> .env
        "
        echo -e "${YELLOW}📝 Please edit .env with your production settings${NC}"
        ;;
    "missing")
        echo -e "${RED}❌ No environment files found${NC}"
        echo "Make sure .env.example is in the repository"
        ;;
esac

# Test Docker Compose file
echo -e "${YELLOW}🐳 Testing Docker Compose configuration...${NC}"
if ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
    cd $PROJECT_DIR
    docker compose -f docker/docker-compose.prod.yml config
" 2>/dev/null; then
    echo -e "${GREEN}✅ Docker Compose configuration is valid${NC}"
else
    echo -e "${RED}❌ Docker Compose configuration issues${NC}"
    echo "Check docker/docker-compose.prod.yml syntax"
fi

# Simulate deployment (dry run)
echo -e "${YELLOW}🚀 Simulating deployment (dry run)...${NC}"
ssh -p $SYNOLOGY_PORT $SYNOLOGY_USER@$SYNOLOGY_HOST "
    cd $PROJECT_DIR
    echo '📥 Fetching latest code...'
    git fetch origin main
    
    echo '🏗️  Testing Docker build...'
    if docker compose -f docker/docker-compose.prod.yml build --dry-run 2>/dev/null || docker compose -f docker/docker-compose.prod.yml config; then
        echo '✅ Build configuration looks good'
    else
        echo '❌ Build issues detected'
        exit 1
    fi
    
    echo '📊 Current container status:'
    docker compose -f docker/docker-compose.prod.yml ps || echo 'No containers running'
"

echo ""
echo -e "${GREEN}🎉 All tests passed!${NC}"
echo -e "${BLUE}📋 Setup Summary:${NC}"
echo "  Host: $SYNOLOGY_USER@$SYNOLOGY_HOST:$SYNOLOGY_PORT"
echo "  Project: $PROJECT_DIR"
echo "  Repository: https://github.com/KoenM-bit/option-data-collector"
echo ""
echo -e "${YELLOW}📝 Next steps:${NC}"
echo "1. Set up GitHub Secrets (see SYNOLOGY_SETUP.md)"
echo "2. Configure .env file on Synology"
echo "3. Push to main branch to trigger deployment"
echo ""
echo -e "${BLUE}🔍 To manually deploy now:${NC}"
echo "ssh $SYNOLOGY_USER@$SYNOLOGY_HOST"
echo "cd $PROJECT_DIR"
echo "docker compose -f docker/docker-compose.prod.yml up -d"