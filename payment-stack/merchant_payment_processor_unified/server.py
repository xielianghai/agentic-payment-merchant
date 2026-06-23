"""Unified Merchant Payment Processor MCP — card initiate + x402 settle."""

import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import (  # noqa: E402
  CP_PAYMENT_RECEIPT_URL,
  SUPPORTED_PAYMENT_METHODS,
  TEMP_DB,
)
from role_logging import log_op_result, setup_role_logger  # noqa: E402

from roles.merchant_payment_processor_mcp import server as card_mpp
from roles.x402_psp_mcp import server as x402_psp

mcp = FastMCP("Unified Merchant Payment Processor MCP Server")

_SCRIPT_DIR = Path(__file__).resolve().parent
_LOG_DIR = Path(os.environ.get("LOGS_DIR", _SCRIPT_DIR.parent.parent / ".logs"))
_LOG_FILE = _LOG_DIR / "merchant-payment-processor-unified-mcp.log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = setup_role_logger(
    "mpp-unified-mcp",
    log_file=_LOG_FILE,
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


def _normalize_payment_method(payment_method: str) -> str:
  method = (payment_method or "").strip().lower()
  if method not in SUPPORTED_PAYMENT_METHODS:
    raise ValueError(f"unsupported payment_method: {payment_method}")
  return method


