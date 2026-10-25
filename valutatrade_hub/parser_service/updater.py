import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
    utc_now,
)
from valutatrade_hub.parser_service.storage import (
    RatesStorage,
    normalize_timestamp,
    timestamp_value,
)


class RatesUpdater:
    """Обновляет курсы из доступных источников."""

    def __init__(self, clients=None, storage=None):
        """Принимает клиентов API и хранилище."""
        if clients is None:
            clients = {
                "coingecko": CoinGeckoClient(),
                "exchangerate": ExchangeRateApiClient(),
            }
        if isinstance(clients, dict):
            self.clients = dict(clients)
        else:
            self.clients = {}
            for client in clients:
                name = client.source.lower().replace("-api", "").replace("-", "")
                self.clients[name] = client
        self.storage = storage if storage is not None else RatesStorage()
        self.logger = logging.getLogger("valutatrade.parser")

    def run_update(self, source=None):
        """Сохраняет успешные ответы, продолжая после ошибки источника."""
        if source is not None and source not in self.clients:
            raise ValueError("Источник должен быть coingecko или exchangerate")
        selected = self.clients if source is None else {source: self.clients[source]}
        self.logger.info("Начато обновление курсов")
        errors = []
        updated = 0
        successful = 0
        last_refresh = None
        for name, client in selected.items():
            self.logger.info("Получение курсов: %s", name)
            try:
                pairs = client.fetch_rates()
                if not pairs:
                    raise ApiRequestError(f"{name}: пустой список курсов")
                fetched_at = normalize_timestamp(
                    getattr(client, "fetched_at", None) or utc_now()
                )
                count = self.storage.save_rates(
                    pairs,
                    client.source,
                    fetched_at,
                    metadata=getattr(client, "last_metadata", {}),
                )
            except (ApiRequestError, ValueError, OSError) as error:
                message = str(error)
                errors.append(message)
                self.logger.error("Не удалось обновить %s: %s", name, message)
                continue
            successful += 1
            updated += count
            if last_refresh is None or timestamp_value(fetched_at) > timestamp_value(
                last_refresh
            ):
                last_refresh = fetched_at
            self.logger.info("%s: сохранено курсов %s", name, count)
        if not successful:
            self.logger.error("Обновление завершено без успешных ответов")
            raise ApiRequestError("; ".join(errors) or "Нет доступных источников")
        self.logger.info(
            "Обновление завершено: %s курсов, %s ошибок", updated, len(errors)
        )
        return {"count": updated, "last_refresh": last_refresh, "errors": errors}
