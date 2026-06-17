"""HNP price-monitor state (backend scheduler drives ticks; no OpenClaw cron)."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from item_display_unified import resolve_display_name
from buyer_mcp_unified.session_store import (
    ToolContext,
    load_tool_context,
    save_tool_context,
    session_id_from_filename,
)

_AGENT_DIR = Path(__file__).resolve().parents[1] / "shopping_agent_unified"
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))
from trusted_surface_gate import _canonical_session_id  # noqa: E402

_STATE_KEY = "ap2:price_monitor"
_MIN_INTERVAL_MINUTES = 1
_MAX_INTERVAL_MINUTES = 1440
_DEFAULT_MAX_TICKS = 288

_STOP_REASONS = {
    "checkout_started": "Checkout started — monitor stops.",
    "purchased": "Purchase completed — monitor stops.",
    "constraints_met": "Constraints met; purchase handled by backend scheduler.",
    "not_found": "Item not found in merchant inventory — monitor stops.",
    "cancelled": "User cancelled monitoring — monitor stops.",
    "max_ticks": "Max monitoring ticks reached — monitor stops.",
    "error": "Unrecoverable error during monitoring — monitor stops.",
}


def _sid(session_id: str) -> str:
  return _canonical_session_id((session_id or "").strip())


def _normalize_item_id(item_id: str) -> str:
  """Normalize slug variants (preview_ prefix, hyphens, ``foo.0`` → ``foo_0``)."""
  s = (item_id or "").strip().lower()
  if s.startswith("preview_"):
    s = s[len("preview_") :]
  s = s.replace("-", "_")
  return re.sub(r"\.(\d+)$", r"_\1", s)


def _monitor_from_context(ctx: ToolContext) -> dict[str, Any] | None:
  raw = ctx.state.get(_STATE_KEY)
  return raw if isinstance(raw, dict) else None


def _clamp_interval_minutes(interval_minutes: float | int) -> int:
  try:
    minutes = int(interval_minutes)
  except (TypeError, ValueError):
    minutes = 5
  return max(_MIN_INTERVAL_MINUTES, min(_MAX_INTERVAL_MINUTES, minutes))


def _currency(value: Any) -> str:
  return str(value or "USD").strip().upper() or "USD"


def _format_money(value: Any, currency: str) -> str:
  try:
    amount = float(value)
  except (TypeError, ValueError):
    return f"{value} {currency}"
  return f"{amount:.2f} {currency}"


def list_session_files() -> list[Path]:
  from buyer_mcp_unified.session_store import _temp_db

  root = _temp_db()
  if not root.is_dir():
    return []
  return sorted(root.glob("session_*.json"))


def session_id_from_path(path: Path) -> str:
  return session_id_from_filename(path.stem)


def list_active_monitors() -> list[tuple[str, dict[str, Any]]]:
  """Return (session_id, monitor dict) for monitors that should be scheduled."""
  out: list[tuple[str, dict[str, Any]]] = []
  for path in list_session_files():
    sid = session_id_from_path(path)
    ctx = load_tool_context(sid)
    monitor = _monitor_from_context(ctx)
    if not monitor:
      continue
    if monitor.get("stopped") or monitor.get("purchased"):
      continue
    if not monitor.get("active"):
      continue
    if monitor.get("purchasing"):
      continue
    out.append((sid, monitor))
  return out


def merge_session_state(session_id: str, extra: dict[str, Any] | None) -> None:
  """Merge keys into persisted session state (web bridge / open mandate sync)."""
  sid = _sid(session_id)
  if not sid or not extra:
    return
  ctx = load_tool_context(sid)
  for key, value in extra.items():
    if value is not None:
      ctx.state[str(key)] = value
  save_tool_context(sid, ctx)


def stop_price_monitor(session_id: str, reason: str = "cancelled") -> dict[str, Any]:
  """Mark a monitor stopped."""
  sid = _sid(session_id)
  if not sid:
    return {"error": "session_id_required", "message": "Pass session_id for this chat."}
  normalized = (reason or "cancelled").strip().lower()
  if normalized not in _STOP_REASONS:
    normalized = "cancelled"
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx)
  if monitor:
    now = time.time()
    monitor["active"] = False
    monitor["stopped"] = True
    monitor["stop_reason"] = normalized
    monitor["next_tick_at"] = now
    ctx.state[_STATE_KEY] = monitor
    save_tool_context(sid, ctx)
  return {
      "status": "ok",
      "session_id": sid,
      "monitor_ref": sid,
      "stop_reason": normalized,
      "had_monitor": bool(monitor),
      "message": _STOP_REASONS.get(normalized, "Monitor stopped."),
  }


def _open_mandate_file_exists(mandate_id: str) -> bool:
  mid = (mandate_id or "").strip()
  if not mid.startswith(("open_chk_", "open_pay_")):
    return False
  from buyer_mcp_unified.session_store import _temp_db

  return (_temp_db() / f"{mid}.sdjwt").is_file()


def _validate_open_mandates_in_session(ctx: ToolContext) -> str | None:
  checkout = str(ctx.state.get("app:open_checkout_mandate_id", "")).strip()
  payment = str(ctx.state.get("app:open_payment_mandate_id", "")).strip()
  if checkout and not _open_mandate_file_exists(checkout):
    return f"Open checkout mandate file missing: {checkout}"
  if payment and not _open_mandate_file_exists(payment):
    return f"Open payment mandate file missing: {payment}"
  return None


def recover_stuck_purchasing_monitors() -> None:
  """Fail monitors left in purchasing state after a crash mid-purchase."""
  timeout = int(os.environ.get("MONITOR_PURCHASING_TIMEOUT_S", "300"))
  now = time.time()
  for path in list_session_files():
    sid = session_id_from_path(path)
    ctx = load_tool_context(sid)
    monitor = _monitor_from_context(ctx)
    if not monitor or not monitor.get("purchasing") or monitor.get("purchased"):
      continue
    started = float(
        monitor.get("purchasing_started_at")
        or monitor.get("last_tick_at")
        or monitor.get("started_at")
        or 0
    )
    if started and now - started > timeout:
      mark_monitor_error(sid, "Purchase timed out; monitor stopped.")


def register_price_monitor(
    session_id: str,
    item_id: str,
    price_cap: float | int,
    interval_minutes: float | int = 5,
    *,
    currency: str = "USD",
    item_name: str = "",
    merchant: str = "",
    max_ticks: int = 0,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Arm HNP price monitoring (backend scheduler on :8105 drives ticks)."""
  sid = _sid(session_id)
  iid = _normalize_item_id(item_id)
  if not sid:
    return {"error": "session_id_required", "message": "Pass session_id for this chat."}
  if not iid:
    return {"error": "item_id_required", "message": "Pass item_id from the signed mandate."}
  interval = _clamp_interval_minutes(interval_minutes)
  try:
    cap = int(max_ticks)
  except (TypeError, ValueError):
    cap = 0
  if cap <= 0:
    cap = _DEFAULT_MAX_TICKS
  now = time.time()
  if session_state:
    merge_session_state(sid, session_state)
  ctx = load_tool_context(sid)
  mandate_err = _validate_open_mandates_in_session(ctx)
  if mandate_err:
    return {
        "error": "open_mandates_missing",
        "message": mandate_err,
    }
  display = resolve_display_name(
      iid,
      merchant=merchant or "shoe",
      item_name=item_name,
  )
  ctx.state[_STATE_KEY] = {
      "active": True,
      "item_id": iid,
      "item_name": display,
      "display_name": display,
      "merchant": (merchant or "shoe").strip().lower() or "shoe",
      "price_cap": float(price_cap),
      "currency": _currency(currency),
      "interval_minutes": interval,
      "max_ticks": cap,
      "started_at": now,
      "last_tick_at": None,
      "next_tick_at": now,
      "tick_count": 0,
      "stopped": False,
      "stop_reason": None,
      "purchasing": False,
      "purchased": False,
      "purchase_result": None,
      "last_monitoring_artifact": None,
  }
  save_tool_context(sid, ctx)
  scheduler_port = int(os.environ.get("UNIFIED_MONITOR_SCHEDULER_PORT", "8105"))
  scheduler_url = f"http://localhost:{scheduler_port}"
  return {
      "status": "ok",
      "session_id": sid,
      "type": "price_monitor_registered",
      "item_id": iid,
      "display_name": display,
      "product_label": display,
      "price_cap": float(price_cap),
      "currency": _currency(currency),
      "price_cap_display": _format_money(price_cap, _currency(currency)),
      "interval_minutes": interval,
      "next_tick_at": now,
      "monitor_ref": sid,
      "driver": "backend_scheduler",
      "scheduler_url": scheduler_url,
      "user_message": (
          f"Price monitoring started (every {interval:g} min). "
          f"**Monitor ref:** `{sid}`. Backend scheduler will check and purchase "
          f"automatically when constraints are met."
      ),
      "feishu_user_message": (
          f"Price monitoring started (every {interval:g} min). **Monitor ref:** `{sid}`."
      ),
      "message": (
          "Monitor armed. Backend scheduler (:8105) drives ticks and purchase; "
          "do not start OpenClaw cron or browser polling loops."
      ),
      "agent_instruction": (
          "Post feishu_user_message only. Do NOT run monitor_cron.sh, /loop, or "
          "manual tick scripts. Backend scheduler handles monitoring and purchase."
      ),
      "max_ticks": cap,
  }


