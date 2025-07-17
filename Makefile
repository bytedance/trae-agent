.PHONY: help uv-venv uv-sync install-dev uv-pre-commit uv-test test pre-commit fix-format pre-commit-install pre-commit-run clean

# Default target
help:
	@echo "Available commands:"
	@echo "  install-dev        - Create venv and install all dependencies (recommended for development)"
	@echo "  uv-venv           - Create a Python virtual environment using uv"
	@echo "  uv-sync           - Install all dependencies (including test/evaluation) using uv"
	@echo "  uv-test           - Run all tests (via uv, skips some external service tests)"
	@echo "  test              - Run all tests (skips some external service tests)"
	@echo "  uv-pre-commit     - Run pre-commit hooks on all files (via uv)"
	@echo "  pre-commit-install- Install pre-commit hooks"
	@echo "  pre-commit-run    - Run pre-commit hooks on all files"
	@echo "  pre-commit        - Install and run pre-commit hooks on all files"
	@echo "  fix-format        - Fix formatting errors"
	@echo "  clean             - Clean up build artifacts and cache"

# Installation commands
uv-venv:
	uv venv
uv-sync:
	uv sync --all-extras
install-dev: uv-venv uv-sync

# Pre-commit commands
uv-pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	pre-commit install
pre-commit-run:
	pre-commit run --all-files
pre-commit: pre-commit-install pre-commit-run

# fix formatting error
fix-format:
	ruff format .
	ruff check --fix .

# Testing commands
uv-test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true uv run pytest tests/ -v --tb=short --continue-on-collection-errors
test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true pytest

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
