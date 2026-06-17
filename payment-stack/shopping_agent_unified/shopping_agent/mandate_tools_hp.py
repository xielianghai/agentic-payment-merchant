"""HP immediate mandates: Open (agent_provider, cnf=user) + Closed (user key)."""

import json
import os
import time
import uuid

from typing import Any

from google.adk.tools.tool_context import ToolContext
from jwcrypto.jwk import JWK

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_payment_mandate import AllowedPaymentInstruments
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient
from ap2.sdk.sdjwt import compute_sd_hash, parse_token
from common.constants import DEFAULT_MANDATE_TTL_SECONDS, TEMP_DB
from shopping_agent.mandate_bridge import _mt_module as _mt_v2

DEMO_MERCHANT = _mt_v2.DEMO_MERCHANT
DEFAULT_CURRENCY = _mt_v2._DEFAULT_CURRENCY
X402_PAYMENT_INSTRUMENT = _mt_v2.X402_PAYMENT_INSTRUMENT
DEMO_PAYMENT_INSTRUMENT = _mt_v2.DEMO_PAYMENT_INSTRUMENT
_get_agent_provider_signing_key = _mt_v2._get_agent_provider_signing_key
_persist_mandate = _mt_v2._persist_mandate
_build_open_checkout_mandate = _mt_v2._build_open_checkout_mandate
_build_open_payment_mandate = _mt_v2._build_open_payment_mandate

from shopping_agent.keys_hp import get_or_create_user_signing_key
from role_logging import log_op, log_op_result, setup_role_logger
from trusted_surface_gate import check_assemble_allowed  # noqa: E402

_logger = setup_role_logger("mandate_tools_hp")


def _payment_instrument(payment_method: str) -> PaymentInstrument:
  if payment_method == "x402":
    return X402_PAYMENT_INSTRUMENT
  return DEMO_PAYMENT_INSTRUMENT


def _parse_immediate_req(mandate_request: str | dict[str, Any]) -> dict[str, Any]:
  req = (
      json.loads(mandate_request)
      if isinstance(mandate_request, str)
      else mandate_request
  )
  if not isinstance(req, dict):
    raise ValueError("mandate_request must be a JSON object")
  return req


def _apply_payment_method(
    req: dict[str, Any], tool_context: ToolContext
) -> str:
  payment_method = (req.get("payment_method") or "card").strip().lower()
  os.environ["FLOW"] = payment_method
  tool_context.state["ap2:payment_method"] = payment_method
  _mt_v2._PAYMENT_METHOD = payment_method
  return payment_method


