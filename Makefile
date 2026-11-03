SHELL := /bin/bash
.DEFAULT_GOAL := help

VENV := .venv
PY := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
PORT ?= 8000
HOST ?= 127.0.0.1

.PHONY: help install run dev test docker docker-down clean clean-all

help: ## Show this help
	@printf '\nSeoul Velo\n\n'
	@printf '  make install   Create the Python 3.12 environment and check the dataset\n'
	@printf '  make run       Serve the app at http://localhost:%s\n' "$(PORT)"
	@printf '  make dev       Serve with auto-reload\n'
	@printf '  make test      Run the test suite\n'
	@printf '  make docker    Build and run everything in Docker\n'
	@printf '  make docker-down  Stop the Docker container\n'
	@printf '  make clean     Remove caches\n'
	@printf '  make clean-all Remove caches and .venv\n\n'

install:
	@bash install.sh

$(UVICORN):
	@printf '\nNo .venv found. Run make install first.\n\n'
	@exit 1

run: $(UVICORN)
	@$(UVICORN) app.main:app --host "$(HOST)" --port "$(PORT)"

dev: $(UVICORN)
	@$(UVICORN) app.main:app --host "$(HOST)" --port "$(PORT)" --reload

$(PYTEST):
	@printf '\nNo test environment found. Run make install first.\n\n'
	@exit 1

test: $(PYTEST)
	@$(PYTEST)

docker:
	@command -v docker >/dev/null 2>&1 || { printf '\nDocker is not installed. See https://docs.docker.com/get-docker/\n\n'; exit 1; }
	@docker compose up --build

docker-down:
	@command -v docker >/dev/null 2>&1 || { printf '\nDocker is not installed.\n\n'; exit 1; }
	@docker compose down

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} +
	@rm -rf .pytest_cache .ruff_cache .cache
	@printf 'Caches removed.\n'

clean-all: clean
	@rm -rf .venv
	@printf 'Environment removed.\n'
