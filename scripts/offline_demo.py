"""Offline deterministic demo without consuming API quota or touching real data."""

import os
import tempfile

from valutatrade_hub.cli.interface import Console
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


class DemoClient:
    """Deterministic fake CoinGecko with no network access."""

    source = "Demo (synthetic; NOT LIVE)"

    def fetch_rates(self) -> dict[str, float]:
        """Return reproducible example rates."""
        return {"BTC_USD": 60000, "ETH_USD": 3000, "EUR_USD": 1.1}


def main() -> None:
    """Perform the full assignment workflow with disposable data."""
    with tempfile.TemporaryDirectory(prefix="valutatrade_demo_") as directory:
        original = os.environ.get("VT_DATA_DIR")
        os.environ["VT_DATA_DIR"] = directory
        SettingsLoader().reload()
        try:
            console = Console()
            commands = [
                "register --username demo --password 1234",
                "login --username demo --password 1234",
                "deposit --amount 10000",
            ]
            for command in commands:
                print(f"\n> {command}\n{console.execute(command)}")
            print("\n> update-rates [OFFLINE FAKE API]")
            print(f"Обновлено: {RatesUpdater([DemoClient()], RatesStorage()).run_update()} пар")
            for command in [
                "show-rates --top 2",
                "buy --currency BTC --amount 0.05",
                "show-portfolio",
                "sell --currency BTC --amount 0.01",
                "get-rate --from USD --to BTC",
                "sell --currency BTC --amount 99",
                "get-rate --from ABC --to USD",
            ]:
                print(f"\n> {command}\n{console.execute(command)}")
            print("\nИстория котировок:", len(DatabaseManager().read("exchange_rates")))
        finally:
            if original is None:
                os.environ.pop("VT_DATA_DIR", None)
            else:
                os.environ["VT_DATA_DIR"] = original
            SettingsLoader().reload()


if __name__ == "__main__":
    main()
