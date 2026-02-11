#!/usr/bin/env bash
# Create .venv, install package with dev deps, run tests.
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -v
