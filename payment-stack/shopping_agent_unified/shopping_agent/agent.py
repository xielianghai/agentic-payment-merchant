"""Unified Shopping Agent: HP + HNP, card + x402 via session config."""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from common.llm_config import get_adk_model
from google.adk.agents import Agent
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.tool_context import ToolContext
from mcp import StdioServerParameters

_ROLES_DIR = Path(__file__).resolve().parents[2]
_UNIFIED_ROOT = _ROLES_DIR.parent
if str(_ROLES_DIR) not in sys.path:
  sys.path.insert(0, str(_ROLES_DIR))

from constants_unified import (
    MPP_INITIATE_PAYMENT_URL,
    SUPPORTED_PAYMENT_METHODS,
    SUPPORTED_PRESENCE_MODES,
    X402_SETTLE_PAYMENT_URL,
)  # noqa: E402
from role_logging import log_op, log_op_result, setup_role_logger  # noqa: E402

from shopping_agent.mandate_bridge import (
  assemble_and_sign_mandates_tool,
  check_constraints_against_mandate,
  create_checkout_presentation,
  create_payment_presentation,
  verify_checkout_receipt,
)
from shopping_agent.mandate_tools_hp import (
  assemble_and_sign_immediate_mandates_tool,
  create_hp_open_mandates_tool,
)
from shopping_agent.merchant_profile import (
  MERCHANT_NEUTRAL_PREAMBLE,
  apply_mandate_overrides,
  get_active_merchant_key,
  get_merchant_profile,
  merchant_instruction_block,
  normalize_merchant_key,
  set_active_merchant_key,
)
from x402_wallet_sign_gate import (  # noqa: E402
  create_x402_wallet_sign_session as _create_x402_wallet_sign_session,
  wait_for_x402_wallet_signed,
)
from trusted_surface_gate import (  # noqa: E402
  create_ts_session,
  wait_for_trusted_surface_signed as _wait_for_trusted_surface_signed,
)

_AGENT_DIR = Path(__file__).resolve().parent
_UNIFIED_SCENARIO = _AGENT_DIR.parents[1]
_LOG_DIR = Path(os.environ.get("LOGS_DIR", _UNIFIED_SCENARIO / ".logs"))
_LOG_FILE = _LOG_DIR / "shopping-agent-unified.log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_logger = setup_role_logger(
    "shopping_agent_unified",
    log_file=_LOG_FILE,
    level=logging.DEBUG,
)

_MERCHANT_PROFILE = get_merchant_profile()
apply_mandate_overrides(_MERCHANT_PROFILE)
set_active_merchant_key(_MERCHANT_PROFILE.key)

_ADAPTER_SERVER = Path(
    os.environ.get(
        "ADAPTER_MCP_SERVER",
        str(_UNIFIED_SCENARIO.parent / "adapter/mcp/server.py"),
    )
)
_MERCHANT_SERVER = _ADAPTER_SERVER if _ADAPTER_SERVER.is_file() else _ROLES_DIR / "merchant_router_unified" / "server.py"
_BUYER_SERVER = _ROLES_DIR / "buyer_mcp_unified" / "server.py"
_CP_SERVER = _ROLES_DIR / "credentials_provider_unified" / "server.py"
_MPP_SERVER = _ROLES_DIR / "merchant_payment_processor_unified" / "server.py"
_PROMPTS_DIR = _AGENT_DIR / "prompts"


def _instruction_neutral(filename: str) -> str:
  """Load prompt templates without binding to one merchant at import time."""
  template = (_PROMPTS_DIR / filename).read_text()
  neutral = template.replace(
      "{{OOS_SECTION}}",
      "(See **merchant_instruction** from get_ap2_session_config.)",
  )
  neutral = neutral.replace(
      "{{HNP_OOS_HINT}}",
      "(See **merchant_instruction** from get_ap2_session_config.)",
  )
  for token in (
      "{{EXAMPLE_ITEM_NAME}}",
      "{{EXAMPLE_TOTAL_CENTS}}",
      "{{CURRENCY}}",
  ):
    neutral = neutral.replace(token, "(from get_ap2_session_config)")
  return f"{MERCHANT_NEUTRAL_PREAMBLE}\n\n{neutral}"


