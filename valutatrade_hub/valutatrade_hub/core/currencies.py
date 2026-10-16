"""Иерархия валют: Currency (ABC) → FiatCurrency / CryptoCurrency + реестр."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Абстрактная валюта.

    Инварианты:
    - code — верхний регистр, 2–5 символов, без пробелов;
    - name — непустая строка.
    """

    def __init__(self, name: str, code: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        if (
            not isinstance(code, str)
            or not 2 <= len(code) <= 5
            or not code.isalpha()
            or code != code.upper()
        ):
            raise ValueError(
                f"Некорректный код валюты '{code}': "
                "нужно 2–5 латинских букв в верхнем регистре"
            )
        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Строковое представление для UI и логов."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r})"


class FiatCurrency(Currency):
    def __init__(self, name: str, code: str, issuing_country: str) -> None:
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float) -> None:
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {_short_number(self.market_cap)})"
        )


def _short_number(value: float) -> str:
    """1.12e+12 → 1.12e12"""
    return f"{value:.2e}".replace("e+", "e")


# ---------- реестр ----------
_REGISTRY: dict[str, Currency] = {
    c.code: c
    for c in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        FiatCurrency("British Pound", "GBP", "United Kingdom"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11),
        CryptoCurrency("Solana", "SOL", "Proof of History", 7.0e10),
    )
}


def get_currency(code: str) -> Currency:
    """Фабрика: валюта по коду. Неизвестный код → CurrencyNotFoundError."""
    normalized = code.strip().upper() if isinstance(code, str) else ""
    try:
        return _REGISTRY[normalized]
    except KeyError:
        raise CurrencyNotFoundError(normalized or str(code)) from None


def supported_codes() -> list[str]:
    return sorted(_REGISTRY)


def all_currencies() -> list[Currency]:
    return [_REGISTRY[c] for c in supported_codes()]


def is_crypto(code: str) -> bool:
    return isinstance(_REGISTRY.get(code), CryptoCurrency)
