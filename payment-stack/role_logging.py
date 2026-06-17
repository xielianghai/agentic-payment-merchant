"""Shared logging for unified AP2 demo roles — file + console (stdout).

Set AP2_CONSOLE_LOG=0 to disable console handlers (file logs remain).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from constants_unified import LOGS_DIR

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"
_CONFIGURED: set[str] = set()


def setup_role_logger(
    name: str,
    *,
    log_file: str | Path | None = None,
    level: int = logging.INFO,
    console: bool | None = None,
) -> logging.Logger:
  """Return a logger with file and/or console handlers (idempotent per name)."""
  logger = logging.getLogger(name)
  if name in _CONFIGURED:
    return logger

  logger.setLevel(level)
  logger.propagate = False
  formatter = logging.Formatter(_LOG_FORMAT)

  if log_file is not None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(Path(log_file), mode="w", encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

  use_console = (
      console
      if console is not None
      else os.environ.get("AP2_CONSOLE_LOG", "1") != "0"
  )
  if use_console:
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

  _CONFIGURED.add(name)
  return logger


def log_op(logger: logging.Logger, role: str, op: str, **fields: Any) -> None:
  """One-line structured log for a key operation."""
  detail = " ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)
  if detail:
    logger.info("[%s] %s %s", role, op, detail)
  else:
    logger.info("[%s] %s", role, op)


def log_op_result(
    logger: logging.Logger,
    role: str,
    op: str,
    result: dict[str, Any] | None,
    **fields: Any,
) -> None:
  """Log completion of an operation; WARN when result contains error."""
  if isinstance(result, dict) and result.get("error"):
    log_op(
        logger,
        role,
        f"{op} FAILED",
        error=result.get("error"),
        message=result.get("message"),
        **fields,
    )
  else:
    keys = list(result.keys()) if isinstance(result, dict) else None
    log_op(logger, role, f"{op} OK", keys=keys, **fields)
