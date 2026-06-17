#!/usr/bin/env python3
"""Backend HNP price-monitor scheduler (port 8105).

Endpoints:
  GET  /health
  GET  /monitor/status?session_id=
  POST /monitor/register  - arm monitor (+ optional session_state for web)
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_SCHED_DIR = Path(__file__).resolve().parent
_ROLES_DIR = _SCHED_DIR.parent
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
for _p in (_SCHED_DIR, _ROLES_DIR, _AGENT_DIR):
  if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from buyer_mcp_unified.price_monitor import register_price_monitor  # noqa: E402
import scheduler as sched_module  # noqa: E402
from role_logging import log_op, setup_role_logger  # noqa: E402

_logger = setup_role_logger("monitor-scheduler", console=True)

PORT = int(
    os.environ.get(
        "UNIFIED_MONITOR_SCHEDULER_PORT",
        os.environ.get("MONITOR_SCHEDULER_PORT", "8105"),
    )
)


def _is_mandate_id(value: str) -> bool:
  v = (value or "").strip()
  return v.startswith("open_chk_") or v.startswith("open_pay_")


def _apply_open_mandate_fields(
    body: dict[str, Any],
    session_state: dict[str, Any],
) -> str | None:
  """Map register body fields to session state; reject SD-JWT strings."""
  for field, state_key in (
      ("open_checkout_mandate", "app:open_checkout_mandate_id"),
      ("open_payment_mandate", "app:open_payment_mandate_id"),
  ):
    raw = body.get(field)
    if not raw:
      continue
    value = str(raw).strip()
    if "~" in value or not _is_mandate_id(value):
      return (
          f"{field} must be an open mandate id (open_chk_… / open_pay_…), "
          "not an SD-JWT token."
      )
    session_state.setdefault(state_key, value)
  return None


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
  length = int(handler.headers.get("Content-Length", 0) or 0)
  if length <= 0:
    return {}
  raw = handler.rfile.read(length)
  try:
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
      return data
  except (json.JSONDecodeError, UnicodeDecodeError):
    pass
  return {}


class MonitorSchedulerHandler(BaseHTTPRequestHandler):
  """HTTP handler for monitor scheduler status/register."""

  def log_message(self, format, *args):
    msg = args[0] if args else format
    log_op(_logger, "monitor-scheduler", "HTTP", message=msg)

  def _cors(self) -> None:
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")

  def do_OPTIONS(self) -> None:
    self.send_response(204)
    self._cors()
    self.end_headers()

  def _json_response(self, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body, ensure_ascii=True).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(payload)))
    self._cors()
    self.end_headers()
    self.wfile.write(payload)

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    qs = parse_qs(parsed.query)
    session_id = (qs.get("session_id") or [""])[0].strip()

    if parsed.path in ("/", "/health"):
      self._json_response(200, {
          "status": "ok",
          "role": "monitor_scheduler_unified",
          "endpoints": [
              "GET /monitor/status?session_id=",
              "POST /monitor/register",
          ],
      })
      return

    if parsed.path == "/monitor/status":
      if not session_id:
        self._json_response(400, {
            "error": "session_id_required",
            "message": "session_id query param required",
        })
        return
      self._json_response(200, sched_module.get_public_status(session_id))
      return

    self.send_response(404)
    self._cors()
    self.end_headers()

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    body = _read_json_body(self)

    if parsed.path == "/monitor/register":
      session_id = str(body.get("session_id", "")).strip()
      item_id = str(body.get("item_id", "")).strip()
      price_cap = body.get("price_cap")
      if not session_id or not item_id or price_cap is None:
        self._json_response(400, {
            "error": "invalid_request",
            "message": "session_id, item_id, and price_cap are required.",
        })
        return
      session_state = body.get("session_state")
      if not isinstance(session_state, dict):
        session_state = {}
      mandate_err = _apply_open_mandate_fields(body, session_state)
      if mandate_err:
        self._json_response(400, {
            "error": "invalid_mandate_id",
            "message": mandate_err,
        })
        return
      if body.get("open_checkout_hash"):
        session_state.setdefault("app:open_checkout_hash", body.get("open_checkout_hash"))
      if body.get("payment_method"):
        session_state.setdefault("ap2:payment_method", body.get("payment_method"))
      session_state.setdefault("ap2:presence_mode", "hnp")

      result = register_price_monitor(
          session_id,
          item_id,
          price_cap,
          interval_minutes=body.get("interval_minutes", 5),
          currency=str(body.get("currency", "USD")),
          item_name=str(body.get("item_name", "")),
          merchant=str(body.get("merchant", "shoe")),
          max_ticks=int(body.get("max_ticks", 0) or 0),
          session_state=session_state or None,
      )
      if result.get("status") == "ok":
        threading.Thread(
            target=sched_module.tick_session_now,
            args=(session_id,),
            name=f"ap2-monitor-immediate-{session_id[:16]}",
            daemon=True,
        ).start()
      status = 200 if result.get("status") == "ok" else 400
      self._json_response(status, result)
      return

    self.send_response(404)
    self._cors()
    self.end_headers()


class ReuseHTTPServer(HTTPServer):
  allow_reuse_address = True


if __name__ == "__main__":
  sched_module.start_scheduler()
  try:
    server = ReuseHTTPServer(("127.0.0.1", PORT), MonitorSchedulerHandler)
  except OSError as e:
    if e.errno == 48:
      print(
          f"Error: Port {PORT} is already in use. "
          f"Kill the process with: lsof -ti:{PORT} | xargs kill -9"
      )
    raise
  print(f"Monitor scheduler: http://localhost:{PORT}/")
  server.serve_forever()
