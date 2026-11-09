# ValutaTrade Hub

Учебная консольная платформа для виртуальной торговли фиатными и криптовалютами, включающая отдельный Parser Service. Виртуальные USD начисляются исключительно командой `deposit`; реальные деньги и сделки не используются.

## Установка и запуск

Требуются Python 3.11+ и [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run python main.py
# или
uv run valutatrade
```

Для обновления **фиатных** курсов получите бесплатный ключ ExchangeRate-API и задайте переменную окружения (не сохраняйте ключ в Git):

```bash
export EXCHANGERATE_API_KEY='ваш_ключ'
uv run python main.py
```

CoinGecko работает без ключа, но возможны ограничения частоты. При отсутствии ключа фиатный клиент выдаст понятное предупреждение, а обновление криптовалют продолжится. Для локального демо без сети используйте тестовые курсы в изолированном каталоге, как показано в `scripts/offline_demo.py`; не принимайте их за актуальные котировки.

## Пример интерактивного сценария

```text
register --username alice --password 1234
login --username alice --password 1234
deposit --amount 10000
update-rates
show-rates --top 2
get-rate --from BTC --to USD
buy --currency BTC --amount 0.01
show-portfolio
sell --currency BTC --amount 0.005
show-portfolio --base EUR
sell --currency BTC --amount 50
logout
exit
```

**Важно:** торговые команды используют только **свежие** котировки, `buy` списывает USD, `sell` зачисляет USD. При отсутствии/устаревании курсов сначала выполните `update-rates`. `deposit` — отдельное виртуальное пополнение, необходимое для покупки. При смене базовой валюты портфель оценивается через USD.

## Команды

`register --username NAME --password PASS`, `login --username NAME --password PASS`, `logout`, `deposit --amount NUMBER`, `show-portfolio [--base USD]`, `buy --currency BTC --amount 0.01`, `sell --currency BTC --amount 0.005`, `get-rate --from BTC --to EUR`, `update-rates [--source coingecko|exchangerate]`, `show-rates [--currency BTC] [--top 2] [--base EUR]`, `currencies`, `help`, `exit`.

## Хранение и архитектура

- `valutatrade_hub/core/` — модели `User`, `Wallet`, `Portfolio`, валютные классы, доменные исключения и usecases.
- `valutatrade_hub/infra/` — `SettingsLoader`, `DatabaseManager`, атомарная JSON-запись.
- `valutatrade_hub/parser_service/` — CoinGecko и ExchangeRate-API, хранение истории, resilient updater.
- `valutatrade_hub/cli/` — shlex-разбор, оркестрация и PrettyTable; бизнес-логики в CLI нет.
- `data/users.json` — парольные хеши с индивидуальными солями; `data/portfolios.json` — кошельки; `data/rates.json` — последний снимок; `data/exchange_rates.json` — уникальные исторические замеры.
- `logs/actions.log` и `logs/parser.log` — ротируемые логи; файлы логов игнорируются Git.

В `rates.json` данные имеют вид `{"pairs":{"BTC_USD":{"rate":60000,"updated_at":"...","source":"CoinGecko"}},"last_refresh":"..."}`. TTL по умолчанию 300 секунд, задаётся через `VT_RATES_TTL`; путь к JSON переопределяется `VT_DATA_DIR`. При устаревании котировки сервис не делает незаметных сетевых запросов, а предлагает `update-rates`. Метки времени — UTC в формате ISO 8601.

Запись делается атомарным `tmp → os.replace`. Блокировки защищают операции в одном процессе; конкурентное изменение из **разных** процессов не поддерживается и потребовало бы файловых локов/СУБД. Денежные суммы представлены `float` в соответствии с заданием; для реальной финансовой системы следует использовать `Decimal` и транзакционное хранилище. SHA-256 с солью реализован согласно учебному ТЗ, но для продакшена следует использовать Argon2id/scrypt/PBKDF2.

## Качество и тесты

```bash
uv run ruff check .
uv run pytest -q
```

GitHub Actions запускает обе проверки при каждом push и pull request. ``python -m scripts.offline_demo` запускает готовый сценарий с контролируемыми фейковыми курсами без сети, с демонстрацией ошибок. Ссылка на Asciinema: https://asciinema.org/a/wJeTKgjT8LTot1r4

**Примечание для локального запуска:** файл `uv.lock` генерируется командой `uv lock` при наличии доступа к PyPI и затем коммитится. В предоставленном архиве lock-файла нет: среда создания архива не имела доступа к реестру пакетов.
