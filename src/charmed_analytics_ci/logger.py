# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class _LevelAwareFormatter(logging.Formatter):
    """Adjust log formatting based on the level (INFO vs others)."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        if record.levelno == logging.INFO:
            self._style._fmt = "%(message)s"
        else:
            self._style._fmt = "[%(levelname)s] %(message)s"
        return super().format(record)


def setup_logger(
    name: str = "charmed_analytics_ci",
    log_file_path: str | None = None,
    file_log_level: int = logging.DEBUG,
    console_log_level: int = logging.INFO,
) -> logging.Logger:
    """
    Set up a logger with configurable console and file output.

    Args:
        name: Name of the logger (module-level reuse).
        log_file_path: Optional path to a log file. Defaults to /tmp/chaci.log.
        file_log_level: Logging level for file logs (default: DEBUG).
        console_log_level: Logging level for console logs (default: INFO).

    Returns:
        A configured logger.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Prevent adding duplicate handlers on reuse

    logger.setLevel(min(console_log_level, file_log_level))

    # Console handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(console_log_level)
    stream_handler.setFormatter(_LevelAwareFormatter())
    logger.addHandler(stream_handler)

    # File handler
    if log_file_path is None:
        log_dir = os.path.join("/tmp", "chaci")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "chaci.log")

    file_handler = RotatingFileHandler(log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(file_log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(module)s:%(funcName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    return logger
