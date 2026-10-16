"""Настройка логирования.

Формат: человекочитаемая строка
    INFO 2025-10-09T12:05:22 BUY user='alice' currency='BTC' amount=0.0500 ...
Ротация: по размеру (RotatingFileHandler), log_max_bytes / log_backup_count.
Уровень: INFO по умолчанию, DEBUG — через log_level в [tool.valutatrade].
"""

import logging
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade.actions"


def setup_logging() -> logging.Logger:
    settings = SettingsLoader()
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:  # уже настроен
        return logger

    log_path = settings.log_path
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
