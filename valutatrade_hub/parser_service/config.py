"""Конфигурация Parser Service.

API-ключ ExchangeRate-API НЕ хранится в коде. Он берётся:
1) из переменной окружения EXCHANGERATE_API_KEY, или
2) из файла .env в корне проекта (строка EXCHANGERATE_API_KEY=...).
Файл .env добавлен в .gitignore.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.infra.settings import PROJECT_ROOT, SettingsLoader

ENV_FILE = PROJECT_ROOT / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    """Простой разбор .env: KEY=VALUE, строки с # игнорируются."""
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


def get_secret(name: str) -> str | None:
    """Секрет из переменной окружения или файла .env."""
    return os.getenv(name) or _read_env_file(ENV_FILE).get(name)


def _data_path(key: str) -> str:
    return str(SettingsLoader().data_file(key))


@dataclass
class ParserConfig:
    # Ключ загружается из окружения / .env (не из кода)
    """Настройки Parser Service: ключ, URL, списки валют, пути, таймаут."""

    EXCHANGERATE_API_KEY: str | None = field(
        default_factory=lambda: get_secret("EXCHANGERATE_API_KEY")
    )

    # Эндпоинты
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    # Списки валют
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")
    # dict — изменяемый тип, поэтому через default_factory
    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    # Пути
    RATES_FILE_PATH: str = field(default_factory=lambda: _data_path("rates_file"))
    HISTORY_FILE_PATH: str = field(default_factory=lambda: _data_path("history_file"))

    # Сетевые параметры
    REQUEST_TIMEOUT: int = 10

    # Планировщик: интервал автообновления, секунд
    UPDATE_INTERVAL: int = 300
