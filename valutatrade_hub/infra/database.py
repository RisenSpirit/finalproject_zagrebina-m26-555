"""DatabaseManager — Singleton-абстракция над JSON-хранилищем."""

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from valutatrade_hub.infra.settings import SettingsLoader

# логическое имя таблицы → (ключ настройки с именем файла, пустое значение)
TABLES: dict[str, tuple[str, Any]] = {
    "users": ("users_file", []),
    "portfolios": ("portfolios_file", []),
    "rates": ("rates_file", {}),
}


class DatabaseManager:
    """Чтение/запись JSON-файлов. Singleton через __new__ (как SettingsLoader)."""

    _instance: "DatabaseManager | None" = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = SettingsLoader()
            instance._lock = threading.RLock()
            cls._instance = instance
        return cls._instance

    def _path(self, table: str) -> Path:
        if table not in TABLES:
            raise KeyError(f"Неизвестная таблица '{table}'")
        return self._settings.data_file(TABLES[table][0])

    def _empty(self, table: str) -> Any:
        empty = TABLES[table][1]
        return type(empty)()

    def read(self, table: str) -> Any:
        """Прочитать таблицу. Нет файла / пустой / битый → пустое значение."""
        path = self._path(table)
        with self._lock:
            try:
                with open(path, encoding="utf-8-sig") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return self._empty(table)

    def write(self, table: str, data: Any) -> None:
        """Атомарная запись: во временный файл, затем замена."""
        path = self._path(table)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    def update(self, table: str, func: Callable[[Any], Any]) -> Any:
        """Безопасная операция чтение → модификация → запись.

        func получает текущие данные и возвращает новые.
        Если func бросает исключение, файл не меняется.
        """
        with self._lock:
            data = self.read(table)
            new_data = func(data)
            self.write(table, new_data)
            return new_data
