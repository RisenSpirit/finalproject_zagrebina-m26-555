"""Клиенты внешних API. Единый интерфейс: fetch_rates() -> {"BTC_USD": 59337.21}."""

import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Базовый клиент. После fetch_rates() в self.last_meta — метаданные запроса."""

    source: str = "Unknown"
    name: str = "unknown"  # короткое имя для --source

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.last_meta: dict[str, Any] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Вернуть курсы в формате {"<FROM>_<TO>": rate}."""

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET с замером времени и единым переводом ошибок в ApiRequestError."""
        started = time.perf_counter()
        try:
            response = requests.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError("превышено время ожидания") from None
        except requests.exceptions.ConnectionError:
            raise ApiRequestError("нет соединения (Network error)") from None
        except requests.exceptions.RequestException as exc:
            raise ApiRequestError(str(exc)) from None

        self.last_meta = {
            "request_ms": round((time.perf_counter() - started) * 1000),
            "status_code": response.status_code,
            "etag": response.headers.get("ETag"),
        }
        if response.status_code == 429:
            raise ApiRequestError("превышен лимит запросов (429)")
        if response.status_code in (401, 403):
            raise ApiRequestError("неверный или отсутствующий API-ключ")
        if response.status_code != 200:
            raise ApiRequestError(f"HTTP {response.status_code}")
        return response

    @staticmethod
    def _json(response: requests.Response, source: str) -> dict:
        try:
            data = response.json()
        except ValueError:
            raise ApiRequestError("ответ не является JSON") from None
        if not isinstance(data, dict):
            raise ApiRequestError("неожиданный формат ответа")
        return data

    @staticmethod
    def _valid_rate(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        )


class CoinGeckoClient(BaseApiClient):
    """Криптовалюты. Запрос по ID монет (bitcoin, ethereum, ...), а не тикерам."""

    source = "CoinGecko"
    name = "coingecko"

    def fetch_rates(self) -> dict[str, float]:
        """Курсы криптовалют к USD: {'BTC_USD': 59337.21, ...}."""
        cfg = self.config
        base = cfg.BASE_CURRENCY.lower()
        ids = [cfg.CRYPTO_ID_MAP[c] for c in cfg.CRYPTO_CURRENCIES]
        response = self._get(
            cfg.COINGECKO_URL, params={"ids": ",".join(ids), "vs_currencies": base}
        )
        data = self._json(response, self.source)

        rates: dict[str, float] = {}
        raw_ids: dict[str, str] = {}
        for code in cfg.CRYPTO_CURRENCIES:
            raw_id = cfg.CRYPTO_ID_MAP[code]
            value = data.get(raw_id, {}).get(base)
            if self._valid_rate(value):
                key = f"{code}_{cfg.BASE_CURRENCY}"
                rates[key] = float(value)
                raw_ids[key] = raw_id
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        self.last_meta["raw_ids"] = raw_ids
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Фиатные валюты. Ключ подставляется в URL."""

    source = "ExchangeRate-API"
    name = "exchangerate"

    def fetch_rates(self) -> dict[str, float]:
        """Курсы фиатных валют к USD: {'EUR_USD': 1.0786, ...}."""
        cfg = self.config
        if not cfg.EXCHANGERATE_API_KEY:
            raise ApiRequestError(
                "не задан EXCHANGERATE_API_KEY (переменная окружения или файл .env)"
            )
        url = (
            f"{cfg.EXCHANGERATE_API_URL}/{cfg.EXCHANGERATE_API_KEY}"
            f"/latest/{cfg.BASE_CURRENCY}"
        )
        response = self._get(url)
        data = self._json(response, self.source)
        if data.get("result") != "success":
            reason = data.get("error-type", "unknown error")
            raise ApiRequestError(str(reason))

        # v6 отдаёт курсы в "conversion_rates", открытый эндпоинт — в "rates"
        api_rates = data.get("conversion_rates") or data.get("rates") or {}
        rates: dict[str, float] = {}
        for code in cfg.FIAT_CURRENCIES:
            value = api_rates.get(code)
            if self._valid_rate(value):
                # API отдаёт «сколько EUR за 1 USD» (USD→EUR).
                # Core хранит EUR_USD — «сколько USD за 1 EUR», поэтому 1 / value.
                rates[f"{code}_{cfg.BASE_CURRENCY}"] = 1 / float(value)
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        self.last_meta["api_updated"] = data.get("time_last_update_utc")
        return rates
