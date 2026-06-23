"""Structured logging for VI credential and mock network flows."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from constants_unified import LOGS_DIR
from role_logging import log_op, setup_role_logger

_LOGGER: logging.Logger | None = None


def get_vi_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        level = (
            logging.DEBUG
            if os.environ.get("AP2_VI_DEBUG", "").strip() == "1"
            else logging.INFO
        )
        log_dir = Path(os.environ.get("LOGS_DIR", str(LOGS_DIR)))
        _LOGGER = setup_role_logger(
            "vi-unified",
            log_file=log_dir / "vi-unified.log",
            level=level,
        )
    return _LOGGER


def vi_log(op: str, **fields: Any) -> None:
    """Log a VI milestone at INFO (always visible in vi-unified.log)."""
    log_op(get_vi_logger(), "vi", op, **fields)


def vi_debug(op: str, **fields: Any) -> None:
    """Verbose VI detail; enable with AP2_VI_DEBUG=1."""
    logger = get_vi_logger()
    detail = " ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)
    if detail:
        logger.debug("[vi] %s %s", op, detail)
    else:
        logger.debug("[vi] %s", op)