def _create_open_mandate_pair(
    req: dict[str, Any],
    payment_method: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
  """Create and persist open checkout + payment mandates (HP step before create_checkout)."""
  user_key = get_or_create_user_signing_key()
  user_pub = JWK.from_json(user_key.export_public())
  agent_provider_key = _get_agent_provider_signing_key()

  now = int(time.time())
  ttl = int(req.get("ttl_seconds", DEFAULT_MANDATE_TTL_SECONDS))

  open_checkout_model = _build_open_checkout_mandate(req, user_pub, now, ttl)
  client = MandateClient()
  open_checkout_sdjwt = client.create(
      payloads=[open_checkout_model],
      issuer_key=agent_provider_key,
  )
  checkout_reference = compute_sd_hash(parse_token(open_checkout_sdjwt))

  open_payment_model = _build_open_payment_mandate(
      req, user_pub, checkout_reference, now, ttl
  )
  if payment_method == "x402":
    open_payment_model.constraints.append(
        AllowedPaymentInstruments(allowed=[X402_PAYMENT_INSTRUMENT])
    )

  open_payment_sdjwt = client.create(
      payloads=[open_payment_model],
      issuer_key=agent_provider_key,
  )

  open_checkout_id = "open_chk_" + str(uuid.uuid4()).replace("-", "")
  open_payment_id = "open_pay_" + str(uuid.uuid4()).replace("-", "")
  _persist_mandate(f"{open_checkout_id}.sdjwt", open_checkout_sdjwt)
  _persist_mandate(f"{open_payment_id}.sdjwt", open_payment_sdjwt)

  open_checkout_hash = compute_sd_hash(parse_token(open_checkout_sdjwt))

  tool_context.state["app:open_checkout_mandate_id"] = open_checkout_id
  tool_context.state["app:open_payment_mandate_id"] = open_payment_id
  tool_context.state["app:open_checkout_hash"] = open_checkout_hash
  tool_context.state["ap2:presence_mode"] = "hp"

  return {
      "open_checkout_mandate": open_checkout_id,
      "open_payment_mandate": open_payment_id,
      "open_checkout_hash": open_checkout_hash,
      "open_checkout_mandate_id": open_checkout_id,
      "open_payment_mandate_id": open_payment_id,
      "open_checkout_sdjwt": open_checkout_sdjwt,
      "open_payment_sdjwt": open_payment_sdjwt,
      "presence_mode": "hp",
      "payment_method": payment_method,
  }


def create_hp_open_mandates_tool(
    mandate_request: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
  """HP step 1: open checkout + payment mandates (before merchant create_checkout).

  Args:
      mandate_request: JSON with item_id, price_cap, qty, payment_method (card|x402).
        Do not pass checkout_jwt yet.
  """
  log_op(_logger, "mandate-hp", "create_hp_open_mandates_tool START")
  try:
    req = _parse_immediate_req(mandate_request)
    payment_method = _apply_payment_method(req, tool_context)
    result = _create_open_mandate_pair(req, payment_method, tool_context)
    # Drop raw SD-JWT strings from tool response (large); ids are enough.
    result.pop("open_checkout_sdjwt", None)
    result.pop("open_payment_sdjwt", None)
    log_op_result(_logger, "mandate-hp", "create_hp_open_mandates_tool", result)
    return result
  except (json.JSONDecodeError, KeyError, ValueError) as e:
    result = {"error": "open_mandate_failed", "message": str(e)}
    log_op_result(_logger, "mandate-hp", "create_hp_open_mandates_tool", result)
    return result


def _load_open_mandates_from_session(
    tool_context: ToolContext,
) -> tuple[str, str, str, str] | None:
  open_checkout_id = tool_context.state.get("app:open_checkout_mandate_id")
  open_payment_id = tool_context.state.get("app:open_payment_mandate_id")
  if not open_checkout_id or not open_payment_id:
    return None
  checkout_path = TEMP_DB / f"{open_checkout_id}.sdjwt"
  payment_path = TEMP_DB / f"{open_payment_id}.sdjwt"
  if not checkout_path.exists() or not payment_path.exists():
    return None
  return (
      open_checkout_id,
      open_payment_id,
      checkout_path.read_text(encoding="ascii").strip(),
      payment_path.read_text(encoding="ascii").strip(),
  )


def assemble_and_sign_immediate_mandates_tool(
    mandate_request: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
  """HP step 2 (after user Confirm): user-sign closed mandates, reuse open pair.

  Args:
      mandate_request: JSON with checkout_jwt, checkout_jwt_hash, amount_cents,
        payment_method, item_id, price_cap, qty. Open mandates must exist in session
        (from create_hp_open_mandates_tool) unless mandate_request recreates them.
  """
  log_op(_logger, "mandate-hp", "assemble_and_sign_immediate_mandates_tool START")
  try:
    req = _parse_immediate_req(mandate_request)
    log_op(
        _logger,
        "mandate-hp",
        "immediate mandate request",
        item_id=req.get("item_id"),
        price_cap=req.get("price_cap"),
        payment_method=req.get("payment_method"),
    )
    payment_method = _apply_payment_method(req, tool_context)

    # Trusted Surface is MANDATORY for HP signing. Fail closed: if the caller
    # omitted price_cap, derive it from amount_cents so the gate always runs and
    # cannot be bypassed by leaving price_cap out of the request.
    price_cap = req.get("price_cap")
    if price_cap is None:
      amount_cents = req.get("amount_cents")
      if amount_cents is not None:
        try:
          price_cap = int(amount_cents) / 100.0
        except (TypeError, ValueError):
          price_cap = None
    gate_err = check_assemble_allowed(
        float(price_cap) if price_cap is not None else 0.0,
        payment_method,
        amount_cents=req.get("amount_cents"),
    )
    if gate_err:
      log_op_result(_logger, "mandate-hp", "assemble blocked", gate_err)
      return gate_err

    loaded = _load_open_mandates_from_session(tool_context)
    if loaded:
      open_checkout_id, open_payment_id, open_checkout_sdjwt, open_payment_sdjwt = (
          loaded
      )
      log_op(
          _logger,
          "mandate-hp",
          "reuse open mandates",
          open_checkout_mandate=open_checkout_id,
          open_payment_mandate=open_payment_id,
      )
    else:
      open_result = _create_open_mandate_pair(req, payment_method, tool_context)
      open_checkout_id = open_result["open_checkout_mandate"]
      open_payment_id = open_result["open_payment_mandate"]
      open_checkout_sdjwt = open_result["open_checkout_sdjwt"]
      open_payment_sdjwt = open_result["open_payment_sdjwt"]

    user_key = get_or_create_user_signing_key()
    client = MandateClient()

    checkout_jwt = req["checkout_jwt"]
    checkout_jwt_hash = req["checkout_jwt_hash"]
    checkout_nonce = req.get("checkout_nonce") or str(uuid.uuid4())
    payment_nonce = req.get("payment_nonce") or str(uuid.uuid4())
    amount_cents = int(req["amount_cents"])

    closed_checkout = CheckoutMandate(
        checkout_jwt=checkout_jwt,
        checkout_hash=checkout_jwt_hash,
    )
    chk_chain = client.present(
        holder_key=user_key,
        mandate_token=open_checkout_sdjwt,
        payloads=[closed_checkout],
        nonce=checkout_nonce,
        aud="merchant",
    )
    chk_id = "chk_" + str(uuid.uuid4()).replace("-", "")
    _persist_mandate(f"{chk_id}.sdjwt", chk_chain)

    payee = Merchant(**req["payee"]) if req.get("payee") else DEMO_MERCHANT
    closed_payment = PaymentMandate(
        payment_amount=Amount(currency=DEFAULT_CURRENCY, amount=amount_cents),
        payment_instrument=_payment_instrument(payment_method),
        payee=payee,
        transaction_id=checkout_jwt_hash,
    )
    pay_chain = client.present(
        holder_key=user_key,
        mandate_token=open_payment_sdjwt,
        payloads=[closed_payment],
        nonce=payment_nonce,
        aud="credential-provider",
    )
    pay_id = "pay_" + str(uuid.uuid4()).replace("-", "")
    _persist_mandate(f"{pay_id}.sdjwt", pay_chain)

    open_checkout_hash = compute_sd_hash(parse_token(open_checkout_sdjwt))

    tool_context.state["app:open_checkout_mandate_id"] = open_checkout_id
    tool_context.state["app:open_payment_mandate_id"] = open_payment_id
    tool_context.state["app:open_checkout_hash"] = open_checkout_hash
    tool_context.state["temp:checkout_mandate_chain"] = chk_id
    tool_context.state["temp:checkout_nonce"] = checkout_nonce
    tool_context.state["temp:payment_mandate_chain"] = pay_id
    tool_context.state["temp:payment_nonce"] = payment_nonce
    tool_context.state["ap2:presence_mode"] = "hp"

    result = {
        "open_checkout_mandate": open_checkout_id,
        "open_payment_mandate": open_payment_id,
        "open_checkout_hash": open_checkout_hash,
        "checkout_mandate_chain_id": chk_id,
        "payment_mandate_chain_id": pay_id,
        "checkout_nonce": checkout_nonce,
        "payment_nonce": payment_nonce,
        "presence_mode": "hp",
        "payment_method": payment_method,
    }
    log_op_result(
        _logger, "mandate-hp", "assemble_and_sign_immediate_mandates_tool", result
    )
    return result
  except (json.JSONDecodeError, KeyError, ValueError) as e:
    result = {"error": "immediate_mandate_failed", "message": str(e)}
    log_op_result(
        _logger, "mandate-hp", "assemble_and_sign_immediate_mandates_tool", result
    )
    return result
