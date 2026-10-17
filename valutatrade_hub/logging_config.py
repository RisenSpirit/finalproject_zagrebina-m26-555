"""Настройка логирования.

Формат: человекочитаемая строка
    INFO 2025-10-09T12:05:22 BUY user='alice' currency='BTC' amount=0.0500 ...
Файлы:
- logs/actions.log — доменные операции (buy/sell/register/login);
- logs/parser.log  — работа Parser Service (запросы к API, обновления).
Ротация: по размеру (RotatingFileHandler), log_max_bytes / log_backup_count.
Уровень: INFO по умолчанию, DEBUG — через log_level в [tool.valutatrade].
"""

import logging
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import PROJECT_ROOT, SettingsLoader

LOGGER_NAME = "valutatrade.actions"
PARSER_LOGGER_NAME = "valutatrade.parser"


def _configure(name: str, file_name: str) -> logging.Logger:
    settings = SettingsLoader()
    logger = logging.getLogger(name)
    if logger.handlers:  # уже настроен
        return logger

    log_path = PROJECT_ROOT / settings.get("log_dir") / file_name
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(settings.get("log_format"), datefmt="%Y-%m-%dT%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(settings.get("log_level", "INFO").upper())
    logger.propagate = False  # не дублировать в консоль
    return logger


def setup_logging() -> logging.Logger:
    """Настроить логгеры actions и parser (вызывается один раз)."""
    settings = SettingsLoader()
    _configure(PARSER_LOGGER_NAME, settings.get("parser_log_file"))
    return _configure(LOGGER_NAME, settings.get("log_file"))
