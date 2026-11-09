"""Domain models for users, wallets and portfolios."""

import hashlib
import hmac
import secrets
from datetime import datetime

from .currencies import get_currency
from .exceptions import CurrencyNotFoundError, InsufficientFundsError, ValidationError
from .utils import currency_code, parse_timestamp, positive_amount, utc_now


class User:
    """Registered user with salted, one-way password hashing."""

    def __init__(
        self,
        user_id: int,
        username: str,
        password: str | None = None,
        hashed_password: str | None = None,
        salt: str | None = None,
        registration_date: str | datetime | None = None,
    ) -> None:
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id < 1:
            raise ValidationError("Некорректный идентификатор пользователя")
        self._user_id = user_id
        self.username = username
        self._salt = salt or secrets.token_hex(16)
        self._hashed_password = hashed_password or ""
        self._registration_date = (
            parse_timestamp(registration_date)
            if isinstance(registration_date, str)
            else registration_date or parse_timestamp(utc_now())
        )
        if password is not None:
            self.change_password(password)
        elif not hashed_password:
            raise ValidationError("Требуется пароль или его хеш")

    @property
    def user_id(self) -> int:
        """User identifier."""
        return self._user_id

    @property
    def username(self) -> str:
        """Non-empty login name."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Stored password digest; not returned in public info."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Unique per-user salt."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Registration date (UTC)."""
        return self._registration_date

    def change_password(self, new_password: str) -> None:
        """Hash a new password with a newly generated salt."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValidationError("Пароль должен быть не короче 4 символов")
        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256((new_password + self._salt).encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        """Compare the supplied password digest in constant time."""
        if not isinstance(password, str):
            return False
        digest = hashlib.sha256((password + self._salt).encode()).hexdigest()
        return hmac.compare_digest(digest, self._hashed_password)

    def get_user_info(self) -> dict:
        """Return non-secret public user fields."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def to_dict(self) -> dict:
        """Serialize including password salt and digest for storage only."""
        return {
            **self.get_user_info(),
            "hashed_password": self._hashed_password,
            "salt": self._salt,
        }


class Wallet:
    """Balance of one currency, never negative."""

    def __init__(self, currency_code: str, balance: float = 0) -> None:
        self.currency_code = currency_code
        get_currency(self.currency_code)
        self.balance = balance

    @property
    def balance(self) -> float:
        """Current wallet balance."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError("Баланс должен быть числом")
        import math

        if not math.isfinite(value) or value < 0:
            raise ValidationError("Баланс не может быть отрицательным или бесконечным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Credit positive units to wallet."""
        self.balance = self.balance + positive_amount(amount)

    def withdraw(self, amount: float) -> None:
        """Debit positive units, refusing overdrafts."""
        amount = positive_amount(amount)
        if amount > self.balance:
            raise InsufficientFundsError(self.balance, amount, self.currency_code)
        self.balance = max(0.0, self.balance - amount)

    def get_balance_info(self) -> dict:
        """Return the code and current balance."""
        return {"currency_code": self.currency_code, "balance": self.balance}


class Portfolio:
    """Collection of distinct wallets belonging to a user."""

    def __init__(self, user: User, wallets: dict[str, Wallet] | None = None) -> None:
        self._user = user
        self._user_id = user.user_id
        self._wallets = dict(wallets) if wallets else {}
        for code, wallet in self._wallets.items():
            currency_code(code)
            if not isinstance(wallet, Wallet) or wallet.currency_code != code:
                raise ValidationError("Некорректные данные кошелька")

    @property
    def user(self) -> User:
        """Owner of portfolio."""
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Return a copy of wallet mapping (wallet objects remain mutable)."""
        return self._wallets.copy()

    def add_currency(self, code: str) -> Wallet:
        """Add a wallet once and return the existing or new wallet."""
        get_currency(code)
        if code not in self._wallets:
            self._wallets[code] = Wallet(code)
        return self._wallets[code]

    def get_wallet(self, code: str) -> Wallet:
        """Retrieve an existing wallet or raise a domain error."""
        try:
            return self._wallets[code]
        except KeyError as exc:
            raise CurrencyNotFoundError(code) from exc

    def get_total_value(self, base_currency: str = "USD", rates: dict | None = None) -> float:
        """Convert all holdings using positive USD-denominated price quotes."""
        get_currency(base_currency)
        rates = rates or {}

        def usd_price(code: str) -> float:
            if code == "USD":
                return 1.0
            pair = f"{code}_USD"
            if pair not in rates:
                raise ValidationError(f"Не удалось получить курс для {code}→USD")
            entry = rates[pair]
            return float(entry["rate"] if isinstance(entry, dict) else entry)

        base_price = usd_price(base_currency)
        if base_price <= 0:
            raise ValidationError("Курс базовой валюты должен быть положительным")
        return sum(
            wallet.balance * usd_price(code) / base_price for code, wallet in self._wallets.items()
        )
