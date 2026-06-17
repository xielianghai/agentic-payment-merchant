"""AP2 buyer MCP for openclaw — mandate tools + session config (mock backend)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

_ROLES_DIR = Path(__file__).resolve().parents[1]
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
_UNIFIED_SCENARIO = _ROLES_DIR.parent

if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)

from buyer_mcp_unified.price_monitor import (  # noqa: E402
  clear_price_monitor,
  complete_price_monitor_tick,
  get_price_monitor_status,
  register_price_monitor,
  stop_price_monitor,
)
from buyer_mcp_unified.session_store import (  # noqa: E402
  load_tool_context,
  run_with_session,
  save_tool_context,
)
from role_logging import setup_role_logger  # noqa: E402
from trusted_surface_gate import (  # noqa: E402
  _canonical_session_id,
  create_ts_session,
  get_otp_delivery_record,
  get_ts_session_status,
  register_trusted_surface_approval as _register_ts,
  reset_request_session_id,
  set_request_session_id,
  verify_payment_otp as _verify_otp,
  wait_for_trusted_surface_signed as _wait_for_ts_signed,
  write_otp_delivery_file,
)

# Import shopping agent tools after path bootstrap.
from shopping_agent.agent import (  # noqa: E402
  clear_open_mandate_session,
  get_ap2_session_config,
  reset_temp_db,
  set_ap2_session_config,
)
from shopping_agent.mandate_bridge import (  # noqa: E402
  assemble_and_sign_mandates_tool,
  check_constraints_against_mandate,
  create_checkout_presentation,
  create_payment_presentation,
  verify_checkout_receipt,
)
from shopping_agent.mandate_tools_hp import (  # noqa: E402
  assemble_and_sign_immediate_mandates_tool,
  create_hp_open_mandates_tool,
)

mcp = FastMCP("AP2 Buyer MCP (Unified)")

_LOG_DIR = Path(os.environ.get("LOGS_DIR", _UNIFIED_SCENARIO / ".logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = setup_role_logger(
    "buyer-mcp-unified",
    log_file=_LOG_DIR / "buyer-mcp-unified.log",
    level=logging.INFO,
)

mcp.add_middleware(
    LoggingMiddleware(
        logger=_logger,
        include_payloads=True,
        include_payload_length=True,
        max_payload_length=8000,
    )
)


_PLACEHOLDER_SESSION_IDS = frozenset({
    "feishu-main",
    "feishu_main",
    "main",
    "test",
    "CHAT_ID",
    "SESSION_ID",
    "session_id",
    "feishu-main",
})


def _validate_session_id(session_id: str) -> dict[str, Any] | None:
  sid = (session_id or "").strip()
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass this Feishu DM's user open_id (ou_...) as session_id.",
    }
  if sid in _PLACEHOLDER_SESSION_IDS:
    return {
        "error": "invalid_session_id",
        "message": (
            f"session_id {sid!r} is a documentation placeholder. Use the real "
            "Feishu open_id (ou_...) for this chat on every ap2-buyer tool call."
        ),
    }
  return None


def _invoke(session_id: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
  session_id = _canonical_session_id(session_id)
  err = _validate_session_id(session_id)
  if err:
    return err
  token = set_request_session_id(session_id)
  try:
    return run_with_session(session_id, fn, *args, **kwargs)
  finally:
    reset_request_session_id(token)


@mcp.tool()
def set_ap2_session_config_tool(
    session_id: str,
    presence_mode: str,
    payment_method: str,
    merchant: str | None = None,
) -> dict[str, Any]:
  """Set AP2 demo mode for this openclaw conversation (hp|hnp, card|x402)."""
  return _invoke(
      session_id,
      set_ap2_session_config,
      presence_mode,
      payment_method,
      merchant=merchant,
  )


@mcp.tool()
def get_ap2_session_config_tool(session_id: str) -> dict[str, Any]:
  """Return current presence, payment rail, and merchant instructions."""
  return _invoke(session_id, get_ap2_session_config)


def _deliver_mock_otp(session_id: str, result: dict[str, Any]) -> dict[str, Any]:
  """Attach the mock OTP code when register returns otp_required."""
  if result.get("status") != "otp_required":
    return result
  delivery = write_otp_delivery_file(session_id)
  record = get_otp_delivery_record(session_id)
  if delivery and record:
    _logger.info(
        "[buyer-mcp] OTP mock delivery session_id=%s path=%s expires_in=%ss "
        "(code included in tool response for mock trusted surface)",
        session_id,
        delivery.get("delivery_path") or record.get("delivery_path"),
        record.get("expires_in_seconds"),
    )
    sid = str(session_id).strip()
    code = str(record.get("code") or "")
    out = dict(result)
    out["otp_ref"] = sid
    out["otp_code"] = code
    out["feishu_user_message"] = (
        "OTP step-up required. "
        f"**OTP ref:** `{sid}`\n"
        f"**OTP code:** `{code}`\n"
        "Reply with this 6-digit code here to continue."
    )
    out["agent_instruction"] = (
        "Post feishu_user_message to the user verbatim (English). "
        "It already includes the mock OTP code. Never paste shell commands, "
        "script paths, mcporter, curl, or file paths in Feishu."
    )
    return out
  return result


@mcp.tool()
def register_trusted_surface_approval(
    session_id: str,
    price_cap: float,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
) -> dict[str, Any]:
  """Record explicit Feishu/user approval before signing mandates."""
  result = _register_ts(
      session_id, price_cap, payment_method, item_id, item_name=item_name
  )
  return _deliver_mock_otp(session_id, result)


@mcp.tool()
def verify_payment_otp(session_id: str, code: str) -> dict[str, Any]:
  """Verify OTP after register_trusted_surface_approval returns otp_required."""
  return _verify_otp(session_id, code)


@mcp.tool()
def create_trusted_surface_session(
    session_id: str,
    price_cap: float,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
    presence_mode: str = "hnp",
    payee: str = "",
    amount_cents: int = 0,
) -> dict[str, Any]:
  """Create H5 Trusted Surface session; return portal_url for user confirmation."""
  err = _validate_session_id(session_id)
  if err:
    return err
  ts_amount_cents = amount_cents if amount_cents > 0 else None
  return create_ts_session(
      session_id,
      price_cap=price_cap,
      payment_method=payment_method,
      item_id=item_id,
      item_name=item_name,
      presence_mode=presence_mode,
      payee=payee,
      amount_cents=ts_amount_cents,
  )


@mcp.tool()
def get_trusted_surface_status(ref: str) -> dict[str, Any]:
  """Return current H5 Trusted Surface session status (single check)."""
  return get_ts_session_status(ref)


@mcp.tool()
def wait_for_trusted_surface_signed(
    ref: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
  """Block until user confirms on the H5 portal (server-side long-poll).

  Call once after posting portal_url. Does not require the user to reply
  'done' in chat. Returns signed | expired | not_found | timeout.
  """
  return _wait_for_ts_signed(ref, timeout_seconds=timeout_seconds)


@mcp.tool()
def register_price_monitor_tool(
    session_id: str,
    item_id: str,
    price_cap: float,
    interval_minutes: float = 5,
    currency: str = "USD",
    item_name: str = "",
    merchant: str = "",
    max_ticks: int = 0,
) -> dict[str, Any]:
  """Arm HNP price monitoring; backend scheduler on :8105 drives ticks and purchase.

  After signing open mandates, call once with session_id, item_id, price_cap, and
  the user's chosen interval_minutes. Do not start OpenClaw cron or manual tick
  scripts — the scheduler checks prices and completes purchase automatically.
  """
  return register_price_monitor(
      session_id,
      item_id,
      price_cap,
      interval_minutes,
      currency=currency,
      item_name=item_name,
      merchant=merchant,
      max_ticks=max_ticks,
  )


@mcp.tool()
def get_price_monitor_status_tool(session_id: str) -> dict[str, Any]:
  """Return whether a scheduled monitoring reminder is due for Feishu."""
  return get_price_monitor_status(session_id)


@mcp.tool()
def complete_price_monitor_tick_tool(
    session_id: str,
    current_price: float,
    available: bool,
    meets_constraints: bool,
    message: str = "",
    not_found: bool = False,
    stop_reason: str = "",
) -> dict[str, Any]:
  """Record a tick; returns should_stop=true on purchase/not-found/cap (stop /loop)."""
  return complete_price_monitor_tick(
      session_id,
      current_price=current_price,
      available=available,
      meets_constraints=meets_constraints,
      message=message,
      not_found=not_found,
      stop_reason=stop_reason,
  )


@mcp.tool()
def clear_price_monitor_tool(session_id: str) -> dict[str, Any]:
  """Stop scheduled price-monitor reminders."""
  return clear_price_monitor(session_id)


@mcp.tool()
def assemble_and_sign_mandates(
    session_id: str,
    mandate_request: str,
) -> dict[str, Any]:
  """HNP: sign open checkout + payment mandates after user approval."""
  return _invoke(
      session_id,
      assemble_and_sign_mandates_tool,
      mandate_request,
  )


@mcp.tool()
def check_constraints(
    session_id: str,
    price: float,
    currency: str = "USD",
    available: bool = True,
) -> dict[str, Any]:
  """HNP: check price/availability against signed open mandates."""
  return _invoke(
      session_id,
      check_constraints_against_mandate,
      price=price,
      currency=currency,
      available=available,
  )


@mcp.tool()
def create_checkout_presentation_tool(
    session_id: str,
    checkout_jwt: str,
    checkout_hash: str,
    nonce: str,
    aud: str = "merchant",
) -> dict[str, Any]:
  """Present closed checkout mandate to merchant."""
  stop_price_monitor(session_id, "checkout_started")
  return _invoke(
      session_id,
      create_checkout_presentation,
      checkout_jwt=checkout_jwt,
      checkout_hash=checkout_hash,
      nonce=nonce,
      aud=aud,
  )


@mcp.tool()
def create_payment_presentation_tool(
    session_id: str,
    checkout_hash: str,
    amount_cents: int,
    nonce: str,
    currency: str = "USD",
    payee_json: str = "{}",
    aud: str = "credential-provider",
) -> dict[str, Any]:
  """Present closed payment mandate to credential provider."""
  stop_price_monitor(session_id, "checkout_started")
  return _invoke(
      session_id,
      create_payment_presentation,
      checkout_hash=checkout_hash,
      amount_cents=amount_cents,
      nonce=nonce,
      currency=currency,
      payee_json=payee_json,
      aud=aud,
  )


@mcp.tool()
def verify_checkout_receipt_tool(checkout_receipt: str) -> dict[str, Any]:
  """Verify merchant checkout receipt JWT."""
  return verify_checkout_receipt(checkout_receipt)


@mcp.tool()
def create_hp_open_mandates(
    session_id: str,
    mandate_request: str,
) -> dict[str, Any]:
  """HP step 1: create open checkout + payment mandates before create_checkout."""
  return _invoke(session_id, create_hp_open_mandates_tool, mandate_request)


@mcp.tool()
def assemble_and_sign_immediate_mandates(
    session_id: str,
    mandate_request: str,
) -> dict[str, Any]:
  """HP step 2: user-signed closed mandates after Feishu approval."""
  return _invoke(
      session_id,
      assemble_and_sign_immediate_mandates_tool,
      mandate_request,
  )


@mcp.tool()
def clear_open_mandate_session_tool(session_id: str) -> dict[str, Any]:
  """Drop open mandate pair only; preserve closed mandate history."""
  return _invoke(session_id, clear_open_mandate_session)


@mcp.tool()
def reset_temp_db_tool() -> dict[str, Any]:
  """Remove all mandate artifacts from .temp-db (keeps signing keys)."""
  if os.environ.get("AP2_ALLOW_RESET_TEMP_DB", "0").strip() != "1":
    return {
        "error": "reset_temp_db_disabled",
        "message": (
            "reset_temp_db_tool is disabled during live checkout. Do NOT call it "
            "to recover from errors — continue the HP/HNP flow from the last good "
            "step (issue_payment_credential → complete_checkout). Only the user can "
            "request a full reset in a new /new session."
        ),
    }
  return reset_temp_db()


if __name__ == "__main__":
  mcp.run()
