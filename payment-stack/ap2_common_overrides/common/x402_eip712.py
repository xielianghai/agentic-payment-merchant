"""EIP-712 payment authorization helpers for x402 SepoliaETH (Ethereum Sepolia)."""

from __future__ import annotations

import os
import time
from typing import Any

from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from common.x402_constants import (
  DEFAULT_MERCHANT_ADDRESS,
  DEFAULT_USER_PRIVATE_KEY,
  x402_eip712_domain,
  x402_eip712_domain_types,
)
from common.x402_eth_price import format_eth_from_wei, usd_cents_to_wei
from common.x402_wallet_sign_store import get_x402_wallet_signature
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

_TRANSFER_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def extract_payee_and_amount(
    parsed_chain: PaymentMandateChain,
) -> tuple[str, int]:
  """Return payee address and amount in cents from a verified mandate chain."""
  try:
    closed = parsed_chain.closed_mandate
    amount_cents = int(closed.payment_amount.amount)
    instrument = closed.payment_instrument
    inst_data = instrument.model_dump() if hasattr(instrument, "model_dump") else {}
    payee_address = inst_data.get("payee_address")
    if not payee_address:
      payee_address = getattr(instrument, "payee_address", None)
    if not payee_address:
      payee_address = (
          os.environ.get("MERCHANT_WALLET_ADDRESS") or DEFAULT_MERCHANT_ADDRESS
      )
    return str(payee_address), amount_cents
  except AttributeError:
    return (
        os.environ.get("MERCHANT_WALLET_ADDRESS") or DEFAULT_MERCHANT_ADDRESS,
        1250,
    )


def mandate_binding_nonce(mandate_chain: str) -> bytes:
  """32-byte nonce bound to the mandate chain."""
  return Web3.keccak(text=mandate_chain)


def amount_cents_to_wei(amount_cents: int) -> tuple[int, float]:
  """Map mandate USD cents to SepoliaETH wei using live ETH/USD."""
  return usd_cents_to_wei(amount_cents)


def normalize_typed_data_for_metamask(typed_data: dict[str, Any]) -> dict[str, Any]:
  """Ensure bytes32 fields use 0x-prefixed hex for MetaMask eth_signTypedData_v4."""
  if not isinstance(typed_data, dict):
    return typed_data
  primary = typed_data.get("primaryType")
  types = typed_data.get("types") or {}
  message = typed_data.get("message")
  if not primary or not isinstance(message, dict):
    return typed_data
  for field in types.get(primary) or []:
    if field.get("type") != "bytes32":
      continue
    name = field.get("name")
    if not name or name not in message:
      continue
    raw = message[name]
    if isinstance(raw, (bytes, bytearray)):
      message[name] = Web3.to_hex(bytes(raw))
      continue
    if not isinstance(raw, str):
      continue
    clean = raw[2:] if raw.startswith("0x") else raw
    if len(clean) == 64:
      message[name] = "0x" + clean.lower()
  return typed_data


def build_transfer_with_authorization(
    mandate_chain: str,
    parsed_chain: PaymentMandateChain,
    *,
    from_address: str,
    valid_before: int | None = None,
) -> dict[str, Any]:
  """Build domain, types, message, and full typed_data for MetaMask signing."""
  payee_address, amount_cents = extract_payee_and_amount(parsed_chain)
  nonce = mandate_binding_nonce(mandate_chain)
  payment_value, eth_usd_rate = amount_cents_to_wei(amount_cents)
  vb = valid_before if valid_before is not None else int(time.time()) + 3600

  domain = x402_eip712_domain()
  message = {
      "from": Web3.to_checksum_address(from_address),
      "to": Web3.to_checksum_address(payee_address),
      "value": payment_value,
      "validAfter": 0,
      "validBefore": vb,
      "nonce": nonce,
  }
  typed_data = {
      "types": {
          "EIP712Domain": x402_eip712_domain_types(),
          "TransferWithAuthorization": _TRANSFER_TYPES["TransferWithAuthorization"],
      },
      "primaryType": "TransferWithAuthorization",
      "domain": domain,
      "message": {
          "from": message["from"],
          "to": message["to"],
          "value": str(payment_value),
          "validAfter": "0",
          "validBefore": str(vb),
          "nonce": Web3.to_hex(nonce),
      },
  }
  normalize_typed_data_for_metamask(typed_data)
  return {
      "domain": domain,
      "types": _TRANSFER_TYPES,
      "message": message,
      "typed_data": typed_data,
      "payee_address": payee_address,
      "amount_cents": amount_cents,
      "payment_value": payment_value,
      "payment_wei": payment_value,
      "eth_usd_rate": eth_usd_rate,
      "eth_amount": format_eth_from_wei(payment_value),
      "usdc_value": payment_value,  # back-compat for older callers
      "nonce": nonce,
      "valid_before": vb,
  }


