#!/bin/bash  
# Quick format-only script for development

set -e

echo "🎨 Quick Code Formatting"
echo "======================"

# Install dev dependencies if needed  
pip install black isort 2>/dev/null || echo "Dependencies already installed"

echo ""
echo "🖤 Formatting with Black..."
black . --line-length 88

echo ""
echo "📦 Sorting imports with isort..."
isort . --profile black

echo ""
echo "✅ Code formatted successfully!"
echo "   Files are now properly formatted and ready to commit."