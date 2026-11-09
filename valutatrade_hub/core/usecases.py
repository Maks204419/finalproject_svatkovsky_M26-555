"""Application service: authentication, trades and rates with persistence."""

import math
from datetime import datetime, timezone

from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

from .currencies import get_currency
from .exceptions import ApiRequestError, AuthenticationError, CurrencyNotFoundError, ValidationError
from .models import Portfolio, User, Wallet
from .utils import parse_timestamp, positive_amount


class TradingService:
    """Encapsulate domain operations and repository writes."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db or DatabaseManager()

    def register(self, username: str, password: str) -> User:
        """Create a new unique user and empty portfolio."""
        if not isinstance(username, str) or not username.strip():
            raise ValidationError("Имя пользователя не может быть пустым")
        if not isinstance(password, str) or len(password) < 4:
            raise ValidationError("Пароль должен быть не короче 4 символов")

        def add_user(users):
            if any(user["username"] == username.strip() for user in users):
                raise ValidationError(f"Имя пользователя '{username.strip()}' уже занято")
            user = User(
                max((u["user_id"] for u in users), default=0) + 1, username.strip(), password
            )
            users.append(user.to_dict())
            return user

        user = self.db.modify("users", add_user)
        self.db.modify(
            "portfolios", lambda rows: rows.append({"user_id": user.user_id, "wallets": {}})
        )
        return user

    def login(self, username: str, password: str) -> User:
        """Authenticate credentials without exposing stored hashes."""
        for row in self.db.read("users"):
            if row["username"] == username:
                user = User(**row)
                if user.verify_password(password):
                    return user
                raise AuthenticationError("Неверный пароль")
        raise AuthenticationError(f"Пользователь '{username}' не найден")

    def _user(self, user_id: int) -> User:
        for row in self.db.read("users"):
            if row["user_id"] == user_id:
                return User(**row)
        raise AuthenticationError("Сначала выполните login")

    def portfolio(self, user_id: int) -> Portfolio:
        """Load all wallets for a registered user."""
        user = self._user(user_id)
        for record in self.db.read("portfolios"):
            if record["user_id"] == user_id:
                wallets = {
                    code: Wallet(code, details["balance"])
                    for code, details in record["wallets"].items()
                }
                return Portfolio(user, wallets)
        return Portfolio(user)

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        record = {
            "user_id": portfolio.user.user_id,
            "wallets": {code: w.get_balance_info() for code, w in portfolio.wallets.items()},
        }

        def save(rows):
            for i, item in enumerate(rows):
                if item["user_id"] == portfolio.user.user_id:
                    rows[i] = record
                    return
            rows.append(record)

        self.db.modify("portfolios", save)

    def seed_usd(self, user_id: int, amount: float) -> float:
        """Top up virtual USD, explicitly for sandbox simulation."""
        portfolio = self.portfolio(user_id)
        wallet = portfolio.add_currency("USD")
        wallet.deposit(amount)
        self._save_portfolio(portfolio)
        return wallet.balance

    def _quote_to_usd(self, code: str) -> tuple[float, str]:
        if code == "USD":
            return 1.0, "USD (базовая валюта)"
        return self.get_rate(code, "USD")

    def get_rate(self, from_code: str, to_code: str) -> tuple[float, str]:
        """Compute cross quote using fresh cached USD pairs."""
        get_currency(from_code)
        get_currency(to_code)
        if from_code == to_code:
            return 1.0, "1:1"
        pairs = self.db.read("rates").get("pairs", {})
        ttl = SettingsLoader().get("rates_ttl_seconds")
        now = datetime.now(timezone.utc)

        def price(code: str) -> tuple[float, str]:
            if code == "USD":
                return 1.0, now.isoformat()
            record = pairs.get(f"{code}_USD")
            if not record:
                raise ApiRequestError(f"Курс {code}→USD недоступен. Выполните update-rates")
            try:
                rate = float(record["rate"])
                updated = parse_timestamp(record["updated_at"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ApiRequestError(f"Повреждён курс {code}→USD") from exc
            if not math.isfinite(rate) or rate <= 0:
                raise ApiRequestError(f"Некорректный курс {code}→USD")
            age = (now - updated).total_seconds()
            if age > ttl or age < -60:
                raise ApiRequestError(f"Курс {code}→USD устарел. Выполните update-rates")
            return rate, record["updated_at"]

        from_price, t1 = price(from_code)
        to_price, t2 = price(to_code)
        return from_price / to_price, min(t1, t2)

    @log_action("BUY", verbose=True)
    def buy(self, user_id: int, currency_code: str, amount: float) -> dict:
        """Buy a currency with available virtual USD; no overdrafts."""
        positive_amount(amount)
        get_currency(currency_code)
        if currency_code == "USD":
            raise ValidationError("Для пополнения USD используйте deposit")
        rate, updated_at = self._quote_to_usd(currency_code)
        cost = amount * rate
        if not math.isfinite(cost):
            raise ValidationError("Стоимость операции слишком велика")
        portfolio = self.portfolio(user_id)
        usd = portfolio.add_currency("USD")
        target = portfolio.add_currency(currency_code)
        before = target.balance
        usd.withdraw(cost)
        target.deposit(amount)
        self._save_portfolio(portfolio)
        return {
            "currency": currency_code,
            "before": before,
            "after": target.balance,
            "amount": amount,
            "rate": rate,
            "usd": cost,
            "updated_at": updated_at,
        }

    @log_action("SELL", verbose=True)
    def sell(self, user_id: int, currency_code: str, amount: float) -> dict:
        """Sell currency holdings and credit virtual USD."""
        positive_amount(amount)
        get_currency(currency_code)
        if currency_code == "USD":
            raise ValidationError("Продажа USD за USD не поддерживается")
        rate, updated_at = self._quote_to_usd(currency_code)
        portfolio = self.portfolio(user_id)
        if currency_code not in portfolio.wallets:
            raise CurrencyNotFoundError(currency_code)
        target = portfolio.get_wallet(currency_code)
        before = target.balance
        target.withdraw(amount)
        proceeds = amount * rate
        if not math.isfinite(proceeds):
            raise ValidationError("Стоимость операции слишком велика")
        portfolio.add_currency("USD").deposit(proceeds)
        self._save_portfolio(portfolio)
        return {
            "currency": currency_code,
            "before": before,
            "after": target.balance,
            "amount": amount,
            "rate": rate,
            "usd": proceeds,
            "updated_at": updated_at,
        }

    def portfolio_valuation(
        self, user_id: int, base: str = "USD"
    ) -> tuple[list[tuple[str, float, float]], float]:
        """Price wallet balances in selected currency with TTL validation."""
        get_currency(base)
        portfolio = self.portfolio(user_id)
        result = []
        for code, wallet in sorted(portfolio.wallets.items()):
            if wallet.balance == 0:
                converted = 0.0
            else:
                rate, _ = self.get_rate(code, base)
                converted = wallet.balance * rate
            result.append((code, wallet.balance, converted))
        return result, sum(item[2] for item in result)
