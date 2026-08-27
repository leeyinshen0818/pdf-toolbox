from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pdf_toolbox.resources import user_data_dir


LOG_FILENAME = "pdf-toolbox.log"


def log_file_path() -> Path:
    return user_data_dir() / "logs" / LOG_FILENAME


def configure_logging() -> Path:
    path = log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in list(root_logger.handlers):
        if getattr(handler, "_pdf_toolbox_handler", False):
            if Path(getattr(handler, "baseFilename", "")) == path:
                return path
            root_logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler._pdf_toolbox_handler = True
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(handler)
    logging.captureWarnings(True)
    return path
