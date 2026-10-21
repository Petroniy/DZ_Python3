import math
import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "history_file": "exchange_rates.json",
    "rates_ttl_seconds": 300,
    "base_currency": "USD",
    "logs_dir": "logs",
    "log_format": "json",
    "log_level": "INFO",
    "log_max_bytes": 1_000_000,
    "log_backup_count": 3,
    "update_interval_seconds": 300,
}


class SettingsLoader:
    _instance = None

    def __new__(cls, *args, **kwargs):
        # __new__ оставляет один экземпляр без отдельного метакласса.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path=None):
        if not hasattr(self, "_values"):
            self._config_path = config_path
            self.reload()
        elif config_path is not None and config_path != self._config_path:
            self.reload(config_path)

    def reload(self, config_path=None):
        """Загружает настройки из TOML и переменных окружения."""
        if config_path is not None:
            self._config_path = config_path
        path = Path(
            self._config_path or os.getenv("VALUTATRADE_CONFIG", "pyproject.toml")
        )
        values = DEFAULTS.copy()
        if path.exists():
            with path.open("rb") as file:
                config = tomllib.load(file)
            values.update(config.get("tool", {}).get("valutatrade", {}))
        for key in ("data_dir", "logs_dir"):
            env_name = "VALUTATRADE_" + key.upper()
            if key == "logs_dir":
                env_name = "VALUTATRADE_LOG_DIR"
            if os.getenv(env_name):
                values[key] = os.environ[env_name]
        for key in ("rates_ttl_seconds", "update_interval_seconds"):
            value = values[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Настройка {key} должна быть числом")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Настройка {key} должна быть положительной")
        self._values = values

    def get(self, key, default=None):
        """Возвращает значение настройки."""
        return self._values.get(key.lower(), default)
