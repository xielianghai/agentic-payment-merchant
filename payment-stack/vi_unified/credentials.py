"""Local VI L2/L3 credential helpers (spec-aligned demo, no Mastercard API)."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from jwcrypto import jwk, jwt
from jwcrypto.common import base64url_encode

from constants_unified import TEMP_DB, USER_SIGNING_KEY_PATH, USER_SIGNING_PUB_PATH

VI_VERSION = "2026-01-demo"
VI_TTL_SECONDS = int(os.environ.get("AP2_VI_TTL_SECONDS", "300"))
VI_STORE_DIR = Path(os.environ.get("TEMP_DB_DIR", str(TEMP_DB)))


def is_vi_enabled() -> bool:
    if os.environ.get("AP2_DISABLE_VI", "").strip() == "1":
        return False
    return os.environ.get("AP2_VI_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def intent_hash(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).digest()
    return base64url_encode(digest)


def build_intent_payload(draft: dict[str, Any]) -> dict[str, Any]:
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
        "session_id": str(draft.get("session_id", "")),
        "item_id": str(draft.get("item_id", "")),
        "item_name": str(draft.get("item_name", draft.get("display_name", ""))),
        "price_cap": float(draft.get("price_cap", 0)),
        "amount_cents": int(amount_cents),
        "payment_method": str(draft.get("payment_method", "card")).lower(),
        "presence_mode": str(draft.get("presence_mode", "hnp")),
        "payee": str(draft.get("payee", "")),
        "constraints": constraints,
    }


def _credential_path(credential_id: str) -> Path:
    safe = (credential_id or "").strip()
    if not safe or "/" in safe or ".." in safe:
        raise ValueError(f"invalid credential_id: {credential_id!r}")
    return VI_STORE_DIR / f"{safe}.json"


def _load_user_signing_key() -> jwk.JWK:
    if USER_SIGNING_KEY_PATH.exists():
        return jwk.JWK.from_json(USER_SIGNING_KEY_PATH.read_text(encoding="utf-8"))
    from cryptography.hazmat.primitives.asymmetric import ec

    raw_key = ec.generate_private_key(ec.SECP256R1())
    key = jwk.JWK.from_pyca(raw_key)
    jwk_dict = json.loads(key.export())
    jwk_dict["kid"] = "user-signing-key-1"
    key = jwk.JWK.from_json(json.dumps(jwk_dict))
    USER_SIGNING_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_SIGNING_KEY_PATH.write_text(key.export(), encoding="utf-8")
    USER_SIGNING_PUB_PATH.write_text(key.export_public(), encoding="utf-8")
    return key


def _load_agent_signing_key() -> jwk.JWK:
    agent_key_path = VI_STORE_DIR / "agent_signing_key.pem"
    agent_pub_path = VI_STORE_DIR / "agent_signing_key.pub"
    if agent_key_path.exists():
        return jwk.JWK.from_json(agent_key_path.read_text(encoding="utf-8"))
    raw = jwk.JWK.generate(kty="EC", crv="P-256")
    jwk_dict = json.loads(raw.export())
    jwk_dict["kid"] = "agent-signing-key-1"
    key = jwk.JWK.from_json(json.dumps(jwk_dict))
    agent_key_path.parent.mkdir(parents=True, exist_ok=True)
    agent_key_path.write_text(key.export(), encoding="utf-8")
    agent_pub_path.write_text(key.export_public(), encoding="utf-8")
    return key


def _sign_payload(payload: dict[str, Any], key: jwk.JWK, *, kid: str) -> str:
    token = jwt.JWT(header={"alg": "ES256", "kid": kid}, claims=payload)
    token.make_signed_token(key)
    return token.serialize()


def _verify_signed_payload(signed: str, key: jwk.JWK) -> dict[str, Any]:
    token = jwt.JWT()
    token.deserialize(signed, key=key)
    claims = json.loads(token.claims)
    if not isinstance(claims, dict):
        raise ValueError("VI credential claims must be an object")
    return claims


def _persist_credential(record: dict[str, Any]) -> None:
    cred_id = str(record["credential_id"])
    path = _credential_path(cred_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def load_credential(credential_id: str) -> dict[str, Any] | None:
    path = _credential_path(credential_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def issue_l2_intent_credential(
    draft: dict[str, Any],
    *,
    session_id: str = "",
) -> dict[str, Any]:
    """Issue VI L2 intent credential after Trusted Surface approval (card only)."""
    if not is_vi_enabled():
        return {"skipped": True, "reason": "vi_disabled"}
    payload = build_intent_payload(draft)
    if payload.get("payment_method") != "card":
        return {"skipped": True, "reason": "not_card"}
    if session_id:
        payload["session_id"] = session_id
    ihash = intent_hash(payload)
    now = int(time.time())
    credential_id = "vi_l2_" + uuid.uuid4().hex
    claims = {
        "vi_version": VI_VERSION,
        "credential_type": "vi_l2_intent",
        "credential_id": credential_id,
        "intent_hash": ihash,
        "intent": payload,
        "iat": now,
        "exp": now + VI_TTL_SECONDS,
    }
    user_key = _load_user_signing_key()
    kid = json.loads(user_key.export()).get("kid", "user-signing-key-1")
    signature = _sign_payload(claims, user_key, kid=str(kid))
    record = {
        "credential_id": credential_id,
        "type": "vi_l2_intent",
        "version": VI_VERSION,
        "intent_hash": ihash,
        "payload": payload,
        "signature": signature,
        "issuer_kid": kid,
        "issued_at": now,
        "expires_at": now + VI_TTL_SECONDS,
        "session_id": payload.get("session_id", ""),
    }
    _persist_credential(record)
    return {
        "vi_l2_credential_id": credential_id,
        "intent_hash": ihash,
        "expires_at": record["expires_at"],
    }


def get_l2_credential(credential_id: str) -> dict[str, Any] | None:
    return load_credential(credential_id)


def _canonical_session_id(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid or "@" in sid:
        return sid
    if sid.lower().startswith("feishu:") or sid.startswith("ou_"):
        return sid
    return f"{sid}@im.wechat"


def get_l2_for_session(session_id: str) -> dict[str, Any] | None:
    """Resolve latest L2 credential id stored on TS approval for a session."""
    sid = _canonical_session_id(session_id)
    if not sid:
        return None
    approvals_path = VI_STORE_DIR / "ts_approvals.json"
    if not approvals_path.is_file():
        return None
    try:
        approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    record = approvals.get(sid) if isinstance(approvals, dict) else None
    if not isinstance(record, dict):
        return None
    cred_id = record.get("vi_l2_credential_id")
    if not cred_id:
        return None
    return load_credential(str(cred_id))


def _is_placeholder_vi_id(credential_id: str) -> bool:
    cid = (credential_id or "").strip().lower()
    if not cid:
        return False
    return cid.endswith("_mock") or cid in {"mock", "vi_mock", "vi_l2_mock", "vi_l3_mock"}


def find_l2_credential_id_for_amount(
    amount_cents: int,
    *,
    payment_method: str = "card",
) -> str:
    """Find a TS-approved L2 credential matching amount and payment method."""
    result = ensure_l2_credential_id_for_amount(
        amount_cents,
        payment_method=payment_method,
        refresh_expired=False,
    )
    return result or ""


def ensure_l2_credential_id_for_amount(
    amount_cents: int,
    *,
    payment_method: str = "card",
    refresh_expired: bool = True,
) -> str:
    """Resolve L2 from TS approvals; optionally re-issue when expired."""
    approvals_path = VI_STORE_DIR / "ts_approvals.json"
    if not approvals_path.is_file():
        return ""
    try:
        approvals = json.loads(approvals_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(approvals, dict):
        return ""

    method = (payment_method or "card").strip().lower()
    target_amount = int(amount_cents)
    for session_id, record in approvals.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("payment_method", "card")).lower() != method:
            continue
        if int(record.get("amount_cents", -1)) != target_amount:
            continue

        cred_id = str(record.get("vi_l2_credential_id", "")).strip()
        if cred_id:
            l2 = load_credential(cred_id)
            if l2:
                ok, _msg = _verify_l2_record(l2)
                if ok:
                    return cred_id

        if not refresh_expired:
            continue

        draft = {
            "session_id": session_id,
            "item_id": record.get("item_id", ""),
            "item_name": record.get("item_name", ""),
            "price_cap": record.get("price_cap", target_amount / 100.0),
            "amount_cents": target_amount,
            "payment_method": method,
            "presence_mode": record.get("presence_mode", "hp"),
            "payee": record.get("payee", ""),
            "constraints": record.get("constraints", {}),
        }
        fresh = issue_l2_intent_credential(draft, session_id=session_id)
        new_id = str(fresh.get("vi_l2_credential_id", "")).strip()
        if not new_id:
            continue
        record["vi_l2_credential_id"] = new_id
        if fresh.get("intent_hash"):
            record["vi_intent_hash"] = fresh["intent_hash"]
        approvals[session_id] = record
        approvals_path.write_text(
            json.dumps(approvals, indent=2),
            encoding="utf-8",
        )
        return new_id
    return ""


def resolve_card_vi_for_issue(
    *,
    vi_l2_credential_id: str = "",
    vi_l3_credential_id: str = "",
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str,
    payment_nonce: str,
    session_id: str = "",
    merchant_id: str = "",
    presence_mode: str = "hp",
) -> dict[str, Any]:
    """Resolve or mint valid VI L2/L3 for card credential issuance."""
    if not is_vi_enabled():
        return {"vi_l2_credential_id": "", "vi_l3_credential_id": ""}
    if (payment_method or "").strip().lower() != "card":
        return {"vi_l2_credential_id": "", "vi_l3_credential_id": ""}

    l2_id = (vi_l2_credential_id or "").strip()
    l3_id = (vi_l3_credential_id or "").strip()
    if _is_placeholder_vi_id(l2_id):
        l2_id = ""
    if _is_placeholder_vi_id(l3_id):
        l3_id = ""

    if l2_id and l3_id:
        chain_err = verify_vi_chain_for_payment(
            vi_l2_credential_id=l2_id,
            vi_l3_credential_id=l3_id,
            payment_method=payment_method,
            amount_cents=amount_cents,
            currency=currency,
            open_checkout_hash=open_checkout_hash,
            checkout_jwt_hash=checkout_jwt_hash,
            payment_mandate_chain_id=payment_mandate_chain_id,
            payment_nonce=payment_nonce,
        )
        if chain_err is None:
            return {"vi_l2_credential_id": l2_id, "vi_l3_credential_id": l3_id}

    if not l2_id:
        if session_id:
            l2 = get_l2_for_session(session_id)
            if l2:
                l2_id = str(l2.get("credential_id", "")).strip()
        if not l2_id:
            l2_id = ensure_l2_credential_id_for_amount(
                amount_cents,
                payment_method=payment_method,
            )

    bundle = prepare_card_vi_l3(
        session_id=session_id,
        vi_l2_credential_id=l2_id,
        payment_method=payment_method,
        amount_cents=amount_cents,
        currency=currency,
        open_checkout_hash=open_checkout_hash,
        checkout_jwt_hash=checkout_jwt_hash,
        payment_mandate_chain_id=payment_mandate_chain_id,
        payment_nonce=payment_nonce,
        merchant_id=merchant_id,
        presence_mode=presence_mode,
    )
    if bundle.get("error"):
        return bundle
    if bundle.get("skipped"):
        return {"vi_l2_credential_id": "", "vi_l3_credential_id": ""}
    return {
        "vi_l2_credential_id": str(bundle.get("vi_l2_credential_id", "")),
        "vi_l3_credential_id": str(bundle.get("vi_l3_credential_id", "")),
    }


def issue_l3_action_credential(
    *,
    vi_l2_credential_id: str,
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str,
    payment_nonce: str,
    merchant_id: str = "",
    presence_mode: str = "hp",
) -> dict[str, Any]:
    """Issue VI L3 action credential bound to L2 and AP2 payment context."""
    if not is_vi_enabled():
        return {"skipped": True, "reason": "vi_disabled"}
    if (payment_method or "").strip().lower() != "card":
        return {"skipped": True, "reason": "not_card"}
    l2 = load_credential(vi_l2_credential_id)
    if not l2:
        return {
            "error": "vi_l2_not_found",
            "message": f"VI L2 credential {vi_l2_credential_id!r} not found.",
        }
    l2_ok, l2_msg = _verify_l2_record(l2)
    if not l2_ok:
        return {"error": "vi_l2_invalid", "message": l2_msg}

    now = int(time.time())
    credential_id = "vi_l3_" + uuid.uuid4().hex
    action_payload = {
        "vi_version": VI_VERSION,
        "credential_type": "vi_l3_action",
        "credential_id": credential_id,
        "l2_credential_id": vi_l2_credential_id,
        "l2_intent_hash": l2.get("intent_hash"),
        "payment_method": "card",
        "amount_cents": int(amount_cents),
        "currency": str(currency or "USD"),
        "open_checkout_hash": str(open_checkout_hash),
        "checkout_jwt_hash": str(checkout_jwt_hash),
        "payment_mandate_chain_id": str(payment_mandate_chain_id),
        "payment_nonce": str(payment_nonce),
        "merchant_id": str(merchant_id or ""),
        "presence_mode": str(presence_mode or "hp"),
        "iat": now,
        "exp": now + VI_TTL_SECONDS,
    }
    agent_key = _load_agent_signing_key()
    kid = json.loads(agent_key.export()).get("kid", "agent-signing-key-1")
    signature = _sign_payload(action_payload, agent_key, kid=str(kid))
    record = {
        "credential_id": credential_id,
        "type": "vi_l3_action",
        "version": VI_VERSION,
        "l2_credential_id": vi_l2_credential_id,
        "l2_intent_hash": l2.get("intent_hash"),
        "payload": action_payload,
        "signature": signature,
        "issuer_kid": kid,
        "issued_at": now,
        "expires_at": now + VI_TTL_SECONDS,
    }
    _persist_credential(record)
    return {
        "vi_l3_credential_id": credential_id,
        "vi_l2_credential_id": vi_l2_credential_id,
        "l2_intent_hash": l2.get("intent_hash"),
        "expires_at": record["expires_at"],
    }


def _verify_l2_record(record: dict[str, Any]) -> tuple[bool, str]:
    if record.get("type") != "vi_l2_intent":
        return False, "invalid L2 credential type"
    expires_at = int(record.get("expires_at", 0))
    if expires_at and time.time() > expires_at:
        return False, "L2 credential expired"
    signature = record.get("signature")
    if not isinstance(signature, str) or not signature:
        return False, "L2 credential missing signature"
    try:
        user_key = _load_user_signing_key()
        claims = _verify_signed_payload(signature, user_key)
    except Exception as exc:
        return False, f"L2 signature verification failed: {exc}"
    expected_hash = record.get("intent_hash")
    if expected_hash and claims.get("intent_hash") != expected_hash:
        return False, "L2 intent_hash mismatch"
    payload = record.get("payload")
    if isinstance(payload, dict) and intent_hash(payload) != expected_hash:
        return False, "L2 payload hash mismatch"
    return True, "ok"


def _verify_l3_record(
    record: dict[str, Any],
    *,
    l2_credential_id: str,
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str,
    payment_nonce: str,
) -> tuple[bool, str]:
    if record.get("type") != "vi_l3_action":
        return False, "invalid L3 credential type"
    expires_at = int(record.get("expires_at", 0))
    if expires_at and time.time() > expires_at:
        return False, "L3 credential expired"
    signature = record.get("signature")
    if not isinstance(signature, str) or not signature:
        return False, "L3 credential missing signature"
    try:
        agent_key = _load_agent_signing_key()
        claims = _verify_signed_payload(signature, agent_key)
    except Exception as exc:
        return False, f"L3 signature verification failed: {exc}"

    l2_id = str(record.get("l2_credential_id", ""))
    if l2_id != l2_credential_id:
        return False, "L3 L2 credential id mismatch"
    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = claims
    checks = [
        (payload.get("payment_method"), "card", "payment_method"),
        (int(payload.get("amount_cents", -1)), int(amount_cents), "amount_cents"),
        (str(payload.get("currency", "")), str(currency or "USD"), "currency"),
        (str(payload.get("open_checkout_hash", "")), str(open_checkout_hash), "open_checkout_hash"),
        (str(payload.get("checkout_jwt_hash", "")), str(checkout_jwt_hash), "checkout_jwt_hash"),
        (
            str(payload.get("payment_mandate_chain_id", "")),
            str(payment_mandate_chain_id),
            "payment_mandate_chain_id",
        ),
        (str(payload.get("payment_nonce", "")), str(payment_nonce), "payment_nonce"),
    ]
    for actual, expected, field in checks:
        if actual != expected:
            return False, f"L3 {field} mismatch"
    l2 = load_credential(l2_credential_id)
    if not l2:
        return False, "referenced L2 credential not found"
    l2_ok, l2_msg = _verify_l2_record(l2)
    if not l2_ok:
        return False, f"referenced L2 invalid: {l2_msg}"
    if str(record.get("l2_intent_hash", "")) != str(l2.get("intent_hash", "")):
        return False, "L3 L2 intent_hash mismatch"
    return True, "ok"


def prepare_card_vi_l3(
    *,
    session_id: str = "",
    vi_l2_credential_id: str = "",
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str,
    payment_nonce: str,
    merchant_id: str = "",
    presence_mode: str = "hp",
) -> dict[str, Any]:
    """Resolve L2 (if needed) and issue L3 for card payment flows."""
    if not is_vi_enabled() or (payment_method or "").strip().lower() != "card":
        return {"skipped": True}
    l2_id = (vi_l2_credential_id or "").strip()
    if not l2_id and session_id:
        l2 = get_l2_for_session(session_id)
        if l2:
            l2_id = str(l2.get("credential_id", ""))
    if not l2_id:
        return {
            "error": "vi_l2_required",
            "message": "card payments require an approved VI L2 intent credential.",
        }
    l3 = issue_l3_action_credential(
        vi_l2_credential_id=l2_id,
        payment_method=payment_method,
        amount_cents=amount_cents,
        currency=currency,
        open_checkout_hash=open_checkout_hash,
        checkout_jwt_hash=checkout_jwt_hash,
        payment_mandate_chain_id=payment_mandate_chain_id,
        payment_nonce=payment_nonce,
        merchant_id=merchant_id,
        presence_mode=presence_mode,
    )
    if l3.get("error"):
        return l3
    return {
        "vi_l2_credential_id": l2_id,
        "vi_l3_credential_id": l3.get("vi_l3_credential_id"),
        "l2_intent_hash": l3.get("l2_intent_hash"),
        "expires_at": l3.get("expires_at"),
    }


def verify_vi_chain_for_payment(
    *,
    vi_l2_credential_id: str,
    vi_l3_credential_id: str,
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str,
    payment_nonce: str,
) -> dict[str, Any] | None:
    """Return error dict if VI chain invalid; None if ok or VI disabled."""
    if not is_vi_enabled():
        return None
    if (payment_method or "").strip().lower() != "card":
        return None
    if not vi_l2_credential_id or not vi_l3_credential_id:
        return {
            "error": "vi_credentials_required",
            "message": "card payments require vi_l2_credential_id and vi_l3_credential_id.",
        }
    l2 = load_credential(vi_l2_credential_id)
    if not l2:
        return {
            "error": "vi_l2_not_found",
            "message": f"VI L2 credential {vi_l2_credential_id!r} not found.",
        }
    l2_ok, l2_msg = _verify_l2_record(l2)
    if not l2_ok:
        return {"error": "vi_l2_invalid", "message": l2_msg}
    l3 = load_credential(vi_l3_credential_id)
    if not l3:
        return {
            "error": "vi_l3_not_found",
            "message": f"VI L3 credential {vi_l3_credential_id!r} not found.",
        }
    l3_ok, l3_msg = _verify_l3_record(
        l3,
        l2_credential_id=vi_l2_credential_id,
        payment_method=payment_method,
        amount_cents=amount_cents,
        currency=currency,
        open_checkout_hash=open_checkout_hash,
        checkout_jwt_hash=checkout_jwt_hash,
        payment_mandate_chain_id=payment_mandate_chain_id,
        payment_nonce=payment_nonce,
    )
    if not l3_ok:
        return {"error": "vi_l3_invalid", "message": l3_msg}
    return None