def _enrich_purchase_complete_chain_ids(
    ctx: Any,
    pc: dict[str, Any],
) -> dict[str, Any]:
  """Backfill closed mandate chain ids from session for Mandates tab."""
  state = getattr(ctx, "state", {}) or {}
  if not pc.get("checkout_mandate_chain_id"):
    chk = str(state.get("temp:checkout_mandate_chain", "")).strip()
    if chk:
      pc["checkout_mandate_chain_id"] = chk
  if not pc.get("payment_mandate_chain_id"):
    pay = str(state.get("temp:payment_mandate_chain", "")).strip()
    if pay:
      pc["payment_mandate_chain_id"] = pay
  return pc


def get_price_monitor_status(session_id: str) -> dict[str, Any]:
  """Return monitor status for agent or HTTP status endpoint."""
  sid = _sid(session_id)
  if not sid:
    return {"error": "session_id_required", "message": "Pass session_id for this chat."}
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx)
  if not monitor:
    return {
        "status": "inactive",
        "session_id": sid,
        "due": False,
        "should_stop": True,
        "message": "No active price monitor. Call register_price_monitor after signing mandates.",
    }
  if monitor.get("purchased"):
    result = monitor.get("purchase_result") if isinstance(
        monitor.get("purchase_result"), dict
    ) else {}
    pc = result.get("purchase_complete")
    if isinstance(pc, dict):
      pc = _enrich_purchase_complete_chain_ids(ctx, dict(pc))
      result = {**result, "purchase_complete": pc}
    return {
        "status": "purchased",
        "session_id": sid,
        "due": False,
        "should_stop": True,
        "stop_reason": "purchased",
        "purchase_result": result,
        "purchase_complete": result.get("purchase_complete"),
        "monitoring": monitor.get("last_monitoring_artifact"),
        "message": "Purchase completed by backend scheduler.",
    }
  # Purchasing flips active=False while the backend completes the chain, so this
  # must be checked before the generic "stopped / not active" fallback below —
  # otherwise an in-flight purchase is misreported as a cancelled monitor.
  if monitor.get("purchasing"):
    return {
        "status": "purchasing",
        "session_id": sid,
        "due": False,
        "should_stop": False,
        "item_id": monitor.get("item_id"),
        "item_name": monitor.get("item_name"),
        "price_cap": monitor.get("price_cap"),
        "monitoring": monitor.get("last_monitoring_artifact"),
        "message": "Backend scheduler is completing purchase.",
    }
  if monitor.get("stopped") or not monitor.get("active"):
    reason = monitor.get("stop_reason") or "cancelled"
    return {
        "status": "stopped",
        "session_id": sid,
        "due": False,
        "should_stop": True,
        "stop_reason": reason,
        "monitoring": monitor.get("last_monitoring_artifact"),
        "message": _STOP_REASONS.get(reason, "Monitor stopped."),
    }
  now = time.time()
  next_tick = float(monitor.get("next_tick_at", now))
  due = now >= next_tick
  wait_seconds = max(0, int(next_tick - now))
  return {
      "status": "active",
      "session_id": sid,
      "due": due,
      "should_stop": False,
      "wait_seconds": wait_seconds,
      "interval_minutes": monitor.get("interval_minutes"),
      "item_id": monitor.get("item_id"),
      "display_name": monitor.get("display_name") or monitor.get("item_name"),
      "item_name": monitor.get("item_name"),
      "price_cap": monitor.get("price_cap"),
      "currency": monitor.get("currency"),
      "next_tick_at": next_tick,
      "last_tick_at": monitor.get("last_tick_at"),
      "tick_count": monitor.get("tick_count", 0),
      "max_ticks": monitor.get("max_ticks", _DEFAULT_MAX_TICKS),
      "monitoring": monitor.get("last_monitoring_artifact"),
      "feishu_prompt": (
          "Backend scheduler is monitoring; no manual tick required."
          if due
          else f"Next backend tick in {wait_seconds}s."
      ),
  }


