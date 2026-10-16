"""Планировщик периодического обновления курсов.

Запуск из терминала (Ctrl+C — остановить):
    uv run python -m valutatrade_hub.parser_service.scheduler --interval 300
"""

import argparse
import logging
import threading

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME, setup_logging
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger(PARSER_LOGGER_NAME)


class RatesScheduler:
    """Периодический запуск RatesUpdater с заданным интервалом."""

    def __init__(
        self, updater: RatesUpdater | None = None, interval: int | None = None
    ) -> None:
        self.updater = updater or RatesUpdater()
        self.interval = interval or ParserConfig().UPDATE_INTERVAL
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> None:
        """Выполнить одно обновление и вывести итог."""
        try:
            result = self.updater.run_update()
            print(
                f"[scheduler] обновлено курсов: {result.total}, "
                f"ошибок: {len(result.errors)}, время: {result.last_refresh}"
            )
        except ApiRequestError as exc:
            logger.error("Scheduled update failed: %s", exc)
            print(f"[scheduler] {exc}")

    def run_forever(self) -> None:
        """Обновлять каждые interval секунд, пока не вызван stop()."""
        logger.info("Scheduler started, interval=%ss", self.interval)
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval)
        logger.info("Scheduler stopped")

    def start(self) -> None:
        """Запустить в фоновом потоке."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Остановить цикл обновлений."""
        self._stop.set()


def main() -> None:
    """Запуск планировщика из командной строки."""
    parser = argparse.ArgumentParser(description="Периодическое обновление курсов")
    parser.add_argument("--interval", type=int, default=None, help="секунды")
    args = parser.parse_args()
    setup_logging()
    scheduler = RatesScheduler(interval=args.interval)
    print(f"Планировщик запущен, интервал {scheduler.interval} с. Ctrl+C — стоп.")
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        scheduler.stop()
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
