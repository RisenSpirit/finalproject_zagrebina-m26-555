# ValutaTrade Hub

Консольная платформа для симуляции торговли валютами: пользователи регистрируются,
ведут виртуальный портфель фиатных и криптовалют, покупают и продают валюту
и смотрят актуальные курсы, которые сервис парсинга получает из публичных API.

Итоговый проект курса «Программирование на Python» (Яндекс Практикум × МИФИ).

![Демо](docs/demo.gif)

## Идея и архитектура

Приложение состоит из двух сервисов:

- **Core Service**: пользователи, портфели, кошельки, сделки и CLI. Работает с
  локальным кешем курсов `data/rates.json`, поэтому не ходит в интернет на каждую команду.
- **Parser Service**: получает курсы из внешних API, ведёт историю замеров
  в `data/exchange_rates.json` и обновляет снимок последних курсов в `data/rates.json`.

| Источник | Валюты | Ключ |
|---|---|---|
| [CoinGecko](https://www.coingecko.com/en/api) | BTC, ETH, SOL | не нужен |
| [ExchangeRate-API](https://www.exchangerate-api.com/) | EUR, GBP, RUB | нужен (бесплатный) |

Базовая валюта — USD. Поддерживаемые коды: `USD, EUR, GBP, RUB, BTC, ETH, SOL`.

## Структура каталогов

```
finalproject_zagrebina-m26-555/
├── data/
│   ├── users.json            # пользователи (хеш пароля + соль)
│   ├── portfolios.json       # портфели и кошельки
│   ├── rates.json            # кеш последних курсов для Core Service
│   └── exchange_rates.json   # история замеров Parser Service
├── valutatrade_hub/
│   ├── logging_config.py     # логи: формат, уровень, ротация
│   ├── decorators.py         # @log_action — логирование операций
│   ├── core/
│   │   ├── currencies.py     # Currency → FiatCurrency / CryptoCurrency, реестр get_currency()
│   │   ├── exceptions.py     # InsufficientFundsError, CurrencyNotFoundError, ApiRequestError
│   │   ├── models.py         # User, Wallet, Portfolio
│   │   ├── usecases.py       # бизнес-логика: register, login, buy, sell, get_rate…
│   │   └── utils.py          # валидация и конвертация
│   ├── infra/
│   │   ├── settings.py       # SettingsLoader (Singleton) — конфигурация
│   │   └── database.py       # DatabaseManager (Singleton) — JSON-хранилище
│   ├── parser_service/
│   │   ├── config.py         # ParserConfig: ключ, URL, списки валют, таймаут
│   │   ├── api_clients.py    # BaseApiClient, CoinGeckoClient, ExchangeRateApiClient
│   │   ├── updater.py        # RatesUpdater — сбор и объединение курсов
│   │   ├── storage.py        # запись истории и снимка (атомарно)
│   │   └── scheduler.py      # периодическое обновление
│   └── cli/
│       └── interface.py      # команды CLI
├── main.py
├── pyproject.toml
├── uv.lock
├── Makefile
├── .env.example              # образец файла с ключом API
└── README.md
```

## Установка

Нужны Python 3.11+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/RisenSpirit/finalproject_zagrebina-m26-555.git
cd finalproject_zagrebina-m26-555
uv sync
```

## Ключ API

Ключ ExchangeRate-API **не хранится в коде** и не попадает в Git (`.env` в `.gitignore`).

1. Зарегистрируйтесь на <https://www.exchangerate-api.com/> и получите ключ.
2. Создайте файл `.env` по образцу `.env.example`:

   ```
   EXCHANGERATE_API_KEY=ваш_ключ
   ```

Вместо `.env` можно задать переменную окружения `EXCHANGERATE_API_KEY`.
Без ключа CoinGecko продолжит работать, а фиатные курсы обновляться не будут.

## Запуск

```bash
uv run project          # или: uv run python main.py
```

Откроется интерактивная оболочка: `help` выводит список команд, `exit` завершает работу.

Проверка стиля:

```bash
uv run ruff check .
```

### Makefile

```bash
make install          # установить зависимости (uv sync)
make project          # запустить приложение
make lint             # проверка ruff
make format           # автоформатирование ruff
make build            # собрать пакет в dist/
make publish          # пробная публикация (dry-run, ничего не отправляет)
make package-install  # установить собранный пакет как команду project
```

## Команды CLI

| Команда | Аргументы | Что делает |
|---|---|---|
| `register` | `--username <str> --password <str>` | регистрация (пароль ≥ 4 символов) |
| `login` | `--username <str> --password <str>` | вход |
| `show-portfolio` | `[--base <str>]` | кошельки и итог в базовой валюте (по умолчанию USD) |
| `buy` | `--currency <str> --amount <float>` | покупка валюты |
| `sell` | `--currency <str> --amount <float>` | продажа, выручка зачисляется в USD |
| `get-rate` | `--from <str> --to <str>` | курс одной валюты к другой |
| `update-rates` | `[--source coingecko\|exchangerate]` | обновить курсы из API |
| `show-rates` | `[--currency <str>] [--top <int>] [--base <str>]` | курсы из кеша |
| `currencies` | — | список поддерживаемых валют |
| `help` | `[<команда>]` | справка |
| `exit` | — | выход |

### Пример сессии

```
> register --username alice --password 1234
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****
> login --username alice --password 1234
Вы вошли как 'alice'
> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2026-10-16T15:30:00Z
> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
Оценочная стоимость покупки: 2,966.86 USD
> sell --currency BTC --amount 0.01
Продажа выполнена: 0.0100 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0500 → стало 0.0400
- USD: было 0.00 → стало 593.37
Оценочная выручка: 593.37 USD
> show-portfolio
Портфель пользователя 'alice' (база: USD):
- BTC: 0.0400  → 2,373.49 USD
- USD: 593.37  → 593.37 USD
---------------------------------
ИТОГО: 2,966.86 USD
> get-rate --from USD --to BTC
Курс USD→BTC: 0.00001685 (обновлено: 2026-10-16 15:30:00Z)
Обратный курс BTC→USD: 59337.21
> show-rates --top 2
Rates from cache (updated at 2026-10-16T15:30:00Z):
- BTC_USD: 59337.21
- ETH_USD: 3720.00
```

Курсы в примере условные: реальные значения зависят от момента запуска.

### Обработка ошибок

```
> sell --currency BTC --amount 5
Недостаточно средств: доступно 0.0400 BTC, требуется 5.0000 BTC
> buy --currency ABC --amount 1
Неизвестная валюта 'ABC'
Поддерживаемые коды: BTC, ETH, EUR, GBP, RUB, SOL, USD. Подробнее: help get-rate или currencies
> buy --currency BTC --amount -1
'amount' должен быть положительным числом
> show-portfolio      # без login
Сначала выполните login
```

## Кеш курсов и TTL

- `data/rates.json` хранит снимок вида
  `{"pairs": {"BTC_USD": {"rate": ..., "updated_at": "...Z", "source": "CoinGecko"}}, "last_refresh": "...Z"}`.
  Для каждой пары остаётся только последнее значение. Новое значение записывается,
  только если его `updated_at` свежее текущего.
- Курс считается актуальным, пока он моложе TTL: `rates_ttl_seconds`, по умолчанию 300 секунд.
- Если курс устарел, `get-rate`, `buy`, `sell` и `show-portfolio` сами запрашивают обновление
  у Parser Service. Если обновить не удалось, выводится понятное сообщение
  с предложением выполнить `update-rates` позже.
- `show-rates` читает только кеш и предупреждает, если данные устарели.

## Parser Service

- Ручное обновление: команда `update-rates`, при необходимости с `--source coingecko` или `--source exchangerate`.
- Автообновление по таймеру, остановка через Ctrl+C:

  ```bash
  uv run python -m valutatrade_hub.parser_service.scheduler --interval 300
  ```

- Если один источник недоступен, данные второго всё равно сохраняются.
- Ошибки сети, таймаут, 401/403 (неверный ключ) и 429 (лимит запросов) превращаются
  в `ApiRequestError` с понятным сообщением.
- Запись в JSON атомарная: сначала во временный файл, затем замена.
- История замеров копится в `data/exchange_rates.json`. Каждая запись получает уникальный
  `id` вида `BTC_USD_2026-10-16T15:30:00Z`, поэтому дублей нет.

## Настройки

Секция `[tool.valutatrade]` в `pyproject.toml`; без неё используются значения по умолчанию.

```toml
[tool.valutatrade]
data_dir = "data"
rates_ttl_seconds = 300
default_base_currency = "USD"
log_dir = "logs"
log_level = "INFO"   # DEBUG для отладки
```

Параметры сервиса парсинга (URL, списки валют, таймаут запросов) собраны
в `valutatrade_hub/parser_service/config.py`.

## Логи

Логи пишутся в папку `logs/` с ротацией по размеру.

- `logs/actions.log` — операции `register`, `login`, `buy`, `sell`, их пишет декоратор `@log_action`:

  ```
  INFO 2026-10-16T18:05:22 BUY user='alice' currency='BTC' amount=0.0500 rate=59337.21 base='USD' wallet='0.0000→0.0500' result=OK
  INFO 2026-10-16T18:06:01 SELL user='alice' currency='BTC' amount=5.0000 result=ERROR error_type=InsufficientFundsError error_message='Недостаточно средств: ...'
  ```

- `logs/parser.log` — шаги обновления курсов и ошибки источников.
