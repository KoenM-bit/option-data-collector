#!/bin/bash
# Comprehensive code quality and formatting script

set -e

echo "🔧 Professional Code Quality Pipeline"
echo "=================================="

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use virtual environment binaries
VENV_BIN="$PROJECT_ROOT/venv/bin"

echo ""
echo "🖤 1. Formatting with Black..."
"$VENV_BIN/black" . --line-length 88

echo ""
echo "📦 2. Sorting imports with isort..."  
"$VENV_BIN/isort" . --profile black

echo ""
echo "🔍 3. Linting with flake8..."
"$VENV_BIN/flake8" . || echo "⚠️ Flake8 found issues (see above)"

echo ""
echo "🔧 4. Advanced linting with pylint..."
"$VENV_BIN/pylint" src/ --rcfile=pylint.rc || echo "⚠️ Pylint found issues (see above)"

echo ""
echo "📊 5. Type checking with mypy..."
"$VENV_BIN/mypy" src/ --config-file=mypy.ini || echo "⚠️ MyPy found issues (see above)"

echo ""
echo "🔒 6. Security scanning with bandit..."
"$VENV_BIN/bandit" -r src/ -ll || echo "⚠️ Bandit found security issues (see above)"

echo ""
echo "🛡️ 7. Vulnerability check with safety..."
"$VENV_BIN/safety" check || echo "⚠️ Safety found vulnerabilities (see above)"

echo ""
echo "✅ Code quality pipeline completed!"
echo "   Files have been formatted and checked."
echo "   Review any warnings above before committing."