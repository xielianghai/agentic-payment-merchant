"""Per-session Trusted Surface approval tracking (web UI + openclaw Feishu)."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import random
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_log = logging.getLogger("trusted-surface")


def _configure_ts_logger() -> None:
  if _log.handlers:
    return
  try:
    from constants_unified import LOGS_DIR
    from role_logging import setup_role_logger

    setup_role_logger(
        "trusted-surface",
        log_file=LOGS_DIR / "trusted-surface-gate.log",
        console=False,
    )
  except ImportError:
    pass


_configure_ts_logger()

_current_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "a2a_session_id",
    default="",
)

# session_id -> {approval_key, item_id, payment_method, price_cap}
_APPROVALS: dict[str, dict[str, Any]] = {}

# session_id -> pending OTP record
_PENDING: dict[str, dict[str, Any]] = {}

_OTP_LENGTH = 6
_OTP_TTL_SECONDS = 300
_TS_SESSION_TTL_SECONDS = 300
_MAX_OTP_ATTEMPTS = 5

# ref -> frozen mandate draft + status (H5 Trusted Surface)
_SESSIONS: dict[str, dict[str, Any]] = {}


def _temp_db() -> Path:
  env = os.environ.get("TEMP_DB_DIR", "").strip()
  if env:
    return Path(env)
  # payment-stack/shopping_agent_unified/trusted_surface_gate.py → payment-stack/.temp-db
  unified = Path(__file__).resolve().parents[1]
  return unified / ".temp-db"


def _approvals_file() -> Path:
  return _temp_db() / "ts_approvals.json"


def _pending_file() -> Path:
  return _temp_db() / "ts_pending.json"


def _sessions_file() -> Path:
  return _temp_db() / "ts_sessions.json"


def _safe_session_filename(session_id: str) -> str:
  return re.sub(r"[^a-zA-Z0-9._-]+", "_", (session_id or "default").strip())[:200]


def otp_delivery_path(session_id: str) -> Path:
  """Path for mock OTP delivery file (debug fallback; code is returned by MCP)."""
  return _temp_db() / f"otp_{_safe_session_filename(session_id)}.json"


def _otp_required() -> bool:
  return os.environ.get("AP2_REQUIRE_OTP", "").strip() == "1"


def _h5_portal_default() -> bool:
  """H5 portal is the default Trusted Surface. When on, instant register is off."""
  return os.environ.get("AP2_TS_H5_DEFAULT", "1").strip() != "0"


def _load_file_json(path: Path) -> dict[str, dict[str, Any]]:
  if not path.is_file():
    return {}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
      return {str(k): v for k, v in data.items() if isinstance(v, dict)}
  except (OSError, json.JSONDecodeError, TypeError):
    pass
  return {}


def _persist_json(path: Path, data: dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
      json.dumps(data, indent=2, ensure_ascii=True),
      encoding="utf-8",
  )


def _load_file_approvals() -> dict[str, dict[str, Any]]:
  return _load_file_json(_approvals_file())


def _load_file_pending() -> dict[str, dict[str, Any]]:
  return _load_file_json(_pending_file())


def _persist_approvals() -> None:
  _persist_json(_approvals_file(), _APPROVALS)


def _persist_pending() -> None:
  _persist_json(_pending_file(), _PENDING)


def _ensure_loaded() -> None:
  if _APPROVALS:
    return
  _APPROVALS.update(_load_file_approvals())


def _ensure_pending_loaded() -> None:
  if _PENDING:
    return
  _PENDING.update(_load_file_pending())


def _load_file_sessions() -> dict[str, dict[str, Any]]:
  return _load_file_json(_sessions_file())


def _persist_sessions() -> None:
  _persist_json(_sessions_file(), _SESSIONS)


def _ensure_sessions_loaded() -> None:
  if _SESSIONS:
    return
  _SESSIONS.update(_load_file_sessions())


def _reload_sessions_from_disk() -> None:
  """Refresh session cache (TS HTTP server runs in a separate process)."""
  _SESSIONS.clear()
  _SESSIONS.update(_load_file_sessions())


def _reload_approvals_from_disk() -> None:
  """Refresh approval cache after TS HTTP / web client writes."""
  _APPROVALS.clear()
  _APPROVALS.update(_load_file_approvals())


def _ts_base_url() -> str:
  return os.environ.get("TS_BASE_URL", "http://localhost:8104").rstrip("/")


def _portal_url(ref: str) -> str:
  return f"{_ts_base_url()}/ts/confirm?ref={ref}"


def _channel_surface_messages(
    portal_url: str,
    *,
    display_name: str,
    price_cap: float,
    payment_method: str,
) -> dict[str, Any]:
  pm_label = payment_method.upper()
  # WeChat bot sends plain text only — markdown [label](url) is NOT clickable,
  # and localhost URLs are never tappable in WeChat. Use a bare URL + copy hint.
  user_message = (
      f"Confirm this purchase on the Trusted Surface portal:\n"
      f"**Product:** {display_name}\n"
      f"**Price cap:** ${price_cap:.2f} {pm_label}\n"
      f"\n{portal_url}\n"
      f"\n(WeChat cannot open localhost links — long-press the URL above to "
      f"copy, then paste it into a browser on this computer.)"
  )
  feishu_user_message = (
      f"Confirm this purchase on the Trusted Surface portal:\n"
      f"**Product:** {display_name}\n"
      f"**Price cap:** ${price_cap:.2f} {pm_label}\n"
      f"**Open:** [Open Trusted Surface portal]({portal_url})"
  )
  return {
      "user_message": user_message,
      "surface_action": {"type": "open_url", "url": portal_url},
      "feishu_user_message": feishu_user_message,
      "agent_instruction": (
          "Post user_message to the user (English) verbatim — include the bare "
          "portal_url on its own line (WeChat: no markdown links; user copies "
          "URL into a browser). On Feishu, you may post feishu_user_message "
          "instead. They review the frozen mandate and confirm on the portal. "
          "Then call wait_for_trusted_surface_signed with this ref (server-side "
          "long-poll; no user 'done' required, no LLM polling loop). Only call "
          "assemble_and_sign_* after status is signed."
      ),
  }


def set_request_session_id(session_id: str) -> contextvars.Token[str]:
  return _current_session.set(session_id or "")


def reset_request_session_id(token: contextvars.Token[str]) -> None:
  _current_session.reset(token)


def _canonical_amount_cents(
    price_cap: float | int | None = None,
    *,
    amount_cents: int | None = None,
) -> int:
  """Return canonical integer cents for approval keys (HP uses amount_cents)."""
  if amount_cents is not None:
    try:
      cents = int(amount_cents)
      if cents > 0:
        return cents
    except (TypeError, ValueError):
      pass
  if price_cap is None:
    return 0
  try:
    return round(float(price_cap) * 100)
  except (TypeError, ValueError):
    return 0


def _approval_key(
    price_cap: float | int | None = None,
    payment_method: str = "card",
    *,
    amount_cents: int | None = None,
) -> str:
  pm = payment_method.strip().lower()
  if pm not in ("card", "x402"):
    pm = "card"
  cents = _canonical_amount_cents(price_cap, amount_cents=amount_cents)
  return f"{cents}c:{pm}"


def _normalize_payment_method(payment_method: str) -> str:
  pm = payment_method.strip().lower()
  if pm not in ("card", "x402"):
    pm = "card"
  return pm


def _generate_otp_code() -> str:
  return "".join(str(random.randint(0, 9)) for _ in range(_OTP_LENGTH))


def _store_approval(
    session_id: str,
    price_cap: float | int,
    payment_method: str,
    item_id: str = "",
    item_name: str = "",
    *,
    amount_cents: int | None = None,
    draft: dict[str, Any] | None = None,
) -> None:
  session_id = _canonical_session_id(session_id)
  if not session_id:
    return
  pm = _normalize_payment_method(payment_method)
  cents = _canonical_amount_cents(price_cap, amount_cents=amount_cents)
  key = _approval_key(payment_method=pm, amount_cents=cents)
  _ensure_loaded()
  display = (item_name or "").strip() or str(item_id)
  record: dict[str, Any] = {
      "approval_key": key,
      "amount_cents": cents,
      "item_id": str(item_id),
      "item_name": display,
      "price_cap": cents / 100.0 if cents > 0 else float(price_cap),
      "payment_method": pm,
  }
  if pm == "card" and isinstance(draft, dict):
    try:
      from vi_unified.credentials import issue_l2_intent_credential, is_vi_enabled

      if is_vi_enabled():
        l2_draft = dict(draft)
        l2_draft.setdefault("session_id", session_id)
        l2_draft.setdefault("payment_method", pm)
        l2_draft.setdefault("amount_cents", cents)
        l2_result = issue_l2_intent_credential(l2_draft, session_id=session_id)
        l2_id = l2_result.get("vi_l2_credential_id")
        if l2_id:
          record["vi_l2_credential_id"] = str(l2_id)
          record["vi_intent_hash"] = l2_result.get("intent_hash")
    except Exception as exc:
      _log.warning("[trusted-surface] VI L2 issuance failed: %s", exc)
  _APPROVALS[session_id] = record
  _persist_approvals()


def _clear_pending(session_id: str) -> None:
  if not session_id:
    return
  _ensure_pending_loaded()
  _PENDING.pop(session_id, None)
  _persist_pending()
  delivery = otp_delivery_path(session_id)
  if delivery.is_file():
    try:
      delivery.unlink()
    except OSError:
      pass


def register_mandate_approved_payload(payload: dict[str, Any]) -> None:
  """Record TS approval from web client mandate_approved JSON."""
  session_id = _current_session.get()
  if not session_id:
    return
  mr = payload.get("mandate_request")
  if not isinstance(mr, dict):
    return
  price_cap = mr.get("price_cap")
  if price_cap is None:
    constraints = mr.get("constraints")
    if isinstance(constraints, dict):
      price_cap = constraints.get("price_lt") or constraints.get("price_cap")
  if price_cap is None:
    return
  ap2 = payload.get("ap2_config")
  payment = "card"
  if isinstance(ap2, dict) and ap2.get("payment_method") in ("card", "x402"):
    payment = str(ap2["payment_method"])
  elif mr.get("payment_method") in ("card", "x402"):
    payment = str(mr["payment_method"])
  _store_approval(
      session_id,
      price_cap,
      payment,
      str(mr.get("item_id", "")),
      item_name=str(mr.get("item_name", "")),
      draft={
          "session_id": session_id,
          "item_id": str(mr.get("item_id", "")),
          "item_name": str(mr.get("item_name", "")),
          "price_cap": price_cap,
          "payment_method": payment,
          "presence_mode": "hnp",
          "constraints": mr.get("constraints")
          if isinstance(mr.get("constraints"), dict)
          else {},
      },
  )


def register_immediate_checkout_approved_payload(payload: dict[str, Any]) -> None:
  """Record TS approval from web client immediate_checkout_approved JSON (HP)."""
  session_id = _current_session.get()
  if not session_id:
    return
  total_cents = payload.get("total_cents")
  if total_cents is None:
    return
  try:
    cents = int(total_cents)
  except (TypeError, ValueError):
    return
  if cents <= 0:
    return
  ap2 = payload.get("ap2_config")
  payment = "card"
  if isinstance(ap2, dict) and ap2.get("payment_method") in ("card", "x402"):
    payment = str(ap2["payment_method"])
  elif payload.get("payment_method") in ("card", "x402"):
    payment = str(payload["payment_method"])
  _store_approval(
      session_id,
      cents / 100.0,
      payment,
      str(payload.get("item_id", "")),
      item_name=str(payload.get("item_name", "")),
      amount_cents=cents,
      draft={
          "session_id": session_id,
          "item_id": str(payload.get("item_id", "")),
          "item_name": str(payload.get("item_name", "")),
          "price_cap": cents / 100.0,
          "amount_cents": cents,
          "payment_method": payment,
          "presence_mode": "hp",
      },
  )


def issue_payment_otp(
    session_id: str,
    price_cap: float | int,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
) -> dict[str, Any]:
  """Create pending OTP; approval is granted only after verify_payment_otp."""
  sid = (session_id or "").strip()
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass session_id (e.g. Feishu chat id) for this conversation.",
    }
  pm = _normalize_payment_method(payment_method)
  cents = _canonical_amount_cents(price_cap)
  key = _approval_key(payment_method=pm, amount_cents=cents)
  code = _generate_otp_code()
  expires_at = time.time() + _OTP_TTL_SECONDS
  _ensure_pending_loaded()
  display = (item_name or "").strip()
  _PENDING[sid] = {
      "approval_key": key,
      "amount_cents": cents,
      "item_id": str(item_id),
      "item_name": display,
      "price_cap": cents / 100.0 if cents > 0 else float(price_cap),
      "payment_method": pm,
      "code": code,
      "expires_at": expires_at,
      "attempts": 0,
  }
  _persist_pending()
  label = display or str(item_id)
  return {
      "status": "otp_required",
      "session_id": sid,
      "approval_key": key,
      "item_id": str(item_id),
      "item_name": label,
      "display_name": label,
      "payment_method": pm,
      "expires_in_seconds": _OTP_TTL_SECONDS,
      "message": "OTP issued. Use feishu_user_message for the user; call verify_payment_otp after they send the code.",
      "otp_ref": sid,
      "otp_code": code,
      "feishu_user_message": (
          "OTP step-up required. "
          f"**OTP ref:** `{sid}`\n"
          f"**OTP code:** `{code}`\n"
          "Reply with this 6-digit code here to continue."
      ),
      "agent_instruction": (
          "Post feishu_user_message only; it already includes the mock OTP code. "
          "Never paste shell commands or file paths in Feishu."
      ),
  }


def get_otp_delivery_record(session_id: str) -> dict[str, Any] | None:
  """Return OTP delivery payload for mock channel (server logging/file only)."""
  sid = (session_id or "").strip()
  if not sid:
    return None
  _ensure_pending_loaded()
  pending = _PENDING.get(sid)
  if not pending:
    return None
  return {
      "session_id": sid,
      "code": pending.get("code"),
      "approval_key": pending.get("approval_key"),
      "expires_at": pending.get("expires_at"),
      "expires_in_seconds": max(
          0,
          int(float(pending.get("expires_at", 0)) - time.time()),
      ),
      "delivery_path": str(otp_delivery_path(sid)),
  }


def write_otp_delivery_file(session_id: str) -> dict[str, Any] | None:
  """Persist mock OTP to .temp-db/otp_<session>.json for user retrieval."""
  record = get_otp_delivery_record(session_id)
  if not record or not record.get("code"):
    return None
  path = otp_delivery_path(session_id)
  payload = {
      "session_id": record["session_id"],
      "code": record["code"],
      "approval_key": record.get("approval_key"),
      "expires_at": record.get("expires_at"),
      "expires_in_seconds": record.get("expires_in_seconds"),
      "delivery_path": str(path),
  }
  _persist_json(path, payload)
  return payload


def verify_payment_otp(session_id: str, code: str) -> dict[str, Any]:
  """Verify OTP and store Trusted Surface approval on success."""
  sid = (session_id or "").strip()
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass session_id for this conversation.",
    }
  submitted = (code or "").strip()
  if not submitted or not submitted.isdigit() or len(submitted) != _OTP_LENGTH:
    return {
        "error": "otp_invalid_format",
        "message": f"OTP must be exactly {_OTP_LENGTH} digits.",
    }
  _ensure_pending_loaded()
  pending = _PENDING.get(sid)
  if not pending:
    return {
        "error": "otp_not_found",
        "message": (
            "No pending OTP for this session. Call register_trusted_surface_approval "
            "(or issue_payment_otp) first after the user confirms the mandate summary."
        ),
    }
  attempts = int(pending.get("attempts", 0))
  if attempts >= _MAX_OTP_ATTEMPTS:
    _clear_pending(sid)
    return {
        "error": "otp_max_attempts",
        "message": "Too many failed OTP attempts. Request a new OTP.",
    }
  if time.time() > float(pending.get("expires_at", 0)):
    _clear_pending(sid)
    return {
        "error": "otp_expired",
        "message": "OTP expired. Call register_trusted_surface_approval again.",
    }
  if submitted != str(pending.get("code", "")):
    pending["attempts"] = attempts + 1
    _persist_pending()
    remaining = _MAX_OTP_ATTEMPTS - int(pending["attempts"])
    return {
        "error": "otp_mismatch",
        "message": f"Incorrect OTP. {remaining} attempt(s) remaining.",
    }
  _store_approval(
      sid,
      pending["price_cap"],
      pending["payment_method"],
      str(pending.get("item_id", "")),
      item_name=str(pending.get("item_name", "")),
      amount_cents=pending.get("amount_cents"),
  )
  key = pending.get("approval_key", "")
  pm = pending.get("payment_method", "card")
  _clear_pending(sid)
  return {
      "status": "ok",
      "session_id": sid,
      "approval_key": key,
      "payment_method": pm,
      "message": "OTP verified. Trusted Surface approval recorded.",
  }


def register_trusted_surface_approval(
    session_id: str,
    price_cap: float | int,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
) -> dict[str, Any]:
  """Record explicit user approval (openclaw Feishu confirm)."""
  if _otp_required():
    return issue_payment_otp(
        session_id, price_cap, payment_method, item_id, item_name=item_name
    )
  if _h5_portal_default():
    # H5 portal is the default Trusted Surface: refuse silent instant approval
    # so the agent cannot bypass the "what you see is what you sign" portal.
    return {
        "error": "use_trusted_surface_portal",
        "message": (
            "Instant approval is disabled (H5 Trusted Surface is required). "
            "Do NOT use register_trusted_surface_approval. Instead call "
            "create_trusted_surface_session with amount_cents (HP) or price_cap "
            "(HNP in USD), payment_method and item, send the user the returned portal_url, "
            "wait for their reply, then call get_trusted_surface_status once. "
            "Only assemble_and_sign_* after status is 'signed'."
        ),
    }
  sid = (session_id or "").strip()
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass session_id (e.g. Feishu chat id) for this conversation.",
    }
  _store_approval(sid, price_cap, payment_method, item_id, item_name=item_name)
  key = _approval_key(price_cap, payment_method)
  display = (item_name or "").strip() or str(item_id)
  return {
      "status": "ok",
      "session_id": sid,
      "approval_key": key,
      "item_id": str(item_id),
      "item_name": display,
      "display_name": display,
      "payment_method": _normalize_payment_method(payment_method),
  }


def clear_session_approval(session_id: str | None = None) -> None:
  sid = session_id or _current_session.get()
  if sid:
    _ensure_loaded()
    _APPROVALS.pop(sid, None)
    _persist_approvals()
    _clear_pending(sid)


def approval_for_session(session_id: str) -> dict[str, Any] | None:
  if not session_id:
    return None
  _reload_approvals_from_disk()
  return _APPROVALS.get(_canonical_session_id(session_id))


def approval_for_request(
    price_cap: float | int,
    payment_method: str,
    *,
    item_id: str = "",
    amount_cents: int | None = None,
) -> dict[str, Any] | None:
  """Find a matching TS approval when request context lost the session id."""
  _reload_approvals_from_disk()
  key = _approval_key(payment_method=payment_method, amount_cents=_canonical_amount_cents(
      price_cap, amount_cents=amount_cents
  ))
  expected_item = (item_id or "").strip()
  matches = [
      approval
      for approval in _APPROVALS.values()
      if approval.get("approval_key") == key
      and (not expected_item or approval.get("item_id") == expected_item)
  ]
  return matches[0] if len(matches) == 1 else None


def approval_for_current_session() -> dict[str, Any] | None:
  sid = _current_session.get()
  if not sid:
    return None
  return approval_for_session(sid)


def grant_trusted_surface_approval(
    price_cap: float | int,
    payment_method: str = "card",
    *,
    session_id: str = "__unit_test__",
) -> contextvars.Token[str]:
  """Register approval for offline tests (verify_unified_tools.py)."""
  _store_approval(session_id, price_cap, payment_method, "")
  return _current_session.set(session_id)


def create_ts_session(
    session_id: str,
    *,
    price_cap: float | int,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
    presence_mode: str = "hnp",
    payee: str = "",
    constraints: dict[str, Any] | None = None,
    amount_cents: int | None = None,
) -> dict[str, Any]:
  """Freeze mandate draft and return H5 portal URL for Trusted Surface approval."""
  sid = _canonical_session_id(session_id)
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass session_id for this conversation.",
    }
  pm = _normalize_payment_method(payment_method)
  pm_mode = (presence_mode or "hnp").strip().lower()
  if pm_mode not in ("hp", "hnp"):
    pm_mode = "hnp"
  display = (item_name or "").strip() or str(item_id)
  cents = 0
  if amount_cents is not None:
    try:
      cents = int(amount_cents)
    except (TypeError, ValueError):
      cents = 0
  if cents > 0:
    price_cap = cents / 100.0
  else:
    cents = _canonical_amount_cents(price_cap)
  ref = secrets.token_urlsafe(12)
  now = time.time()
  draft = {
      "session_id": sid,
      "item_id": str(item_id),
      "item_name": display,
      "display_name": display,
      "price_cap": float(price_cap),
      "amount_cents": cents,
      "payment_method": pm,
      "presence_mode": pm_mode,
      "payee": str(payee or ""),
      "constraints": constraints if isinstance(constraints, dict) else {},
  }
  _ensure_sessions_loaded()
  _SESSIONS[ref] = {
      "ref": ref,
      "session_id": sid,
      "draft": draft,
      "status": "pending",
      "created_at": now,
      "expires_at": now + _TS_SESSION_TTL_SECONDS,
      "signed_at": None,
  }
  _persist_sessions()
  portal = _portal_url(ref)
  channel = _channel_surface_messages(
      portal,
      display_name=display,
      price_cap=float(price_cap),
      payment_method=pm,
  )
  return {
      "status": "pending",
      "ref": ref,
      "session_id": sid,
      "portal_url": portal,
      "amount_cents": cents,
      "expires_in_seconds": _TS_SESSION_TTL_SECONDS,
      **channel,
  }


def get_trusted_surface_draft(ref: str) -> dict[str, Any] | None:
  """Return frozen mandate summary for display on the H5 portal."""
  rid = (ref or "").strip()
  if not rid:
    return None
  _reload_sessions_from_disk()
  record = _SESSIONS.get(rid)
  if not record:
    return None
  if time.time() > float(record.get("expires_at", 0)):
    if record.get("status") == "pending":
      record["status"] = "expired"
      _persist_sessions()
    return None
  draft = record.get("draft")
  if not isinstance(draft, dict):
    return None
  return {
      **draft,
      "ref": rid,
      "status": record.get("status", "pending"),
      "expires_in_seconds": max(
          0,
          int(float(record.get("expires_at", 0)) - time.time()),
      ),
  }


def get_ts_session_status(ref: str) -> dict[str, Any]:
  """Return pending | signed | expired for agent polling."""
  rid = (ref or "").strip()
  if not rid:
    return {"status": "not_found", "message": "ref is required"}
  _reload_sessions_from_disk()
  record = _SESSIONS.get(rid)
  if not record:
    return {"status": "not_found", "message": f"No TS session for ref {rid!r}"}
  if time.time() > float(record.get("expires_at", 0)):
    if record.get("status") != "signed":
      record["status"] = "expired"
      _persist_sessions()
  status = str(record.get("status", "pending"))
  out: dict[str, Any] = {
      "status": status,
      "ref": rid,
      "session_id": record.get("session_id"),
  }
  if status == "signed":
    out["message"] = "Trusted Surface approval recorded. Continue with assemble_and_sign_*."
    _ensure_openclaw_woken(str(record.get("session_id") or ""), rid)
  elif status == "expired":
    out["message"] = "TS session expired. Call create_trusted_surface_session again."
  else:
    out["message"] = "Waiting for user to confirm on the Trusted Surface portal."
    out["portal_url"] = _portal_url(rid)
  return out


def wait_for_trusted_surface_signed(
    ref: str,
    *,
    timeout_seconds: int = 300,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
  """Block until the H5 portal records signed approval (server-side long-poll).

  The agent calls this once after posting portal_url. The MCP server polls
  ts_sessions.json locally — no extra LLM turns and no tight client polling.
  """
  rid = (ref or "").strip()
  if not rid:
    return {"status": "not_found", "message": "ref is required"}
  initial = get_ts_session_status(rid)
  if initial.get("status") == "signed":
    _ensure_openclaw_woken(str(initial.get("session_id") or ""), rid)
    initial["waited_seconds"] = 0
    initial["message"] = (
        "Trusted Surface approval recorded. Continue with assemble_and_sign_*."
    )
    return initial
  try:
    timeout = max(1, int(timeout_seconds))
  except (TypeError, ValueError):
    timeout = _TS_SESSION_TTL_SECONDS
  try:
    interval = max(0.5, float(poll_interval_seconds))
  except (TypeError, ValueError):
    interval = 2.0
  deadline = time.time() + timeout
  while time.time() < deadline:
    status = get_ts_session_status(rid)
    st = str(status.get("status", ""))
    if st == "signed":
      _ensure_openclaw_woken(str(status.get("session_id") or ""), rid)
      status["waited_seconds"] = round(timeout - max(0, deadline - time.time()), 1)
      status["message"] = (
          "Trusted Surface approval recorded. Continue with assemble_and_sign_*."
      )
      return status
    if st in ("expired", "not_found"):
      status["waited_seconds"] = round(timeout - max(0, deadline - time.time()), 1)
      return status
    time.sleep(min(interval, max(0, deadline - time.time())))
  final = get_ts_session_status(rid)
  if final.get("status") == "pending" and not final.get("portal_url"):
    final["portal_url"] = _portal_url(rid)
  final["status"] = "timeout"
  final["message"] = (
      f"Timed out after {timeout}s waiting for Trusted Surface approval. "
      "Ask the user to open portal_url and confirm, then call "
      "wait_for_trusted_surface_signed again with the same ref."
  )
  final["waited_seconds"] = timeout
  return final


def _canonical_session_id(session_id: str) -> str:
  """Normalize channel peer ids to the full AP2 session_id form."""
  sid = (session_id or "").strip()
  if not sid or "@" in sid:
    return sid
  if sid.lower().startswith("feishu:") or sid.startswith("ou_"):
    return sid
  # Bare WeChat open id from channel metadata (no @im.wechat suffix).
  return f"{sid}@im.wechat"


def _openclaw_session_key(session_id: str) -> str | None:
  """Map AP2 session_id to an OpenClaw agent sessionKey when possible."""
  sid = _canonical_session_id(session_id)
  if not sid:
    return None
  lower = sid.lower()
  if "@im.wechat" in lower:
    return f"agent:main:openclaw-weixin:direct:{lower}"
  if lower.startswith("feishu:") or "@feishu" in lower:
    peer = sid.split(":", 1)[-1].strip().lower()
    if peer:
      return f"agent:main:feishu:direct:{peer}"
  return None


def _resolve_openclaw_hook_token() -> str:
  """Read hooks.token from env or ~/.openclaw/openclaw.json."""
  token = os.environ.get("AP2_OPENCLAW_HOOK_TOKEN", "").strip()
  if token:
    return token
  cfg_path = Path.home() / ".openclaw" / "openclaw.json"
  if not cfg_path.is_file():
    return ""
  try:
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    hooks = data.get("hooks") or {}
    if isinstance(hooks, dict):
      return str(hooks.get("token") or "").strip()
  except (OSError, json.JSONDecodeError, TypeError):
    pass
  return ""


def _ensure_openclaw_woken(session_id: str, ref: str) -> None:
  """Wake OpenClaw once after TS sign (retry if hook was down at sign time)."""
  rid = (ref or "").strip()
  if not rid:
    return
  _reload_sessions_from_disk()
  record = _SESSIONS.get(rid)
  if not record or record.get("status") != "signed":
    return
  if record.get("openclaw_woken_at"):
    return
  sid = _canonical_session_id(
      str(record.get("session_id") or (record.get("draft") or {}).get("session_id") or session_id)
  )
  if _wake_openclaw_agent_after_ts_signed(sid, rid):
    record["openclaw_woken_at"] = time.time()
    _persist_sessions()


def _wake_openclaw_agent_after_ts_signed(session_id: str, ref: str) -> bool:
  """POST OpenClaw /hooks/agent so checkout continues without a user 'done' reply."""
  if os.environ.get("AP2_OPENCLAW_HOOK_ENABLED", "1").strip().lower() in (
      "0",
      "false",
      "no",
  ):
    return False
  hook_url = os.environ.get(
      "AP2_OPENCLAW_HOOK_URL",
      "http://127.0.0.1:18789/hooks/agent",
  ).strip()
  hook_token = _resolve_openclaw_hook_token()
  if not hook_url or not hook_token:
    _log.info(
        "[trusted-surface] skip openclaw wake (hook url/token not configured)"
    )
    return False
  session_key = _openclaw_session_key(session_id)
  if not session_key:
    _log.info(
        "[trusted-surface] skip openclaw wake (no sessionKey for %r)",
        session_id,
    )
    return False
  canonical_sid = _canonical_session_id(session_id)
  message = (
      f"[AP2] Trusted Surface signed (ref={ref}). Continue HP checkout on "
      f"session_id={canonical_sid}. Call assemble_and_sign_immediate_mandates "
      f"with closed mandate JWTs, then ap2-cp.issue_payment_credential, then "
      f"ap2-merchant.complete_checkout. Do NOT create a new TS session."
  )
  payload: dict[str, Any] = {
      "message": message,
      "sessionKey": session_key,
      "channel": "openclaw-weixin" if "@im.wechat" in canonical_sid.lower() else "last",
      "wakeMode": "now",
      "deliver": True,
      "name": "AP2 Trusted Surface",
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
  try:
    last_exc: Exception | None = None
    for attempt in range(3):
      try:
        with urllib.request.urlopen(req, timeout=10) as resp:
          _log.info(
              "[trusted-surface] openclaw wake OK ref=%s status=%s attempt=%s",
              ref,
              resp.status,
              attempt + 1,
          )
          return True
      except urllib.error.HTTPError as exc:
        last_exc = exc
        if exc.code in (502, 503, 504) and attempt < 2:
          time.sleep(2.0 * (attempt + 1))
          continue
        _log.warning(
            "[trusted-surface] openclaw wake HTTP %s ref=%s",
            exc.code,
            ref,
        )
        return False
      except Exception as exc:
        last_exc = exc
        if attempt < 2:
          time.sleep(2.0 * (attempt + 1))
          continue
        break
    if last_exc is not None:
      _log.warning(
          "[trusted-surface] openclaw wake failed ref=%s: %s",
          ref,
          last_exc,
      )
  except Exception as exc:
    _log.warning(
        "[trusted-surface] openclaw wake failed ref=%s: %s",
        ref,
        exc,
    )
  return False


def confirm_trusted_surface_approval(
    ref: str,
    *,
    pin: str | None = None,
) -> dict[str, Any]:
  """Record approval after user confirms on the H5 Trusted Surface portal."""
  rid = (ref or "").strip()
  if not rid:
    return {"error": "ref_required", "message": "Pass ref from the TS session."}
  _reload_sessions_from_disk()
  record = _SESSIONS.get(rid)
  if not record:
    return {"error": "session_not_found", "message": f"No TS session for ref {rid!r}"}
  if record.get("status") == "signed":
    return {
        "status": "ok",
        "ref": rid,
        "session_id": record.get("session_id"),
        "message": "Already approved.",
    }
  if time.time() > float(record.get("expires_at", 0)):
    record["status"] = "expired"
    _persist_sessions()
    return {"error": "session_expired", "message": "TS session expired."}
  expected_pin = os.environ.get("TS_PIN", "").strip()
  if expected_pin and (pin or "").strip() != expected_pin:
    return {"error": "pin_mismatch", "message": "Incorrect PIN."}
  draft = record.get("draft")
  if not isinstance(draft, dict):
    return {"error": "invalid_draft", "message": "TS session draft is missing."}
  sid = _canonical_session_id(
      str(record.get("session_id") or draft.get("session_id") or "")
  )
  draft_cents = draft.get("amount_cents")
  if draft_cents is None:
    draft_cents = _canonical_amount_cents(draft.get("price_cap", 0))
  _store_approval(
      sid,
      draft.get("price_cap", 0),
      str(draft.get("payment_method", "card")),
      str(draft.get("item_id", "")),
      item_name=str(draft.get("item_name", "")),
      amount_cents=draft_cents,
      draft=draft,
  )
  record["status"] = "signed"
  record["signed_at"] = time.time()
  if sid and _APPROVALS.get(sid, {}).get("vi_l2_credential_id"):
    record["vi_l2_credential_id"] = _APPROVALS[sid]["vi_l2_credential_id"]
  _persist_sessions()
  _ensure_openclaw_woken(sid, rid)
  return {
      "status": "ok",
      "ref": rid,
      "session_id": sid,
      "approval_key": _approval_key(
          payment_method=str(draft.get("payment_method", "card")),
          amount_cents=draft_cents,
      ),
      "vi_l2_credential_id": _APPROVALS.get(sid, {}).get("vi_l2_credential_id"),
      "message": "Trusted Surface approval recorded.",
  }


def approval_vi_l2_credential_id(session_id: str | None = None) -> str | None:
  """Return VI L2 credential id from the latest approval for this session."""
  sid = _canonical_session_id(session_id or _current_session.get() or "")
  if not sid:
    return None
  approval = approval_for_session(sid)
  if not approval:
    return None
  cred = approval.get("vi_l2_credential_id")
  return str(cred) if cred else None

def check_assemble_allowed(
    price_cap: float,
    payment_method: str,
    *,
    session_id: str | None = None,
    amount_cents: int | None = None,
    item_id: str = "",
) -> dict[str, str] | None:
  """Return an error dict if assemble must not run yet."""
  if os.environ.get("AP2_DISABLE_TS_GATE") == "1":
    return None
  sid = session_id or _current_session.get()
  approval = approval_for_session(sid) if sid else approval_for_current_session()
  if not approval:
    approval = approval_for_request(
        price_cap,
        payment_method,
        item_id=item_id,
        amount_cents=amount_cents,
    )
  if not approval:
    otp_hint = ""
    if _otp_required():
      otp_hint = (
          " If OTP step-up is enabled: user must verify with verify_payment_otp "
          "after register_trusted_surface_approval returns otp_required."
      )
    h5_hint = (
        " Or use create_trusted_surface_session, send the user portal_url, "
        "poll get_trusted_surface_status until signed, then assemble."
    )
    return {
        "error": "trusted_surface_approval_required",
        "message": (
            "User must explicitly approve the mandate first. "
            "On openclaw: present the mandate summary and wait for "
            "confirmation, then call create_trusted_surface_session (H5 portal) "
            "or register_trusted_surface_approval"
            + (" (issues OTP)" if _otp_required() else "")
            + ". "
            "On the web demo: client sends JSON type mandate_approved. "
            "Plain-text budget or payment choices are not approval."
            + otp_hint
            + h5_hint
        ),
    }
  request_cents = _canonical_amount_cents(price_cap, amount_cents=amount_cents)
  key = _approval_key(payment_method=payment_method, amount_cents=request_cents)
  if approval.get("approval_key") != key:
    return {
        "error": "trusted_surface_approval_mismatch",
        "message": (
            f"Trusted Surface approved {approval.get('approval_key')!r} but "
            f"assemble requested {key!r} ({request_cents} cents). "
            "For HP, pass the same amount_cents to create_trusted_surface_session "
            "and assemble_and_sign_immediate_mandates. Do not recreate the portal "
            "unless the checkout total changed."
        ),
    }
  return None
