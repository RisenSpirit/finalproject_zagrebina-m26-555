.PHONY: install project build publish package-install lint format

install:
	uv sync

project:
	uv run project

build:
	uv build

publish:
	uv publish --dry-run --token dry-run

package-install:
	uv tool install --force $(lastword $(wildcard dist/*.whl))

lint:
	uv run ruff check .

format:
	uv run ruff format .