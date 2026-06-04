.PHONY: install dev lint format typecheck test test-unit eval \
        deploy-dev deploy-prod logs traces setup-gcp pre-commit clean help

help:
	@echo ""
	@echo "{{cookiecutter.project_name}} — available targets"
	@echo ""
	@echo "  install      Install all dependencies with uv"
	@echo "  dev          Run agent locally via adk web UI (http://localhost:8000)"
	@echo "  lint         Run ruff lint check"
	@echo "  format       Run ruff formatter"
	@echo "  typecheck    Run pyright type checker"
	@echo "  test         Run all unit tests with coverage"
	@echo "  test-unit    Run unit tests only"
	@echo "  eval         Run promptfoo red-team evaluation"
	@echo "  deploy-dev   Deploy to Agent Engine (dev)"
	@echo "  deploy-prod  Deploy to Agent Engine (prod)"
	@echo "  logs         Stream Cloud Logging output for this agent"
	@echo "  traces       Open Cloud Trace in browser"
	@echo "  setup-gcp    One-time GCP project bootstrap"
	@echo "  pre-commit   Run all pre-commit hooks on all files"
	@echo "  clean        Remove build artefacts and caches"
	@echo ""

install:
	uv sync

dev:
	uv run adk web

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run pyright

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit -v

eval:
	uv run python tests/evals/run_eval.py

deploy-dev:
	uv run python deployment/deploy.py --env dev

deploy-prod:
	uv run python deployment/deploy.py --env prod

logs:
	bash deployment/scripts/read_logs.sh

traces:
	bash deployment/scripts/read_traces.sh

setup-gcp:
	bash deployment/scripts/setup_gcp.sh

pre-commit:
	uv run pre-commit run --all-files

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov .mypy_cache
