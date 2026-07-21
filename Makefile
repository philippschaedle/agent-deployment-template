.PHONY: install lint format typecheck validate pre-commit help

help:
	@echo ""
	@echo "agent-deployment-template — available targets"
	@echo ""
	@echo "  install     Install dev dependencies for the template repo"
	@echo "  lint        Lint hooks/ with ruff"
	@echo "  format      Format hooks/ with ruff"
	@echo "  typecheck   Type-check hooks/ with pyright"
	@echo "  validate    Generate a test project and run its lint + unit + integration tests"
	@echo "  pre-commit  Run all pre-commit hooks on all files"
	@echo ""

install:
	uv sync

lint:
	uv run ruff check hooks/

format:
	uv run ruff format hooks/

typecheck:
	uv run pyright hooks/

validate:
	@echo "Generating test project from template..."
	rm -rf /tmp/cc-validate
	cookiecutter . --no-input \
		--output-dir /tmp/cc-validate \
		project_name="Test Agent" \
		author_email="test@example.com" \
		gcp_project_id="test-project-123"
	@echo "Running lint and tests in generated project..."
	cd /tmp/cc-validate/test-agent && uv sync --frozen
	cd /tmp/cc-validate/test-agent && uv run ruff check .
	cd /tmp/cc-validate/test-agent && uv run pytest tests/unit -v --no-cov
	cd /tmp/cc-validate/test-agent && uv run pytest tests/integration -v --tb=short --no-cov
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo ""; \
		echo "Building container image..."; \
		docker build -t cc-validate-test-agent:latest /tmp/cc-validate/test-agent; \
		echo "Smoke-testing container entrypoint..."; \
		docker run --rm cc-validate-test-agent:latest python -m agent --help; \
		docker rmi cc-validate-test-agent:latest >/dev/null; \
	else \
		echo ""; \
		echo "WARNING: Docker not available — skipping container build validation."; \
	fi
	@echo ""
	@echo "Template validation passed."
	rm -rf /tmp/cc-validate

pre-commit:
	uv run pre-commit run --all-files
