"""SettingsLoader — единственная точка конфигурации (Singleton).

Источник: секция [tool.valutatrade] в pyproject.toml (если есть),
иначе значения по умолчанию из DEFAULTS.

Ключи:
- data_dir               папка с JSON-файлами
- users_file / portfolios_file / rates_file   имена файлов в data_dir
- rates_ttl_seconds      сколько секунд курс в rates.json считается свежим
- default_base_currency  базовая валюта по умолчанию
- log_dir / log_file     куда писать лог операций
- log_level              INFO (по умолчанию) или DEBUG
- log_format             формат строки лога (logging)
- log_max_bytes / log_backup_count   ротация по размеру
"""

import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULTS: dict[str, Any] = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_dir": "logs",
    "log_file": "actions.log",
    "log_level": "INFO",
    "log_format": "%(levelname)s %(asctime)s %(message)s",
    "log_max_bytes": 1_000_000,
    "log_backup_count": 3,
}

_MISSING = object()


class SettingsLoader:
    """Singleton через __new__.

    Выбран __new__, а не метакласс: так проще и читабельнее — вся логика
    в одном классе, без дополнительной «магии». Экземпляр хранится
    в атрибуте класса, поэтому повторные SettingsLoader() и импорты
    из разных модулей возвращают один и тот же объект.
    """

    _instance: "SettingsLoader | None" = None

    def __new__(cls) -> "SettingsLoader":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._config = {}
            instance._load()
            cls._instance = instance
        return cls._instance

    def _load(self) -> None:
        config = dict(DEFAULTS)
        pyproject = PROJECT_ROOT / "pyproject.toml"
        try:
            with open(pyproject, "rb") as f:
                section = tomllib.load(f).get("tool", {}).get("valutatrade", {})
            config.update(section)
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            pass
        self._config = config

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key in self._config:
            return self._config[key]
        if default is _MISSING:
            raise KeyError(f"Нет настройки '{key}'")
        return default

    def reload(self) -> None:
        """Перечитать конфигурацию."""
        self._load()

    # удобные пути
    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / self.get("data_dir")

    def data_file(self, key: str) -> Path:
        """key: 'users_file' | 'portfolios_file' | 'rates_file'."""
        return self.data_dir / self.get(key)

    @property
    def log_path(self) -> Path:
        return PROJECT_ROOT / self.get("log_dir") / self.get("log_file")
