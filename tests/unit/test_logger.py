# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import uuid
from typing import Generator, Optional

import pytest

from charmed_analytics_ci.logger import setup_logger


@pytest.fixture()
def logger_setup(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[logging.Logger, None, None]:
    """Fixture to set up a unique logger with a temporary log file."""
    unique_logger_name = f"test_logger_{uuid.uuid4().hex}"
    log_file_path = tmp_path_factory.mktemp("logs") / "test.log"

    logger = logging.getLogger(unique_logger_name)
    logger.handlers.clear()

    # Recreate with setup
    logger = setup_logger(name=unique_logger_name, log_file_path=str(log_file_path))

    logger.debug("Logger initialized")  # Force file creation
    yield logger

    if log_file_path.exists():
        os.remove(log_file_path)


def get_log_file_path(logger: logging.Logger) -> Optional[str]:
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            return handler.baseFilename
    return None


@pytest.mark.parametrize(
    "log_level, log_message, expected_prefix",
    [
        (logging.DEBUG, "Debugging...", "[DEBUG]"),
        (logging.INFO, "Just info", ""),  # INFO has no prefix in console
        (logging.WARNING, "A warning!", "[WARNING]"),
        (logging.ERROR, "Something broke", "[ERROR]"),
    ],
)
def test_file_logs(
    logger_setup: logging.Logger, log_level: int, log_message: str, expected_prefix: str
):
    logger = logger_setup
    logger.log(log_level, log_message)

    log_path = get_log_file_path(logger)
    assert log_path is not None

    with open(log_path) as f:
        content = f.read()

    assert log_message in content
    if expected_prefix:
        assert expected_prefix in content


@pytest.mark.parametrize(
    "log_level, log_message, expected_prefix",
    [
        (logging.INFO, "Info is clean", ""),
        (logging.WARNING, "Watch out!", "[WARNING]"),
        (logging.ERROR, "Big issue", "[ERROR]"),
    ],
)
def test_console_logs(
    tmp_path_factory: pytest.TempPathFactory,
    capfd: pytest.CaptureFixture,
    log_level: int,
    log_message: str,
    expected_prefix: str,
):
    """Test that logs include the correct prefix in console output."""
    # Setup logger *after* capfd is active
    unique_logger_name = f"test_logger_{uuid.uuid4().hex}"
    log_file_path = tmp_path_factory.mktemp("logs") / "console.log"
    logger = setup_logger(name=unique_logger_name, log_file_path=str(log_file_path))

    logger.log(log_level, log_message)

    captured = capfd.readouterr()
    assert log_message in captured.out

    if expected_prefix:
        assert expected_prefix in captured.out
    else:
        assert "[" not in captured.out
