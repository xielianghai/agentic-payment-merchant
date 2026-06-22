"""Persistent store for MetaMask x402 wallet signatures (shared across MCP processes)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from common.constants import TEMP_DB

_SESSION_TTL_SECONDS = 300
_SESSIONS: dict[str, dict[str, Any]] = {}


def _sessions_path() -> Path:
  unified = os.environ.get("TEMP_DB_DIR")
  if unified:
    return Path(unified) / "x402_wallet_sign_sessions.json"
  return TEMP_DB / "x402_wallet_sign_sessions.json"


def _load_sessions() -> dict[str, dict[str, Any]]:
  path = _sessions_path()
  if not path.is_file():
    return {}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
      return {str(k): v for k, v in data.items() if isinstance(v, dict)}
  except (OSError, json.JSONDecodeError, TypeError):
    pass
  return {}


def _persist_sessions() -> None:
  path = _sessions_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
      json.dumps(_SESSIONS, indent=2, ensure_ascii=True),
      encoding="utf-8",
  )


def _reload_from_disk() -> None:
  _SESSIONS.clear()
  _SESSIONS.update(_load_sessions())


def _ensure_loaded() -> None:
  if not _SESSIONS:
    _SESSIONS.update(_load_sessions())


def save_wallet_sign_session(ref: str, record: dict[str, Any]) -> None:
  _ensure_loaded()
  _SESSIONS[ref] = record
  _persist_sessions()


def get_wallet_sign_session(ref: str) -> dict[str, Any] | None:
  _reload_from_disk()
  record = _SESSIONS.get(ref)
  if not record:
    return None
  if time.time() > float(record.get("expires_at", 0)):
    if record.get("status") == "pending":
      record["status"] = "expired"
      _persist_sessions()
    return None
  return record


def get_x402_wallet_signature(
    payment_mandate_chain_id: str,
) -> dict[str, str] | None:
  """Return {from, signature, valid_before} for a signed chain id."""
  _reload_from_disk()
  chain_id = (payment_mandate_chain_id or "").strip()
  if not chain_id:
    return None
  for record in _SESSIONS.values():
    if record.get("payment_mandate_chain_id") != chain_id:
      continue
    if record.get("status") != "signed":
      continue
    sig = record.get("signature")
    addr = record.get("wallet_address")
    if sig and addr:
      return {
          "from": str(addr),
          "signature": str(sig),
          "valid_before": str(record.get("valid_before", "")),
          "tx_hash": str(record.get("tx_hash") or ""),
          "payment_wei": str(record.get("payment_wei") or ""),
          "eth_usd_rate": str(record.get("eth_usd_rate") or ""),
      }
  return None


def get_wallet_address_for_session(session_id: str) -> str | None:
  """Most recent signed wallet for an AP2 session (for UI labels)."""
  _reload_from_disk()
  sid = (session_id or "").strip()
  if not sid:
    return None
  best: dict[str, Any] | None = None
  for record in _SESSIONS.values():
    if record.get("session_id") != sid:
      continue
    if record.get("status") != "signed":
      continue
    signed_at = float(record.get("signed_at") or 0)
    if best is None or signed_at > float(best.get("signed_at") or 0):
      best = record
  if best and best.get("wallet_address"):
    return str(best["wallet_address"])
  return None
