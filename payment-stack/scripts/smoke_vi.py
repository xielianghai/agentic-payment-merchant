#!/usr/bin/env python3
"""Smoke tests for local VI credential helpers."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

_UNIFIED_ROOT = Path(__file__).resolve().parents[1]
_TEMP_DB = _UNIFIED_ROOT / ".temp-db"
sys.path.insert(0, str(_UNIFIED_ROOT))
os.environ.setdefault("TEMP_DB_DIR", str(_TEMP_DB))
os.environ.setdefault("AP2_VI_ENABLED", "1")
os.environ.setdefault("AP2_DISABLE_VI", "0")

from vi_unified.credentials import (  # noqa: E402
    issue_l2_intent_credential,
    issue_l3_action_credential,
    verify_vi_chain_for_payment,
)
from vi_unified.network_mock import mock_mastercard_network_verify  # noqa: E402


def _assert_ok(name: str, result: dict) -> None:
    if result.get("error"):
        raise SystemExit(f"FAIL {name}: {result}")
    print(f"OK  {name}")


def main() -> None:
    session_id = f"vi-smoke-{uuid.uuid4()}"
    draft = {
        "session_id": session_id,
        "item_id": "rt_sin_pvg",
        "item_name": "SIN-PVG Economy",
        "price_cap": 600.0,
        "amount_cents": 59900,
        "payment_method": "card",
        "presence_mode": "hp",
        "constraints": {"price_lt": 650.0},
    }
    l2 = issue_l2_intent_credential(draft, session_id=session_id)
    _assert_ok("issue_l2", l2)
    l2_id = l2["vi_l2_credential_id"]

    l3 = issue_l3_action_credential(
        vi_l2_credential_id=l2_id,
        payment_method="card",
        amount_cents=59900,
        currency="USD",
        open_checkout_hash="open_hash_demo",
        checkout_jwt_hash="checkout_hash_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
        presence_mode="hp",
    )
    _assert_ok("issue_l3", l3)
    l3_id = l3["vi_l3_credential_id"]

    vi_err = verify_vi_chain_for_payment(
        vi_l2_credential_id=l2_id,
        vi_l3_credential_id=l3_id,
        payment_method="card",
        amount_cents=59900,
        currency="USD",
        open_checkout_hash="open_hash_demo",
        checkout_jwt_hash="checkout_hash_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
    )
    if vi_err:
        raise SystemExit(f"FAIL verify_vi_chain: {vi_err}")
    print("OK  verify_vi_chain")

    bad = verify_vi_chain_for_payment(
        vi_l2_credential_id=l2_id,
        vi_l3_credential_id=l3_id,
        payment_method="card",
        amount_cents=1,
        currency="USD",
        open_checkout_hash="open_hash_demo",
        checkout_jwt_hash="checkout_hash_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
    )
    if not bad or bad.get("error") != "vi_l3_invalid":
        raise SystemExit(f"FAIL expected vi_l3_invalid, got {bad}")
    print("OK  verify_vi_chain_rejects_mismatch")

    network = mock_mastercard_network_verify(
        payment_token="tok_demo",
        vi_l2_credential_id=l2_id,
        vi_l3_credential_id=l3_id,
        payment_method="card",
        amount_cents=59900,
        currency="USD",
        open_checkout_hash="open_hash_demo",
        checkout_jwt_hash="checkout_hash_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
    )
    _assert_ok("mock_network", network)
    if not network.get("auth_code", "").startswith("MCVI-"):
        raise SystemExit(f"FAIL missing auth_code: {network}")
    print(f"    auth_code={network['auth_code']}")

    bad_network = mock_mastercard_network_verify(
        payment_token="tok_demo",
        vi_l2_credential_id=l2_id,
        vi_l3_credential_id=l3_id,
        payment_method="card",
        amount_cents=1,
        currency="USD",
        open_checkout_hash="open_hash_demo",
        checkout_jwt_hash="checkout_hash_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
    )
    if bad_network.get("error") != "vi_network_verification_failed":
        raise SystemExit(f"FAIL expected network failure, got {bad_network}")
    print("OK  mock_network_rejects_mismatch")
    print("")
    print("VI smoke PASSED")


if __name__ == "__main__":
    main()
