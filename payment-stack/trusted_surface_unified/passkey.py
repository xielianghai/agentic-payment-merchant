"""WebAuthn passkey helpers for Trusted Surface (mandate-bound challenge)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from webauthn import (
  generate_authentication_options,
  generate_registration_options,
  options_to_json,
  verify_authentication_response,
  verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
  AuthenticatorAttachment,
  AuthenticatorSelectionCriteria,
  PublicKeyCredentialDescriptor,
  ResidentKeyRequirement,
  UserVerificationRequirement,
)

_ROLES_DIR = Path(__file__).resolve().parents[1]
_AGENT_DIR = _ROLES_DIR / "shopping_agent_unified"
if str(_AGENT_DIR) not in sys.path:
  sys.path.insert(0, str(_AGENT_DIR))

from trusted_surface_gate import (  # noqa: E402
  _persist_json,
  _temp_db,
  get_trusted_surface_draft,
)

_PASSKEYS: dict[str, dict[str, Any]] = {}
_PASSKEY_STATE: dict[str, dict[str, Any]] = {}


def _passkeys_file() -> Path:
  return _temp_db() / "ts_passkeys.json"


def _passkey_state_file() -> Path:
  return _temp_db() / "ts_passkey_state.json"


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


def _ensure_passkeys_loaded() -> None:
  if _PASSKEYS:
    return
  _PASSKEYS.update(_load_file_json(_passkeys_file()))


def _ensure_state_loaded() -> None:
  if _PASSKEY_STATE:
    return
  _PASSKEY_STATE.update(_load_file_json(_passkey_state_file()))


def _persist_passkeys() -> None:
  _persist_json(_passkeys_file(), _PASSKEYS)


def _persist_passkey_state() -> None:
  _persist_json(_passkey_state_file(), _PASSKEY_STATE)


def _rp_id() -> str:
  return os.environ.get("TS_RP_ID", "localhost").strip() or "localhost"


def _rp_name() -> str:
  return os.environ.get("TS_RP_NAME", "AP2 Trusted Surface").strip()


def _origin() -> str:
  port = os.environ.get(
      "UNIFIED_TRUSTED_SURFACE_PORT",
      os.environ.get("TRUSTED_SURFACE_PORT", "8104"),
  )
  default = f"http://localhost:{port}"
  return os.environ.get("TS_ORIGIN", default).rstrip("/")


def _authenticator_selection() -> AuthenticatorSelectionCriteria:
  """Prefer platform authenticator (Touch ID / Windows Hello) on localhost demo.

  ``resident_key=PREFERRED`` without ``platform`` attachment makes Chrome show
  "Choose where to save your passkey" (Google vs iCloud) and often never
  reaches Touch ID. ``platform`` + ``discouraged`` uses the local secure enclave.
  """
  mode = os.environ.get("TS_AUTHENTICATOR", "platform").strip().lower()
  if mode in {"any", "cross-platform", "cross_platform"}:
    return AuthenticatorSelectionCriteria(
        resident_key=ResidentKeyRequirement.PREFERRED,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
  return AuthenticatorSelectionCriteria(
      authenticator_attachment=AuthenticatorAttachment.PLATFORM,
      resident_key=ResidentKeyRequirement.DISCOURAGED,
      user_verification=UserVerificationRequirement.REQUIRED,
  )


def _user_handle(session_id: str) -> bytes:
  digest = hashlib.sha256((session_id or "demo").encode("utf-8")).digest()
  return digest[:16]


def _user_handle_key(session_id: str) -> str:
  return bytes_to_base64url(_user_handle(session_id))


def _mandate_binding_payload(draft: dict[str, Any]) -> dict[str, Any]:
  amount_cents = draft.get("amount_cents")
  if amount_cents is None:
    try:
      amount_cents = round(float(draft.get("price_cap", 0)) * 100)
    except (TypeError, ValueError):
      amount_cents = 0
  constraints = draft.get("constraints")
  if not isinstance(constraints, dict):
    constraints = {}
  return {
      "item_id": str(draft.get("item_id", "")),
      "item_name": str(draft.get("item_name", "")),
      "price_cap": float(draft.get("price_cap", 0)),
      "amount_cents": int(amount_cents),
      "payment_method": str(draft.get("payment_method", "card")),
      "presence_mode": str(draft.get("presence_mode", "hnp")),
      "payee": str(draft.get("payee", "")),
      "constraints": constraints,
  }


def bound_challenge(ref: str) -> bytes | None:
  draft = get_trusted_surface_draft(ref)
  if not draft:
    return None
  payload = _mandate_binding_payload(draft)
  canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
  return hashlib.sha256(canonical.encode("utf-8")).digest()


def _session_id_for_ref(ref: str) -> str | None:
  draft = get_trusted_surface_draft(ref)
  if not draft:
    return None
  sid = str(draft.get("session_id", "")).strip()
  return sid or None


def _get_credential(user_key: str) -> dict[str, Any] | None:
  _ensure_passkeys_loaded()
  return _PASSKEYS.get(user_key)


def _store_challenge_state(ref: str, *, challenge: bytes, op: str, user_key: str) -> None:
  _ensure_state_loaded()
  _PASSKEY_STATE[ref] = {
      "challenge_b64": bytes_to_base64url(challenge),
      "op": op,
      "user_key": user_key,
  }
  _persist_passkey_state()


def _pop_challenge_state(ref: str) -> dict[str, Any] | None:
  _ensure_state_loaded()
  state = _PASSKEY_STATE.pop(ref, None)
  if state:
    _persist_passkey_state()
  return state


def build_options(ref: str) -> dict[str, Any]:
  """Return WebAuthn register/auth options bound to the frozen mandate."""
  rid = (ref or "").strip()
  if not rid:
    return {"error": "ref_required", "message": "ref is required."}

  draft = get_trusted_surface_draft(rid)
  if not draft:
    return {"error": "not_found", "message": "Session not found or expired."}

  session_id = _session_id_for_ref(rid)
  if not session_id:
    return {"error": "invalid_draft", "message": "TS session draft is missing session_id."}

  challenge = bound_challenge(rid)
  if not challenge:
    return {"error": "not_found", "message": "Could not derive mandate-bound challenge."}

  user_key = _user_handle_key(session_id)
  user_id = _user_handle(session_id)
  existing = _get_credential(user_key)

  if existing:
    allow = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(str(existing["credential_id"])),
        ),
    ]
    options = generate_authentication_options(
        rp_id=_rp_id(),
        challenge=challenge,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    op = "auth"
  else:
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=user_id,
        user_name=session_id[:32] or "ap2-user",
        user_display_name=f"AP2 user {session_id[:8]}",
        challenge=challenge,
        authenticator_selection=_authenticator_selection(),
    )
    op = "register"

  _store_challenge_state(rid, challenge=challenge, op=op, user_key=user_key)
  public_key = json.loads(options_to_json(options))
  return {"op": op, "publicKey": public_key}


def _credential_from_client(body: dict[str, Any]) -> dict[str, Any]:
  return {
      "id": str(body.get("id", "")),
      "rawId": str(body.get("rawId", "")),
      "type": str(body.get("type", "public-key")),
      "response": body.get("response") if isinstance(body.get("response"), dict) else {},
      "clientExtensionResults": body.get("clientExtensionResults")
      if isinstance(body.get("clientExtensionResults"), dict)
      else {},
  }


def verify_register(ref: str, body: dict[str, Any]) -> dict[str, Any]:
  """Verify passkey registration; first enrollment counts as authorization."""
  rid = (ref or "").strip()
  if not rid:
    return {"error": "ref_required", "message": "ref is required."}

  state = _pop_challenge_state(rid)
  if not state or state.get("op") != "register":
    return {
        "error": "challenge_not_found",
        "message": "Registration challenge expired or missing. Reload the page.",
    }

  expected_challenge = base64url_to_bytes(str(state["challenge_b64"]))
  user_key = str(state.get("user_key", ""))

  try:
    verification = verify_registration_response(
        credential=_credential_from_client(body),
        expected_challenge=expected_challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        require_user_verification=True,
    )
  except Exception as exc:
    return {"error": "registration_failed", "message": str(exc)}

  _ensure_passkeys_loaded()
  _PASSKEYS[user_key] = {
      "credential_id": bytes_to_base64url(verification.credential_id),
      "public_key": bytes_to_base64url(verification.credential_public_key),
      "sign_count": int(verification.sign_count),
  }
  _persist_passkeys()
  return {
      "status": "ok",
      "ref": rid,
      "op": "register",
      "credential_id": _PASSKEYS[user_key]["credential_id"],
      "message": "Passkey registered and mandate authorized.",
  }


def verify_assertion(ref: str, body: dict[str, Any]) -> dict[str, Any]:
  """Verify passkey authentication bound to the frozen mandate."""
  rid = (ref or "").strip()
  if not rid:
    return {"error": "ref_required", "message": "ref is required."}

  state = _pop_challenge_state(rid)
  if not state or state.get("op") != "auth":
    return {
        "error": "challenge_not_found",
        "message": "Authentication challenge expired or missing. Reload the page.",
    }

  user_key = str(state.get("user_key", ""))
  stored = _get_credential(user_key)
  if not stored:
    return {"error": "credential_not_found", "message": "No passkey registered for this user."}

  expected_challenge = base64url_to_bytes(str(state["challenge_b64"]))
  credential_id = base64url_to_bytes(str(stored["credential_id"]))
  public_key = base64url_to_bytes(str(stored["public_key"]))
  sign_count = int(stored.get("sign_count", 0))

  try:
    verification = verify_authentication_response(
        credential=_credential_from_client(body),
        expected_challenge=expected_challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        credential_public_key=public_key,
        credential_current_sign_count=sign_count,
        require_user_verification=True,
    )
  except Exception as exc:
    return {"error": "authentication_failed", "message": str(exc)}

  _ensure_passkeys_loaded()
  _PASSKEYS[user_key]["sign_count"] = int(verification.new_sign_count)
  _persist_passkeys()

  return {
      "status": "ok",
      "ref": rid,
      "op": "auth",
      "credential_id": stored["credential_id"],
      "new_sign_count": int(verification.new_sign_count),
      "message": "Passkey verified and mandate authorized.",
  }
