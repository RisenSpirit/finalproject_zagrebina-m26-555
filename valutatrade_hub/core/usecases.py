"""Бизнес-логика: регистрация, вход, портфель, сделки, курсы."""

from datetime import datetime, timedelta

from valutatrade_hub.core.models import DEFAULT_RATES_TO_USD, Portfolio, User
from valutatrade_hub.core.utils import (
    PORTFOLIOS_FILE,
    RATES_FILE,
    USERS_FILE,
    load_json,
    save_json,
    validate_amount,
    validate_currency_code,
)

BASE_CURRENCY = "USD"
RATES_TTL = timedelta(minutes=5)
CRYPTO = {"BTC", "ETH"}


class RateUnavailableError(Exception):
    """Курс не удалось получить ни из кеша, ни из источника."""


def _load_users() -> list[User]:
    return [User.from_dict(d) for d in load_json(USERS_FILE, [])]


def _save_users(users: list[User]) -> None:
    save_json(USERS_FILE, [u.to_dict() for u in users])


def _find_user(username: str) -> User | None:
    for user in _load_users():
        if user.username == username:
            return user
    return None


def register(username: str, password: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValueError("Имя пользователя не может быть пустым")
    users = _load_users()
    if any(u.username == username for u in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    user_id = max((u.user_id for u in users), default=0) + 1
    user = User.create(user_id, username, password)  # проверит длину пароля
    users.append(user)
    _save_users(users)

    portfolios = load_json(PORTFOLIOS_FILE, [])
    portfolios.append(Portfolio(user_id).to_dict())
    save_json(PORTFOLIOS_FILE, portfolios)

    return (
        f"Пользователь '{username}' зарегистрирован (id={user_id}). "
        f"Войдите: login --username {username} --password ****"
    )


def login(username: str, password: str) -> User:
    user = _find_user(username)
    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user


def _load_portfolio(user: User) -> Portfolio:
    for data in load_json(PORTFOLIOS_FILE, []):
        if data["user_id"] == user.user_id:
            return Portfolio.from_dict(data, user)
    return Portfolio(user.user_id, user=user)


def _save_portfolio(portfolio: Portfolio) -> None:
    portfolios = load_json(PORTFOLIOS_FILE, [])
    portfolios = [p for p in portfolios if p["user_id"] != portfolio.user_id]
    portfolios.append(portfolio.to_dict())
    portfolios.sort(key=lambda p: p["user_id"])
    save_json(PORTFOLIOS_FILE, portfolios)


def _fetch_rates() -> dict[str, float]:
    """Источник курсов. Пока Parser Service не подключён — заглушка."""
    return dict(DEFAULT_RATES_TO_USD)


def _refresh_rates_cache() -> dict:
    now = datetime.now().replace(microsecond=0).isoformat()
    fetched = _fetch_rates()
    cache = {
        key: {"rate": rate, "updated_at": now}
        for key, rate in fetched.items()
        if key != "USD_USD"
    }
    cache["source"] = "StubRates"
    cache["last_refresh"] = now
    save_json(RATES_FILE, cache)
    return cache


def _is_fresh(updated_at: str) -> bool:
    try:
        return datetime.now() - datetime.fromisoformat(updated_at) < RATES_TTL
    except (TypeError, ValueError):
        return False


def _rate_to_usd(code: str, cache: dict) -> tuple[float, str] | None:
    """Курс 1 code в USD и время обновления из кеша."""
    if code == BASE_CURRENCY:
        return 1.0, cache.get("last_refresh") or datetime.now().isoformat()
    entry = cache.get(f"{code}_USD")
    if isinstance(entry, dict) and "rate" in entry:
        return float(entry["rate"]), entry.get("updated_at", "")
    return None


def _get_cache(codes: list[str]) -> dict:
    """Кеш rates.json; обновить, если нужных курсов нет или они устарели."""
    cache = load_json(RATES_FILE, {})
    for code in codes:
        found = _rate_to_usd(code, cache)
        if found is None or (code != BASE_CURRENCY and not _is_fresh(found[1])):
            try:
                return _refresh_rates_cache()
            except Exception:  # источник недоступен — работаем с тем, что есть
                return cache
    return cache


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Единый контракт: курс from→to (сколько to за 1 from) и время обновления."""
    from_code = validate_currency_code(from_code)
    to_code = validate_currency_code(to_code)
    cache = _get_cache([from_code, to_code])
    src = _rate_to_usd(from_code, cache)
    dst = _rate_to_usd(to_code, cache)
    if src is None or dst is None:
        raise RateUnavailableError(
            f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже."
        )
    updated = max(src[1], dst[1])
    return src[0] / dst[0], updated


def _rates_for_portfolio(portfolio: Portfolio, base: str) -> dict[str, float]:
    codes = [*portfolio.wallets, base]
    cache = _get_cache(codes)
    rates = {}
    for code in codes:
        found = _rate_to_usd(code, cache)
        if found is None:
            if code == base:
                raise ValueError(f"Неизвестная базовая валюта '{base}'")
            raise RateUnavailableError(f"Не удалось получить курс для {code}→USD")
        rates[f"{code}_USD"] = found[0]
    return rates


def _fmt_amount(code: str, value: float) -> str:
    return f"{value:.4f}" if code in CRYPTO else f"{value:.2f}"


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def show_portfolio(user: User, base: str = BASE_CURRENCY) -> str:
    base = validate_currency_code(base)
    portfolio = _load_portfolio(user)
    wallets = portfolio.wallets
    if not wallets:
        return f"У пользователя '{user.username}' пока нет кошельков"

    rates = _rates_for_portfolio(portfolio, base)
    lines = [f"Портфель пользователя '{user.username}' (база: {base}):"]
    for code, wallet in wallets.items():
        value = wallet.balance * rates[f"{code}_USD"] / rates[f"{base}_USD"]
        lines.append(
            f"- {code}: {_fmt_amount(code, wallet.balance)}  → "
            f"{_fmt_money(value)} {base}"
        )
    total = portfolio.get_total_value(base, rates)
    lines.append("-" * 33)
    lines.append(f"ИТОГО: {_fmt_money(total)} {base}")
    return "\n".join(lines)


def buy(user: User, currency: str, amount: float) -> str:
    currency = validate_currency_code(currency)
    amount = validate_amount(amount)
    try:
        rate, _ = get_rate(currency, BASE_CURRENCY)
    except RateUnavailableError:
        raise RateUnavailableError(
            f"Не удалось получить курс для {currency}→{BASE_CURRENCY}"
        ) from None

    portfolio = _load_portfolio(user)
    wallet = portfolio.get_wallet(currency) or portfolio.add_currency(currency)
    before = wallet.balance
    wallet.deposit(amount)
    _save_portfolio(portfolio)

    return (
        f"Покупка выполнена: {_fmt_amount(currency, amount)} {currency} "
        f"по курсу {_fmt_price(rate)} {BASE_CURRENCY}/{currency}\n"
        f"Изменения в портфеле:\n"
        f"- {currency}: было {_fmt_amount(currency, before)} → "
        f"стало {_fmt_amount(currency, wallet.balance)}\n"
        f"Оценочная стоимость покупки: {_fmt_money(amount * rate)} {BASE_CURRENCY}"
    )


def sell(user: User, currency: str, amount: float) -> str:
    currency = validate_currency_code(currency)
    amount = validate_amount(amount)
    portfolio = _load_portfolio(user)
    wallet = portfolio.get_wallet(currency)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{currency}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    try:
        rate, _ = get_rate(currency, BASE_CURRENCY)
    except RateUnavailableError:
        raise RateUnavailableError(
            f"Не удалось получить курс для {currency}→{BASE_CURRENCY}"
        ) from None

    before = wallet.balance
    wallet.withdraw(amount)  # проверит достаточность средств
    lines = [
        f"Продажа выполнена: {_fmt_amount(currency, amount)} {currency} "
        f"по курсу {_fmt_price(rate)} {BASE_CURRENCY}/{currency}",
        "Изменения в портфеле:",
        f"- {currency}: было {_fmt_amount(currency, before)} → "
        f"стало {_fmt_amount(currency, wallet.balance)}",
    ]
    if currency != BASE_CURRENCY:
        revenue = amount * rate
        usd = portfolio.get_wallet(BASE_CURRENCY) or portfolio.add_currency(
            BASE_CURRENCY
        )
        usd_before = usd.balance
        usd.deposit(revenue)
        lines.append(
            f"- {BASE_CURRENCY}: было {usd_before:.2f} → стало {usd.balance:.2f}"
        )
        lines.append(f"Оценочная выручка: {_fmt_money(revenue)} {BASE_CURRENCY}")
    _save_portfolio(portfolio)
    return "\n".join(lines)


def rate_info(from_code: str, to_code: str) -> str:
    from_code = validate_currency_code(from_code)
    to_code = validate_currency_code(to_code)
    rate, updated = get_rate(from_code, to_code)
    updated_str = updated.replace("T", " ")
    reverse = 1 / rate
    return (
        f"Курс {from_code}→{to_code}: {_fmt_rate(rate)} (обновлено: {updated_str})\n"
        f"Обратный курс {to_code}→{from_code}: {_fmt_rate(reverse)}"
    )


def _fmt_rate(rate: float) -> str:
    return f"{rate:.8f}" if rate < 1 else f"{rate:.2f}"


def _fmt_price(rate: float) -> str:
    return f"{rate:.4f}" if rate < 100 else f"{rate:.2f}"
