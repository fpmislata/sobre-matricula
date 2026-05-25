# ── OS detection ──────────────────────────────────────────────────────────────
ifeq ($(OS),Windows_NT)
    PYTHON  := .venv\Scripts\python.exe
    RMRF    := if exist .coverage del /f .coverage & \
               if exist htmlcov rd /s /q htmlcov & \
               for /d /r . %%d in (__pycache__ .pytest_cache) do @if exist "%%d" rd /s /q "%%d"
    SEP     := \\
else
    PYTHON  := .venv/bin/python
    RMRF    := rm -rf .coverage htmlcov .pytest_cache \
               $$(find . -name '__pycache__' -not -path './.venv/*')
    SEP     := /
endif

PYTEST := $(PYTHON) -m pytest

# ── Targets ───────────────────────────────────────────────────────────────────
.PHONY: test unit integration fast cov clean installer help

.DEFAULT_GOAL := help

## test       Run full test suite
test:
	$(PYTEST) tests/ -v

## unit       Unit tests only (fast, no side effects)
unit:
	$(PYTEST) tests/unit/ -v -m unit

## integration  Integration tests only
integration:
	$(PYTEST) tests/integration/ -v -m integration

## fast       All tests except @slow
fast:
	$(PYTEST) tests/ -v -m "not slow"

## cov        Run full suite with coverage report
cov:
	$(PYTEST) tests/ --cov=modules --cov=utils --cov-report=term-missing --cov-report=html

## clean      Remove coverage, cache, and __pycache__
clean:
	$(RMRF)

## installer  Bump build version and recompile Inno Setup installer (Windows only)
installer:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -ExecutionPolicy Bypass -File build\bump_installer.ps1
else
	@echo "installer: target Windows-only (requires Inno Setup / iscc.exe)" && exit 1
endif

## help       Show this help
help:
	@grep -E '^## ' Makefile | sed 's/^## /  /'
