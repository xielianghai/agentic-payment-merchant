"""Backend scheduler loop for HNP price monitors."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

_SCHED_DIR = Path(__file__).resolve().parent
_ROLES_DIR = _SCHED_DIR.parent
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
for _p in (_SCHED_DIR, _ROLES_DIR, _AGENT_DIR):
  if str(_p) not in sys.path:
    sys.path.insert(0, str(_p))

from buyer_mcp_unified.price_monitor import (
  complete_price_monitor_tick,
  get_price_monitor_status,
  list_active_monitors,
  mark_monitor_error,
  mark_purchased,
  recover_stuck_purchasing_monitors,
  try_acquire_purchasing_lock,
)
import notify
from purchase_executor import (
  check_product_for_monitor,
  evaluate_constraints,
  execute_hnp_purchase,
)

_logger = logging.getLogger("monitor-scheduler")

_loop_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.Lock()


def _poll_seconds() -> float:
  try:
    return max(2.0, float(os.environ.get("MONITOR_SCHEDULER_POLL_SECONDS", "5")))
  except (TypeError, ValueError):
    return 5.0


def _tick_one(session_id: str, monitor: dict[str, Any]) -> None:
  now = time.time()
  next_tick = float(monitor.get("next_tick_at", now))
  if now < next_tick:
    return

  try:
    product = asyncio.run(check_product_for_monitor(monitor))
  except Exception as exc:
    _logger.warning("check_product failed session=%s: %s", session_id, exc)
    mark_monitor_error(session_id, str(exc))
    return

  if product.get("error"):
    err = str(product.get("error", "")).lower()
    msg = str(product.get("message", "")).lower()
    not_found = "not_found" in err or "not found" in msg
    if not_found:
      result = complete_price_monitor_tick(
          session_id,
          current_price=0,
          available=False,
          meets_constraints=False,
          not_found=True,
          message=str(product.get("message") or product.get("error") or "Item not found."),
      )
      notify.notify_monitor_stopped(session_id, result)
      return
    mark_monitor_error(
        session_id,
        str(product.get("message") or product.get("error") or "check_product failed"),
    )
    return

  price = float(product.get("price") or product.get("current_price") or 0)
  available = bool(product.get("available", product.get("in_stock", False)))
  currency = str(product.get("currency") or monitor.get("currency") or "USD")

  try:
    constraints = evaluate_constraints(
        session_id,
        price=price,
        currency=currency,
        available=available,
        merchant=str(monitor.get("merchant") or "shoe"),
    )
  except Exception as exc:
    _logger.warning("check_constraints failed session=%s: %s", session_id, exc)
    mark_monitor_error(session_id, str(exc))
    return

  if constraints.get("error"):
    err_msg = str(
        constraints.get("message") or constraints.get("error") or "constraint_check_failed"
    )
    _logger.warning(
        "constraint error session=%s: %s",
        session_id,
        err_msg,
    )
    mark_monitor_error(session_id, err_msg)
    notify.notify_monitor_stopped(
        session_id,
        {"user_message": f"Monitor stopped: {err_msg}"},
    )
    return

  meets = bool(constraints.get("meets_constraints", False))
  msg = str(constraints.get("message") or "")
  violations = constraints.get("violations")
  if not meets and available and violations:
    _logger.info(
        "constraints not met session=%s price=%s cap=%s violations=%s",
        session_id,
        price,
        monitor.get("price_cap"),
        violations,
    )

  if meets and available:
    if not try_acquire_purchasing_lock(session_id):
      _logger.info("skip purchase; lock held session=%s", session_id)
      return
    _logger.info("constraints met; purchasing session=%s", session_id)
    purchase = execute_hnp_purchase(session_id, monitor)
    if purchase.get("error"):
      mark_monitor_error(session_id, str(purchase.get("message") or purchase.get("error")))
      notify.notify_monitor_stopped(
          session_id,
          {
              "user_message": (
                  f"Monitor stopped: purchase failed — "
                  f"{purchase.get('message') or purchase.get('error')}"
              ),
          },
      )
      return
    mark_purchased(session_id, purchase)
    notify.notify_purchase_complete(session_id, purchase)
    return

  result = complete_price_monitor_tick(
      session_id,
      current_price=price,
      available=available,
      meets_constraints=meets,
      message=msg,
  )
  if result.get("should_stop"):
    notify.notify_monitor_stopped(session_id, result)
  elif result.get("status") == "ok":
    notify.notify_monitor_tick(session_id, result)


def run_scheduler_cycle() -> None:
  recover_stuck_purchasing_monitors()
  for session_id, monitor in list_active_monitors():
    try:
      _tick_one(session_id, monitor)
    except Exception as exc:
      _logger.exception("tick failed session=%s: %s", session_id, exc)


def tick_session_now(session_id: str) -> None:
  """Run one monitor tick immediately after register (e.g. price already ≤ cap)."""
  from buyer_mcp_unified.price_monitor import _STATE_KEY
  from buyer_mcp_unified.session_store import load_tool_context
  from trusted_surface_gate import _canonical_session_id

  sid = _canonical_session_id((session_id or "").strip())
  if not sid:
    return
  ctx = load_tool_context(sid)
  monitor = ctx.state.get(_STATE_KEY)
  if not isinstance(monitor, dict):
    return
  if monitor.get("stopped") or monitor.get("purchased"):
    return
  if monitor.get("purchasing"):
    return
  if not monitor.get("active"):
    return
  _tick_one(sid, monitor)


def _loop() -> None:
  _logger.info("monitor scheduler loop started (poll=%ss)", _poll_seconds())
  while not _stop_event.is_set():
    with _lock:
      run_scheduler_cycle()
    _stop_event.wait(_poll_seconds())
  _logger.info("monitor scheduler loop stopped")


def start_scheduler() -> None:
  global _loop_thread
  if _loop_thread and _loop_thread.is_alive():
    return
  _stop_event.clear()
  _loop_thread = threading.Thread(target=_loop, name="ap2-monitor-scheduler", daemon=True)
  _loop_thread.start()


def stop_scheduler() -> None:
  _stop_event.set()
  if _loop_thread and _loop_thread.is_alive():
    _loop_thread.join(timeout=5)


def get_public_status(session_id: str) -> dict[str, Any]:
  return get_price_monitor_status(session_id)