def sign_transfer_with_authorization(
    mandate_chain: str,
    parsed_chain: PaymentMandateChain,
    *,
    private_key: str | None = None,
    payment_nonce: str = "",
) -> dict[str, Any]:
  """Sign authorization with a local private key (mock / CI mode)."""
  key = private_key or os.environ.get("X402_USER_PRIVATE_KEY") or DEFAULT_USER_PRIVATE_KEY
  account = Account.from_key(key)
  built = build_transfer_with_authorization(
      mandate_chain, parsed_chain, from_address=account.address
  )
  signed = Account.sign_typed_data(
      key,
      domain_data=built["domain"],
      message_types=built["types"],
      message_data=built["message"],
  )
  return build_eip3009_payload(
      mandate_chain=mandate_chain,
      from_address=account.address,
      built=built,
      signature_hex=signed.signature.hex(),
      payment_nonce=payment_nonce,
  )


def build_eip3009_payload(
    *,
    mandate_chain: str,
    from_address: str,
    built: dict[str, Any],
    signature_hex: str,
    payment_nonce: str = "",
    settlement_tx_hash: str = "",
    payment_wei: int | None = None,
    eth_usd_rate: float = 0.0,
) -> dict[str, Any]:
  """Assemble bundled x402 token fields (EIP-712 authorization envelope)."""
  sig = signature_hex if signature_hex.startswith("0x") else f"0x{signature_hex}"
  msg = built["message"]
  nonce = built["nonce"]
  payment_value = payment_wei if payment_wei is not None else built["payment_value"]
  out: dict[str, Any] = {
      "payment_mandate_chain": mandate_chain,
      "payment_nonce": payment_nonce,
      "payment_wei": payment_value,
      "eth_amount": format_eth_from_wei(payment_value),
      "eip_3009_payload": {
          "signature": sig,
          "authorization": {
              "from": from_address,
              "to": built["payee_address"],
              "value": str(payment_value),
              "validAfter": "0",
              "validBefore": str(msg["validBefore"]),
              "nonce": nonce.hex(),
          },
      },
  }
  if eth_usd_rate > 0:
    out["eth_usd_rate"] = eth_usd_rate
  if settlement_tx_hash:
    out["settlement_tx_hash"] = settlement_tx_hash
  return out


def verify_transfer_with_authorization_signature(
    mandate_chain: str,
    signature: str,
    from_address: str,
    *,
    parsed_chain: PaymentMandateChain,
    valid_before: int | None = None,
) -> tuple[bool, str]:
  """Verify EIP-712 signature; return (ok, error_message)."""
  built = build_transfer_with_authorization(
      mandate_chain,
      parsed_chain,
      from_address=from_address,
      valid_before=valid_before,
  )
  typed_data = {
      "types": {
          "EIP712Domain": x402_eip712_domain_types(),
          "TransferWithAuthorization": _TRANSFER_TYPES["TransferWithAuthorization"],
      },
      "primaryType": "TransferWithAuthorization",
      "domain": built["domain"],
      "message": built["message"],
  }
  try:
    signable = encode_typed_data(full_message=typed_data)
    recovered = Account.recover_message(signable, signature=signature)
  except Exception as exc:
    return False, f"ecrecover failed: {exc}"

  if recovered.lower() != from_address.lower():
    return False, (
        f"recovered signer {recovered} != from {from_address}"
    )
  return True, ""


def issue_x402_bundled(
    mandate_chain: str,
    parsed_chain: PaymentMandateChain,
    payment_nonce: str,
    payment_mandate_chain_id: str,
) -> dict[str, Any]:
  """Build bundled x402 payload (MetaMask or mock signing)."""
  mode = x402_wallet_mode()
  if mode == "mock":
    return sign_transfer_with_authorization(
        mandate_chain, parsed_chain, payment_nonce=payment_nonce
    )
  stored = get_x402_wallet_signature(payment_mandate_chain_id)
  if not stored:
    return {
        "error": "wallet_signature_required",
        "message": (
            "MetaMask wallet signature required. Call "
            "create_x402_wallet_sign_session, have the user sign on the "
            "wallet portal, then wait_for_x402_wallet_signed before "
            "issue_payment_credential."
        ),
    }
  if not stored.get("tx_hash"):
    return {
        "error": "wallet_tx_required",
        "message": (
            "On-chain SepoliaETH transfer required. User must confirm the "
            "MetaMask send transaction on the wallet sign portal."
        ),
    }
  built = build_transfer_with_authorization(
      mandate_chain,
      parsed_chain,
      from_address=stored["from"],
      valid_before=int(stored["valid_before"]) if stored.get("valid_before") else None,
  )
  return build_eip3009_payload(
      mandate_chain=mandate_chain,
      from_address=stored["from"],
      built=built,
      signature_hex=stored["signature"],
      payment_nonce=payment_nonce,
      settlement_tx_hash=stored.get("tx_hash") or "",
      payment_wei=int(stored.get("payment_wei") or built["payment_value"]),
      eth_usd_rate=float(stored.get("eth_usd_rate") or built.get("eth_usd_rate") or 0),
  )


def x402_wallet_mode() -> str:
  """Return 'metamask' or 'mock' (default metamask)."""
  return os.environ.get("AP2_X402_WALLET_MODE", "metamask").strip().lower()
