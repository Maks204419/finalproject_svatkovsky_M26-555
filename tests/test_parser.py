"""Mock external API results and verify fault-tolerant persistence."""

from unittest.mock import Mock

import pytest
import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import CoinGeckoClient, ExchangeRateApiClient
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Redirect all tests to a clean temp directory."""
    monkeypatch.setenv("VT_DATA_DIR", str(tmp_path))
    SettingsLoader().reload()
    yield
    monkeypatch.delenv("VT_DATA_DIR", raising=False)
    SettingsLoader().reload()


def test_api_adapters(monkeypatch):
    responses = [
        {"bitcoin": {"usd": 60000}, "ethereum": {"usd": 2000}, "solana": {"usd": 100}},
        {"result": "success", "conversion_rates": {"EUR": 0.8, "GBP": 0.5, "RUB": 100}},
    ]
    monkeypatch.setattr(
        "requests.get", lambda *args, **kwargs: Mock(status_code=200, json=lambda: responses.pop(0))
    )
    assert CoinGeckoClient().fetch_rates()["BTC_USD"] == 60000
    config = ParserConfig(exchangerate_api_key="not_a_real_key")
    assert ExchangeRateApiClient(config).fetch_rates()["EUR_USD"] == 1.25


def test_network_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr("requests.get", boom)
    with pytest.raises(ApiRequestError):
        CoinGeckoClient().fetch_rates()


def test_http_status_and_bad_json(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: Mock(status_code=429))
    with pytest.raises(ApiRequestError, match="429"):
        CoinGeckoClient().fetch_rates()
    monkeypatch.setattr("requests.get", lambda *a, **kw: Mock(status_code=200, json=lambda: [1]))
    with pytest.raises(ApiRequestError):
        CoinGeckoClient().fetch_rates()


def test_resilient_update_and_history_dedup():
    class Good:
        source = "Good"

        def fetch_rates(self):
            return {"BTC_USD": 123.45}

    class Bad:
        source = "Bad"

        def fetch_rates(self):
            raise ApiRequestError("offline")

    updater = RatesUpdater([Bad(), Good()])
    assert updater.run_update() == 1
    assert len(updater.errors) == 1
    db = DatabaseManager()
    assert db.read("rates")["pairs"]["BTC_USD"]["rate"] == 123.45
    assert len(db.read("exchange_rates")) == 1
    entry = db.read("rates")["pairs"]["BTC_USD"]
    assert RatesStorage().save({"BTC_USD": entry}) == 0
    assert len(db.read("exchange_rates")) == 1


def test_all_sources_fail():
    class Bad:
        source = "Bad"

        def fetch_rates(self):
            raise ApiRequestError("offline")

    with pytest.raises(ApiRequestError):
        RatesUpdater([Bad()]).run_update()
