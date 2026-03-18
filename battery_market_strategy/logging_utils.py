from __future__ import annotations

import logging
import sys

from .config import AppConfig


def setup_logging(config: AppConfig) -> None:
    root_logger = logging.getLogger()
    configured_path = getattr(root_logger, "_battery_market_strategy_log_file", None)
    if configured_path == str(config.log_file_path):
        return

    config.log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(config.log_file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    setattr(root_logger, "_battery_market_strategy_log_file", str(config.log_file_path))
