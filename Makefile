# Needs `make` (macOS/Linux). On Windows just double-click run.bat instead.
PY ?= python3

.PHONY: setup dev test

setup:
	$(PY) -m venv .venv
	.venv/bin/pip install -r requirements.txt

dev: setup
	.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	.venv/bin/python -m pytest -q
