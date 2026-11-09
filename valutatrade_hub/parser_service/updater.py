"""Resilient orchestration of multiple API providers."""

import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now

from .api_clients import BaseApiClient
from .storage import RatesStorage


class RatesUpdater:
    """Collect independent provider quotes, continuing after source failures."""

    def __init__(self, clients: list[BaseApiClient], storage: RatesStorage | None = None) -> None:
        self.clients = clients
        self.storage = storage or RatesStorage()
        self.errors: list[str] = []

    def run_update(self) -> int:
        """Retrieve rates, persist snapshots/history, return updated pair count."""
        logger = logging.getLogger("valutatrade.parser")
        logger.info("Starting rates update")
        self.errors.clear()
        records = {}
        for client in self.clients:
            try:
                response = client.fetch_rates()
                moment = utc_now()
                for pair, price in response.items():
                    records[pair] = {"rate": price, "updated_at": moment, "source": client.source}
                logger.info("Fetched %s: %s rates", client.source, len(response))
            except ApiRequestError as exc:
                self.errors.append(f"{client.source}: {exc}")
                logger.error("Failed from %s: %s", client.source, exc)
        if not records:
            raise ApiRequestError("Нет данных ни от одного источника. " + "; ".join(self.errors))
        updated = self.storage.save(records)
        logger.info(
            "Update completed: %s fresh pairs; %s failed sources", updated, len(self.errors)
        )
        return updated
