"""Unified Credential Provider MCP — routes card/x402 payment rails."""

import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware
from jwcrypto.jwk import JWK

from path_setup import bootstrap_unified  # noqa: E402

bootstrap_unified(__file__)
from constants_unified import SUPPORTED_PAYMENT_METHODS  # noqa: E402
from role_logging import log_op, setup_role_logger  # noqa: E402

from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.receipt_wrapper import ReceiptClient
from ap2.sdk.sdjwt.common import ParsedToken
from ap2.sdk.utils import compute_sha256_b64url
from common.constants import (
  AGENT_PROVIDER_PUB_PATH,
  MERCHANT_PAYMENT_PROCESSOR_PUB_PATH,
  TEMP_DB,
)
from roles.credentials_provider_mcp import server as card_cp
from roles.x402_credentials_provider_mcp import server as x402_cp

mcp = FastMCP("Unified Credential Provider MCP Server")

_SCRIPT_DIR = Path(__file__).resolve().parent
_LOG_DIR = Path(os.environ.get("LOGS_DIR", _SCRIPT_DIR.parent.parent / ".logs"))
_LOG_FILE = _LOG_DIR / "credentials-provider-unified-mcp.log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_logger = setup_role_logger(
    "credentials-provider-unified-mcp",
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

_TOKEN_STORE_PATH = Path(
    os.environ.get(
        "AP2_TOKEN_STORE_PATH",
        str(TEMP_DB / "ap2_token_store.json"),
    )
)


def _normalize_payment_method(payment_method: str) -> str:
  method = (payment_method or "").strip().lower()
  if method not in SUPPORTED_PAYMENT_METHODS:
    raise ValueError(f"unsupported payment_method: {payment_method}")
  return method


def _get_agent_provider_public_key() -> JWK | None:
  if not AGENT_PROVIDER_PUB_PATH.exists():
    return None
  try:
    return JWK.from_json(AGENT_PROVIDER_PUB_PATH.read_text(encoding="utf-8"))
  except (ValueError, json.JSONDecodeError, OSError) as e:
    _logger.warning("could not load agent-provider public key: %s", e)
  return None


def _get_user_public_key() -> JWK | None:
  from constants_unified import USER_SIGNING_PUB_PATH

  if not USER_SIGNING_PUB_PATH.exists():
    return None
  try:
    return JWK.from_json(USER_SIGNING_PUB_PATH.read_text(encoding="utf-8"))
  except (ValueError, json.JSONDecodeError, OSError) as e:
    _logger.warning("could not load user public key: %s", e)
  return None


def _key_or_provider_for_mandate(token: ParsedToken) -> JWK:
  """Resolve signing key: agent-provider for open hop, user for closed (HP)."""
  agent_pub = _get_agent_provider_public_key()
  user_pub = _get_user_public_key()
  try:
    kid = token.header.get("kid", "")
    if user_pub and isinstance(kid, str) and kid.startswith("user-signing-key"):
      return user_pub
  except (AttributeError, TypeError):
    pass
  if agent_pub:
    return agent_pub
  raise ValueError("no verification key available")


def _load_token_store() -> dict[str, Any]:
  try:
    with open(_TOKEN_STORE_PATH) as f:
      return json.load(f)
  except FileNotFoundError:
    return {}
  except (json.JSONDecodeError, OSError):
    return {}


@mcp.tool()
def issue_payment_credential(
    payment_method: str,
    payment_mandate_chain_id: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_nonce: str,
    presence_mode: str = "hnp",
) -> Mapping[str, Any]:
  """Issue a scoped payment token for card or x402."""
  _logger.info(
      "issue_payment_credential unified: method=%s presence=%s",
      payment_method,
      presence_mode,
  )
  try:
    method = _normalize_payment_method(payment_method)
  except ValueError as e:
    return {"error": "unsupported_payment_method", "message": str(e)}

  if presence_mode == "hp":
    return _issue_payment_credential_hp(
        method,
        payment_mandate_chain_id,
        open_checkout_hash,
        checkout_jwt_hash,
        payment_nonce,
    )

  if method == "card":
    return card_cp.issue_payment_credential(
        payment_mandate_chain_id,
        open_checkout_hash,
        checkout_jwt_hash,
        payment_nonce,
    )
  return x402_cp.issue_payment_credential(
      payment_mandate_chain_id,
      open_checkout_hash,
      checkout_jwt_hash,
      payment_nonce,
  )


