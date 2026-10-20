import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging():
    """Настраивает файлы логов и их ротацию."""
    settings = SettingsLoader()
    directory = Path(settings.get("logs_dir")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for name, filename in (
        ("valutatrade.actions", "actions.log"),
        ("valutatrade.parser", "parser.log"),
    ):
        logger = logging.getLogger(name)
        target = directory / filename
        for handler in logger.handlers[:]:
            if getattr(handler, "baseFilename", None) != str(target):
                logger.removeHandler(handler)
                handler.close()
        if not logger.handlers:
            handler = RotatingFileHandler(
                target,
                maxBytes=settings.get("log_max_bytes"),
                backupCount=settings.get("log_backup_count"),
                encoding="utf-8",
            )
            pattern = "%(message)s"
            if name.endswith("parser"):
                pattern = "%(asctime)s %(levelname)s %(message)s"
            handler.setFormatter(logging.Formatter(pattern))
            logger.addHandler(handler)
        logger.setLevel(settings.get("log_level"))
        logger.propagate = False
