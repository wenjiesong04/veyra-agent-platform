PYTHON ?= python
PIP := $(PYTHON) -m pip
RUFF := $(PYTHON) -m ruff
MYPY := $(PYTHON) -m mypy
PYTEST := $(PYTHON) -m pytest
ALEMBIC := $(PYTHON) -m alembic
CONSTRAINTS := requirements/constraints-py311.txt

.PHONY: install format format-check lint typecheck test dependency-check \
	check migrate-local migrate-community migrations

install:
	$(PIP) install --constraint $(CONSTRAINTS) --editable '.[dev]'

format:
	$(RUFF) format backend tests

format-check:
	$(RUFF) format --check backend tests

lint:
	$(RUFF) check backend tests

typecheck:
	$(MYPY)

test:
	$(PYTEST)

dependency-check:
	$(PIP) check

check: dependency-check format-check lint typecheck test

migrate-local:
	$(ALEMBIC) -c backend/migrations/local/alembic.ini upgrade head

migrate-community:
	$(ALEMBIC) -c backend/migrations/community/alembic.ini upgrade head

migrations: migrate-local migrate-community
