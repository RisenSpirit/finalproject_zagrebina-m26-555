install:
	uv sync

project:
	uv run finalproject-zagrebina-m26-555

build:
	uv build

lint:
	uv run ruff check .