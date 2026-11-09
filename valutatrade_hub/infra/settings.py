"""Single source of project configuration."""

import os
import tomllib
from pathlib import Path
from threading import Lock
from typing import Any


class SettingsLoader:
    """Singleton settings provider via __new__ for a simple shared cache."""

    _instance: "SettingsLoader | None" = None
    _lock = Lock()

    def __new__(cls) -> "SettingsLoader":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._settings = {}
                cls._instance.reload()
            return cls._instance

    def reload(self) -> None:
        """Re-read package settings from pyproject, optionally using VT_DATA_DIR."""
        root = Path(__file__).resolve().parents[2]
        file_path = root / "pyproject.toml"
        values = {}
        if file_path.exists():
            with file_path.open("rb") as stream:
                values = tomllib.load(stream).get("tool", {}).get("valutatrade", {})
        self._settings = {
            "data_dir": Path(os.environ.get("VT_DATA_DIR", values.get("data_dir", "data"))),
            "rates_ttl_seconds": int(
                os.environ.get("VT_RATES_TTL", values.get("rates_ttl_seconds", 300))
            ),
            "base_currency": values.get("base_currency", "USD"),
            "log_dir": Path(values.get("log_dir", "logs")),
            "log_format": values.get("log_format", "text"),
        }
        for name in ("data_dir", "log_dir"):
            if not self._settings[name].is_absolute():
                self._settings[name] = root / self._settings[name]

    def get(self, key: str, default: Any = None) -> Any:
        """Return setting by name or fallback."""
        return self._settings.get(key, default)