def _session_merchant_key(tool_context: ToolContext) -> str:
  stored = tool_context.state.get("ap2:merchant")
  if stored:
    return normalize_merchant_key(str(stored))
  return get_active_merchant_key()


def _make_mcp_toolset(server_path: Path, tool_filter=None) -> McpToolset:
  env = os.environ.copy()
  env.setdefault("LOGS_DIR", str(_UNIFIED_SCENARIO / ".logs"))
  env.setdefault("TEMP_DB_DIR", str(_UNIFIED_SCENARIO / ".temp-db"))
  if "AP2_TOKEN_STORE_PATH" not in env:
    env["AP2_TOKEN_STORE_PATH"] = str(
        Path(env["TEMP_DB_DIR"]) / "ap2_token_store.json"
    )
  env["MERCHANT_PAYMENT_PROCESSOR_URL"] = MPP_INITIATE_PAYMENT_URL
  env["X402_PSP_SETTLE_URL"] = X402_SETTLE_PAYMENT_URL
  env["HEG_FLIGHT_BACKEND_URL"] = os.environ.get(
      "HEG_FLIGHT_BACKEND_URL", "http://127.0.0.1:9000"
  )
  return McpToolset(
      connection_params=StdioConnectionParams(
          server_params=StdioServerParameters(
              command=sys.executable,
              args=[server_path.name],
              cwd=str(server_path.parent),
              env=env,
          ),
          timeout=60.0,
      ),
      tool_filter=tool_filter,
  )


def _payment_method_description(
    payment_method: str, session_id: str = ""
) -> str:
  """Human-readable payment rail label for mandate / checkout UI."""
  if payment_method == "x402":
    try:
      from common.x402_eip712 import x402_wallet_mode
      from common.x402_wallet_sign_store import get_wallet_address_for_session

      if x402_wallet_mode() != "mock":
        addr = get_wallet_address_for_session(session_id) if session_id else None
        if addr:
          masked = f"{addr[:6]}...{addr[-4:]}"
          return f"x402 · {masked} · SepoliaETH (Sepolia)"
        return "x402 · MetaMask · SepoliaETH (Sepolia)"

      from eth_account import Account

      from common.x402_constants import DEFAULT_USER_PRIVATE_KEY

      private_key = (
          os.environ.get("X402_USER_PRIVATE_KEY") or DEFAULT_USER_PRIVATE_KEY
      )
      address = Account.from_key(private_key).address
      masked = f"{address[:6]}...{address[-4:]}"
      return f"x402 · {masked} · SepoliaETH (Sepolia)"
    except Exception:
      return "x402 · SepoliaETH (Sepolia)"
  return "Card •••4242"


def _tool_context_session_id(tool_context: ToolContext) -> str:
  """Best-effort session id for payment display labels."""
  try:
    return str(tool_context._invocation_context.session.id)
  except AttributeError:
    return ""


def create_x402_wallet_sign_session(
    payment_mandate_chain_id: str,
    tool_context: ToolContext,
    payment_nonce: str = "",
) -> dict[str, Any]:
  """Create a MetaMask x402 signing session for the current ADK session."""
  return _create_x402_wallet_sign_session(
      _tool_context_session_id(tool_context),
      payment_mandate_chain_id,
      payment_nonce=payment_nonce.strip() or None,
  )


def create_trusted_surface_session(
    price_cap: float,
    tool_context: ToolContext,
    payment_method: str = "card",
    item_id: str = "",
    item_name: str = "",
    presence_mode: str = "hp",
    amount_cents: int = 0,
) -> dict[str, Any]:
  """Create H5 Trusted Surface session; return portal_url (/ts/confirm?ref=...)."""
  ts_amount_cents = amount_cents if amount_cents > 0 else None
  return create_ts_session(
      _tool_context_session_id(tool_context),
      price_cap=price_cap,
      payment_method=payment_method,
      item_id=item_id,
      item_name=item_name,
      presence_mode=presence_mode,
      amount_cents=ts_amount_cents,
  )


