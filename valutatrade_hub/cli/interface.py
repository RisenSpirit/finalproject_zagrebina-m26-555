"""Командный интерфейс. Разбор команд, вызов usecases и вывод сообщений."""

import shlex

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import all_currencies, is_crypto, supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.logging_config import setup_logging

COMMANDS = {
    "register": ("--username <str> --password <str>", "Регистрация"),
    "login": ("--username <str> --password <str>", "Вход"),
    "show-portfolio": ("[--base <str>]", "Портфель и итоговая стоимость"),
    "buy": ("--currency <str> --amount <float>", "Купить валюту"),
    "sell": ("--currency <str> --amount <float>", "Продать валюту"),
    "get-rate": ("--from <str> --to <str>", "Курс валюты"),
    "update-rates": ("[--source coingecko|exchangerate]", "Обновить курсы из API"),
    "show-rates": (
        "[--currency <str>] [--top <int>] [--base <str>]",
        "Курсы из локального кеша",
    ),
    "currencies": ("", "Список поддерживаемых валют"),
    "help": ("[<команда>]", "Список команд или справка по команде"),
    "exit": ("", "Выход"),
}


def parse_args(tokens: list[str]) -> dict[str, str]:
    """Разобрать ['--username', 'alice', ...] в {'username': 'alice'}."""
    args: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("--"):
            raise ValueError(f"Неожиданный аргумент '{token}'")
        if i + 1 >= len(tokens) or tokens[i + 1].startswith("--"):
            raise ValueError(f"Не указано значение для '{token}'")
        args[token[2:]] = tokens[i + 1]
        i += 2
    return args


def require(args: dict[str, str], *names: str) -> list[str]:
    """Вернуть значения обязательных аргументов или бросить ValueError."""
    missing = [f"--{n}" for n in names if n not in args]
    if missing:
        raise ValueError(f"Не хватает аргументов: {', '.join(missing)}")
    return [args[n] for n in names]


def fmt_amount(code: str, value: float) -> str:
    """Форматировать количество валюты: 4 знака для крипты, 2 для фиата."""
    return f"{value:.4f}" if is_crypto(code) else f"{value:.2f}"


def fmt_money(value: float) -> str:
    """Форматировать денежную сумму с разделителем тысяч."""
    return f"{value:,.2f}"


def fmt_rate(rate: float) -> str:
    """Форматировать курс: больше знаков для маленьких значений."""
    if rate < 1:
        return f"{rate:.8f}"
    return f"{rate:.4f}" if rate < 100 else f"{rate:.2f}"


def print_help(command: str | None = None) -> None:
    """Вывести таблицу команд или справку по одной команде."""
    if command:
        if command not in COMMANDS:
            print(f"Неизвестная команда '{command}'")
            return
        params, descr = COMMANDS[command]
        print(f"{command} {params}\n  {descr}")
        if command == "get-rate":
            print(f"  Поддерживаемые коды: {', '.join(supported_codes())}")
        return
    table = PrettyTable(["Команда", "Аргументы", "Описание"])
    table.align = "l"
    for name, (params, descr) in COMMANDS.items():
        table.add_row([name, params, descr])
    print(table)


def print_currencies() -> None:
    """Вывести таблицу поддерживаемых валют."""
    table = PrettyTable(["Код", "Описание"])
    table.align = "l"
    for currency in all_currencies():
        table.add_row([currency.code, currency.get_display_info()])
    print(table)


