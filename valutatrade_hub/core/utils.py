"""Вспомогательные функции: валидация и конвертация."""

from typing import Any

from valutatrade_hub.core.currencies import get_currency


def validate_currency_code(code: Any) -> str:
    """Проверить код валюты по реестру. Неизвестный → CurrencyNotFoundError."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")
    return get_currency(code).code


def validate_amount(value: Any) -> float:
    """Сумма: число > 0."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return amount


def convert(amount: float, from_rate_usd: float, to_rate_usd: float) -> float:
    """Перевести amount из валюты A в валюту B через курсы к USD."""
    return amount * from_rate_usd / to_rate_usd
