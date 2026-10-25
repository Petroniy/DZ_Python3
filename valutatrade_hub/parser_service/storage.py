import math
from datetime import datetime, timezone

from valutatrade_hub.infra.database import DatabaseManager


def normalize_timestamp(value):
    """Приводит время с часовым поясом к ISO UTC."""
    if not isinstance(value, str):
        raise ValueError("Время обновления должно быть строкой ISO UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Некорректное время обновления") from None
    if parsed.tzinfo is None:
        raise ValueError("Для времени обновления нужен часовой пояс")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_value(value):
    """Возвращает время для сравнения измерений."""
    return datetime.fromisoformat(normalize_timestamp(value).replace("Z", "+00:00"))


class RatesStorage:
    """Сохраняет новые измерения и последние значения пар."""

    def __init__(self, database=None):
        """Принимает общее хранилище приложения."""
        self.database = database if database is not None else DatabaseManager()

    def save_rates(self, pairs, source, timestamp, metadata=None):
        """Добавляет историю и обновляет только более свежие курсы."""
        if not isinstance(pairs, dict):
            raise ValueError("Курсы должны быть словарём")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Не указан источник курсов")
        timestamp = normalize_timestamp(timestamp)
        measured_at = timestamp_value(timestamp)
        metadata = metadata if metadata is not None else {}
        if not isinstance(metadata, dict):
            raise ValueError("Метаданные должны быть словарём")
        validated = []
        for pair, rate in pairs.items():
            if not isinstance(pair, str):
                raise ValueError("Некорректная валютная пара")
            codes = pair.split("_")
            if len(codes) != 2 or any(
                not (2 <= len(code) <= 5 and code.isascii() and code.isalpha())
                or code != code.upper()
                for code in codes
            ):
                raise ValueError(f"Некорректная валютная пара: {pair}")
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise ValueError(f"Некорректный курс для {pair}")
            try:
                rate = float(rate)
            except OverflowError:
                raise ValueError(f"Некорректный курс для {pair}") from None
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(f"Некорректный курс для {pair}")
            details = metadata.get(pair, {})
            if not isinstance(details, dict):
                raise ValueError(f"Некорректные метаданные для {pair}")
            record = {
                "id": f"{pair}_{timestamp}",
                "from_currency": codes[0],
                "to_currency": codes[1],
                "rate": float(rate),
                "timestamp": timestamp,
                "source": source,
            }
            if details:
                record["meta"] = dict(details)
            validated.append((pair, float(rate), record))
        with self.database.transaction():
            snapshot = self.database.load_rates()
            history = self.database.load_history()
            cached_pairs = snapshot.get("pairs", {})
            if not isinstance(cached_pairs, dict) or (
                snapshot and "pairs" not in snapshot
            ):
                raise ValueError("Неверный формат кеша курсов")
            for cached in cached_pairs.values():
                if not isinstance(cached, dict) or "updated_at" not in cached:
                    raise ValueError("Неверный формат курса в кеше")
                timestamp_value(cached["updated_at"])
            if any(
                not isinstance(record, dict) or not isinstance(record.get("id"), str)
                for record in history
            ):
                raise ValueError("Неверный формат истории курсов")
            last_refresh = snapshot.get("last_refresh")
            if last_refresh is not None:
                timestamp_value(last_refresh)
            current = dict(cached_pairs)
            identifiers = {record["id"] for record in history}
            new_history = list(history)
            updated = 0
            for pair, rate, record in validated:
                if record["id"] not in identifiers:
                    new_history.append(record)
                    identifiers.add(record["id"])
                previous = current.get(pair)
                if previous is None or measured_at > timestamp_value(
                    previous["updated_at"]
                ):
                    current[pair] = {
                        "rate": rate,
                        "updated_at": timestamp,
                        "source": source,
                    }
                    updated += 1
            if new_history != history:
                self.database.save_history(new_history)
            if updated:
                if last_refresh is None or measured_at > timestamp_value(last_refresh):
                    last_refresh = timestamp
                self.database.save_rates(
                    {"pairs": current, "last_refresh": last_refresh}
                )
        return updated
