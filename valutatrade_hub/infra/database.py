import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    _instance = None

    def __new__(cls):
        # __new__ позволяет всем модулям использовать одно хранилище.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = RLock()
        return cls._instance

    def _path(self, key):
        settings = SettingsLoader()
        return Path(settings.get("data_dir")) / settings.get(key)

    @contextmanager
    def transaction(self):
        """Блокирует чтение и изменение данных на время операции."""
        with self._lock:
            yield self

    def _load(self, key, default):
        path = self._path(key)
        with self._lock:
            if not path.exists():
                return default.copy()
            try:
                with path.open(encoding="utf-8") as file:
                    value = json.load(file)
            except json.JSONDecodeError as error:
                raise ValueError(f"Поврежден JSON-файл {path.name}") from error
            if not isinstance(value, type(default)):
                raise ValueError(f"Неверный формат файла {path.name}")
            return value

    def _save(self, key, value, expected_type):
        if not isinstance(value, expected_type):
            raise ValueError("Неверный тип сохраняемых данных")
        path = self._path(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=path.name + ".",
                    suffix=".tmp",
                    delete=False,
                ) as file:
                    temporary = Path(file.name)
                    json.dump(
                        value, file, ensure_ascii=False, indent=2, allow_nan=False
                    )
                    file.write("\n")
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def load_users(self):
        """Читает список пользователей."""
        return self._load("users_file", [])

    def save_users(self, users):
        """Сохраняет список пользователей."""
        self._save("users_file", users, list)

    def load_portfolios(self):
        """Читает портфели пользователей."""
        return self._load("portfolios_file", [])

    def save_portfolios(self, portfolios):
        """Сохраняет портфели пользователей."""
        self._save("portfolios_file", portfolios, list)

    def load_rates(self):
        """Читает последние курсы валют."""
        return self._load("rates_file", {})

    def save_rates(self, rates):
        """Сохраняет последние курсы валют."""
        self._save("rates_file", rates, dict)

    def load_history(self):
        """Читает историю курсов."""
        return self._load("history_file", [])

    def save_history(self, history):
        """Сохраняет историю курсов."""
        self._save("history_file", history, list)
