# auto-bioinfo — developer quality commands (WP-01c / T-01-07).
#
# Single source of truth for lint / format / type-check / unit-test / coverage.
# Every command is repo-native (configured in pyproject.toml) and runs fully
# offline and deterministically — no network, no database, no paid service.
#
# Local use:   make check        (the full local gate)
# CI use:      the dedicated CI workflow WO should invoke these same targets so
#              local and CI commands stay identical (T-01-07 acceptance).
#
# Tooling lives in the `dev` optional-dependency group:  make install
#   ruff      -> lint + format          (required, blocking)
#   mypy      -> static type check      (advisory / non-blocking, see `typecheck`)
#   coverage  -> coverage over unittest (reporting; no hard threshold yet)

# unittest is the canonical runner (matches the held CI step and the protocol).
TEST_CMD := python -m unittest discover -t . -s tests -p "test_*.py"
SRC := auto_bioinfo
LINT_PATHS := auto_bioinfo tests

.PHONY: help install lint format format-check typecheck test coverage check clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-14s %s\n", $$1, $$2}'

install:  ## Install the package with dev tooling (ruff, mypy, coverage, pytest)
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

lint:  ## Lint with ruff (blocking)
	ruff check $(LINT_PATHS)

format:  ## Auto-format with ruff (writes changes)
	ruff format $(LINT_PATHS)

format-check:  ## Verify formatting without writing (blocking)
	ruff format --check $(LINT_PATHS)

typecheck:  ## Static type check with mypy (advisory / non-blocking)
	mypy $(SRC) --ignore-missing-imports || true

test:  ## Run the offline, deterministic unit suite
	$(TEST_CMD)

coverage:  ## Run the suite under coverage and print a report
	coverage run -m unittest discover -t . -s tests -p "test_*.py"
	coverage report

check: lint format-check typecheck test  ## Full local gate (lint + format + type + test)

clean:  ## Remove caches and coverage artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
