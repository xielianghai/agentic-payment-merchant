"""x402 MetaMask wallet signing sessions (QClaw + Chrome extension)."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.sdjwt.common import ParsedToken
from common.constants import AGENT_PROVIDER_PUB_PATH, TEMP_DB
from common.x402_constants import (
  SEPOLIA_CHAIN_ID,
  X402_NETWORK_NAME,
  X402_NETWORK_SLUG,
  X402_TOKEN_SYMBOL,
)
from common.x402_eth_price import format_eth_from_wei
from common.x402_eip712 import (
  build_transfer_with_authorization,
  extract_payee_and_amount,
  normalize_typed_data_for_metamask,
  verify_transfer_with_authorization_signature,
)
from common.x402_wallet_sign_store import (
  get_wallet_sign_session,
  get_x402_wallet_signature,
  save_wallet_sign_session,
)
from jwcrypto.jwk import JWK

_log = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 300


def _temp_db() -> Path:
  unified = os.environ.get("TEMP_DB_DIR")
  if unified:
    return Path(unified)
  return TEMP_DB


def _ts_base_url() -> str:
  return os.environ.get("TS_BASE_URL", "http://127.0.0.1:8104").rstrip("/")


def _wallet_sign_portal_url(ref: str) -> str:
  return f"{_ts_base_url()}/ts/x402/sign?ref={ref}"


def _canonical_session_id(session_id: str) -> str:
  sid = (session_id or "").strip()
  if not sid or "@" in sid:
    return sid
  if sid.lower().startswith("feishu:") or sid.startswith("ou_"):
    return sid
  return f"{sid}@im.wechat"


def _openclaw_session_key(session_id: str) -> str | None:
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


def _wake_openclaw_agent_after_x402_signed(session_id: str, ref: str) -> bool:
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
    _log.info("[x402-wallet] skip openclaw wake (hook url/token not configured)")
    return False
  canonical_sid = _canonical_session_id(session_id)
  session_key = _openclaw_session_key(canonical_sid)
  if not session_key:
    _log.info("[x402-wallet] skip openclaw wake (no sessionKey for %r)", session_id)
    return False
  message = (
      f"[AP2] x402 MetaMask wallet signed (ref={ref}). Continue HP checkout on "
      f"session_id={canonical_sid}. Call wait_for_x402_wallet_signed with this "
      f"ref, then ap2-cp.issue_payment_credential, then "
      f"ap2-merchant.complete_checkout. Do NOT create a new Trusted Surface, "
      f"wallet-sign session, cart, or checkout."
  )
  payload: dict[str, Any] = {
      "message": message,
      "sessionKey": session_key,
      "channel": "openclaw-weixin" if "@im.wechat" in canonical_sid.lower() else "last",
      "wakeMode": "now",
      "deliver": True,
      "name": "AP2 x402 Wallet",
  }
  if "@im.wechat" in canonical_sid.lower():
    payload["to"] = canonical_sid
  req = urllib.request.Request(
      hook_url,
      data=json.dumps(payload).encode("utf-8"),
      headers={
          "Content-Type": "application/json",
          "Authorization": f"Bearer {hook_token}",
      },
      method="POST",
  )
  try:
    with urllib.request.urlopen(req, timeout=10) as resp:
      _log.info("[x402-wallet] openclaw wake OK ref=%s status=%s", ref, resp.status)
      return True
  except urllib.error.HTTPError as exc:
    _log.warning("[x402-wallet] openclaw wake HTTP %s ref=%s", exc.code, ref)
  except Exception as exc:
    _log.warning("[x402-wallet] openclaw wake failed ref=%s: %s", ref, exc)
  return False


def _get_agent_provider_public_key() -> JWK | None:
  if not AGENT_PROVIDER_PUB_PATH.exists():
    return None
  try:
    return JWK.from_json(AGENT_PROVIDER_PUB_PATH.read_text(encoding="utf-8"))
  except (ValueError, json.JSONDecodeError, OSError) as exc:
    _log.warning("could not load agent-provider public key: %s", exc)
  return None


def _get_user_public_key() -> JWK | None:
  try:
    from constants_unified import USER_SIGNING_PUB_PATH
  except ImportError:
    return None
  if not USER_SIGNING_PUB_PATH.exists():
    return None
  try:
    return JWK.from_json(USER_SIGNING_PUB_PATH.read_text(encoding="utf-8"))
  except (ValueError, json.JSONDecodeError, OSError) as exc:
    _log.warning("could not load user public key: %s", exc)
  return None


def _key_or_provider_for_mandate(token: ParsedToken) -> JWK:
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


def _load_mandate_chain_text(payment_mandate_chain_id: str) -> str | None:
  chain_id = (payment_mandate_chain_id or "").strip()
  if not chain_id:
    return None
  path = _temp_db() / f"{chain_id}.sdjwt"
  try:
    return path.read_text(encoding="ascii").strip()
  except OSError:
    return None


def _parse_verified_payment_chain(
    mandate_chain: str,
    *,
    payment_nonce: str | None = None,
) -> PaymentMandateChain:
  verify_kwargs: dict[str, Any] = {
      "token": mandate_chain,
      "key_or_provider": _key_or_provider_for_mandate,
  }
  if payment_nonce:
    verify_kwargs["expected_aud"] = "credential-provider"
    verify_kwargs["expected_nonce"] = payment_nonce
  payloads = MandateClient().verify(**verify_kwargs)
  return PaymentMandateChain.parse(payloads)


def _open_checkout_hash_from_chain(parsed: PaymentMandateChain) -> str:
  for constraint in parsed.open_mandate.constraints or []:
    cid = getattr(constraint, "conditional_transaction_id", None)
    if cid:
      return str(cid)
    if isinstance(constraint, dict):
      cid = constraint.get("conditional_transaction_id")
      if cid:
        return str(cid)
  return ""


def _hp_credential_context(record: dict[str, Any]) -> dict[str, str]:
  """Recover HP issue_payment_credential args after MetaMask resume."""
  out = {
      "payment_nonce": str(record.get("payment_nonce") or ""),
      "payment_mandate_chain_id": str(record.get("payment_mandate_chain_id") or ""),
      "open_checkout_hash": str(record.get("open_checkout_hash") or ""),
      "checkout_jwt_hash": str(record.get("checkout_jwt_hash") or ""),
      "checkout_mandate_chain_id": str(record.get("checkout_mandate_chain_id") or ""),
      "checkout_nonce": str(record.get("checkout_nonce") or ""),
  }
  mandate_chain = str(record.get("mandate_chain") or "")
  if not mandate_chain:
    return out
  try:
    parsed = _parse_verified_payment_chain(
        mandate_chain,
        payment_nonce=out["payment_nonce"] or None,
    )
    if not out["checkout_jwt_hash"]:
      out["checkout_jwt_hash"] = str(parsed.closed_mandate.transaction_id or "")
    if not out["open_checkout_hash"]:
      out["open_checkout_hash"] = _open_checkout_hash_from_chain(parsed)
  except (ValueError, TypeError, AttributeError):
    pass
  return out


def _signed_wallet_status_extras(record: dict[str, Any]) -> dict[str, Any]:
  ctx = _hp_credential_context(record)
  return {
      **ctx,
      "presence_mode": "hp",
      "agent_instruction": (
          "Call ap2-cp.issue_payment_credential with payment_method=x402, "
          "presence_mode=hp, and the payment_mandate_chain_id, payment_nonce, "
          "open_checkout_hash, checkout_jwt_hash fields from this tool result. "
          "Then complete_checkout with payment_token plus checkout_mandate_chain_id "
          "and checkout_nonce from this result. Do NOT call list_wallets or restart "
          "search/cart/checkout."
      ),
  }


def _wallet_sign_channel_messages(
    portal_url: str,
    *,
    amount_cents: int,
    payee_address: str,
    eth_amount: str,
    eth_usd_rate: float,
) -> dict[str, Any]:
  usd_display = amount_cents / 100.0
  user_message = (
      f"Sign and send {X402_TOKEN_SYMBOL} on {X402_NETWORK_NAME} via MetaMask:\n"
      f"**Amount:** {eth_amount} {X402_TOKEN_SYMBOL} "
      f"(~ ${usd_display:.2f} USD @ ${eth_usd_rate:,.2f}/ETH)\n"
      f"**Payee:** {payee_address}\n"
      f"\n{portal_url}\n"
      f"\nOpen in Chrome with MetaMask, switch to {X402_NETWORK_NAME}, "
      f"sign EIP-712, then confirm the SepoliaETH transfer."
  )
  feishu_user_message = (
      f"Sign and send {X402_TOKEN_SYMBOL} on {X402_NETWORK_NAME} via MetaMask:\n"
      f"**Amount:** {eth_amount} {X402_TOKEN_SYMBOL} "
      f"(~ ${usd_display:.2f} USD @ ${eth_usd_rate:,.2f}/ETH)\n"
      f"**Payee:** {payee_address}\n"
      f"**Open:** [Sign with MetaMask]({portal_url})"
  )
  return {
      "user_message": user_message,
      "feishu_user_message": feishu_user_message,
      "agent_instruction": (
          "Post user_message verbatim (English). User must open wallet_sign_portal_url "
          "in Chrome with MetaMask, sign EIP-712 and confirm the on-chain SepoliaETH "
          "transfer, then call wait_for_x402_wallet_signed with this ref before "
          "ap2-cp.issue_payment_credential."
      ),
  }


def create_x402_wallet_sign_session(
    session_id: str,
    payment_mandate_chain_id: str,
    *,
    payment_nonce: str | None = None,
    open_checkout_hash: str | None = None,
    checkout_jwt_hash: str | None = None,
    checkout_mandate_chain_id: str | None = None,
    checkout_nonce: str | None = None,
) -> dict[str, Any]:
  """Create MetaMask wallet sign session; return portal URL."""
  sid = _canonical_session_id(session_id)
  if not sid:
    return {
        "error": "session_id_required",
        "message": "Pass session_id for this conversation.",
    }
  chain_id = (payment_mandate_chain_id or "").strip()
  if not chain_id:
    return {
        "error": "payment_mandate_chain_id_required",
        "message": "Pass payment_mandate_chain_id from assemble / presentation step.",
    }
  mandate_chain = _load_mandate_chain_text(chain_id)
  if not mandate_chain:
    return {
        "error": "mandate_not_found",
        "message": f"Could not load {chain_id}.sdjwt",
    }
  try:
    parsed = _parse_verified_payment_chain(
        mandate_chain, payment_nonce=payment_nonce
    )
  except (ValueError, TypeError, AttributeError) as exc:
    return {
        "error": "mandate_verify_failed",
        "message": str(exc),
    }

  ref = secrets.token_urlsafe(12)
  now = time.time()
  payee, amount_cents = extract_payee_and_amount(parsed)
  resolved_checkout_jwt_hash = (checkout_jwt_hash or "").strip() or str(
      parsed.closed_mandate.transaction_id or ""
  )
  resolved_open_checkout_hash = (open_checkout_hash or "").strip() or (
      _open_checkout_hash_from_chain(parsed)
  )
  valid_before = int(now) + 3600
  built = build_transfer_with_authorization(
      mandate_chain,
      parsed,
      from_address="0x0000000000000000000000000000000000000000",
      valid_before=valid_before,
  )
  record: dict[str, Any] = {
      "ref": ref,
      "session_id": sid,
      "payment_mandate_chain_id": chain_id,
      "payment_nonce": payment_nonce or "",
      "open_checkout_hash": resolved_open_checkout_hash,
      "checkout_jwt_hash": resolved_checkout_jwt_hash,
      "checkout_mandate_chain_id": (checkout_mandate_chain_id or "").strip(),
      "checkout_nonce": (checkout_nonce or "").strip(),
      "mandate_chain": mandate_chain,
      "typed_data": built["typed_data"],
      "payment_wei": built["payment_value"],
      "eth_amount": built["eth_amount"],
      "eth_usd_rate": built["eth_usd_rate"],
      "valid_before": valid_before,
      "status": "pending",
      "created_at": now,
      "expires_at": now + _SESSION_TTL_SECONDS,
      "signed_at": None,
      "wallet_address": None,
      "signature": None,
  }
  save_wallet_sign_session(ref, record)

  portal_url = _wallet_sign_portal_url(ref)
  channel = _wallet_sign_channel_messages(
      portal_url,
      amount_cents=amount_cents,
      payee_address=str(payee or ""),
      eth_amount=str(built["eth_amount"]),
      eth_usd_rate=float(built["eth_usd_rate"]),
  )
  return {
      "status": "pending",
      "ref": ref,
      "session_id": sid,
      "payment_mandate_chain_id": chain_id,
      "portal_url": portal_url,
      "wallet_sign_portal_url": portal_url,
      "amount_cents": amount_cents,
      "payment_wei": built["payment_value"],
      "eth_amount": built["eth_amount"],
      "eth_usd_rate": built["eth_usd_rate"],
      "expires_in_seconds": _SESSION_TTL_SECONDS,
      **channel,
  }


def get_x402_wallet_sign_draft(ref: str) -> dict[str, Any] | None:
  """Return signing draft for H5 portal (typed_data built server-side)."""
  record = get_wallet_sign_session(ref)
  if not record:
    return None
  mandate_chain = str(record.get("mandate_chain") or "")
  if not mandate_chain:
    return None
  try:
    parsed = _parse_verified_payment_chain(
        mandate_chain,
        payment_nonce=record.get("payment_nonce") or None,
    )
  except (ValueError, TypeError, AttributeError):
    return None
  payee, amount_cents = extract_payee_and_amount(parsed)
  valid_before = int(record.get("valid_before") or 0) or None
  built = build_transfer_with_authorization(
      mandate_chain,
      parsed,
      from_address="0x0000000000000000000000000000000000000000",
      valid_before=valid_before,
  )
  typed_data = normalize_typed_data_for_metamask(built["typed_data"])
  return {
      "ref": ref,
      "status": record.get("status", "pending"),
      "session_id": record.get("session_id"),
      "payment_mandate_chain_id": record.get("payment_mandate_chain_id"),
      "amount_cents": amount_cents,
      "payee_address": payee,
      "chain_id": SEPOLIA_CHAIN_ID,
      "network": X402_NETWORK_SLUG,
      "network_name": X402_NETWORK_NAME,
      "token_symbol": X402_TOKEN_SYMBOL,
      "payment_wei": built["payment_value"],
      "eth_amount": built["eth_amount"],
      "eth_usd_rate": built["eth_usd_rate"],
      "typed_data": typed_data,
      "expires_in_seconds": max(
          0,
          int(float(record.get("expires_at", 0)) - time.time()),
      ),
  }


def submit_x402_wallet_signature(
    ref: str,
    from_address: str,
    signature: str,
    *,
    tx_hash: str | None = None,
) -> dict[str, Any]:
  """Validate MetaMask signature and persist for CP."""
  rid = (ref or "").strip()
  addr = (from_address or "").strip()
  sig = (signature or "").strip()
  if not rid:
    return {"error": "ref_required", "message": "ref is required."}
  if not addr or not sig:
    return {
        "error": "missing_fields",
        "message": "from_address and signature are required.",
    }

  record = get_wallet_sign_session(rid)
  if not record:
    return {"error": "session_not_found", "message": f"No wallet sign session for {rid!r}"}
  if record.get("status") == "signed":
    return {
        "status": "ok",
        "ref": rid,
        "wallet_address": record.get("wallet_address"),
        "message": "Already signed.",
    }
  if record.get("status") == "expired":
    return {"error": "session_expired", "message": "Wallet sign session expired."}

  mandate_chain = str(record.get("mandate_chain") or "")
  try:
    parsed = _parse_verified_payment_chain(
        mandate_chain,
        payment_nonce=record.get("payment_nonce") or None,
    )
  except (ValueError, TypeError) as exc:
    return {"error": "mandate_verify_failed", "message": str(exc)}

  built = build_transfer_with_authorization(
      mandate_chain,
      parsed,
      from_address=addr,
      valid_before=int(record.get("valid_before") or 0) or None,
  )
  ok, err = verify_transfer_with_authorization_signature(
      mandate_chain,
      sig,
      addr,
      parsed_chain=parsed,
      valid_before=built["valid_before"],
  )
  if not ok:
    return {"error": "invalid_signature", "message": err}

  tx = (tx_hash or "").strip()
  if not tx:
    return {
        "error": "tx_hash_required",
        "message": (
            "On-chain SepoliaETH transfer required. Confirm the MetaMask "
            "send transaction and retry submit with tx_hash."
        ),
    }
  if not tx.startswith("0x"):
    tx = f"0x{tx}"

  record["status"] = "signed"
  record["wallet_address"] = _checksum_address(addr)
  record["signature"] = sig if sig.startswith("0x") else f"0x{sig}"
  record["tx_hash"] = tx
  record["signed_at"] = time.time()
  sid = str(record.get("session_id") or "")
  if not record.get("openclaw_woken_at") and _wake_openclaw_agent_after_x402_signed(
      sid, rid
  ):
    record["openclaw_woken_at"] = time.time()
  save_wallet_sign_session(rid, record)
  return {
      "status": "ok",
      "ref": rid,
      "wallet_address": record["wallet_address"],
      "tx_hash": tx,
      "eth_amount": record.get("eth_amount"),
      "message": (
          "Wallet signature and on-chain transfer recorded. "
          "Return to chat - agent will continue checkout."
      ),
  }


def _checksum_address(address: str) -> str:
  from web3 import Web3

  return Web3.to_checksum_address(address)


def get_x402_wallet_sign_status(ref: str) -> dict[str, Any]:
  """Return pending | signed | expired for agent polling."""
  rid = (ref or "").strip()
  if not rid:
    return {"status": "not_found", "message": "ref is required"}
  record = get_wallet_sign_session(rid)
  if not record:
    return {"status": "not_found", "message": f"No wallet sign session for {rid!r}"}
  status = str(record.get("status", "pending"))
  out: dict[str, Any] = {
      "status": status,
      "ref": rid,
      "session_id": record.get("session_id"),
      "payment_mandate_chain_id": record.get("payment_mandate_chain_id"),
  }
  if status == "signed":
    out["wallet_address"] = record.get("wallet_address")
    out.update(_signed_wallet_status_extras(record))
    out["message"] = (
        "MetaMask signature recorded. Use the credential fields in this result "
        "for ap2-cp.issue_payment_credential, then complete_checkout."
    )
  elif status == "expired":
    out["message"] = (
        "Wallet sign session expired. Call create_x402_wallet_sign_session again."
    )
  else:
    out["message"] = (
        "Waiting for user to sign with MetaMask on the wallet sign portal."
    )
    out["wallet_sign_portal_url"] = _wallet_sign_portal_url(rid)
  return out


def wait_for_x402_wallet_signed(
    ref: str,
    *,
    timeout_seconds: int = 300,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
  """Block until MetaMask signature is recorded (server-side long-poll)."""
  rid = (ref or "").strip()
  if not rid:
    return {"status": "not_found", "message": "ref is required"}
  try:
    timeout = max(1, int(timeout_seconds))
  except (TypeError, ValueError):
    timeout = _SESSION_TTL_SECONDS
  try:
    interval = max(0.5, float(poll_interval_seconds))
  except (TypeError, ValueError):
    interval = 2.0
  deadline = time.time() + timeout
  while time.time() < deadline:
    status = get_x402_wallet_sign_status(rid)
    st = str(status.get("status", ""))
    if st == "signed":
      status["waited_seconds"] = round(timeout - max(0, deadline - time.time()), 1)
      return status
    if st in ("expired", "not_found"):
      status["waited_seconds"] = round(timeout - max(0, deadline - time.time()), 1)
      return status
    time.sleep(min(interval, max(0, deadline - time.time())))
  final = get_x402_wallet_sign_status(rid)
  if final.get("status") == "pending" and not final.get("wallet_sign_portal_url"):
    final["wallet_sign_portal_url"] = _wallet_sign_portal_url(rid)
  final["status"] = "timeout"
  final["message"] = (
      f"Timed out after {timeout}s waiting for MetaMask signature. "
      "Ask the user to open wallet_sign_portal_url in Chrome and sign, then call "
      "wait_for_x402_wallet_signed again with the same ref."
  )
  final["waited_seconds"] = timeout
  return final


def get_wallet_address_for_session(session_id: str) -> str | None:
  """Re-export for agent payment labels."""
  from common.x402_wallet_sign_store import get_wallet_address_for_session as _get

  return _get(session_id)