def wait_for_trusted_surface_signed(
    ref: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
  """Poll until user confirms on /ts/confirm (card/HNP mandate portal)."""
  return _wait_for_trusted_surface_signed(ref, timeout_seconds=timeout_seconds)


def set_ap2_session_config(
    presence_mode: str,
    payment_method: str,
    tool_context: ToolContext,
    merchant: str | None = None,
) -> dict[str, str | bool]:
  """Store AP2 demo mode in session (hp|hnp, card|x402, optional merchant)."""
  log_op(
      _logger,
      "shopping-agent",
      "set_ap2_session_config",
      presence=presence_mode,
      payment=payment_method,
      merchant=merchant,
  )
  presence = presence_mode.strip().lower()
  payment = payment_method.strip().lower()
  if presence not in SUPPORTED_PRESENCE_MODES:
    return {
        "error": "invalid_presence_mode",
        "message": f"Use one of: {sorted(SUPPORTED_PRESENCE_MODES)}",
    }
  if payment not in SUPPORTED_PAYMENT_METHODS:
    return {
        "error": "invalid_payment_method",
        "message": f"Use one of: {sorted(SUPPORTED_PAYMENT_METHODS)}",
    }
  tool_context.state["ap2:presence_mode"] = presence
  prev_payment = tool_context.state.get("ap2:payment_method")
  tool_context.state["ap2:payment_method"] = payment
  os.environ["FLOW"] = payment

  prev_merchant = _session_merchant_key(tool_context)
  if merchant:
    merchant_key = set_active_merchant_key(merchant)
    tool_context.state["ap2:merchant"] = merchant_key
    apply_mandate_overrides(get_merchant_profile(merchant_key))
  else:
    merchant_key = prev_merchant
    tool_context.state.setdefault("ap2:merchant", merchant_key)

  _logger.info(
      "Session config: presence=%s payment=%s merchant=%s",
      presence,
      payment,
      merchant_key,
  )

  profile = get_merchant_profile(merchant_key)
  result: dict[str, str | bool] = {
      "status": "ok",
      "presence_mode": presence,
      "payment_method": payment,
      "payment_method_description": _payment_method_description(
          payment, _tool_context_session_id(tool_context)
      ),
      "merchant": merchant_key,
      "merchant_display_name": profile.display_name,
      "currency": profile.currency,
      "merchant_instruction": merchant_instruction_block(profile),
  }

  had_open_mandates = bool(
      tool_context.state.get("app:open_checkout_mandate_id")
      or tool_context.state.get("app:open_payment_mandate_id")
  )
  if (
      merchant
      and normalize_merchant_key(merchant) != prev_merchant
      and had_open_mandates
  ):
    reset_result = clear_open_mandate_session(tool_context)
    log_op(
        _logger,
        "shopping-agent",
        "merchant_switch",
        from_merchant=prev_merchant,
        to_merchant=merchant_key,
        removed=reset_result.get("removed_open_mandate_files"),
    )
    result["merchant_changed"] = True
    result["requires_reauthorization"] = True
    result["message"] = (
        f"Merchant changed from {prev_merchant} to {merchant_key}. "
        "Open mandates invalidated; emit a new mandate_request if needed."
    )
    if "error" in reset_result:
      result["reset_warning"] = reset_result.get("message", "")
  elif prev_payment and prev_payment != payment and had_open_mandates:
    reset_result = clear_open_mandate_session(tool_context)
    log_op(
        _logger,
        "shopping-agent",
        "payment_rail_switch",
        from_rail=prev_payment,
        to_rail=payment,
        removed=reset_result.get("removed_open_mandate_files"),
    )
    result["payment_method_changed"] = True
    result["requires_reauthorization"] = True
    result["message"] = (
        "Payment rail changed from "
        f"{prev_payment} to {payment}. Open mandates invalidated; "
        "closed mandate history preserved. "
        "Emit a new mandate_request so the user can Approve & Sign again."
    )
    if "error" in reset_result:
      result["reset_warning"] = reset_result.get("message", "")

  log_op_result(_logger, "shopping-agent", "set_ap2_session_config", result)
  return result


def get_ap2_session_config(tool_context: ToolContext) -> dict[str, str]:
  """Return current session presence, payment method, and merchant profile."""
  presence = tool_context.state.get("ap2:presence_mode")
  payment = tool_context.state.get("ap2:payment_method")
  merchant_key = _session_merchant_key(tool_context)
  tool_context.state.setdefault("ap2:merchant", merchant_key)
  profile = get_merchant_profile(merchant_key)
  apply_mandate_overrides(profile)
  set_active_merchant_key(merchant_key)
  result = {
      "presence_mode": presence or "unset",
      "payment_method": payment or "unset",
      "configured": bool(presence and payment),
      "merchant": merchant_key,
      "merchant_display_name": profile.display_name,
      "currency": profile.currency,
      "merchant_instruction": merchant_instruction_block(profile),
  }
  if presence and payment:
    result["payment_method_description"] = _payment_method_description(
        payment, _tool_context_session_id(tool_context)
    )
  log_op(_logger, "shopping-agent", "get_ap2_session_config", **result)
  return result


def _error_escalation_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, str] | None:
  if isinstance(tool_response, dict) and "error" in tool_response:
    code = tool_response["error"]
    msg = tool_response.get("message", str(tool_response))
    log_op(
        _logger,
        "shopping-agent",
        "tool_error_escalation",
        tool=getattr(tool, "name", type(tool).__name__),
        error=code,
        message=msg,
    )
    error_json = json.dumps(
        {"type": "error", "error": code, "message": msg},
        ensure_ascii=True,
    )
    return {
        "error": code,
        "message": msg,
        "action_required": (
            "STOP all processing. Emit EXACTLY this JSON as your"
            f" complete response, nothing else: {error_json}"
        ),
    }
  return None


