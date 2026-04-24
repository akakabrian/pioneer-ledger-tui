.PHONY: all venv run test test-only playtest perf clean

all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python oregon_trail.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

playtest: venv
	.venv/bin/python -m tests.playtest

perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf pioneer_ledger_tui/__pycache__ tests/__pycache__ tests/out/*.svg
