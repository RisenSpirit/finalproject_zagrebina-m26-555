"""Хранилище Parser Service.

- data/exchange_rates.json — история замеров (список записей, id уникален);
- data/rates.json — снимок последних курсов для Core Service.
Запись атомарная через DatabaseManager (временный файл → замена).
"""

from datetime import UTC, datetime
from typing import Any

from valutatrade_hub.infra.database import DatabaseManager


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(value: str) -> datetime | None:
    """ISO-строка → datetime с часовым поясом (без пояса считаем UTC)."""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def make_record(
    pair: str, rate: float, timestamp: str, source: str, meta: dict[str, Any]
) -> dict[str, Any]:
    from_code, to_code = pair.split("_", 1)
    return {
        "id": f"{pair}_{timestamp}",
        "from_currency": from_code,
        "to_currency": to_code,
        "rate": rate,
        "timestamp": timestamp,
        "source": source,
        "meta": meta,
    }


class RatesStorage:
    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db or DatabaseManager()

    # ---------- история ----------
    def append_history(self, records: list[dict[str, Any]]) -> int:
        """Добавить записи без дублей по id. Вернуть число добавленных."""
        added = 0

        def merge(history: list[dict]) -> list[dict]:
            nonlocal added
            known = {r.get("id") for r in history}
            new = [r for r in records if r["id"] not in known]
            added = len(new)
            return [*history, *new]

        self.db.update("history", merge)
        return added

    def read_history(self) -> list[dict[str, Any]]:
        return self.db.read("history")

    # ---------- снимок ----------
    def save_snapshot(
        self, pairs: dict[str, dict[str, Any]], last_refresh: str
    ) -> dict[str, Any]:
        """Обновить rates.json. Для пары побеждает более свежий updated_at."""

        def merge(cache: dict) -> dict:
            current = cache.get("pairs", {}) if isinstance(cache, dict) else {}
            merged = dict(current)
            for pair, entry in pairs.items():
                old = current.get(pair)
                old_ts = parse_ts(old.get("updated_at", "")) if old else None
                new_ts = parse_ts(entry["updated_at"])
                if old_ts is None or (new_ts and new_ts >= old_ts):
                    merged[pair] = entry
            return {"pairs": merged, "last_refresh": last_refresh}

        return self.db.update("rates", merge)

    def read_snapshot(self) -> dict[str, Any]:
        data = self.db.read("rates")
        return data if isinstance(data, dict) else {}
