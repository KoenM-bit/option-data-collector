#!/bin/bash
echo "🚀 Deploying to Synology..."

# Run tests first
./scripts/test.sh

if [ $? -eq 0 ]; then
    echo "✅ Tests passed, proceeding with deployment..."
    
    # Copy files to Synology (adjust IP and path as needed)
    SYNOLOGY_IP="192.168.1.200"  # Your Synology IP
    SYNOLOGY_PATH="/volume1/docker/option-api"
    
    echo "📁 Syncing files to Synology..."
    rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          ./ $SYNOLOGY_IP:$SYNOLOGY_PATH/
    
    # Restart containers on Synology
    echo "🔄 Restarting containers..."
    ssh $SYNOLOGY_IP "cd $SYNOLOGY_PATH && docker compose -f docker compose.prod.yml down && docker compose -f docker compose.prod.yml up -d"
    
    echo "✅ Deployment complete!"
    echo "📊 Check status: ssh $SYNOLOGY_IP 'cd $SYNOLOGY_PATH && docker compose -f docker compose.prod.yml ps'"
else
    echo "❌ Tests failed, deployment aborted"
    exit 1
fi