import os

from valutatrade_hub.infra.settings import SettingsLoader


class ParserConfig:
    """Параметры API и файлов парсера."""

    COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6"
    BASE_CURRENCY = "USD"
    FIAT_CURRENCIES = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    REQUEST_TIMEOUT = 10

    def __init__(self):
        """Загружает ключи из окружения, пути — из настроек."""
        settings = SettingsLoader()
        self.EXCHANGERATE_API_KEY = os.getenv("EXCHANGERATE_API_KEY", "")
        self.COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
        data_dir = settings.get("data_dir", "data")
        self.RATES_FILE_PATH = os.path.join(
            data_dir, settings.get("rates_file", "rates.json")
        )
        self.HISTORY_FILE_PATH = os.path.join(
            data_dir, settings.get("history_file", "exchange_rates.json")
        )
        self.UPDATE_INTERVAL_SECONDS = settings.get("update_interval_seconds", 300)