def try_acquire_purchasing_lock(session_id: str) -> bool:
  """Atomically mark monitor as purchasing (idempotent guard)."""
  sid = _sid(session_id)
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx)
  if not monitor or not monitor.get("active"):
    return False
  if monitor.get("purchasing") or monitor.get("purchased") or monitor.get("stopped"):
    return False
  monitor["purchasing"] = True
  monitor["purchasing_started_at"] = time.time()
  monitor["active"] = False
  ctx.state[_STATE_KEY] = monitor
  save_tool_context(sid, ctx)
  return True


def mark_purchased(session_id: str, purchase_result: dict[str, Any]) -> None:
  sid = _sid(session_id)
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx) or {}
  now = time.time()
  monitor["active"] = False
  monitor["purchasing"] = False
  monitor["purchased"] = True
  monitor["stopped"] = True
  monitor["stop_reason"] = "purchased"
  monitor["purchase_result"] = purchase_result
  monitor["next_tick_at"] = now
  ctx.state[_STATE_KEY] = monitor
  save_tool_context(sid, ctx)


def mark_monitor_error(session_id: str, message: str) -> None:
  sid = _sid(session_id)
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx) or {}
  monitor["active"] = False
  monitor["purchasing"] = False
  monitor["stopped"] = True
  monitor["stop_reason"] = "error"
  monitor["purchase_result"] = {"error": message}
  ctx.state[_STATE_KEY] = monitor
  save_tool_context(sid, ctx)


