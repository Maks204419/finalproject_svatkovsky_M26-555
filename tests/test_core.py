"""Focused domain invariants and end-to-end service tests."""

from datetime import datetime, timedelta, timezone

import pytest

from valutatrade_hub.core.currencies import CryptoCurrency, FiatCurrency, get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, InsufficientFundsError, ValidationError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.core.utils import utc_now
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate every JSON store inside temporary working space."""
    monkeypatch.setenv("VT_DATA_DIR", str(tmp_path))
    SettingsLoader().reload()
    yield TradingService()
    monkeypatch.delenv("VT_DATA_DIR", raising=False)
    SettingsLoader().reload()


def test_user_password_and_public_fields():
    user = User(1, "alice", "secret")
    assert user.verify_password("secret")
    assert not user.verify_password("wrong")
    assert "hashed_password" not in user.get_user_info()
    assert "password" not in user.get_user_info()
    assert len(user.salt) >= 16
    assert User(**user.to_dict()).verify_password("secret")
    user.change_password("new_secret")
    assert not user.verify_password("secret")
    assert user.verify_password("new_secret")
    with pytest.raises(ValidationError):
        User(2, " ", "1234")
    with pytest.raises(ValidationError):
        User(2, "bob", "12")


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf"), "10", True])
def test_wallet_rejects_invalid_amount(invalid):
    wallet = Wallet("BTC")
    with pytest.raises(ValidationError):
        wallet.deposit(invalid)


def test_wallet_overdraft_and_portfolio_copy():
    wallet = Wallet("USD", 20)
    wallet.withdraw(10)
    assert wallet.balance == 10
    with pytest.raises(InsufficientFundsError):
        wallet.withdraw(11)
    portfolio = Portfolio(User(1, "a", "1234"))
    assert portfolio.add_currency("BTC") is portfolio.add_currency("BTC")
    portfolio.wallets.clear()
    assert "BTC" in portfolio.wallets
    assert get_currency("BTC").code == "BTC"
    assert isinstance(get_currency("BTC"), CryptoCurrency)
    assert isinstance(get_currency("USD"), FiatCurrency)


def test_registration_login_and_balance(sandbox):
    user = sandbox.register("alice", "1234")
    assert sandbox.login("alice", "1234").user_id == user.user_id
    with pytest.raises(ValidationError):
        sandbox.register("alice", "1234")
    assert sandbox.seed_usd(user.user_id, 1000) == 1000
    assert sandbox.portfolio(user.user_id).get_wallet("USD").balance == 1000


def test_buy_sell_and_insufficient_funds(sandbox):
    user = sandbox.register("bob", "1234")
    sandbox.seed_usd(user.user_id, 1000)
    DatabaseManager().write(
        "rates",
        {
            "pairs": {"EUR_USD": {"rate": 2.0, "updated_at": utc_now(), "source": "test"}},
            "last_refresh": utc_now(),
        },
    )
    purchased = sandbox.buy(user.user_id, "EUR", 20)
    assert purchased["usd"] == 40
    assert sandbox.portfolio(user.user_id).get_wallet("USD").balance == 960
    assert sandbox.sell(user.user_id, "EUR", 10)["usd"] == 20
    assert sandbox.portfolio(user.user_id).get_wallet("USD").balance == 980
    assert sandbox.portfolio(user.user_id).get_wallet("EUR").balance == 10
    with pytest.raises(InsufficientFundsError):
        sandbox.sell(user.user_id, "EUR", 100)
    with pytest.raises(InsufficientFundsError):
        sandbox.buy(user.user_id, "EUR", 10000)
    assert sandbox.portfolio(user.user_id).get_wallet("USD").balance == 980
    assert sandbox.portfolio_valuation(user.user_id)[1] == 1000


def test_rate_conversion_and_ttl(sandbox):
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    DatabaseManager().write(
        "rates",
        {
            "pairs": {
                "EUR_USD": {"rate": 2.0, "updated_at": utc_now(), "source": "test"},
                "BTC_USD": {"rate": 100.0, "updated_at": old, "source": "test"},
            },
            "last_refresh": utc_now(),
        },
    )
    assert sandbox.get_rate("USD", "EUR")[0] == 0.5
    with pytest.raises(ApiRequestError, match="устарел"):
        sandbox.get_rate("BTC", "EUR")


def test_singletons():
    assert DatabaseManager() is DatabaseManager()
    assert SettingsLoader() is SettingsLoader()
