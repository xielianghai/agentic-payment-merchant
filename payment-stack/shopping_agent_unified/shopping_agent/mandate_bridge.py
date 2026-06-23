"""Bridge to shopping_agent_v2 mandate tools with runtime payment_method."""

import importlib.util
import json
import os
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from google.adk.tools.tool_context import ToolContext

from role_logging import log_op, log_op_result, setup_role_logger

_GATE_ROOT = Path(__file__).resolve().parents[1]
_STACK_ROOT = _GATE_ROOT.parent
if str(_GATE_ROOT) not in sys.path:
  sys.path.insert(0, str(_GATE_ROOT))
if str(_STACK_ROOT) not in sys.path:
  sys.path.insert(0, str(_STACK_ROOT))
from path_setup import ensure_src_on_path  # noqa: E402
from trusted_surface_gate import (  # noqa: E402
    approval_vi_l2_credential_id,
    check_assemble_allowed,
)

_V2_MANDATE_TOOLS_PATH = (
    ensure_src_on_path()
    / "roles"
    / "shopping_agent_v2"
    / "shopping_agent"
    / "mandate_tools.py"
)

_logger = setup_role_logger("mandate-bridge")

F = TypeVar("F", bound=Callable[..., Any])


def _load_v2_mandate_tools():
  """Load v2 mandate_tools without importing v2 shopping_agent package __init__."""
  spec = importlib.util.spec_from_file_location(
      "v2_mandate_tools", _V2_MANDATE_TOOLS_PATH
  )
  if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {_V2_MANDATE_TOOLS_PATH}")
  mod = importlib.util.module_from_spec(spec)
  mod.__spec__ = spec
  sys.modules["v2_mandate_tools"] = mod
  spec.loader.exec_module(mod)
  return mod


_mt_module = _load_v2_mandate_tools()


def _sync_flow_from_context(tool_context: ToolContext) -> None:
  pm = tool_context.state.get("ap2:payment_method", "card")
  os.environ["FLOW"] = str(pm)
  # mandate_tools reads _PAYMENT_METHOD at call time; avoid importlib.reload
  # on the dynamically loaded module (reload raises "spec not found").
  _mt_module._PAYMENT_METHOD = str(pm)


def _bridge_log(op: str, **fields: Any) -> Callable[[F], F]:
  def decorator(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
      log_op(_logger, "mandate-bridge", f"{op} START", **fields)
      try:
        result = fn(*args, **kwargs)
        log_op_result(_logger, "mandate-bridge", op, result)
        return result
      except Exception as exc:
        log_op(_logger, "mandate-bridge", f"{op} EXCEPTION", error=str(exc))
        raise

    return wrapper  # type: ignore[return-value]

  return decorator


@_bridge_log("assemble_and_sign_mandates_tool")
def assemble_and_sign_mandates_tool(
    mandate_request: str,
    tool_context: ToolContext,
) -> dict[str, str]:
  _sync_flow_from_context(tool_context)
  preview = (mandate_request or "")[:120]
  log_op(_logger, "mandate-bridge", "mandate_request", preview=preview)
  try:
    raw = (
        json.loads(mandate_request)
        if isinstance(mandate_request, str)
        else dict(mandate_request)
    )
    normalized = _mt_module.normalize_mandate_request(raw)
    pm = str(tool_context.state.get("ap2:payment_method", "card"))
    session_id = (
        raw.get("session_id")
        or tool_context.state.get("app:session_id")
        or tool_context.state.get("session_id")
    )
    gate_err = check_assemble_allowed(
        normalized["price_cap"],
        pm,
        session_id=str(session_id or ""),
        item_id=str(normalized.get("item_id", "")),
    )
    if gate_err:
      log_op_result(_logger, "mandate-bridge", "assemble blocked", gate_err)
      return gate_err
  except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
    log_op(_logger, "mandate-bridge", "assemble gate skip", error=str(exc))
    return {
        "error": "mandate_request_invalid",
        "message": f"Cannot assemble mandates: {exc}",
    }
  result = _mt_module.assemble_and_sign_mandates_tool(mandate_request, tool_context)
  if (
      isinstance(result, dict)
      and not result.get("error")
      and str(tool_context.state.get("ap2:payment_method", "card")) == "card"
  ):
    sid = str(
        session_id
        or tool_context.state.get("app:session_id")
        or tool_context.state.get("session_id")
        or ""
    )
    l2_id = approval_vi_l2_credential_id(sid or None)
    if l2_id:
      tool_context.state["vi:l2_credential_id"] = l2_id
      result["vi_l2_credential_id"] = l2_id
  return result


assemble_and_sign_mandates_tool.__doc__ = (
    _mt_module.assemble_and_sign_mandates_tool.__doc__
)


@_bridge_log("check_constraints_against_mandate")
def check_constraints_against_mandate(
    price: float,
    currency: str = "USD",
    available: bool = True,
    tool_context: ToolContext = None,
) -> dict[str, Any]:
  log_op(
      _logger,
      "mandate-bridge",
      "check_constraints",
      price=price,
      currency=currency,
      available=available,
  )
  if tool_context:
    _sync_flow_from_context(tool_context)
  return _mt_module.check_constraints_against_mandate(
      price=price,
      currency=currency,
      available=available,
      tool_context=tool_context,
  )


check_constraints_against_mandate.__doc__ = (
    _mt_module.check_constraints_against_mandate.__doc__
)


@_bridge_log("create_checkout_presentation")
def create_checkout_presentation(
    checkout_jwt: str,
    checkout_hash: str,
    nonce: str,
    aud: str = "merchant",
    tool_context: ToolContext = None,
) -> dict[str, str]:
  log_op(
      _logger,
      "mandate-bridge",
      "create_checkout_presentation",
      checkout_hash=checkout_hash[:16] if checkout_hash else None,
      aud=aud,
  )
  if tool_context:
    _sync_flow_from_context(tool_context)
  return _mt_module.create_checkout_presentation(
      checkout_jwt=checkout_jwt,
      checkout_hash=checkout_hash,
      nonce=nonce,
      aud=aud,
      tool_context=tool_context,
  )


create_checkout_presentation.__doc__ = (
    _mt_module.create_checkout_presentation.__doc__
)


@_bridge_log("create_payment_presentation")
def create_payment_presentation(
    checkout_hash: str,
    amount_cents: int,
    nonce: str,
    currency: str = "USD",
    payee_json: str = "{}",
    aud: str = "credential-provider",
    tool_context: ToolContext = None,
) -> dict[str, str]:
  log_op(
      _logger,
      "mandate-bridge",
      "create_payment_presentation",
      checkout_hash=checkout_hash[:16] if checkout_hash else None,
      amount_cents=amount_cents,
      currency=currency,
      aud=aud,
  )
  if tool_context:
    _sync_flow_from_context(tool_context)
  return _mt_module.create_payment_presentation(
      checkout_hash=checkout_hash,
      amount_cents=amount_cents,
      nonce=nonce,
      currency=currency,
      payee_json=payee_json,
      aud=aud,
      tool_context=tool_context,
  )


create_payment_presentation.__doc__ = _mt_module.create_payment_presentation.__doc__


@_bridge_log("verify_checkout_receipt")
def verify_checkout_receipt(
    checkout_receipt: str,
) -> dict[str, Any]:
  log_op(
      _logger,
      "mandate-bridge",
      "verify_checkout_receipt",
      receipt_len=len(checkout_receipt) if checkout_receipt else 0,
  )
  return _mt_module.verify_checkout_receipt(checkout_receipt)


verify_checkout_receipt.__doc__ = _mt_module.verify_checkout_receipt.__doc__
