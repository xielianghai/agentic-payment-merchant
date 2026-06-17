"""File-backed session state for openclaw buyer MCP (replaces ADK tool_context.state)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class _State(dict):
  """Minimal stand-in for ADK session state."""


class ToolContext:
  def __init__(self, state: _State | None = None):
    self.state = state if state is not None else _State()


def _temp_db() -> Path:
  unified = Path(__file__).resolve().parents[1]
  return Path(os.environ.get("TEMP_DB_DIR", unified.parent / ".temp-db"))


def _session_path(session_id: str) -> Path:
  safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", (session_id or "default").strip())[:200]
  return _temp_db() / f"session_{safe}.json"


def session_id_from_filename(stem: str) -> str:
  """Decode a session id from ``session_<safe>.json`` stem (inverse of _session_path)."""
  sid = stem[len("session_") :] if stem.startswith("session_") else stem
  # Filename sanitization maps ``@`` → ``_`` (e.g. ``uuid@im.wechat`` → ``uuid_im.wechat``).
  if "_im.wechat" in sid and "@" not in sid:
    sid = sid.replace("_im.wechat", "@im.wechat", 1)
  return sid


def load_tool_context(session_id: str) -> ToolContext:
  path = _session_path(session_id)
  if not path.is_file():
    return ToolContext(_State())
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
      return ToolContext(_State(data))
  except (OSError, json.JSONDecodeError, TypeError):
    pass
  return ToolContext(_State())


def save_tool_context(session_id: str, ctx: ToolContext) -> None:
  path = _session_path(session_id)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
      json.dumps(dict(ctx.state), indent=2, ensure_ascii=True),
      encoding="utf-8",
  )


def run_with_session(
    session_id: str,
    fn: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
  """Load session, invoke tool fn, persist state."""
  ctx = load_tool_context(session_id)
  kwargs.setdefault("tool_context", ctx)
  result = fn(*args, **kwargs)
  save_tool_context(session_id, ctx)
  return result
