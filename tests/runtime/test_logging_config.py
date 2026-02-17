"""Logging configuration tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from palfrey.config import PalfreyConfig
from palfrey.logging_config import configure_logging


def test_configure_logging_with_default_level() -> None:
    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_level="debug")
    configure_logging(config)
    logger = logging.getLogger("palfrey.test")
    assert logger.isEnabledFor(logging.DEBUG)


def test_configure_logging_from_json_file(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {"std": {"format": "%(levelname)s %(message)s"}},
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "std",
                        "stream": "ext://sys.stdout",
                    }
                },
                "root": {"level": "INFO", "handlers": ["console"]},
            }
        ),
        encoding="utf-8",
    )

    config = PalfreyConfig(app="tests.fixtures.apps:http_app", log_config=str(config_path))
    configure_logging(config)
    logger = logging.getLogger("palfrey.test")
    assert logger.isEnabledFor(logging.INFO)