def _issue_x402_credential_after_verify(
    mandate_chain: str,
    parsed_chain: PaymentMandateChain,
    checkout_jwt_hash: str,
    payment_nonce: str,
) -> Mapping[str, Any]:
  """Issue x402 bundled token after HP verify (user-key closed hop already verified)."""
  import time
  import uuid

  from common.x402_constants import (
    DEFAULT_MERCHANT_ADDRESS,
    DEFAULT_USDC_CONTRACT,
    DEFAULT_USER_PRIVATE_KEY,
  )
  from eth_account import Account
  from web3 import Web3

  chain = parsed_chain
  try:
    payee_address = chain.closed_mandate.payment_instrument.payee_address
    amount_cents = chain.closed_mandate.payment_amount.amount
    if not payee_address:
      payee_address = (
          os.environ.get("MERCHANT_WALLET_ADDRESS") or DEFAULT_MERCHANT_ADDRESS
      )
  except AttributeError:
    payee_address = (
        os.environ.get("MERCHANT_WALLET_ADDRESS") or DEFAULT_MERCHANT_ADDRESS
    )
    amount_cents = 1250

  nonce = Web3.keccak(text=mandate_chain)
  private_key = os.environ.get("X402_USER_PRIVATE_KEY") or DEFAULT_USER_PRIVATE_KEY
  account = Account.from_key(private_key)
  usdc_value = amount_cents * 10000
  domain = {
      "name": "USD Coin",
      "version": "2",
      "chainId": 84532,
      "verifyingContract": DEFAULT_USDC_CONTRACT,
  }
  types = {
      "TransferWithAuthorization": [
          {"name": "from", "type": "address"},
          {"name": "to", "type": "address"},
          {"name": "value", "type": "uint256"},
          {"name": "validAfter", "type": "uint256"},
          {"name": "validBefore", "type": "uint256"},
          {"name": "nonce", "type": "bytes32"},
      ]
  }
  message = {
      "from": account.address,
      "to": payee_address,
      "value": usdc_value,
      "validAfter": 0,
      "validBefore": int(time.time()) + 3600,
      "nonce": nonce,
  }
  signed_message = Account.sign_typed_data(
      private_key, domain_data=domain, message_types=types, message_data=message
  )
  bundled = {
      "payment_mandate_chain": mandate_chain,
      "payment_nonce": payment_nonce,
      "eip_3009_payload": {
          "signature": signed_message.signature.hex(),
          "authorization": {
              "from": account.address,
              "to": payee_address,
              "value": str(usdc_value),
              "validAfter": "0",
              "validBefore": str(message["validBefore"]),
              "nonce": nonce.hex(),
          },
      },
  }
  token_id = "x402_tok_" + str(uuid.uuid4()).replace("-", "")
  expires_at = int(time.time()) + 300
  store = _load_token_store()
  store[token_id] = {
      "checkout_jwt_hash": checkout_jwt_hash,
      "payment_nonce": payment_nonce,
      "bundled_payload": bundled,
      "used": False,
      "expires_at": expires_at,
  }
  _TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
  with open(_TOKEN_STORE_PATH, "w") as f:
    json.dump(store, f, indent=2)
  return {
      "payment_token": token_id,
      "expires_at": expires_at,
      "bundled_token": json.dumps(bundled),
  }


