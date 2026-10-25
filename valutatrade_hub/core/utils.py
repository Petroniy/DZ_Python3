import math
from datetime import datetime, timezone


def validate_currency_code(code):
    """Проверяет формат и возвращает код в верхнем регистре."""
    if not isinstance(code, str):
        raise ValueError("Код валюты должен быть строкой")
    normalized = code.upper()
    if (
        not 2 <= len(normalized) <= 5
        or not normalized.isascii()
        or not normalized.isalpha()
    ):
        raise ValueError("Код валюты должен содержать от 2 до 5 латинских букв")
    return normalized


def validate_number(value, *, positive=False):
    """Проверяет число для баланса или суммы операции."""
    message = (
        "'amount' должен быть положительным числом"
        if positive
        else "Баланс должен быть неотрицательным числом"
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(message)
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError(message) from error
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(message)
    return value


def utc_now():
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def parse_timestamp(value):
    """Возвращает время с часовым поясом для сравнения сроков."""
    if not isinstance(value, str):
        raise ValueError("Некорректная дата обновления курса")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_rate_fresh(record, ttl):
    if not isinstance(record, dict):
        return False
    try:
        validate_number(record.get("rate"), positive=True)
        age = (
            datetime.now(timezone.utc) - parse_timestamp(record["updated_at"])
        ).total_seconds()
        return 0 <= age <= ttl
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
