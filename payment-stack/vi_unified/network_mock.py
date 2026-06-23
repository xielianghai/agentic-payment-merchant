"""Mock Mastercard network verifier for local VI proof validation."""

from __future__ import annotations

import secrets
import time
from typing import Any

from vi_unified.credentials import load_credential, verify_vi_chain_for_payment
from vi_unified.logging import vi_log


def mock_mastercard_network_verify(
    *,
    payment_token: str,
    vi_l2_credential_id: str,
    vi_l3_credential_id: str,
    payment_method: str,
    amount_cents: int,
    currency: str,
    open_checkout_hash: str,
    checkout_jwt_hash: str,
    payment_mandate_chain_id: str = "",
    payment_nonce: str = "",
    merchant_id: str = "",
) -> dict[str, Any]:
    """Simulate Mastercard network/issuer VI proof check before card settlement."""
    vi_log(
        "network_verify_start",
        payment_token=payment_token,
        l2_id=vi_l2_credential_id,
        l3_id=vi_l3_credential_id,
        amount_cents=amount_cents,
        currency=currency,
    )
    vi_err = verify_vi_chain_for_payment(
        vi_l2_credential_id=vi_l2_credential_id,
        vi_l3_credential_id=vi_l3_credential_id,
        payment_method=payment_method,
        amount_cents=amount_cents,
        currency=currency,
        open_checkout_hash=open_checkout_hash,
        checkout_jwt_hash=checkout_jwt_hash,
        payment_mandate_chain_id=payment_mandate_chain_id,
        payment_nonce=payment_nonce,
    )
    if vi_err:
        vi_log(
            "network_verify_failed",
            payment_token=payment_token,
            error=vi_err.get("error"),
            message=vi_err.get("message"),
        )
        return {
            "error": "vi_network_verification_failed",
            "network": "mastercard_mock",
            "vi_verified": False,
            "message": vi_err.get("message", "VI network verification failed."),
            "payment_token": payment_token,
        }

    l3 = load_credential(vi_l3_credential_id) or {}
    auth_code = "MCVI-" + secrets.token_hex(3).upper()
    vi_log(
        "network_verify_ok",
        payment_token=payment_token,
        auth_code=auth_code,
        l2_id=vi_l2_credential_id,
        l3_id=vi_l3_credential_id,
        amount_cents=amount_cents,
        l2_intent_hash=l3.get("l2_intent_hash"),
    )
    return {
        "network": "mastercard_mock",
        "decision": "approved",
        "vi_verified": True,
        "auth_code": auth_code,
        "payment_token": payment_token,
        "vi_l2_credential_id": vi_l2_credential_id,
        "vi_l3_credential_id": vi_l3_credential_id,
        "merchant_id": merchant_id,
        "amount_cents": int(amount_cents),
        "currency": str(currency or "USD"),
        "verified_at": int(time.time()),
        "l2_intent_hash": l3.get("l2_intent_hash"),
    }
