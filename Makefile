.DEFAULT_GOAL := help
PY := python

.PHONY: help install dev test cov lint fmt run docker docker-run demo clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	$(PY) -m pip install -e .

dev: ## Install with dev extras
	$(PY) -m pip install -e ".[dev]"

test: ## Run the test suite
	pytest

cov: ## Run tests with a coverage report
	pytest --cov=src/aidoctor --cov-report=term-missing

lint: ## Lint
	ruff check src tests

fmt: ## Format
	ruff format src tests && ruff check --fix src tests

run: ## Serve on :8000
	uvicorn aidoctor.main:app --reload --port 8000

demo: ## Ingest the sample corpus and ask a question
	$(PY) scripts/demo.py

docker: ## Build the image
	docker build -t ai-doctor:local .

docker-run: ## Run the image
	docker run --rm -p 8000:8000 ai-doctor:local

clean: ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
