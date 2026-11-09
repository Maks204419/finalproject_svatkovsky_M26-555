"""Parser API credentials and rate tracking configuration."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParserConfig:
    """External API configuration with secrets read from environment."""

    exchangerate_api_key: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY")
    )
    coingecko_url: str = "https://api.coingecko.com/api/v3/simple/price"
    exchangerate_api_url: str = "https://v6.exchangerate-api.com/v6"
    base_currency: str = "USD"
    fiat_currencies: tuple[str, ...] = ("EUR", "GBP", "RUB")
    crypto_currencies: tuple[str, ...] = ("BTC", "ETH", "SOL")
    crypto_id_map: dict[str, str] = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    )
    request_timeout: int = 10
    rates_file_path: str = "data/rates.json"
    history_file_path: str = "data/exchange_rates.json"
