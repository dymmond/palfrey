from __future__ import annotations

import json
from pathlib import Path

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "default": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}

Path("logging.json").write_text(json.dumps(logging_config, indent=2), encoding="utf-8")