def complete_price_monitor_tick(
    session_id: str,
    *,
    current_price: float,
    available: bool,
    meets_constraints: bool,
    message: str = "",
    not_found: bool = False,
    stop_reason: str = "",
) -> dict[str, Any]:
  """Record a monitoring tick (non-purchase path; terminal ticks stop monitor)."""
  sid = _sid(session_id)
  if not sid:
    return {"error": "session_id_required", "message": "Pass session_id for this chat."}
  ctx = load_tool_context(sid)
  monitor = _monitor_from_context(ctx)
  if not monitor or not monitor.get("active"):
    return {
        "error": "monitor_not_active",
        "should_stop": True,
        "message": "Monitor is not active.",
    }
  now = time.time()
  interval = _clamp_interval_minutes(monitor.get("interval_minutes", 5))
  tick_count = int(monitor.get("tick_count", 0)) + 1
  max_ticks = int(monitor.get("max_ticks", _DEFAULT_MAX_TICKS) or _DEFAULT_MAX_TICKS)
  monitor["last_tick_at"] = now
  monitor["tick_count"] = tick_count
  monitor["last_result"] = {
      "current_price": float(current_price),
      "available": bool(available),
      "meets_constraints": bool(meets_constraints),
      "message": str(message or ""),
  }

  reason: str | None = None
  explicit = (stop_reason or "").strip().lower()
  if explicit in _STOP_REASONS:
    reason = explicit
  elif not_found:
    reason = "not_found"
  elif tick_count >= max_ticks:
    reason = "max_ticks"
  # constraints_met handled by scheduler purchase path, not here

  should_stop = reason is not None
  if should_stop:
    monitor["active"] = False
    monitor["stopped"] = True
    monitor["stop_reason"] = reason
    monitor["next_tick_at"] = now
  else:
    monitor["next_tick_at"] = now + interval * 60

  merchant = str(monitor.get("merchant") or "shoe")
  display = resolve_display_name(
      str(monitor.get("item_id", "")),
      merchant=merchant,
      item_name=str(monitor.get("item_name") or ""),
  )
  currency = _currency(monitor.get("currency"))
  artifact = {
      "type": "monitoring",
      "item_id": monitor.get("item_id"),
      "item_name": display,
      "display_name": display,
      "product_label": display,
      "price_cap": monitor.get("price_cap"),
      "currency": currency,
      "price_cap_display": _format_money(monitor.get("price_cap"), currency),
      "current_price": float(current_price),
      "current_price_display": _format_money(current_price, currency),
      "meets_constraints": bool(meets_constraints),
      "available": bool(available),
      "message": message or "Scheduled price monitor tick.",
  }
  monitor["last_monitoring_artifact"] = artifact
  ctx.state[_STATE_KEY] = monitor
  save_tool_context(sid, ctx)

  if should_stop:
    stop_note = _STOP_REASONS.get(reason, "Monitor stopped.")
    user_message = (
        f"**Product:** {display} · **Price:** {_format_money(current_price, currency)} "
        f"· **Cap:** {_format_money(monitor.get('price_cap'), currency)}\n"
        f"**Available:** {available} · **Meets constraints:** {meets_constraints}\n"
        f"**Monitor ref:** `{sid}`\n{stop_note}"
    )
    return {
        "status": "stopped",
        "session_id": sid,
        "monitor_ref": sid,
        "monitoring": artifact,
        "should_stop": True,
        "stop_reason": reason,
        "tick_count": tick_count,
        "user_message": user_message,
        "feishu_user_message": user_message,
        "message": stop_note,
    }

  user_message = (
      f"**Product:** {display} · **Price:** {_format_money(current_price, currency)} "
      f"· **Cap:** {_format_money(monitor.get('price_cap'), currency)}\n"
      f"**Available:** {available} · **Meets constraints:** {meets_constraints}\n"
      f"**Monitor ref:** `{sid}`"
  )
  return {
      "status": "ok",
      "session_id": sid,
      "monitor_ref": sid,
      "monitoring": artifact,
      "should_stop": False,
      "next_tick_at": monitor["next_tick_at"],
      "interval_minutes": interval,
      "tick_count": tick_count,
      "max_ticks": max_ticks,
      "user_message": user_message,
      "feishu_user_message": user_message,
      "message": f"Tick recorded ({tick_count}/{max_ticks}).",
  }


def clear_price_monitor(session_id: str) -> dict[str, Any]:
  """Clear monitor state after purchase completion."""
  sid = _sid(session_id)
  if not sid:
    return {"error": "session_id_required", "message": "Pass session_id for this chat."}
  ctx = load_tool_context(sid)
  ctx.state.pop(_STATE_KEY, None)
  save_tool_context(sid, ctx)
  return {
      "status": "ok",
      "session_id": sid,
      "message": "Price monitor cleared.",
  }
