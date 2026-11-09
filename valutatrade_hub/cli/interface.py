"""Interactive shlex-based console interface with presentation-only handlers."""

import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import REGISTRY
from valutatrade_hub.core.exceptions import ValutaTradeError
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.logging_config import configure_logging
from valutatrade_hub.parser_service.api_clients import CoinGeckoClient, ExchangeRateApiClient
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater


class SafeParser(argparse.ArgumentParser):
    """Argument parser that raises errors instead of ending the REPL."""

    def error(self, message: str) -> None:
        """Surface argument errors to the user without terminating the session."""
        raise ValueError(message)


class Console:
    """Maintain a login session and delegate commands to application services."""

    def __init__(self, service: TradingService | None = None) -> None:
        self.service = service or TradingService()
        self.user_id: int | None = None
        self.username: str | None = None

    def _require_login(self) -> int:
        if self.user_id is None:
            from valutatrade_hub.core.exceptions import AuthenticationError

            raise AuthenticationError("Сначала выполните login")
        return self.user_id

    def execute(self, line: str) -> str:
        """Execute a single command and return a human-readable response."""
        try:
            tokens = shlex.split(line)
            if not tokens:
                return ""
            command, *arguments = tokens
            if command in {"exit", "quit"}:
                return "До свидания!"
            if command == "help":
                return (
                    "Команды: register, login, logout, deposit, show-portfolio, buy, sell, "
                    "get-rate, update-rates, show-rates, currencies, help, exit"
                )
            if command == "currencies":
                return "\n".join(currency.get_display_info() for currency in REGISTRY.values())
            return self._dispatch(command, arguments)
        except (ValutaTradeError, ValueError, OSError, KeyError) as exc:
            return f"Ошибка: {exc}"

    def _dispatch(self, command: str, args: list[str]) -> str:
        options = {
            "register": (("--username", "--password"), ()),
            "login": (("--username", "--password"), ()),
            "logout": ((), ()),
            "deposit": (("--amount",), ()),
            "show-portfolio": ((), ("--base",)),
            "buy": (("--currency", "--amount"), ()),
            "sell": (("--currency", "--amount"), ()),
            "get-rate": (("--from", "--to"), ()),
            "update-rates": ((), ("--source",)),
            "show-rates": ((), ("--currency", "--top", "--base")),
        }
        if command not in options:
            return f"Неизвестная команда '{command}'. Введите help"
        required, optional = options[command]
        parser = SafeParser(prog=command, add_help=False)
        for flag in required:
            parser.add_argument(flag, required=True)
        for flag in optional:
            parser.add_argument(flag)
        data = vars(parser.parse_args(args))
        if command == "register":
            user = self.service.register(data["username"], data["password"])
            return f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). Войдите: login --username {user.username} --password ****"
        if command == "login":
            user = self.service.login(data["username"], data["password"])
            self.user_id, self.username = user.user_id, user.username
            return f"Вы вошли как '{user.username}'"
        if command == "logout":
            self.user_id = self.username = None
            return "Сессия завершена"
        if command == "deposit":
            balance = self.service.seed_usd(self._require_login(), float(data["amount"]))
            return f"Виртуальный USD-кошелёк пополнен. Баланс: {balance:,.2f} USD"
        if command == "show-portfolio":
            base = data["base"] or "USD"
            rows, total = self.service.portfolio_valuation(self._require_login(), base)
            if not rows:
                return "В портфеле пока нет кошельков. Используйте deposit --amount 10000"
            table = PrettyTable(["Валюта", "Баланс", f"Стоимость, {base}"])
            for code, amount, converted in rows:
                table.add_row([code, f"{amount:,.6f}", f"{converted:,.2f}"])
            return f"Портфель пользователя '{self.username}' (база: {base}):\n{table}\nИТОГО: {total:,.2f} {base}"
        if command in {"buy", "sell"}:
            result = getattr(self.service, command)(
                self._require_login(), data["currency"], float(data["amount"])
            )
            caption = "Покупка" if command == "buy" else "Продажа"
            total_caption = "Стоимость" if command == "buy" else "Выручка"
            return (
                f"{caption} выполнена: {result['amount']:.6f} {result['currency']} по курсу "
                f"{result['rate']:.6f} USD/{result['currency']}\n"
                f"Баланс: {result['before']:.6f} → {result['after']:.6f}\n"
                f"{total_caption}: {result['usd']:,.2f} USD"
            )
        if command == "get-rate":
            source, target = data["from"], data["to"]
            rate, stamp = self.service.get_rate(source, target)
            return f"Курс {source}→{target}: {rate:.10f} (обновлено: {stamp})\nОбратный курс {target}→{source}: {1 / rate:.10f}"
        if command == "update-rates":
            config = ParserConfig()
            clients = {
                "coingecko": CoinGeckoClient(config),
                "exchangerate": ExchangeRateApiClient(config),
            }
            source = data["source"]
            if source and source not in clients:
                raise ValueError("Источник: coingecko или exchangerate")
            updater = RatesUpdater([clients[source]] if source else list(clients.values()))
            count = updater.run_update()
            suffix = f"; ошибки: {'; '.join(updater.errors)}" if updater.errors else ""
            return f"Курсы обновлены: {count} пар{suffix}"
        if command == "show-rates":
            return self._show_rates(data)
        raise ValueError("Команда не поддерживается")

    @staticmethod
    def _show_rates(args: dict) -> str:
        snapshot = DatabaseManager().read("rates")
        pairs = snapshot.get("pairs", {})
        if not pairs:
            return "Локальный кеш курсов пуст. Выполните update-rates"
        requested = args["currency"]
        base = args["base"] or "USD"
        count = None
        if args["top"] is not None:
            count = int(args["top"])
            if count <= 0:
                raise ValueError("--top должен быть положительным числом")
        service = TradingService()
        result = []
        for pair, data in pairs.items():
            code, _ = pair.split("_")
            if requested and requested != code:
                continue
            if count is not None and code not in {"BTC", "ETH", "SOL"}:
                continue
            try:
                rate, _ = service.get_rate(code, base)
            except ValutaTradeError:
                if base != "USD":
                    raise
                rate = data["rate"]
            result.append((code, rate, data["updated_at"], data["source"]))
        if not result:
            return f"Курс для '{requested}' не найден в кеше"
        result.sort(key=(lambda item: -item[1]) if count else (lambda item: item[0]))
        if count:
            result = result[:count]
        table = PrettyTable(["Валюта", f"Курс к {base}", "Обновлён", "Источник"])
        for code, rate, stamp, source in result:
            table.add_row([code, f"{rate:.8f}", stamp, source])
        return f"Курсы из кеша ({snapshot.get('last_refresh')}):\n{table}"


def main() -> None:
    """Start the interactive CLI application."""
    configure_logging()
    console = Console()
    print("ValutaTrade Hub · Виртуальные валюты (help — команды)")
    while True:
        try:
            line = input("valutatrade> ")
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break
        output = console.execute(line)
        if output:
            print(output)
        if line.strip() in {"exit", "quit"}:
            break
