#!/bin/bash

# Setup script for Synology deployment
echo "🔧 Setting up environment for Synology deployment..."

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file with your database credentials:"
    echo "   DB_USER=your_actual_db_username"
    echo "   DB_PASSWORD=your_actual_db_password" 
    echo ""
    echo "Edit .env now? (y/n)"
    read -r response
    if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
        if command -v nano &> /dev/null; then
            nano .env
        elif command -v vi &> /dev/null; then
            vi .env
        else
            echo "Please manually edit .env file with your database credentials"
        fi
    fi
else
    echo "✅ .env file already exists"
fi

# Check if required variables are set
echo ""
echo "🔍 Checking environment configuration..."
if grep -q "your_db_user" .env 2>/dev/null; then
    echo "⚠️  Warning: DB_USER still contains placeholder value"
fi

if grep -q "your_secure_password" .env 2>/dev/null; then
    echo "⚠️  Warning: DB_PASSWORD still contains placeholder value"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Now run deployment:"
echo "   ./emergency-deploy.sh --portainer"
echo ""