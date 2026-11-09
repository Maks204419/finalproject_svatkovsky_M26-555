"""Independent rate API adapters using one normalized pair format."""

import math
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError

from .config import ParserConfig


def checked_get(url: str, *, params: dict | None = None, timeout: int = 10) -> dict:
    """Request JSON, classify HTTP and networking failures."""
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise ApiRequestError(f"Ошибка сети: {type(exc).__name__}") from exc
    if response.status_code == 429:
        raise ApiRequestError("Превышен лимит запросов (HTTP 429)")
    if response.status_code in (401, 403):
        raise ApiRequestError(f"Нет доступа к API (HTTP {response.status_code})")
    if response.status_code != 200:
        raise ApiRequestError(f"Сервис вернул HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ApiRequestError("Сервис вернул некорректный JSON") from exc
    if not isinstance(data, dict):
        raise ApiRequestError("Неожиданный формат ответа API")
    return data


def valid_rate(raw: object) -> float:
    """Ensure API quote is finite and positive."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ApiRequestError("API вернул нечисловой курс")
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ApiRequestError("API вернул некорректный курс")
    return value


class BaseApiClient(ABC):
    """Common normalized currency rate provider interface."""

    source: str

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Return quotes keyed as FROM_USD."""


class CoinGeckoClient(BaseApiClient):
    """Fetch USD prices by CoinGecko asset ID."""

    source = "CoinGecko"

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Fetch and normalize crypto USD quotes."""
        ids = ",".join(self.config.crypto_id_map[code] for code in self.config.crypto_currencies)
        data = checked_get(
            self.config.coingecko_url,
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=self.config.request_timeout,
        )
        try:
            return {
                f"{code}_USD": valid_rate(data[self.config.crypto_id_map[code]]["usd"])
                for code in self.config.crypto_currencies
            }
        except (KeyError, TypeError) as exc:
            raise ApiRequestError("CoinGecko: отсутствует ожидаемый курс") from exc


class ExchangeRateApiClient(BaseApiClient):
    """Fetch fiat pairs via ExchangeRate-API (USD-based reciprocal rates)."""

    source = "ExchangeRate-API"

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig()

    def fetch_rates(self) -> dict[str, float]:
        """Convert API USD→fiat quotes into fiat→USD prices."""
        if not self.config.exchangerate_api_key:
            raise ApiRequestError("Не задан EXCHANGERATE_API_KEY")
        url = f"{self.config.exchangerate_api_url}/{self.config.exchangerate_api_key}/latest/{self.config.base_currency}"
        data = checked_get(url, timeout=self.config.request_timeout)
        if data.get("result") not in (None, "success"):
            raise ApiRequestError(f"ExchangeRate-API: {data.get('error-type', 'ошибка ответа')}")
        rates = data.get("conversion_rates", data.get("rates"))
        if not isinstance(rates, dict):
            raise ApiRequestError("ExchangeRate-API: отсутствуют conversion_rates")
        try:
            return {
                f"{code}_USD": 1.0 / valid_rate(rates[code]) for code in self.config.fiat_currencies
            }
        except (KeyError, TypeError) as exc:
            raise ApiRequestError("ExchangeRate-API: отсутствует ожидаемый курс") from exc
