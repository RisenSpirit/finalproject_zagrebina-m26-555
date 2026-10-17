"""Точка входа: python main.py запускает CLI ValutaTrade Hub."""

from valutatrade_hub.cli.interface import run_cli


def main() -> None:
    """Запустить интерактивный CLI."""
    run_cli()


if __name__ == "__main__":
    main()
