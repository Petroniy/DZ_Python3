import inspect
import json
import logging
import math
from datetime import UTC, datetime
from functools import wraps

from valutatrade_hub.logging_config import setup_logging


def log_action(action, verbose=False):
    """Записывает результат операции и пробрасывает исключения."""

    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            setup_logging()
            arguments = inspect.signature(function).bind(*args, **kwargs).arguments
            service = arguments.get("self")
            user = getattr(service, "current_user", None)
            username = getattr(user, "username", None)
            if isinstance(user, dict):
                username = user.get("username")
            entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": action.upper(),
                "username": username,
                "currency_code": arguments.get("currency_code"),
                "amount": arguments.get("amount"),
                "rate": None,
                "base": "USD",
            }
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                entry.update(
                    result="ERROR",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                _write_entry(entry)
                raise
            if isinstance(result, dict):
                for key in ("username", "rate", "base"):
                    if key in result:
                        entry[key] = result[key]
                if verbose:
                    entry["before"] = result.get("before")
                    entry["after"] = result.get("after")
            entry["result"] = "OK"
            _write_entry(entry)
            return result

        return wrapper

    return decorator


def _write_entry(entry):
    for key, value in entry.items():
        if isinstance(value, float) and not math.isfinite(value):
            entry[key] = str(value)
    logging.getLogger("valutatrade.actions").info(
        json.dumps(entry, ensure_ascii=False, allow_nan=False, default=str)
    )
