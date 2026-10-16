"""Доменные модели: пользователь, кошелёк, портфель."""

import hashlib
import secrets
from datetime import datetime

from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)

MIN_PASSWORD_LENGTH = 4


def hash_password(password: str, salt: str) -> str:
    """Односторонний псевдо-хеш пароля: sha256(password + salt)."""
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


class User:
    """Пользователь системы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        self._user_id = user_id
        self.username = username  # через сеттер с проверкой
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создать нового пользователя с солью и хешем пароля."""
        cls._validate_password(password)
        salt = secrets.token_hex(4)
        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hash_password(password, salt),
            salt=salt,
            registration_date=datetime.now().replace(microsecond=0),
        )

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )

    # --- геттеры / сеттеры ---
    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    # --- методы ---
    def get_user_info(self) -> dict:
        """Информация о пользователе без пароля и соли."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Сменить пароль: новая соль и новый хеш."""
        self._validate_password(new_password)
        self._salt = secrets.token_hex(4)
        self._hashed_password = hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверить введённый пароль."""
        return hash_password(password, self._salt) == self._hashed_password

    # --- сериализация ---
    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Кошелёк пользователя для одной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым")
        self._currency_code = currency_code.strip().upper()
        self.balance = balance  # через сеттер с проверкой

    @property
    def currency_code(self) -> str:
        """Код валюты кошелька (только чтение)."""
        return self._currency_code

    @staticmethod
    def _validate_amount(amount: float) -> float:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("'amount' должен быть числом")
        if amount <= 0:
            raise ValueError("'amount' должен быть положительным числом")
        return float(amount)

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополнить баланс."""
        self.balance = self._balance + self._validate_amount(amount)

    def withdraw(self, amount: float) -> None:
        """Снять средства, если баланса хватает."""
        amount = self._validate_amount(amount)
        if amount > self._balance:
            raise InsufficientFundsError(self._balance, amount, self._currency_code)
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        return f"{self.currency_code}: {self._balance:.4f}"

    def to_dict(self) -> dict:
        return {"currency_code": self.currency_code, "balance": self._balance}


class Portfolio:
    """Все кошельки одного пользователя."""

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ) -> None:
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = dict(wallets) if wallets else {}
        self._user = user

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User | None:
        """Владелец портфеля (только чтение)."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Копия словаря кошельков."""
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавить новый кошелёк. Код валюты должен быть уникален."""
        if currency_code in self._wallets:
            raise ValueError(f"Кошелёк '{currency_code}' уже существует")
        wallet = Wallet(currency_code)
        self._wallets[currency_code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        return self._wallets.get(currency_code)

    def get_total_value(
        self, base_currency: str = "USD", exchange_rates: dict | None = None
    ) -> float:
        """Общая стоимость всех кошельков в base_currency.

        exchange_rates — словарь вида {"BTC_USD": 59337.21, ...}
        (курс валюты к USD). Без него используются фиксированные курсы.
        """
        rates = exchange_rates or DEFAULT_RATES_TO_USD
        rates = {**rates, "USD_USD": 1.0}
        base_key = f"{base_currency}_USD"
        if base_key not in rates:
            raise CurrencyNotFoundError(base_currency)
        total_usd = 0.0
        for code, wallet in self._wallets.items():
            key = f"{code}_USD"
            if key not in rates:
                raise CurrencyNotFoundError(code)
            total_usd += wallet.balance * rates[key]
        return total_usd / rates[base_key]

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": w.balance} for code, w in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, user: User | None = None) -> "Portfolio":
        wallets = {
            code: Wallet(code, info.get("balance", 0.0))
            for code, info in data.get("wallets", {}).items()
        }
        return cls(data["user_id"], wallets, user)


# Фиксированные курсы-заглушки (1 единица валюты = N долларов),
# пока не подключён Parser Service.
DEFAULT_RATES_TO_USD: dict[str, float] = {
    "USD_USD": 1.0,
    "EUR_USD": 1.0786,
    "RUB_USD": 0.01016,
    "GBP_USD": 1.2700,
    "BTC_USD": 59337.21,
    "ETH_USD": 3720.00,
    "SOL_USD": 145.12,
}
