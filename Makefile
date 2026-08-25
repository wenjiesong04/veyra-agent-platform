PYTHON ?= /opt/anaconda3/envs/veyra-agent-platform/bin/python
PIP := $(PYTHON) -m pip
RUFF := $(PYTHON) -m ruff
MYPY := $(PYTHON) -m mypy
PYTEST := $(PYTHON) -m pytest
ALEMBIC := $(PYTHON) -m alembic
RUNTIME_LOCK := requirements/runtime-py311.txt
DEV_LOCK := requirements/dev-py311.txt
LOCKFILE ?= $(DEV_LOCK)
LOCK_OPTIONS := --generate-hashes --reuse-hashes --no-emit-index-url --no-emit-trusted-host --no-emit-options --allow-unsafe --strip-extras

.PHONY: install verify-environment format format-check lint typecheck test \
	install-runtime lock-refresh dependency-check dependency-lock-check \
	dependency-lock-refresh check \
	migrate-local migrate-community migrations

install: verify-environment
	$(PIP) install --require-hashes --requirement $(DEV_LOCK)
	$(PIP) install --no-deps --no-build-isolation --editable .

install-runtime: verify-environment
	$(PIP) install --require-hashes --requirement $(RUNTIME_LOCK)
	$(PIP) install --no-deps --no-build-isolation --editable .

verify-environment:
	@$(PYTHON) -c 'import os, sys; from pathlib import Path; legacy = Path("/opt/anaconda3/envs/veyra").resolve(); prefix = Path(sys.prefix).resolve(); assert sys.version_info[:2] == (3, 11), f"Python 3.11 required, got {sys.version.split()[0]}"; assert prefix != legacy, f"legacy veyra environment is forbidden: {prefix}"; assert not os.environ.get("PYTHONPATH"), "PYTHONPATH must be unset"; print(f"python={sys.version.split()[0]} executable={sys.executable} prefix={prefix}")'

format:
	$(RUFF) format backend tests scripts

format-check:
	$(RUFF) format --check backend tests scripts

lint:
	$(RUFF) check backend tests scripts

typecheck:
	$(MYPY)

test:
	$(PYTEST)

dependency-check:
	$(PIP) check

dependency-lock-check:
	$(PYTHON) scripts/check_lock.py --lock $(LOCKFILE) --kind $(if $(findstring dev,$(notdir $(LOCKFILE))),dev,runtime)

lock-refresh:
	$(PYTHON) -m piptools compile $(LOCK_OPTIONS) --output-file $(RUNTIME_LOCK) pyproject.toml requirements/build.in
	$(PYTHON) -m piptools compile $(LOCK_OPTIONS) --extra dev --output-file $(DEV_LOCK) pyproject.toml requirements/build.in

dependency-lock-refresh: lock-refresh

check: verify-environment dependency-check dependency-lock-check format-check lint typecheck test

migrate-local:
	$(ALEMBIC) -c backend/migrations/local/alembic.ini upgrade head

migrate-community:
	$(ALEMBIC) -c backend/migrations/community/alembic.ini upgrade head

migrations: migrate-local migrate-community
