import math
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


def utc_now():
    """Возвращает время получения данных в UTC."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def positive_rate(value):
    """Проверяет числовое значение курса."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiRequestError("API вернул нечисловой курс")
    try:
        rate = float(value)
    except OverflowError:
        raise ApiRequestError("API вернул некорректный курс") from None
    if not math.isfinite(rate) or rate <= 0:
        raise ApiRequestError("API вернул некорректный курс")
    return rate


class BaseApiClient(ABC):
    """Общий интерфейс источников курсов."""

    source = ""

    def __init__(self, config=None):
        """Сохраняет конфигурацию клиента."""
        self.config = config if config is not None else ParserConfig()
        self.last_metadata = {}
        self.fetched_at = None

    @abstractmethod
    def fetch_rates(self) -> dict:
        """Возвращает курсы в формате PAIR: rate."""
        raise NotImplementedError

    def _request_json(self, url, params=None, headers=None):
        """Проверяет ответ сервиса, скрывая URL с ключами."""
        self.last_metadata = {}
        self.fetched_at = None
        started = time.monotonic()
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
            )
        except requests.exceptions.RequestException as error:
            reason = type(error).__name__
            raise ApiRequestError(f"{self.source}: ошибка сети ({reason})") from None
        if response.status_code != 200:
            raise ApiRequestError(
                f"{self.source}: сервер вернул HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError:
            raise ApiRequestError(f"{self.source}: ответ не является JSON") from None
        if not isinstance(payload, dict):
            raise ApiRequestError(f"{self.source}: неверный формат ответа")
        metadata = {
            "request_ms": round((time.monotonic() - started) * 1000),
            "status_code": response.status_code,
        }
        etag = response.headers.get("ETag")
        if etag:
            metadata["etag"] = etag
        return payload, metadata


class CoinGeckoClient(BaseApiClient):
    """Получает цены криптовалют к доллару."""

    source = "CoinGecko"

    def fetch_rates(self) -> dict:
        """Запрашивает все настроенные криптовалюты одним запросом."""
        config = self.config
        try:
            ids = [config.CRYPTO_ID_MAP[code] for code in config.CRYPTO_CURRENCIES]
        except KeyError:
            raise ApiRequestError("CoinGecko: не задан ID криптовалюты") from None
        headers = {}
        if config.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = config.COINGECKO_API_KEY
        base = config.BASE_CURRENCY.lower()
        payload, metadata = self._request_json(
            config.COINGECKO_URL,
            params={"ids": ",".join(ids), "vs_currencies": base},
            headers=headers,
        )
        rates = {}
        pair_metadata = {}
        for code, raw_id in zip(config.CRYPTO_CURRENCIES, ids, strict=True):
            record = payload.get(raw_id)
            if not isinstance(record, dict) or base not in record:
                raise ApiRequestError(f"CoinGecko: отсутствует курс {code}")
            pair = f"{code}_{config.BASE_CURRENCY}"
            rates[pair] = positive_rate(record[base])
            pair_metadata[pair] = {**metadata, "raw_id": raw_id}
        self.last_metadata = pair_metadata
        self.fetched_at = utc_now()
        return rates
