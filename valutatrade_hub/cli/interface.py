"""Командный интерфейс. Только разбор команд и вывод — логика в usecases."""

import shlex

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.models import User

COMMANDS = {
    "register": ("--username <str> --password <str>", "Регистрация"),
    "login": ("--username <str> --password <str>", "Вход"),
    "show-portfolio": ("[--base <str>]", "Портфель и итоговая стоимость"),
    "buy": ("--currency <str> --amount <float>", "Купить валюту"),
    "sell": ("--currency <str> --amount <float>", "Продать валюту"),
    "get-rate": ("--from <str> --to <str>", "Курс валюты"),
    "help": ("", "Список команд"),
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
        key = token[2:]
        if i + 1 >= len(tokens) or tokens[i + 1].startswith("--"):
            raise ValueError(f"Не указано значение для '{token}'")
        args[key] = tokens[i + 1]
        i += 2
    return args


def require(args: dict[str, str], *names: str) -> list[str]:
    missing = [f"--{n}" for n in names if n not in args]
    if missing:
        raise ValueError(f"Не хватает аргументов: {', '.join(missing)}")
    return [args[n] for n in names]


def print_help() -> None:
    table = PrettyTable(["Команда", "Аргументы", "Описание"])
    table.align = "l"
    for name, (params, descr) in COMMANDS.items():
        table.add_row([name, params, descr])
    print(table)


class CLI:
    def __init__(self) -> None:
        self.current_user: User | None = None

    def _require_login(self) -> User:
        if self.current_user is None:
            raise PermissionError("Сначала выполните login")
        return self.current_user

    def handle(self, line: str) -> bool:
        """Выполнить одну команду. Вернуть False, если пора выйти."""
        tokens = shlex.split(line)
        if not tokens:
            return True
        command, args = tokens[0], parse_args(tokens[1:])

        if command in ("exit", "quit"):
            return False
        if command == "help":
            print_help()
        elif command == "register":
            username, password = require(args, "username", "password")
            print(usecases.register(username, password))
        elif command == "login":
            username, password = require(args, "username", "password")
            self.current_user = usecases.login(username, password)
            print(f"Вы вошли как '{self.current_user.username}'")
        elif command == "show-portfolio":
            user = self._require_login()
            print(usecases.show_portfolio(user, args.get("base", "USD")))
        elif command == "buy":
            user = self._require_login()
            currency, amount = require(args, "currency", "amount")
            print(usecases.buy(user, currency, amount))
        elif command == "sell":
            user = self._require_login()
            currency, amount = require(args, "currency", "amount")
            print(usecases.sell(user, currency, amount))
        elif command == "get-rate":
            from_code, to_code = require(args, "from", "to")
            print(usecases.rate_info(from_code, to_code))
        else:
            print(f"Неизвестная команда '{command}'. Введите help")
        return True

    def run(self) -> None:
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
            except (ValueError, TypeError, PermissionError) as e:
                print(e)
            except usecases.RateUnavailableError as e:
                print(e)


def run_cli() -> None:
    CLI().run()
