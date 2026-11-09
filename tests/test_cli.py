"""CLI interactive-session integration tests."""

from valutatrade_hub.cli.interface import Console
from valutatrade_hub.core.utils import utc_now
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader


def test_complete_cli_scenario(tmp_path, monkeypatch):
    """Ensure all major command paths remain available and user friendly."""
    monkeypatch.setenv("VT_DATA_DIR", str(tmp_path))
    SettingsLoader().reload()
    console = Console()
    assert "Сначала выполните login" in console.execute("show-portfolio")
    assert "зарегистрирован" in console.execute("register --username alice --password 1234")
    assert "вошли" in console.execute("login --username alice --password 1234")
    assert "пополнен" in console.execute("deposit --amount 1000")
    DatabaseManager().write(
        "rates",
        {
            "pairs": {"EUR_USD": {"rate": 2.0, "updated_at": utc_now(), "source": "test"}},
            "last_refresh": utc_now(),
        },
    )
    assert "Покупка выполнена" in console.execute("buy --currency EUR --amount 100")
    assert "ИТОГО" in console.execute("show-portfolio")
    assert "Продажа выполнена" in console.execute("sell --currency EUR --amount 20")
    assert "Недостаточно средств" in console.execute("sell --currency EUR --amount 1000")
    assert "Курс EUR→USD" in console.execute("get-rate --from EUR --to USD")
    assert "Курсы из кеша" in console.execute("show-rates --currency EUR")
    assert "Неизвестная валюта" in console.execute("get-rate --from ABC --to USD")
    assert "Сессия завершена" in console.execute("logout")
    monkeypatch.delenv("VT_DATA_DIR")
    SettingsLoader().reload()
