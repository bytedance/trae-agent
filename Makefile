.PHONY: help install install-test install-dev test test-cov test-watch pre-commit pre-commit-install pre-commit-run lint format type-check clean

# Default target
help:
	@echo "Available commands:"
	@echo "  install         - Install the package in development mode"
	@echo "  install-test    - Install test dependencies"
	@echo "  install-dev     - Install all dependencies including test and evaluation"
	@echo "  test            - Run tests (skips external service tests)"
	@echo "  pre-commit      - Run pre-commit hooks on all files"
	@echo "  pre-commit-install - Install pre-commit hooks"
	@echo "  pre-commit-run  - Run pre-commit hooks on changed files"
	@echo "  clean           - Clean up build artifacts and cache"

# Installation commands
uv-venv:
	uv venv

uv-sync:
	uv sync --all-extras

uv-pre-commit:
	uv run pre-commit run --all-files

uv-test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true uv run pytest tests/ -v --tb=short --continue-on-collection-errors

# Testing commands
test:
	SKIP_OLLAMA_TEST=true SKIP_OPENROUTER_TEST=true SKIP_GOOGLE_TEST=true pytest

# Pre-commit commands
pre-commit: pre-commit-install pre-commit-run

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

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
