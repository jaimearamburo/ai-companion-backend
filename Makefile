# Common tasks. Run `make` or `make help` to list them.
# Every target runs through uv, so it uses the exact tool versions in uv.lock.

.DEFAULT_GOAL := help
.PHONY: help install lint format test check eval

help: ## List the available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install all dependencies and the git pre-commit hooks
	uv sync --all-groups
	uv run pre-commit install

lint: ## Lint, check formatting and type-check (the same checks CI runs)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format: ## Format the code and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

test: ## Run the test suite with coverage
	uv run pytest

check: lint test ## Everything CI checks on the code

eval: ## Run the evaluation suite (not built yet)
	@echo "The eval harness does not exist yet; it arrives in PLAN.md step S5." >&2
	@exit 1