def _load_token_entry(payment_token: str) -> dict[str, Any]:
  store_path = Path(
      os.environ.get("AP2_TOKEN_STORE_PATH", str(TEMP_DB / "ap2_token_store.json"))
  )
  try:
    store = json.loads(store_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return {}
  entry = store.get(payment_token) if isinstance(store, dict) else None
  return entry if isinstance(entry, dict) else {}


def _persist_token_vi_metadata(
    payment_token: str,
    *,
    vi_l2_credential_id: str,
    vi_l3_credential_id: str,
) -> None:
  store_path = Path(
      os.environ.get("AP2_TOKEN_STORE_PATH", str(TEMP_DB / "ap2_token_store.json"))
  )
  try:
    store = json.loads(store_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return
  if not isinstance(store, dict):
    return
  entry = store.get(payment_token)
  if not isinstance(entry, dict):
    return
  entry["vi_l2_credential_id"] = vi_l2_credential_id
  entry["vi_l3_credential_id"] = vi_l3_credential_id
  store[payment_token] = entry
  reference = entry.get("reference")
  if isinstance(reference, str) and reference in store:
    store[reference] = entry
  store_path.parent.mkdir(parents=True, exist_ok=True)
  store_path.write_text(json.dumps(store, indent=2), encoding="utf-8")


async def _send_payment_receipt_to_cp(receipt: str) -> None:
  async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
    try:
      response = await client.post(
          CP_PAYMENT_RECEIPT_URL,
          json={"payment_receipt": receipt},
      )
      response.raise_for_status()
      _logger.info("Sent payment receipt to unified CP at %s", CP_PAYMENT_RECEIPT_URL)
    except httpx.HTTPStatusError as exc:
      _logger.warning("Failed to send payment receipt: %s", exc.response.text)
    except Exception as e:
      _logger.warning("Error sending payment receipt: %s", e)


async def _verify_card_vi_network(
    payment_token: str,
    checkout_jwt_hash: str,
    open_checkout_hash: str,
) -> dict[str, Any] | None:
  from vi_unified.credentials import (
      is_vi_enabled,
      load_credential,
      resolve_card_vi_for_issue,
  )
  from vi_unified.logging import vi_debug, vi_log
  from vi_unified.network_mock import mock_mastercard_network_verify

  if not is_vi_enabled():
    vi_log("mpp_vi_skipped", reason="vi_disabled", payment_token=payment_token)
    return None
  if (payment_token or "").strip() == "startup_probe":
    vi_debug("mpp_vi_skipped", reason="startup_probe", payment_token=payment_token)
    return None
  entry = _load_token_entry(payment_token)
  vi_l2 = str(entry.get("vi_l2_credential_id", "")).strip()
  vi_l3 = str(entry.get("vi_l3_credential_id", "")).strip()
  amount_cents = int(entry.get("amount_cents") or 0)
  currency = str(entry.get("currency") or "USD")
  resolved_open = open_checkout_hash or str(entry.get("open_checkout_hash", ""))
  resolved_checkout = checkout_jwt_hash or str(entry.get("checkout_jwt_hash", ""))
  payment_mandate_chain_id = str(entry.get("payment_mandate_chain_id", ""))
  payment_nonce = str(entry.get("payment_nonce", ""))
  presence_mode = str(entry.get("presence_mode") or "hp")

  if (
      not vi_l2
      or not vi_l3
      or not load_credential(vi_l2)
      or not load_credential(vi_l3)
  ):
    vi_log(
        "mpp_vi_fallback_resolve",
        payment_token=payment_token,
        token_l2=vi_l2 or None,
        token_l3=vi_l3 or None,
        amount_cents=amount_cents,
    )
    resolved = resolve_card_vi_for_issue(
        vi_l2_credential_id=vi_l2,
        vi_l3_credential_id=vi_l3,
        payment_method="card",
        amount_cents=amount_cents,
        currency=currency,
        open_checkout_hash=resolved_open,
        checkout_jwt_hash=resolved_checkout,
        payment_mandate_chain_id=payment_mandate_chain_id,
        payment_nonce=payment_nonce,
        presence_mode=presence_mode,
    )
    if resolved.get("error"):
      vi_log(
          "mpp_vi_fallback_failed",
          payment_token=payment_token,
          error=resolved.get("error"),
          message=resolved.get("message"),
      )
      return {
          "error": "vi_network_verification_failed",
          "message": resolved.get("message", "VI network verification failed."),
      }
    vi_l2 = str(resolved.get("vi_l2_credential_id", "")).strip()
    vi_l3 = str(resolved.get("vi_l3_credential_id", "")).strip()
    if vi_l2 and vi_l3:
      vi_log(
          "mpp_vi_fallback_ok",
          payment_token=payment_token,
          l2_id=vi_l2,
          l3_id=vi_l3,
      )
      _persist_token_vi_metadata(
          payment_token,
          vi_l2_credential_id=vi_l2,
          vi_l3_credential_id=vi_l3,
      )

  if not vi_l2 or not vi_l3:
    vi_log(
        "mpp_vi_missing_refs",
        payment_token=payment_token,
        l2_id=vi_l2 or None,
        l3_id=vi_l3 or None,
    )
    return {
        "error": "vi_network_verification_failed",
        "message": "card payment token is missing VI credential references.",
    }
  vi_log(
      "mpp_network_check",
      payment_token=payment_token,
      l2_id=vi_l2,
      l3_id=vi_l3,
      amount_cents=amount_cents,
  )
  network = mock_mastercard_network_verify(
      payment_token=payment_token,
      vi_l2_credential_id=vi_l2,
      vi_l3_credential_id=vi_l3,
      payment_method="card",
      amount_cents=amount_cents,
      currency=currency,
      open_checkout_hash=resolved_open,
      checkout_jwt_hash=resolved_checkout,
      payment_mandate_chain_id=payment_mandate_chain_id,
      payment_nonce=payment_nonce,
  )
  if network.get("error"):
    return network
  return network


async def _initiate_payment_card(
    payment_token: str,
    checkout_jwt_hash: str,
    open_checkout_hash: str,
) -> dict[str, Any]:
  """Run card MPP logic but POST receipt to unified CP port."""
  network = await _verify_card_vi_network(
      payment_token, checkout_jwt_hash, open_checkout_hash
  )
  if isinstance(network, dict) and network.get("error"):
    return network

  original_send = card_mpp._send_payment_receipt_to_credentials_provider

  async def _redirect_send(receipt: str) -> None:
    await _send_payment_receipt_to_cp(receipt)

  card_mpp._send_payment_receipt_to_credentials_provider = _redirect_send
  try:
    result = await card_mpp.initiate_payment(
        payment_token,
        checkout_jwt_hash,
        open_checkout_hash,
    )
    if isinstance(result, dict) and network and not result.get("error"):
      result["vi_network"] = network
    return result
  finally:
    card_mpp._send_payment_receipt_to_credentials_provider = original_send


@mcp.tool()
async def initiate_or_settle_payment(
    payment_method: str,
    payment_token: str,
    checkout_jwt_hash: str = "",
    open_checkout_hash: str = "",
) -> Mapping[str, Any]:
  """Card: initiate_payment. x402: settle_payment (payment_token is bundled JSON)."""
  _logger.info("initiate_or_settle_payment: method=%s", payment_method)
  try:
    method = _normalize_payment_method(payment_method)
  except ValueError as e:
    return {"error": "unsupported_payment_method", "message": str(e)}

  if method == "card":
    if not checkout_jwt_hash or not open_checkout_hash:
      result = {
          "error": "missing_fields",
          "message": "checkout_jwt_hash and open_checkout_hash required for card",
      }
      log_op_result(_logger, "mpp", "initiate_or_settle_payment", result)
      return result
    result = await _initiate_payment_card(
        payment_token,
        checkout_jwt_hash,
        open_checkout_hash,
    )
    if isinstance(result, dict) and result.get("vi_network"):
      vn = result["vi_network"]
      if isinstance(vn, dict):
        from vi_unified.logging import vi_log

        vi_log(
            "mpp_settle_vi_network",
            payment_token=payment_token,
            auth_code=vn.get("auth_code"),
            decision=vn.get("decision"),
            l2_id=vn.get("vi_l2_credential_id"),
            l3_id=vn.get("vi_l3_credential_id"),
        )
    log_op_result(_logger, "mpp", "initiate_or_settle_payment", result, method=method)
    return result

  result = x402_psp.settle_payment(
      payment_token,
      checkout_jwt_hash or None,
      open_checkout_hash or None,
  )
  log_op_result(_logger, "mpp", "initiate_or_settle_payment", result, method=method)
  return result


if __name__ == "__main__":
  mcp.run()