class CLI:
    """Интерактивная оболочка: хранит текущего пользователя и вызывает usecases."""

    def __init__(self) -> None:
        self.current_user: User | None = None

    def _require_login(self) -> User:
        if self.current_user is None:
            raise PermissionError("Сначала выполните login")
        return self.current_user

    def cmd_register(self, args: dict[str, str]) -> None:
        """Команда register: регистрация нового пользователя."""
        username, password = require(args, "username", "password")
        user = usecases.register(username, password)
        print(
            f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
            f"Войдите: login --username {user.username} --password ****"
        )

    def cmd_login(self, args: dict[str, str]) -> None:
        """Команда login: вход и запоминание текущего пользователя."""
        username, password = require(args, "username", "password")
        self.current_user = usecases.login(username, password)
        print(f"Вы вошли как '{self.current_user.username}'")

    def cmd_show_portfolio(self, args: dict[str, str]) -> None:
        """Команда show-portfolio: кошельки и итог в базовой валюте."""
        user = self._require_login()
        data = usecases.show_portfolio(user, args.get("base"))
        if not data["rows"]:
            print(f"У пользователя '{user.username}' пока нет кошельков")
            return
        base = data["base"]
        print(f"Портфель пользователя '{data['username']}' (база: {base}):")
        for code, balance, value in data["rows"]:
            print(f"- {code}: {fmt_amount(code, balance)}  → {fmt_money(value)} {base}")
        print("-" * 33)
        print(f"ИТОГО: {fmt_money(data['total'])} {base}")

    def cmd_buy(self, args: dict[str, str]) -> None:
        """Команда buy: покупка валюты."""
        user = self._require_login()
        currency, amount = require(args, "currency", "amount")
        r = usecases.buy(user, currency, amount)
        code, base = r["currency"], r["base"]
        print(
            f"Покупка выполнена: {fmt_amount(code, r['amount'])} {code} "
            f"по курсу {fmt_rate(r['rate'])} {base}/{code}"
        )
        print("Изменения в портфеле:")
        print(
            f"- {code}: было {fmt_amount(code, r['before'])} → "
            f"стало {fmt_amount(code, r['after'])}"
        )
        print(f"Оценочная стоимость покупки: {fmt_money(r['cost'])} {base}")

    def cmd_sell(self, args: dict[str, str]) -> None:
        """Команда sell: продажа валюты с зачислением выручки в USD."""
        user = self._require_login()
        currency, amount = require(args, "currency", "amount")
        r = usecases.sell(user, currency, amount)
        code, base = r["currency"], r["base"]
        print(
            f"Продажа выполнена: {fmt_amount(code, r['amount'])} {code} "
            f"по курсу {fmt_rate(r['rate'])} {base}/{code}"
        )
        print("Изменения в портфеле:")
        print(
            f"- {code}: было {fmt_amount(code, r['before'])} → "
            f"стало {fmt_amount(code, r['after'])}"
        )
        if r["revenue"] is not None:
            print(
                f"- {base}: было {r['base_before']:.2f} → стало {r['base_after']:.2f}"
            )
            print(f"Оценочная выручка: {fmt_money(r['revenue'])} {base}")

    def cmd_get_rate(self, args: dict[str, str]) -> None:
        """Команда get-rate: курс одной валюты к другой."""
        from_code, to_code = require(args, "from", "to")
        from_code, to_code = from_code.upper(), to_code.upper()
        try:
            rate, updated = usecases.get_rate(from_code, to_code)
        except ApiRequestError as e:
            print(e)
            print(f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже.")
            return
        print(
            f"Курс {from_code}→{to_code}: {fmt_rate(rate)} "
            f"(обновлено: {updated.replace('T', ' ')})"
        )
        print(f"Обратный курс {to_code}→{from_code}: {fmt_rate(1 / rate)}")

    def cmd_update_rates(self, args: dict[str, str]) -> None:
        """Команда update-rates: обновить курсы через Parser Service."""
        try:
            result = usecases.refresh_rates(args.get("source"))
        except ApiRequestError as e:
            print("INFO: Starting rates update...")
            for part in e.reason.split("; "):
                print(f"ERROR: Failed to fetch from {part}")
            print("Update failed. Check logs/parser.log for details.")
            return
        print("INFO: Starting rates update...")
        for source, count, error in result.steps:
            if error is None:
                print(f"INFO: Fetching from {source}... OK ({count} rates)")
            else:
                print(f"ERROR: Failed to fetch from {source}: {error}")
        print(f"INFO: Writing {result.total} rates to data/rates.json...")
        if result.has_errors:
            print(
                "Update completed with errors. Check logs/parser.log for details. "
                f"Total rates updated: {result.total}."
            )
        else:
            print(
                f"Update successful. Total rates updated: {result.total}. "
                f"Last refresh: {result.last_refresh}"
            )

    def cmd_show_rates(self, args: dict[str, str]) -> None:
        """Команда show-rates: курсы из локального кеша с фильтрами."""
        top = args.get("top")
        if top is not None:
            try:
                top = int(top)
            except ValueError:
                raise ValueError("'top' должен быть целым числом") from None
        data = usecases.show_rates(args.get("currency"), top, args.get("base"))
        print(f"Rates from cache (updated at {data['last_refresh']}):")
        for pair, rate, _updated in data["rows"]:
            print(f"- {pair}: {fmt_rate(rate)}")
        if data["stale"]:
            print("Внимание: данные устарели. Выполните 'update-rates'.")

    def handle(self, line: str) -> bool:
        """Выполнить одну команду. Вернуть False, если пора выйти."""
        tokens = shlex.split(line)
        if not tokens:
            return True
        command, rest = tokens[0], tokens[1:]

        if command in ("exit", "quit"):
            return False
        if command == "help":
            print_help(rest[0] if rest else None)
            return True
        if command == "currencies":
            print_currencies()
            return True

        handlers = {
            "register": self.cmd_register,
            "login": self.cmd_login,
            "show-portfolio": self.cmd_show_portfolio,
            "buy": self.cmd_buy,
            "sell": self.cmd_sell,
            "get-rate": self.cmd_get_rate,
            "update-rates": self.cmd_update_rates,
            "show-rates": self.cmd_show_rates,
        }
        handler = handlers.get(command)
        if handler is None:
            print(f"Неизвестная команда '{command}'. Введите help")
            return True
        handler(parse_args(rest))
        return True

    def run(self) -> None:
        """Главный цикл: читать команды и выводить понятные ошибки."""
        print("ValutaTrade Hub. Введите help для списка команд, exit — выход.")
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                if not self.handle(line):
                    break
            except InsufficientFundsError as e:
                print(e)
            except CurrencyNotFoundError as e:
                print(e)
                print(
                    f"Поддерживаемые коды: {', '.join(supported_codes())}. "
                    "Подробнее: help get-rate или currencies"
                )
            except ApiRequestError as e:
                print(e)
                print("Повторите попытку позже или проверьте подключение к сети.")
            except (ValueError, TypeError, PermissionError) as e:
                print(e)


def run_cli() -> None:
    """Точка входа CLI: настроить логирование и запустить оболочку."""
    setup_logging()
    CLI().run()
