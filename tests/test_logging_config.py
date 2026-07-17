from __future__ import annotations

import logging
import logging.handlers

from bot.logging_config import setup_logging


def test_setup_logging_creates_logger_with_level(tmp_path):
    logger = setup_logging(level="DEBUG", log_dir=str(tmp_path / "logs"))

    assert logger.name == "bot"
    assert logger.level == logging.DEBUG


def test_setup_logging_adds_console_and_file_handlers(tmp_path):
    logger = setup_logging(level="INFO", log_dir=str(tmp_path / "logs"))

    console_handlers = [h for h in logger.handlers if type(h) is logging.StreamHandler]
    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]

    assert len(console_handlers) == 1
    assert len(file_handlers) == 1


def test_setup_logging_creates_log_file_on_disk(tmp_path):
    log_dir = tmp_path / "logs"

    setup_logging(level="INFO", log_dir=str(log_dir), log_file="test.log")

    assert (log_dir / "test.log").exists()


def test_setup_logging_replaces_handlers_on_repeated_calls(tmp_path):
    setup_logging(level="INFO", log_dir=str(tmp_path / "logs"))
    logger = setup_logging(level="WARNING", log_dir=str(tmp_path / "logs"))

    assert logger.level == logging.WARNING
    assert len(logger.handlers) == 2
