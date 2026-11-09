"""Atomic JSON persistence and singleton database manager."""

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from .settings import SettingsLoader


class DatabaseManager:
    """Singleton JSON repository with process-local read/modify/write locking."""

    _instance: "DatabaseManager | None" = None
    _construction_lock = RLock()

    def __new__(cls) -> "DatabaseManager":
        with cls._construction_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._lock = RLock()
            return cls._instance

    def path(self, name: str) -> Path:
        """Return location of an approved JSON file."""
        if name not in {"users", "portfolios", "rates", "exchange_rates", "transactions"}:
            raise ValueError("Неизвестный JSON-файл")
        return SettingsLoader().get("data_dir") / f"{name}.json"

    def read(self, name: str) -> Any:
        """Read a JSON document, returning the expected empty structure if missing."""
        with self._lock:
            path = self.path(name)
            if not path.exists():
                return {"pairs": {}, "last_refresh": None} if name == "rates" else []
            with path.open(encoding="utf-8") as stream:
                return json.load(stream)

    def write(self, name: str, payload: Any) -> None:
        """Atomically replace JSON using a temp file in the same directory."""
        with self._lock:
            path = self.path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
                ) as stream:
                    temp_path = Path(stream.name)
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, path)
            finally:
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()

    def modify(self, name: str, callback: Any) -> Any:
        """Run a read-change-write transaction while holding the local lock."""
        with self._lock:
            data = self.read(name)
            result = callback(data)
            self.write(name, data)
            return result