def _issue_payment_credential_hp(
    payment_method: str,
    payment_mandate_chain_id: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_nonce: str,
) -> Mapping[str, Any]:
  """HP: verify chain with user key on closed hop, then issue token."""
  path = TEMP_DB / f"{payment_mandate_chain_id}.sdjwt"
  if not path.exists():
    return {
        "error": "mandate_not_found",
        "message": f"Could not load {payment_mandate_chain_id}.sdjwt",
    }
  mandate_chain = path.read_text(encoding="ascii").strip()

  try:
    payloads = MandateClient().verify(
        token=mandate_chain,
        key_or_provider=_key_or_provider_for_mandate,
        expected_aud="credential-provider",
        expected_nonce=payment_nonce,
    )
    chain = PaymentMandateChain.parse(payloads)
    violations = chain.verify(
        expected_open_checkout_hash=open_checkout_hash,
        expected_transaction_id=checkout_jwt_hash,
    )
  except (ValueError, TypeError) as e:
    return {"error": "verification_failed", "message": str(e)}

  if violations:
    return {"error": "verification_failed", "message": "; ".join(violations)}

  if payment_method == "x402":
    return _issue_x402_credential_after_verify(
        mandate_chain,
        chain,
        checkout_jwt_hash,
        payment_nonce,
    )

  import time
  import uuid

  token = "tok_" + str(uuid.uuid4()).replace("-", "")
  reference = compute_sha256_b64url(
      MandateClient().get_closed_mandate_jwt(mandate_chain)
  )
  expires_at = int(time.time()) + 300
  token_data = {
      "token": token,
      "reference": reference,
      "payment_mandate_chain": mandate_chain,
      "payment_nonce": payment_nonce,
      "payment_method": payment_method,
      "presence_mode": "hp",
      "used": False,
      "expires_at": expires_at,
  }
  store = _load_token_store()
  store.update(
      dict.fromkeys([token, reference], token_data)
  )
  _TOKEN_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
  with open(_TOKEN_STORE_PATH, "w") as f:
    json.dump(store, f, indent=2)
  return {"payment_token": token, "expires_at": expires_at}


@mcp.tool()
def revoke_payment_credential(
    payment_method: str,
    payment_token: str,
) -> Mapping[str, Any]:
  """Revoke a previously issued payment token."""
  try:
    method = _normalize_payment_method(payment_method)
  except ValueError as e:
    return {"error": "unsupported_payment_method", "message": str(e)}
  if method == "card":
    return card_cp.revoke_payment_credential(payment_token)
  return x402_cp.revoke_payment_credential(payment_token)


@mcp.tool()
def verify_payment_receipt(payment_receipt: str) -> Mapping[str, Any]:
  """Verify a payment receipt from the merchant payment processor."""
  mpp_pub = None
  try:
    if MERCHANT_PAYMENT_PROCESSOR_PUB_PATH.exists():
      mpp_pub = JWK.from_json(
          MERCHANT_PAYMENT_PROCESSOR_PUB_PATH.read_text(encoding="utf-8")
      )
  except (ValueError, json.JSONDecodeError, OSError) as e:
    _logger.warning("could not load MPP public key: %s", e)
  if not mpp_pub:
    return {"error": "merchant_payment_processor_public_key_not_found"}

  result = ReceiptClient().verify_receipt(
      receipt_jwt=payment_receipt,
      receipt_issuer_public_key=mpp_pub,
      has_reference_in_store_cb=lambda reference: reference in _load_token_store(),
      is_payment_receipt=True,
  )
  if "error" in result:
    return result
  return {"verified": True}


@mcp.tool()
def list_wallets(payment_method: str = "x402") -> Mapping[str, Any]:
  """Return wallet info for x402."""
  if _normalize_payment_method(payment_method) != "x402":
    return {"error": "unsupported_payment_method", "message": "x402 only"}
  return x402_cp.list_x402_wallets()


if __name__ == "__main__":
  mcp.run()
