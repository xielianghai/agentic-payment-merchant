#!/usr/bin/env python3
"""Smoke test buyer MCP HTTP + session tools (no LLM)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_UNIFIED = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED / "roles"
_AGENT = _ROLES / "shopping_agent_unified"
_SAMPLES_SRC = _UNIFIED.parents[2] / "src"

os.environ.setdefault("TEMP_DB_DIR", str(_UNIFIED / ".temp-db"))
os.environ.setdefault("AP2_DISABLE_TS_GATE", "1")
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT), str(_ROLES)]

from trusted_surface_gate import grant_trusted_surface_approval, reset_request_session_id  # noqa: E402

from buyer_mcp_unified.session_store import load_tool_context  # noqa: E402
from shopping_agent.agent import set_ap2_session_config  # noqa: E402
from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool  # noqa: E402

SESSION = "smoke_openclaw"


def main() -> None:
  token = grant_trusted_surface_approval(200, "card", session_id=SESSION)
  try:
    ctx = load_tool_context(SESSION)
    cfg = set_ap2_session_config("hnp", "card", ctx, merchant="shoe")
    if cfg.get("error"):
      raise SystemExit(f"set_ap2_session_config failed: {cfg}")
    req = json.dumps({
        "item_id": "smoke_openclaw_item_0",
        "item_name": "Smoke Item",
        "price_cap": 200,
        "qty": 1,
    })
    signed = assemble_and_sign_mandates_tool(req, ctx)
    if signed.get("error"):
      raise SystemExit(f"assemble failed: {signed}")
    print("OK  smoke_openclaw_buyer: session + assemble (card/hnp)")
  finally:
    reset_request_session_id(token)


if __name__ == "__main__":
  main()