def _delete_mandate_file(mandate_id: str) -> bool:
  """Remove one persisted SD-JWT by mandate id (e.g. open_chk_…)."""
  if not mandate_id:
    return False
  temp_db_dir = Path(os.environ.get("TEMP_DB_DIR", _UNIFIED_SCENARIO / ".temp-db"))
  file_path = temp_db_dir / f"{mandate_id}.sdjwt"
  try:
    if file_path.is_file():
      file_path.unlink()
      return True
  except OSError as e:
    _logger.warning("Failed to delete mandate file %s: %s", file_path, e)
  return False


def _remove_state_keys(state: Any, *keys: str) -> None:
  """Remove session keys; ADK State has no public pop/delete."""
  for key in keys:
    if hasattr(state, "pop"):
      state.pop(key, None)
      continue
    for bucket_name in ("_value", "_delta"):
      bucket = getattr(state, bucket_name, None)
      if isinstance(bucket, dict):
        bucket.pop(key, None)


def clear_open_mandate_session(tool_context: ToolContext) -> dict[str, str | int]:
  """Invalidate only the current open mandate pair; preserve closed mandate history."""
  log_op(
      _logger,
      "shopping-agent",
      "clear_open_mandate_session",
      open_checkout=tool_context.state.get("app:open_checkout_mandate_id"),
      open_payment=tool_context.state.get("app:open_payment_mandate_id"),
  )
  open_checkout_id = str(tool_context.state.get("app:open_checkout_mandate_id", ""))
  open_payment_id = str(tool_context.state.get("app:open_payment_mandate_id", ""))
  removed = 0
  if _delete_mandate_file(open_checkout_id):
    removed += 1
  if _delete_mandate_file(open_payment_id):
    removed += 1
  _remove_state_keys(
      tool_context.state,
      "app:open_checkout_mandate_id",
      "app:open_payment_mandate_id",
      "app:open_checkout_hash",
      "app:signed_payment_method",
  )
  result = {
      "status": "ok",
      "removed_open_mandate_files": removed,
      "message": (
          "Cleared open mandate session state"
          + (f" ({removed} file(s) removed)" if removed else "")
          + "; closed mandate records (chk_/pay_) were preserved."
      ),
  }
  log_op_result(_logger, "shopping-agent", "clear_open_mandate_session", result)
  return result


