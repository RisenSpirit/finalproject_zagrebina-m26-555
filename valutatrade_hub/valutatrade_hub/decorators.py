"""Декоратор @log_action — логирование доменных операций."""

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from valutatrade_hub.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


PLAIN_KEYS = {"result", "error_type"}  # без кавычек


def _fmt(key: str, value: Any) -> str:
    if key in PLAIN_KEYS:
        return str(value)
    if key == "rate" and isinstance(value, float):
        return f"{value:.2f}" if value >= 1 else f"{value:.8f}"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, str):
        return repr(value)
    return str(value)


def log_action(action: str, verbose: bool = False) -> Callable:
    """Логировать вызов операции (BUY/SELL/REGISTER/LOGIN) на уровне INFO.

    Поля: action, user, currency, amount, rate, base, result (OK/ERROR),
    error_type/error_message при исключении.
    verbose=True добавляет состояние кошелька «было→стало».
    Исключения не глотаются — после записи в лог пробрасываются дальше.
    """

    def decorator(func: Callable) -> Callable:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind_partial(*args, **kwargs).arguments
            user = bound.get("user")
            username = getattr(user, "username", None) or bound.get("username")
            fields: dict[str, Any] = {"user": username}
            if "currency" in bound:
                fields["currency"] = str(bound["currency"]).upper()
            if "amount" in bound:
                try:
                    fields["amount"] = float(bound["amount"])
                except (TypeError, ValueError):
                    fields["amount"] = bound["amount"]

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                fields["result"] = "ERROR"
                fields["error_type"] = type(exc).__name__
                fields["error_message"] = str(exc)
                logger.info(_line(action, fields))
                raise

            if isinstance(result, dict):
                for key in ("rate", "base"):
                    if key in result:
                        fields[key] = result[key]
                if verbose and "before" in result and "after" in result:
                    fields["wallet"] = f"{result['before']:.4f}→{result['after']:.4f}"
            fields["result"] = "OK"
            logger.info(_line(action, fields))
            return result

        return wrapper

    return decorator


def _line(action: str, fields: dict[str, Any]) -> str:
    parts = [action] + [f"{k}={_fmt(k, v)}" for k, v in fields.items() if v is not None]
    return " ".join(parts)
