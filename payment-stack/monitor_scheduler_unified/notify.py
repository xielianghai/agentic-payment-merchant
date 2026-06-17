"""User notifications after backend monitor ticks / purchases."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_ROLES_DIR = Path(__file__).resolve().parents[1]
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))

from trusted_surface_gate import _canonical_session_id, _openclaw_session_key  # noqa: E402


def notify_monitor_tick(session_id: str, payload: dict[str, Any]) -> None:
  """Optional tick update (openclaw only when user_message present)."""
  if payload.get("status") != "ok":
    return
  message = str(payload.get("user_message") or payload.get("feishu_user_message") or "")
  if message:
    _wake_openclaw(session_id, message, name="AP2 Price Monitor")


def notify_purchase_complete(session_id: str, purchase_result: dict[str, Any]) -> None:
  pc = purchase_result.get("purchase_complete")
  if not isinstance(pc, dict):
    pc = purchase_result
  display = pc.get("display_name") or pc.get("item_id") or "item"
  order_id = pc.get("order_id") or "—"
  pm = pc.get("payment_method") or "card"
  total = pc.get("total_cents")
  currency = pc.get("currency") or "USD"
  total_line = ""
  if total is not None:
    try:
      total_line = f" · **Total:** {float(total) / 100:.2f} {currency}"
    except (TypeError, ValueError):
      pass
  message = (
      f"Purchase complete (backend scheduler).\n"
      f"**Product:** {display}{total_line}\n"
      f"**Order:** {order_id} · **Payment:** {str(pm).upper()}\n"
      f"**Monitor ref:** `{_canonical_session_id(session_id)}`"
  )
  _wake_openclaw(session_id, message, name="AP2 Purchase Complete")


def notify_monitor_stopped(session_id: str, payload: dict[str, Any]) -> None:
  message = str(payload.get("user_message") or payload.get("feishu_user_message") or "")
  if message:
    _wake_openclaw(session_id, message, name="AP2 Price Monitor")


def _wake_openclaw(session_id: str, message: str, *, name: str) -> None:
  if os.environ.get("AP2_OPENCLAW_HOOK_ENABLED", "1").strip().lower() in (
      "0",
      "false",
      "no",
  ):
    return
  hook_url = os.environ.get(
      "AP2_OPENCLAW_HOOK_URL",
      "http://127.0.0.1:18789/hooks/agent",
  ).strip()
  hook_token = os.environ.get("AP2_OPENCLAW_HOOK_TOKEN", "").strip()
  if not hook_url or not hook_token:
    return
  session_key = _openclaw_session_key(session_id)
  if not session_key:
    return
  canonical_sid = _canonical_session_id(session_id)
  payload: dict[str, Any] = {
      "message": message,
      "sessionKey": session_key,
      "channel": "openclaw-weixin" if "@im.wechat" in canonical_sid.lower() else "last",
      "wakeMode": "now",
      "deliver": True,
      "name": name,
  }
  if "@im.wechat" in canonical_sid.lower():
    payload["to"] = canonical_sid
  body = json.dumps(payload).encode("utf-8")
  req = urllib.request.Request(
      hook_url,
      data=body,
      headers={
          "Content-Type": "application/json",
          "Authorization": f"Bearer {hook_token}",
      },
      method="POST",
  )

  def _post() -> None:
    try:
      with urllib.request.urlopen(req, timeout=10):
        pass
    except (urllib.error.URLError, OSError):
      pass

  threading.Thread(target=_post, daemon=True).start()