def reset_temp_db() -> dict[str, str]:
  """Remove mandate files from unified .temp-db (preserves keys).

  Deletes open *and* closed mandate artifacts — use only when the user asks
  to start over. Payment-rail switches use clear_open_mandate_session instead.
  """
  log_op(_logger, "shopping-agent", "reset_temp_db START")
  try:
    temp_db_dir = Path(os.environ.get("TEMP_DB_DIR", _UNIFIED_SCENARIO / ".temp-db"))
    if not temp_db_dir.exists():
      result = {"status": "ok", "message": f"No temp DB at {temp_db_dir}"}
      log_op_result(_logger, "shopping-agent", "reset_temp_db", result)
      return result
    prefixes = ("chk_", "open_chk_", "pay_", "open_pay_")
    count = sum(
        1
        for item in temp_db_dir.iterdir()
        if item.is_file() and item.name.startswith(prefixes)
    )
    for item in temp_db_dir.iterdir():
      if item.is_file() and item.name.startswith(prefixes):
        item.unlink()
    result = {
        "status": "ok",
        "message": f"Removed {count} mandate files from {temp_db_dir}",
    }
    log_op_result(_logger, "shopping-agent", "reset_temp_db", result, count=count)
    return result
  except OSError as e:
    result = {"error": "reset_failed", "message": str(e)}
    log_op_result(_logger, "shopping-agent", "reset_temp_db", result)
    return result


_model = get_adk_model()

_MCP_TOOLS_PURCHASE = [
    _make_mcp_toolset(_MERCHANT_SERVER),
    _make_mcp_toolset(_CP_SERVER),
    _make_mcp_toolset(
        _MPP_SERVER,
        tool_filter=lambda tool, ctx=None: tool.name
        not in ("initiate_or_settle_payment",),
    ),
]

_PURCHASE_HNP_INSTRUCTION = _instruction_neutral("purchase_hnp.md")
_PURCHASE_HP_INSTRUCTION = _instruction_neutral("purchase_hp.md")

purchase_hnp_agent = Agent(
    name="purchase_hnp_agent",
    model=_model,
    description="HNP autonomous purchase when constraints are met.",
    instruction=_PURCHASE_HNP_INSTRUCTION,
    output_key="purchase_result",
    tools=[
        check_constraints_against_mandate,
        create_checkout_presentation,
        create_payment_presentation,
        verify_checkout_receipt,
        get_ap2_session_config,
        _make_mcp_toolset(
            _BUYER_SERVER,
            tool_filter=lambda tool, ctx=None: tool.name == "clear_price_monitor_tool",
        ),
        create_x402_wallet_sign_session,
        wait_for_x402_wallet_signed,
        *_MCP_TOOLS_PURCHASE,
    ],
    after_tool_callback=_error_escalation_callback,
)

purchase_hp_agent = Agent(
    name="purchase_hp_agent",
    model=_model,
    description="HP immediate purchase with user-signed closed mandates.",
    instruction=_PURCHASE_HP_INSTRUCTION,
    output_key="purchase_hp_result",
    tools=[
        create_hp_open_mandates_tool,
        assemble_and_sign_immediate_mandates_tool,
        get_ap2_session_config,
        create_x402_wallet_sign_session,
        wait_for_x402_wallet_signed,
        create_trusted_surface_session,
        wait_for_trusted_surface_signed,
        *_MCP_TOOLS_PURCHASE,
    ],
    after_tool_callback=_error_escalation_callback,
)

monitoring_agent = Agent(
    name="monitoring_agent",
    model=_model,
    description=(
        "HNP: poll check_product + check_constraints; emit monitoring artifacts. "
        "Backend scheduler (:8105) owns purchase — never transfer to purchase_hnp_agent."
    ),
    instruction=_instruction_neutral("monitoring_unified.md"),
    output_key="monitoring_result",
    tools=[
        check_constraints_against_mandate,
        get_ap2_session_config,
        _make_mcp_toolset(_MERCHANT_SERVER),
    ],
    after_tool_callback=_error_escalation_callback,
)

consent_agent = Agent(
    name="consent_agent",
    model=_model,
    description=(
        "Unified consent: HNP drop delegation or HP immediate shop."
        " Call set_ap2_session_config first."
    ),
    instruction=_instruction_neutral("consent_unified.md"),
    output_key="consent_result",
    tools=[
        set_ap2_session_config,
        get_ap2_session_config,
        reset_temp_db,
        assemble_and_sign_mandates_tool,
        _make_mcp_toolset(_MERCHANT_SERVER),
    ],
    sub_agents=[monitoring_agent, purchase_hp_agent],
    after_tool_callback=_error_escalation_callback,
)

root_agent = consent_agent
