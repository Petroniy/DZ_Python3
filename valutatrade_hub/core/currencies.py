from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code, validate_number


class Currency(ABC):
    def __init__(self, name, code):
        self.name = name
        self.code = code

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Название валюты не может быть пустым")
        self._name = value.strip()

    @property
    def code(self):
        return self._code

    @code.setter
    def code(self, value):
        self._code = validate_currency_code(value)

    @abstractmethod
    def get_display_info(self):
        pass


class FiatCurrency(Currency):
    def __init__(self, name, code, issuing_country):
        super().__init__(name, code)
        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Не указана страна или зона эмиссии")
        self.issuing_country = issuing_country.strip()

    def get_display_info(self):
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(self, name, code, algorithm, market_cap=0.0):
        super().__init__(name, code)
        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Не указан алгоритм криптовалюты")
        self.algorithm = algorithm.strip()
        self.market_cap = validate_number(market_cap)

    def get_display_info(self):
        market_cap = f"{self.market_cap:.3g}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


CURRENCIES = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256"),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Proof of Stake"),
    "SOL": CryptoCurrency("Solana", "SOL", "Proof of History"),
}


def get_currency(code):
    """Находит валюту по коду в общем реестре."""
    try:
        normalized = validate_currency_code(code)
    except ValueError as error:
        raise CurrencyNotFoundError(code) from error
    if normalized not in CURRENCIES:
        raise CurrencyNotFoundError(normalized)
    return CURRENCIES[normalized]


def get_supported_codes():
    return tuple(CURRENCIES)
