"""Centralised, safe logging configuration for API and worker processes."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).with_name("logs")

def configure_logging(debug: bool = False) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cropverse")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    console = logging.StreamHandler(); console.setFormatter(formatter)
    app_file = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"); app_file.setFormatter(formatter)
    error_file = RotatingFileHandler(LOG_DIR / "error.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"); error_file.setLevel(logging.ERROR); error_file.setFormatter(formatter)
    logger.addHandler(console); logger.addHandler(app_file); logger.addHandler(error_file)
    return logger
