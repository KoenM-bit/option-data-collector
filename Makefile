# Professional Options Data Collector - Development Commands

.PHONY: help install install-dev format lint test test-cov clean docker-build docker-test

help: ## Show available commands
	@echo "🏢 Professional Options Data Collector"
	@echo "======================================"
	@echo "Available commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install production dependencies
	@echo "📦 Installing production dependencies..."
	@./venv/bin/pip install -r requirements.txt

install-dev: ## Install development dependencies
	@echo "🛠️ Installing development dependencies..."
	@./venv/bin/pip install -r requirements.txt
	@./venv/bin/pip install -r requirements-dev.txt
	@echo "✅ Development environment ready!"

format: ## Format code with Black and isort
	@echo "🎨 Formatting code..."
	@./venv/bin/black . --line-length 88
	@./venv/bin/isort . --profile black
	@echo "✅ Code formatted!"

lint: ## Run all linting and quality checks
	@echo "🔍 Running comprehensive code quality checks..."
	@./scripts/lint.sh

test: ## Run tests
	@echo "🧪 Running tests..."
	@./venv/bin/pytest tests/ -v

test-cov: ## Run tests with coverage report
	@echo "📊 Running tests with coverage..."
	@./venv/bin/pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

clean: ## Clean temporary files and artifacts
	@echo "🧹 Cleaning temporary files..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .mypy_cache .coverage htmlcov/ bandit-report.json
	@echo "✅ Cleaned!"

docker-build: ## Build Docker image
	@echo "🐳 Building Docker image..."
	@docker build -f docker/Dockerfile -t option-collector:latest .

docker-test: ## Test Docker image functionality
	@echo "🔬 Testing Docker image..."
	@docker run --rm option-collector:latest python -c "import src.services.option_service; print('✅ Docker image works!')"

pre-commit: ## Install pre-commit hooks
	@echo "🪝 Installing pre-commit hooks..."
	@./venv/bin/pre-commit install
	@echo "✅ Pre-commit hooks installed!"

ci-local: ## Run full CI pipeline locally
	@echo "🚀 Running full CI pipeline locally..."
	@make format
	@make lint
	@make test-cov
	@make docker-build
	@make docker-test
	@echo "✅ Local CI pipeline completed!"

# Development shortcuts
dev-setup: install-dev pre-commit ## Full development environment setup
	@echo "🎯 Development environment ready!"
	@echo "   Run 'make help' to see available commands"
	@echo "   Run 'make ci-local' to test everything locally"

# Quick quality check
quick-check: format lint ## Quick format and lint check
	@echo "⚡ Quick quality check completed!"