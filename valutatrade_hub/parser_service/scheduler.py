import argparse
import logging
import math
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater


def positive_interval(value):
    """Проверяет период обновления в секундах."""
    try:
        interval = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("Интервал должен быть числом") from None
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("Интервал должен быть положительным")
    return interval


def main(argv=None):
    """Запускает обновление один раз или с указанным периодом."""
    parser = argparse.ArgumentParser(description="Периодическое обновление курсов")
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=ParserConfig().UPDATE_INTERVAL_SECONDS,
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--source", choices=("coingecko", "exchangerate"))
    args = parser.parse_args(argv)
    interval = positive_interval(args.interval)
    setup_logging()
    logger = logging.getLogger("valutatrade.parser")
    updater = RatesUpdater()
    try:
        while True:
            started = time.monotonic()
            try:
                updater.run_update(source=args.source)
            except ApiRequestError as error:
                logger.error("Ошибка обновления: %s", error)
                if args.once:
                    return 1
            if args.once:
                return 0
            remaining = max(0, interval - (time.monotonic() - started))
            while remaining > 0:
                time.sleep(min(remaining, 1))
                remaining = max(0, interval - (time.monotonic() - started))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
