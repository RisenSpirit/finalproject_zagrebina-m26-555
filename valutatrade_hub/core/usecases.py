"""Бизнес-логика: регистрация, вход, портфель, сделки, курсы.

Функции возвращают данные (dict / объекты), а текст для пользователя
формирует CLI. Ошибки — через исключения из core/exceptions.py.

Синглтоны:
- SettingsLoader — TTL курсов (rates_ttl_seconds), базовая валюта;
- DatabaseManager — все чтения/записи JSON (users, portfolios, rates).
Курсы получает Parser Service (RatesUpdater), Core читает снимок rates.json.

@log_action применяется к register, login, buy, sell.
"""

from datetime import UTC, datetime, timedelta

from valutatrade_hub.core.currencies import is_crypto
from valutatrade_hub.core.exceptions import ApiRequestError, CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import validate_amount, validate_currency_code
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.storage import parse_ts, utc_now_iso
from valutatrade_hub.parser_service.updater import RatesUpdater, UpdateResult

settings = SettingsLoader()
db = DatabaseManager()

BASE_CURRENCY = settings.get("default_base_currency", "USD")


def _load_users() -> list[User]:
    return [User.from_dict(d) for d in db.read("users")]


def _find_user(username: str) -> User | None:
    for user in _load_users():
        if user.username == username:
            return user
    return None


