SHELL := /bin/zsh

# Project and tooling
PROJECT_NAME ?= option-data-collector
PY ?= python3
VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
DOCKER ?= docker
DOCKER_COMPOSE ?= docker compose
IMAGE ?= $(PROJECT_NAME):latest
API_URL ?= http://127.0.0.1:8080

# Load environment from .env for local runs (DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT)
ENV_EXPORT := set -a; [ -f .env ] && . ./.env; set +a;

.DEFAULT_GOAL := help

# Run each recipe in a single shell so here-docs work across lines
.ONESHELL:

.PHONY: help venv install dev-install clean clean-venv fresh-start check-imports \
	run-api run-etl run-sentiment run-scraper run-scraper-once test-greeks test-score test-all \
	lint format format-check test test-smoke \
	docker-build docker-up docker-logs docker-logs-ts docker-up-logs docker-down docker-restart docker-clean \
	docker-wait-api docker-health docker-test-api docker-test \
	docker-etl-up docker-etl-logs docker-etl-down

help: ## Show this help
	@echo "Available targets:" && \
	grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS=":.*?## "} {printf "  %-20s %s\n", $$1, $$2}'

# -----------------------------
# Python environment
# -----------------------------
venv: ## Create local virtualenv (.venv)
	@if [ ! -d "$(VENV)" ]; then \
		$(PY) -m venv $(VENV); \
		$(PIP) install -U pip setuptools wheel; \
	fi

install: venv ## Install Python dependencies
	$(PIP) install -r requirements.txt

dev-install: venv ## Install dev tools (pytest, ruff, black)
	@if [ -f requirements-dev.txt ]; then \
		$(PIP) install -r requirements-dev.txt; \
	else \
		$(PIP) install pytest ruff black; \
	fi

clean: ## Remove caches and build artifacts
	find . -name '__pycache__' -type d -exec rm -rf {} + || true
	find . -type f -name '*.py[co]' -delete || true
	rm -rf .pytest_cache .mypy_cache .coverage dist build || true

clean-venv: ## Remove virtualenv (.venv)
	rm -rf $(VENV)

fresh-start: clean clean-venv install ## Clean repo and reinstall deps into a fresh venv

check-imports: venv ## Quick import test of core modules
	printf '%s\n' \
	"import importlib, sys" \
	"mods = ['app.api.routes','app.etl.fd_overview_scraper','app.etl.fd_options_scraper','app.etl.daily_etl','app.etl.sentiment_tracker','app.etl.beursduivel_scraper','app.compute.option_greeks','app.compute.compute_option_score','app.utils.helpers','app.db']" \
	"ok = True" \
	"for m in mods:" \
	"    try:" \
	"        importlib.import_module(m)" \
	"        print(f'OK: {m}')" \
	"    except Exception as e:" \
	"        ok = False" \
	"        print(f'FAIL: {m} -> {e}')" \
	"sys.exit(0 if ok else 1)" | $(PYTHON) -

# -----------------------------
# Quick-run helpers (local)
# -----------------------------
run-api: venv ## Run the API locally (Ctrl+C to stop)
	$(ENV_EXPORT) $(PYTHON) -m app.api.routes

run-etl: venv ## Run the daily ETL once
	$(ENV_EXPORT) $(PYTHON) -m app.etl.daily_etl

run-sentiment: venv ## Fetch and store sentiment once
	$(ENV_EXPORT) $(PYTHON) -m app.etl.sentiment_tracker

run-scraper: venv ## Run the live Beursduivel scraper (15min intervals during market hours, Ctrl+C to stop)
	$(ENV_EXPORT) $(PYTHON) -m app.etl.beursduivel_scraper --continuous

run-scraper-once: venv ## Run a single Beursduivel scrape iteration
	$(ENV_EXPORT) $(PYTHON) -c "from app.etl.beursduivel_scraper import run_once; run_once()"

test-greeks: venv ## Compute Greeks for latest missing days
	$(ENV_EXPORT) $(PYTHON) -c "from app.compute.option_greeks import compute_greeks_for_day; compute_greeks_for_day('AD.AS'); print('Greeks computed for AD.AS')"

test-score: venv ## Compute option scores incrementally
	$(ENV_EXPORT) $(PYTHON) -c "from app.compute.compute_option_score import compute_option_score; compute_option_score('AD.AS'); print('Scores computed for AD.AS')"

test-all: ## Run import check, greeks, scores, and one scraper pass
	$(MAKE) check-imports
	$(MAKE) test-greeks
	$(MAKE) test-score
	$(MAKE) run-scraper-once

