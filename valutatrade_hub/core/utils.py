"""Вспомогательные функции: пути, JSON, валидация."""

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
PORTFOLIOS_FILE = DATA_DIR / "portfolios.json"
RATES_FILE = DATA_DIR / "rates.json"


def load_json(path: Path, default: Any) -> Any:
    """Прочитать JSON. Если файла нет или он пуст/битый — вернуть default."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    """Записать JSON (создаёт папку при необходимости)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def validate_currency_code(code: str) -> str:
    """Код валюты: непустая строка, приводится к верхнему регистру."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")
    code = code.strip().upper()
    if not code.isalpha():
        raise ValueError(f"Некорректный код валюты '{code}'")
    return code


def validate_amount(value: Any) -> float:
    """Сумма: число > 0."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount
