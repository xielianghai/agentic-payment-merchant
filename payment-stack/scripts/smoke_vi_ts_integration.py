#!/usr/bin/env python3
"""Integration smoke: Trusted Surface approval -> VI L2 -> VI L3."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

_UNIFIED_ROOT = Path(__file__).resolve().parents[1]
_AGENT_DIR = _UNIFIED_ROOT / "shopping_agent_unified"
sys.path.insert(0, str(_UNIFIED_ROOT))
sys.path.insert(0, str(_AGENT_DIR))
os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED_ROOT / ".temp-db"))
os.environ.setdefault("AP2_VI_ENABLED", "1")

from trusted_surface_gate import (  # noqa: E402
    approval_vi_l2_credential_id,
    confirm_trusted_surface_approval,
    create_ts_session,
    set_request_session_id,
)
from vi_unified.credentials import prepare_card_vi_l3  # noqa: E402


def main() -> None:
    session_id = f"vi-ts-smoke-{uuid.uuid4()}"
    ts = create_ts_session(
        session_id,
        price_cap=120.0,
        payment_method="card",
        item_id="rt_demo",
        item_name="Demo Flight",
        presence_mode="hp",
        amount_cents=11900,
        constraints={"price_lt": 130.0},
    )
    if ts.get("error"):
        raise SystemExit(f"FAIL create_ts_session: {ts}")
    confirm = confirm_trusted_surface_approval(ts["ref"])
    if confirm.get("error"):
        raise SystemExit(f"FAIL confirm_trusted_surface_approval: {confirm}")
    if not confirm.get("vi_l2_credential_id"):
        raise SystemExit(f"FAIL missing vi_l2_credential_id: {confirm}")
    set_request_session_id(session_id)
    l2_id = approval_vi_l2_credential_id()
    if l2_id != confirm["vi_l2_credential_id"]:
        raise SystemExit(f"FAIL approval lookup mismatch: {l2_id} != {confirm['vi_l2_credential_id']}")
    l3 = prepare_card_vi_l3(
        session_id=session_id,
        payment_method="card",
        amount_cents=11900,
        currency="USD",
        open_checkout_hash="open_demo",
        checkout_jwt_hash="checkout_demo",
        payment_mandate_chain_id="pay_demo",
        payment_nonce="nonce_demo",
        presence_mode="hp",
    )
    if l3.get("error"):
        raise SystemExit(f"FAIL prepare_card_vi_l3: {l3}")
    print("OK  trusted_surface_vi_chain")
    print(f"    vi_l2={l3['vi_l2_credential_id']}")
    print(f"    vi_l3={l3['vi_l3_credential_id']}")
    print("")
    print("VI TS integration smoke PASSED")


if __name__ == "__main__":
    main()