@log_action("REGISTER")
def register(username: str, password: str) -> User:
    """Зарегистрировать пользователя и создать ему пустой портфель."""
    username = (username or "").strip()
    if not username:
        raise ValueError("Имя пользователя не может быть пустым")

    created: dict[str, User] = {}

    def add_user(users: list[dict]) -> list[dict]:
        if any(u["username"] == username for u in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        user_id = max((u["user_id"] for u in users), default=0) + 1
        user = User.create(user_id, username, password)  # проверит пароль
        created["user"] = user
        return [*users, user.to_dict()]

    db.update("users", add_user)
    user = created["user"]
    db.update(
        "portfolios",
        lambda ps: [*ps, Portfolio(user.user_id).to_dict()],
    )
    return user


@log_action("LOGIN")
def login(username: str, password: str) -> User:
    """Проверить имя и пароль, вернуть пользователя."""
    user = _find_user(username)
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def _load_portfolio(user: User) -> Portfolio:
    for data in db.read("portfolios"):
        if data["user_id"] == user.user_id:
            return Portfolio.from_dict(data, user)
    return Portfolio(user.user_id, user=user)


def _save_portfolio(portfolio: Portfolio) -> None:
    def replace(portfolios: list[dict]) -> list[dict]:
        rest = [p for p in portfolios if p["user_id"] != portfolio.user_id]
        return sorted([*rest, portfolio.to_dict()], key=lambda p: p["user_id"])

    db.update("portfolios", replace)


# rates.json (снимок от Parser Service):
# {"pairs": {"BTC_USD": {"rate": ..., "updated_at": "...Z", "source": ...}},
#  "last_refresh": "...Z"}


def refresh_rates(source: str | None = None) -> UpdateResult:
    """Запросить свежие курсы у Parser Service (ApiRequestError при неудаче)."""
    return RatesUpdater().run_update(source)


def _pairs(cache: dict) -> dict:
    if not isinstance(cache, dict):
        return {}
    pairs = cache.get("pairs")
    return pairs if isinstance(pairs, dict) else {}


def _is_fresh(updated_at: str) -> bool:
    ttl = timedelta(seconds=settings.get("rates_ttl_seconds", 300))
    ts = parse_ts(updated_at)
    return ts is not None and datetime.now(UTC) - ts < ttl


def _rate_to_usd(code: str, cache: dict) -> tuple[float, str] | None:
    """Курс 1 code в USD и время обновления из кеша."""
    if code == "USD":
        return 1.0, cache.get("last_refresh") or utc_now_iso()
    entry = _pairs(cache).get(f"{code}_USD")
    if isinstance(entry, dict) and "rate" in entry:
        return float(entry["rate"]), entry.get("updated_at", "")
    return None


def _get_cache(codes: list[str]) -> dict:
    """Кеш rates.json. Если нужных курсов нет или они старше TTL —
    обновить через Parser Service; не вышло → ApiRequestError.
    """
    cache = db.read("rates")
    for code in codes:
        found = _rate_to_usd(code, cache)
        if found is None or (code != "USD" and not _is_fresh(found[1])):
            try:
                refresh_rates()
            except ApiRequestError as exc:
                state = "устарели" if found else "отсутствуют"
                raise ApiRequestError(
                    f"данные о курсе {code} {state}, обновить не удалось "
                    f"({exc.reason}). Выполните 'update-rates' позже"
                ) from None
            return db.read("rates")
    return cache


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Единый контракт: курс from→to (сколько to за 1 from) и updated_at."""
    from_code = validate_currency_code(from_code)  # CurrencyNotFoundError
    to_code = validate_currency_code(to_code)
    cache = _get_cache([from_code, to_code])  # ApiRequestError
    src = _rate_to_usd(from_code, cache)
    dst = _rate_to_usd(to_code, cache)
    if src is None or dst is None:
        raise ApiRequestError(f"нет данных о курсе {from_code}→{to_code}")
    return src[0] / dst[0], max(src[1], dst[1])


def _rates_for(codes: list[str]) -> dict[str, float]:
    cache = _get_cache(codes)
    rates = {}
    for code in codes:
        found = _rate_to_usd(code, cache)
        if found is None:
            raise ApiRequestError(f"нет данных о курсе {code}→USD")
        rates[f"{code}_USD"] = found[0]
    return rates


def show_rates(
    currency: str | None = None, top: int | None = None, base: str | None = None
) -> dict:
    """Курсы из локального кеша (без обращения к API) с фильтрами."""
    cache = db.read("rates")
    pairs = _pairs(cache)
    if not pairs:
        raise ValueError(
            "Локальный кеш курсов пуст. Выполните 'update-rates', "
            "чтобы загрузить данные."
        )

    base = validate_currency_code(base) if base else "USD"
    if base != "USD" and f"{base}_USD" not in pairs:
        raise ValueError(f"Курс для '{base}' не найден в кеше.")
    base_rate = 1.0 if base == "USD" else float(pairs[f"{base}_USD"]["rate"])

    rows = []  # (pair, rate, updated_at)
    for pair, entry in pairs.items():
        code = pair.split("_", 1)[0]
        if code == base:
            continue
        rows.append(
            (
                f"{code}_{base}",
                float(entry["rate"]) / base_rate,
                entry.get("updated_at", ""),
            )
        )
    if base != "USD":  # сам USD относительно новой базы
        rows.append((f"USD_{base}", 1 / base_rate, pairs[f"{base}_USD"]["updated_at"]))

    if currency:
        code = currency.strip().upper()
        rows = [r for r in rows if r[0].split("_", 1)[0] == code]
        if not rows:
            raise ValueError(f"Курс для '{code}' не найден в кеше.")
    if top is not None:
        if top <= 0:
            raise ValueError("'top' должен быть положительным целым числом")
        rows = [r for r in rows if is_crypto(r[0].split("_", 1)[0])]
        rows = sorted(rows, key=lambda r: r[1], reverse=True)[:top]
    else:
        rows.sort(key=lambda r: r[0])

    return {
        "last_refresh": cache.get("last_refresh", ""),
        "rows": rows,
        "stale": not _is_fresh(cache.get("last_refresh", "")),
    }


def show_portfolio(user: User, base: str | None = None) -> dict:
    """Кошельки пользователя с оценкой в базовой валюте и итогом."""
    base = base or BASE_CURRENCY
    try:
        base = validate_currency_code(base)
    except CurrencyNotFoundError:
        raise ValueError(f"Неизвестная базовая валюта '{base.upper()}'") from None

    portfolio = _load_portfolio(user)
    wallets = portfolio.wallets
    if not wallets:
        return {"username": user.username, "base": base, "rows": [], "total": 0.0}

    rates = _rates_for([*wallets, base])
    rows = []
    for code, wallet in wallets.items():
        value = wallet.balance * rates[f"{code}_USD"] / rates[f"{base}_USD"]
        rows.append((code, wallet.balance, value))
    return {
        "username": user.username,
        "base": base,
        "rows": rows,
        "total": portfolio.get_total_value(base, rates),
    }


@log_action("BUY", verbose=True)
def buy(user: User, currency: str, amount: float) -> dict:
    """Купить amount валюты: пополнить (или создать) кошелёк, оценить в USD."""
    currency = validate_currency_code(currency)
    amount = validate_amount(amount)
    rate, _ = get_rate(currency, BASE_CURRENCY)

    portfolio = _load_portfolio(user)
    wallet = portfolio.get_wallet(currency) or portfolio.add_currency(currency)
    before = wallet.balance
    wallet.deposit(amount)
    _save_portfolio(portfolio)

    return {
        "currency": currency,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "before": before,
        "after": wallet.balance,
        "cost": amount * rate,
    }


@log_action("SELL", verbose=True)
def sell(user: User, currency: str, amount: float) -> dict:
    """Продать amount валюты: списать с кошелька, выручку зачислить в USD."""
    currency = validate_currency_code(currency)
    amount = validate_amount(amount)
    portfolio = _load_portfolio(user)
    wallet = portfolio.get_wallet(currency)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{currency}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    rate, _ = get_rate(currency, BASE_CURRENCY)

    before = wallet.balance
    wallet.withdraw(amount)  # InsufficientFundsError
    result = {
        "currency": currency,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "before": before,
        "after": wallet.balance,
        "revenue": None,
    }
    if currency != BASE_CURRENCY:
        revenue = amount * rate
        base_wallet = portfolio.get_wallet(BASE_CURRENCY) or portfolio.add_currency(
            BASE_CURRENCY
        )
        result["base_before"] = base_wallet.balance
        base_wallet.deposit(revenue)
        result["base_after"] = base_wallet.balance
        result["revenue"] = revenue
    _save_portfolio(portfolio)
    return result
