"""Merge fresh snapshots and append deduplicated historical quotes."""

from datetime import timezone

from valutatrade_hub.core.utils import parse_timestamp, utc_now
from valutatrade_hub.infra.database import DatabaseManager


class RatesStorage:
    """Persistence facade for current and historical quotes."""

    def __init__(self, database: DatabaseManager | None = None) -> None:
        self.db = database or DatabaseManager()

    def save(self, records: dict[str, dict]) -> int:
        """Store only newer rates and unique timestamped history records."""
        saved = {}

        def update(snapshot):
            pairs = snapshot.setdefault("pairs", {})
            for pair, incoming in records.items():
                current = pairs.get(pair)
                if current is None or parse_timestamp(incoming["updated_at"]) > parse_timestamp(
                    current["updated_at"]
                ):
                    pairs[pair] = incoming
                    saved[pair] = incoming
            if saved:
                snapshot["last_refresh"] = utc_now()

        self.db.modify("rates", update)
        if saved:

            def append(history):
                seen = {item["id"] for item in history}
                for pair, entry in saved.items():
                    source_code, destination = pair.split("_")
                    moment = parse_timestamp(entry["updated_at"]).astimezone(timezone.utc)
                    stamp = moment.isoformat(timespec="microseconds").replace("+00:00", "Z")
                    record_id = f"{pair}_{stamp}"
                    if record_id not in seen:
                        history.append(
                            {
                                "id": record_id,
                                "from_currency": source_code,
                                "to_currency": destination,
                                "rate": entry["rate"],
                                "timestamp": stamp,
                                "source": entry["source"],
                                "meta": {},
                            }
                        )
                        seen.add(record_id)

            self.db.modify("exchange_rates", append)
        return len(saved)
