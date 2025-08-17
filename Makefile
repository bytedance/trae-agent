.PHONY: help uv-venv uv-sync install-dev install-api uv-pre-commit uv-test test test-api pre-commit fix-format fix-format-api check-api pre-commit-install pre-commit-run run-api clean

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "Installation:"
	@echo "  install-dev        - Create venv and install all dependencies (recommended for development)"
	@echo "  install-api        - Install API dependencies"
	@echo "  uv-venv           - Create a Python virtual environment using uv"
	@echo "  uv-sync           - Install all dependencies (including test/evaluation) using uv"
	@echo ""
	@echo "Testing:"
	@echo "  uv-test           - Run all tests (via uv, skips some external service tests)"
	@echo "  test              - Run all tests (skips some external service tests)"
	@echo "  test-api          - Run API-specific tests"
	@echo "  test-one          - Run single integration test with Gemini"
	@echo ""
	@echo "Code Quality:"
	@echo "  uv-pre-commit     - Run pre-commit hooks on all files (via uv)"
	@echo "  pre-commit-install- Install pre-commit hooks"
	@echo "  pre-commit-run    - Run pre-commit hooks on all files"
	@echo "  pre-commit        - Install and run pre-commit hooks on all files"
	@echo "  fix-format        - Fix formatting errors"
	@echo "  fix-format-api    - Fix formatting errors for API code"
	@echo "  check-api         - Run all API code quality checks"
	@echo ""
	@echo "API:"
	@echo "  run-api           - Install dependencies and run the API server"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean             - Clean up build artifacts and cache"

# Installation commands
uv-venv:
	uv venv
uv-sync:
	uv sync --all-extras
install-dev: uv-venv uv-sync
install-api:
	uv sync --extra trae_api

# Pre-commit commands
uv-pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	pre-commit install
pre-commit-run:
	pre-commit run --all-files
pre-commit: pre-commit-install pre-commit-run

# Code Quality commands
fix-format:
	ruff format .
	ruff check --fix .
fix-format-api:
	uv run ruff format trae_api
	uv run ruff check --fix --unsafe-fixes trae_api
check-type-api: fix-format-api
	@echo "Running type check on API code..."
	uv run mypy trae_api
	@echo "API code quality checks completed!"

# Testing commands
uv-test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true uv run pytest tests/ -v --tb=short --continue-on-collection-errors
test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true uv run pytest
test-api:
	uv run pytest tests/api

# Unit tests only (fast, no external dependencies)
test-unit:
	@echo "Running unit tests..."
	TRAE_API_ENVIRONMENT=pytest uv run pytest tests/api/agent/unit/ tests/api/unit/ -v --tb=short

# Integration tests (uses test fixtures/mocks, no real API calls)
test-integration:
	@echo "Running integration tests..."
	TRAE_API_ENVIRONMENT=pytest uv run pytest tests/api/agent/integration/ tests/api/integration/ -v --tb=short -m "not e2e"

# E2E tests (makes real API calls)
test-e2e:
	@echo "Running E2E tests..."
	TRAE_API_ENVIRONMENT=pytest uv run pytest tests/api/e2e/ -v --tb=short

# Run all API tests
test-all:
	@echo "Running all API tests..."
	TRAE_API_ENVIRONMENT=pytest uv run pytest tests/api/ -v --tb=short

# Placeholder for current test being worked on
test-one:
	@echo "Running current test (e2e API test)..."
	python test_e2e_api.py

# API commands
run-api: uv-sync
	@echo "Starting API server..."
	uv run python -m trae_api

# Clean up
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
