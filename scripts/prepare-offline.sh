#!/bin/bash

# Pre-download Python packages for offline Synology deployment
echo "📦 Pre-downloading Python packages for offline deployment..."

# Create wheels directory
mkdir -p wheels

# Download all requirements as wheels (offline installation)
echo "🔽 Downloading packages..."
pip download -r requirements.txt -d wheels/ --prefer-binary

echo "📋 Creating offline requirements..."
# Create a simple requirements list for offline install
pip freeze > requirements.offline.txt

echo "✅ Packages ready for offline deployment!"
echo "📝 Files created:"
echo "  - wheels/ directory with .whl files"
echo "  - requirements.offline.txt"
echo ""
echo "🚀 Now run: git add . && git commit -m 'Add offline packages' && git push"
echo "📤 Then deploy on Synology with offline mode"