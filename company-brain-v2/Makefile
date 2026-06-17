.DEFAULT_GOAL := help
.PHONY: help install format lint typecheck test run-api clean

# Use uv if available, otherwise fall back to pip/python from the active venv.
UV := $(shell command -v uv 2>/dev/null)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the project and dev dependencies
ifdef UV
	uv pip install -e ".[dev]"
else
	python -m pip install -e ".[dev]"
endif

format: ## Auto-format the codebase with ruff
	ruff format app tests
	ruff check --fix app tests

lint: ## Lint the codebase with ruff (no changes)
	ruff check app tests
	ruff format --check app tests

typecheck: ## Run static type checking with mypy
	mypy app

test: ## Run the test suite
	pytest

run-api: ## Run the FastAPI app locally with reload
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

clean: ## Remove caches and build artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
