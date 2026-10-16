"""RatesUpdater — координация обновления курсов из всех источников."""

import logging
from dataclasses import dataclass, field

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import (
    RatesStorage,
    make_record,
    utc_now_iso,
)

logger = logging.getLogger(PARSER_LOGGER_NAME)


@dataclass
class UpdateResult:
    total: int = 0
    last_refresh: str = ""
    ok: list[tuple[str, int]] = field(default_factory=list)  # (source, count)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (source, msg)
    # по порядку опроса: (source, count или None, сообщение об ошибке или None)
    steps: list[tuple[str, int | None, str | None]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class RatesUpdater:
    def __init__(
        self,
        clients: list[BaseApiClient] | None = None,
        storage: RatesStorage | None = None,
        config: ParserConfig | None = None,
    ) -> None:
        self.config = config or ParserConfig()
        self.clients = clients or [
            CoinGeckoClient(self.config),
            ExchangeRateApiClient(self.config),
        ]
        self.storage = storage or RatesStorage()

    def run_update(self, source: str | None = None) -> UpdateResult:
        """Опросить клиентов, объединить курсы, сохранить историю и снимок.

        source — 'coingecko' / 'exchangerate' или None (все).
        Падение одного клиента не останавливает остальных.
        Если не ответил ни один — ApiRequestError.
        """
        clients = self.clients
        if source:
            source = source.lower()
            clients = [c for c in self.clients if c.name == source]
            if not clients:
                names = ", ".join(c.name for c in self.clients)
                raise ValueError(f"Неизвестный источник '{source}'. Доступно: {names}")

        logger.info("Starting rates update...")
        result = UpdateResult()
        pairs: dict[str, dict] = {}
        records: list[dict] = []

        for client in clients:
            logger.info("Fetching from %s...", client.source)
            try:
                rates = client.fetch_rates()
            except ApiRequestError as exc:
                logger.error("Failed to fetch from %s: %s", client.source, exc.reason)
                result.errors.append((client.source, exc.reason))
                result.steps.append((client.source, None, exc.reason))
                continue

            timestamp = utc_now_iso()
            meta = dict(client.last_meta)
            raw_ids = meta.pop("raw_ids", {})
            for pair, rate in rates.items():
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": client.source,
                }
                record_meta = dict(meta)
                if pair in raw_ids:
                    record_meta["raw_id"] = raw_ids[pair]
                records.append(
                    make_record(pair, rate, timestamp, client.source, record_meta)
                )
            logger.info("%s OK (%d rates)", client.source, len(rates))
            result.ok.append((client.source, len(rates)))
            result.steps.append((client.source, len(rates), None))

        if not pairs:
            logger.error("Update failed: no data from any source")
            reasons = "; ".join(f"{src}: {msg}" for src, msg in result.errors)
            raise ApiRequestError(reasons or "нет данных ни от одного источника")

        result.last_refresh = utc_now_iso()
        result.total = len(pairs)
        logger.info(
            "Writing %d rates to %s...", result.total, self.config.RATES_FILE_PATH
        )
        self.storage.save_snapshot(pairs, result.last_refresh)
        added = self.storage.append_history(records)
        logger.info(
            "Update finished: %d rates, %d history records, errors: %d",
            result.total,
            added,
            len(result.errors),
        )
        return result
