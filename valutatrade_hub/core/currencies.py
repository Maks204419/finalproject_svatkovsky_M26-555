"""Currency hierarchy and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .exceptions import CurrencyNotFoundError
from .utils import currency_code


@dataclass(frozen=True)
class Currency(ABC):
    """Abstract immutable monetary instrument."""

    name: str
    code: str

    def __post_init__(self) -> None:
        currency_code(self.code)
        if not self.name.strip():
            raise ValueError("Имя валюты не может быть пустым")

    @abstractmethod
    def get_display_info(self) -> str:
        """Return descriptive presentation for a currency."""


@dataclass(frozen=True)
class FiatCurrency(Currency):
    """Currency issued by a country or monetary union."""

    issuing_country: str

    def get_display_info(self) -> str:
        """Render a fiat-specific description."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


@dataclass(frozen=True)
class CryptoCurrency(Currency):
    """Cryptocurrency with an algorithm and market capitalization."""

    algorithm: str
    market_cap: float

    def get_display_info(self) -> str:
        """Render a crypto-specific description."""
        return f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"


REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("British Pound", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Proof of Stake", 4.5e11),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of Stake", 7.0e10),
}


def get_currency(code: str) -> Currency:
    """Return currency metadata, or raise CurrencyNotFoundError."""
    currency_code(code)
    try:
        return REGISTRY[code]
    except KeyError as exc:
        raise CurrencyNotFoundError(code) from exc
