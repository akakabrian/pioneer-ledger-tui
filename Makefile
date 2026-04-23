.PHONY: all venv run test test-only clean

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

clean:
	rm -rf oregon_trail_tui/__pycache__ tests/__pycache__ tests/out/*.svg