# -----------------------------
# Linting, formatting, testing
# -----------------------------
lint: dev-install ## Run ruff (lint + import order)
	$(VENV)/bin/ruff check .

format: dev-install ## Format with black (source + tests only)
	$(VENV)/bin/black app tests

format-check: dev-install ## Check formatting (black --check)
	$(VENV)/bin/black --check app tests

test: dev-install ## Run pytest (all tests)
	$(VENV)/bin/pytest -q

test-smoke: dev-install ## Run only smoke tests
	$(VENV)/bin/pytest -q -k smoke

# -----------------------------
# Docker workflow
# -----------------------------
docker-build: ## Build Docker image for the project
	$(DOCKER) build -t $(IMAGE) .

docker-up: ## Start services with Docker Compose (also builds if needed)
	$(DOCKER_COMPOSE) up -d
	$(MAKE) docker-wait-api

docker-logs: ## Tail service logs
	$(DOCKER_COMPOSE) logs -f --tail=100

docker-logs-ts: ## Tail service logs with timestamps
	$(DOCKER_COMPOSE) logs -f --tail=200 --timestamps

docker-up-logs: ## Start services and immediately tail all logs (timestamps)
	$(DOCKER_COMPOSE) up -d
	$(DOCKER_COMPOSE) logs -f --tail=200 --timestamps

docker-down: ## Stop and remove services
	$(DOCKER_COMPOSE) down

docker-restart: docker-down docker-up ## Restart services

docker-clean: docker-down ## Remove built image and prune dangling images
	-$(DOCKER) rmi $(IMAGE) || true
	-$(DOCKER) image prune -f || true

# -----------------------------
# Docker health checks
# -----------------------------
docker-wait-api: ## Wait for API to become healthy (timeout ~60s)
	if ! which curl >/dev/null 2>&1; then echo "curl not available; skipping wait"; exit 0; fi
	for i in {1..60}; do \
	  if curl -fsS $(API_URL)/api/status >/dev/null 2>&1; then \
	    echo "API is up at $(API_URL)"; exit 0; \
	  fi; \
	  sleep 1; \
	done; \
	echo "API did not become ready in time"; exit 1

docker-health: ## Print API status JSON (fails if not reachable)
	@if which curl >/dev/null 2>&1; then \
	  curl -fsS $(API_URL)/api/status | sed 's/.*/API status: &/'; \
	else \
	  echo "curl not available"; exit 1; \
	fi

docker-test-api: ## Hit common endpoints to smoke-test the API
	@if which curl >/dev/null 2>&1; then \
	  set -e; \
	  echo "GET $(API_URL)/api/status"; curl -fsS $(API_URL)/api/status | head -c 200; echo; \
	  echo "GET $(API_URL)/api/latest"; curl -fsS $(API_URL)/api/latest | head -c 200; echo; \
	  echo "GET $(API_URL)/api/contracts"; curl -fsS $(API_URL)/api/contracts | head -c 200; echo; \
	  echo "GET $(API_URL)/api/sentiment/AD.AS"; curl -fsS $(API_URL)/api/sentiment/AD.AS | head -c 200; echo; \
	else \
	  echo "curl not available"; exit 1; \
	fi

docker-test: ## Bring up stack and run API health checks
	$(MAKE) docker-up
	$(MAKE) docker-health
	$(MAKE) docker-test-api

# -----------------------------
# Docker: ETL-only compose (runs once)
# -----------------------------
.PHONY: docker-etl-up docker-etl-logs docker-etl-down
docker-etl-up: ## Build and run only the daily ETL container once (exits when done)
	$(DOCKER_COMPOSE) -f deploy/docker-compose.etl.yml up --build --abort-on-container-exit

docker-etl-logs: ## Show logs from the ETL-only compose
	$(DOCKER_COMPOSE) -f deploy/docker-compose.etl.yml logs --tail=200 -f

docker-etl-down: ## Stop and remove the ETL-only compose
	$(DOCKER_COMPOSE) -f deploy/docker-compose.etl.yml down
# -----------------------------
# Portainer/local stack test (prebuilt image)
# -----------------------------
.PHONY: docker-up-portainer docker-down-portainer
docker-up-portainer: ## Start services using the Portainer stack file (pulls GHCR image)
	$(DOCKER_COMPOSE) -f deploy/portainer-stack.yml up -d

docker-down-portainer: ## Stop services from the Portainer stack file
	$(DOCKER_COMPOSE) -f deploy/portainer-stack.yml down
