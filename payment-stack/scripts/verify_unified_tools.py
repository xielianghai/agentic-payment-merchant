#!/usr/bin/env python3
"""Pre-flight checks for unified shopping-agent mandate bridge tools.

Run before ./run.sh or in CI to catch ADK schema / bridge wiring regressions
without driving the full LLM flow.

Usage (from repo):
  cd code/samples/python/scenarios/a2a/unified/roles/shopping_agent_unified
  uv run --no-sync python ../../scripts/verify_unified_tools.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Offline checks call assemble without HTTP / Trusted Surface UI.
os.environ["AP2_DISABLE_TS_GATE"] = "1"
os.environ["AP2_DISABLE_VI"] = "1"

from google.adk.tools.function_tool import FunctionTool

_UNIFIED_ROOT = Path(__file__).resolve().parents[1]
_ROLES = _UNIFIED_ROOT
_AGENT_DIR = _UNIFIED_ROOT / "shopping_agent_unified"
_TEMP_DB = _UNIFIED_ROOT / ".temp-db"

sys.path.insert(0, str(_UNIFIED_ROOT))
from path_setup import ensure_src_on_path

_SAMPLES_SRC = ensure_src_on_path()
sys.path[:0] = [str(_SAMPLES_SRC), str(_AGENT_DIR), str(_ROLES)]

# Minimal env for mandate_tools key paths (same as run.sh).
os.environ.setdefault("TEMP_DB_DIR", str(_TEMP_DB))
os.environ.setdefault("FLOW", "card")


class _State(dict):
  """Minimal stand-in for ADK session state."""


class _ToolContext:
  def __init__(self, state: _State | None = None):
    self.state = state if state is not None else _State()


REQUIRED_TOOL_PARAMS: dict[str, set[str]] = {
    "assemble_and_sign_mandates_tool": {"mandate_request"},
    "check_constraints_against_mandate": {"price"},
    "create_checkout_presentation": {
        "checkout_jwt",
        "checkout_hash",
        "nonce",
    },
    "create_payment_presentation": {
        "checkout_hash",
        "amount_cents",
        "nonce",
    },
    "verify_checkout_receipt": {"checkout_receipt"},
}


def _schema_properties(tool: FunctionTool) -> set[str]:
  decl = tool._get_declaration()
  if decl.parameters is None or decl.parameters.properties is None:
    return set()
  return set(decl.parameters.properties.keys())


def check_adk_schemas() -> None:
  from shopping_agent.mandate_bridge import (
      assemble_and_sign_mandates_tool,
      check_constraints_against_mandate,
      create_checkout_presentation,
      create_payment_presentation,
      verify_checkout_receipt,
  )

  fns = {
      "assemble_and_sign_mandates_tool": assemble_and_sign_mandates_tool,
      "check_constraints_against_mandate": check_constraints_against_mandate,
      "create_checkout_presentation": create_checkout_presentation,
      "create_payment_presentation": create_payment_presentation,
      "verify_checkout_receipt": verify_checkout_receipt,
  }

  errors: list[str] = []
  for name, fn in fns.items():
    props = _schema_properties(FunctionTool(fn))
    required = REQUIRED_TOOL_PARAMS[name]
    missing = required - props
    if missing:
      errors.append(
          f"{name}: ADK schema missing parameters {sorted(missing)} "
          f"(got {sorted(props) or 'none'})"
      )
  if errors:
    raise SystemExit("ADK tool schema checks failed:\n  " + "\n  ".join(errors))
  print(f"OK  ADK schemas for {len(fns)} mandate bridge tools")


def check_matches_true_coercion() -> None:
  """LLM sometimes emits matches: true; backend must not iterate it."""
  from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool

  ctx = _ToolContext(
      _State({"ap2:payment_method": "card", "ap2:presence_mode": "hnp"})
  )
  mandate_request = json.dumps(
      {
          "item_id": "verify_matches_bool_item_0",
          "item_name": "Verify Matches Bool",
          "price_cap": 150,
          "qty": 1,
          "matches": True,
      }
  )
  signed = assemble_and_sign_mandates_tool(mandate_request, ctx)
  if "error" in signed:
    raise SystemExit(f"assemble_and_sign with matches:true failed: {signed}")
  print("OK  coerce matches:true → ignore and assemble")


def check_mandate_hnp_chain() -> None:
  """assemble_and_sign → check_constraints(price=0) without LLM."""
  from shopping_agent.mandate_bridge import (
      assemble_and_sign_mandates_tool,
      check_constraints_against_mandate,
  )

  if not _TEMP_DB.is_dir():
    raise SystemExit(
        f"TEMP_DB missing at {_TEMP_DB}; run ./run.sh once to generate keys"
    )

  ctx = _ToolContext(
      _State({"ap2:payment_method": "card", "ap2:presence_mode": "hnp"})
  )
  mandate_request = json.dumps(
      {
          "item_id": "verify_unified_tools_item_0",
          "item_name": "Verify Unified Tools Item",
          "price_cap": 200,
          "qty": 1,
      }
  )
  signed = assemble_and_sign_mandates_tool(mandate_request, ctx)
  if "error" in signed:
    raise SystemExit(f"assemble_and_sign_mandates_tool failed: {signed}")

  for key in ("open_checkout_mandate", "open_payment_mandate"):
    if key not in signed:
      raise SystemExit(f"assemble_and_sign_mandates_tool missing {key}")

  constraints = check_constraints_against_mandate(
      price=0,
      currency="USD",
      available=True,
      tool_context=ctx,
  )
  if "error" in constraints:
    raise SystemExit(f"check_constraints_against_mandate failed: {constraints}")
  if "line_items" not in constraints:
    raise SystemExit(
        "check_constraints_against_mandate(price=0) missing line_items"
    )
  print("OK  mandate HNP chain: assemble_and_sign → check_constraints(price=0)")


def check_assemble_idempotency() -> None:
  """Second assemble_and_sign in same session must not mint new open mandates."""
  from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool

  ctx = _ToolContext(
      _State({"ap2:payment_method": "card", "ap2:presence_mode": "hnp"})
  )
  req = json.dumps(
      {
          "item_id": "verify_idempotent_item_0",
          "item_name": "Idempotent Item",
          "price_cap": 100,
          "qty": 1,
      }
  )
  first = assemble_and_sign_mandates_tool(req, ctx)
  second = assemble_and_sign_mandates_tool(req, ctx)
  if "error" in first or "error" in second:
    raise SystemExit(f"idempotency check failed: first={first} second={second}")
  if first["open_checkout_mandate"] != second["open_checkout_mandate"]:
    raise SystemExit("second assemble_and_sign minted a new open checkout mandate")
  if first["open_payment_mandate"] != second["open_payment_mandate"]:
    raise SystemExit("second assemble_and_sign minted a new open payment mandate")
  if second.get("status") != "already_signed":
    raise SystemExit(f"expected status=already_signed, got {second}")
  print("OK  assemble_and_sign idempotent within session")


def check_assemble_reresign_on_payment_switch() -> None:
  """Payment rail change must mint new open mandates, not reuse idempotent skip."""
  from shopping_agent.mandate_bridge import assemble_and_sign_mandates_tool

  ctx = _ToolContext(
      _State({"ap2:payment_method": "card", "ap2:presence_mode": "hnp"})
  )
  req = json.dumps(
      {
          "item_id": "verify_switch_item_0",
          "item_name": "Switch Item",
          "price_cap": 100,
          "qty": 1,
      }
  )
  card_signed = assemble_and_sign_mandates_tool(req, ctx)
  if "error" in card_signed:
    raise SystemExit(f"card assemble failed: {card_signed}")

  ctx.state["ap2:payment_method"] = "x402"
  ctx.state.pop("app:open_checkout_mandate_id", None)
  ctx.state.pop("app:open_payment_mandate_id", None)
  ctx.state.pop("app:open_checkout_hash", None)
  ctx.state.pop("app:signed_payment_method", None)

  x402_signed = assemble_and_sign_mandates_tool(req, ctx)
  if "error" in x402_signed:
    raise SystemExit(f"x402 assemble failed: {x402_signed}")
  if x402_signed.get("status") == "already_signed":
    raise SystemExit("payment switch must not hit already_signed idempotency")
  if card_signed["open_checkout_mandate"] == x402_signed["open_checkout_mandate"]:
    raise SystemExit("payment switch reused open checkout mandate id")
  if card_signed["open_payment_mandate"] == x402_signed["open_payment_mandate"]:
    raise SystemExit("payment switch reused open payment mandate id")
  if ctx.state.get("app:signed_payment_method") != "x402":
    raise SystemExit("signed_payment_method not updated after x402 assemble")
  print("OK  assemble_and_sign re-signs when payment rail changes")


def check_clear_open_preserves_closed() -> None:
  """Payment switch must drop only open_chk_/open_pay_, not closed chk_/pay_."""
  from shopping_agent.agent import clear_open_mandate_session

  _TEMP_DB.mkdir(parents=True, exist_ok=True)
  closed_chk = _TEMP_DB / "chk_closed_history.sdjwt"
  closed_pay = _TEMP_DB / "pay_closed_history.sdjwt"
  open_chk = _TEMP_DB / "open_chk_stale.sdjwt"
  open_pay = _TEMP_DB / "open_pay_stale.sdjwt"
  for path in (closed_chk, closed_pay, open_chk, open_pay):
    path.write_text("fake-sdjwt", encoding="ascii")

  ctx = _ToolContext(
      _State({
          "app:open_checkout_mandate_id": "open_chk_stale",
          "app:open_payment_mandate_id": "open_pay_stale",
          "app:open_checkout_hash": "hash123",
          "app:signed_payment_method": "card",
      })
  )
  result = clear_open_mandate_session(ctx)
  if result.get("removed_open_mandate_files") != 2:
    raise SystemExit(
        f"expected 2 open files removed, got {result.get('removed_open_mandate_files')}"
    )
  if not closed_chk.is_file() or not closed_pay.is_file():
    raise SystemExit("closed mandate files must be preserved")
  if open_chk.is_file() or open_pay.is_file():
    raise SystemExit("stale open mandate files must be deleted")
  if ctx.state.get("app:open_checkout_mandate_id"):
    raise SystemExit("open session keys must be cleared")
  print("OK  clear_open_mandate_session preserves closed mandate history")


def check_normalize_price_cap_from_constraints() -> None:
  """mandate_request with only constraints.price_lt must assemble."""
  from shopping_agent import mandate_bridge

  normalize_mandate_request = mandate_bridge._mt_module.normalize_mandate_request
  assemble_and_sign_mandates_tool = mandate_bridge.assemble_and_sign_mandates_tool

  req = normalize_mandate_request({
      "item_id": "verify_price_lt_item_0",
      "constraints": {"price_lt": 175},
      "qty": 1,
  })
  if req.get("price_cap") != 175.0:
    raise SystemExit(f"expected price_cap=175, got {req.get('price_cap')}")

  ctx = _ToolContext(
      _State({"ap2:payment_method": "card", "ap2:presence_mode": "hnp"})
  )
  signed = assemble_and_sign_mandates_tool(json.dumps(req), ctx)
  if "error" in signed:
    raise SystemExit(
        f"assemble with constraints.price_lt only failed: {signed}"
    )
  print("OK  normalize price_cap from constraints.price_lt")


def check_payment_method_switch() -> None:
  from shopping_agent import mandate_bridge

  mandate_bridge._sync_flow_from_context(
      _ToolContext(_State({"ap2:payment_method": "x402"}))
  )
  if mandate_bridge._mt_module._PAYMENT_METHOD != "x402":
    raise SystemExit("payment method sync failed for x402")
  mandate_bridge._sync_flow_from_context(
      _ToolContext(_State({"ap2:payment_method": "card"}))
  )
  if mandate_bridge._mt_module._PAYMENT_METHOD != "card":
    raise SystemExit("payment method sync failed for card")
  print("OK  runtime payment_method sync (card / x402)")


def check_prompt_render_for_profiles() -> None:
  """All prompt templates must render without leftover {{TOKEN}} placeholders."""
  from shopping_agent import merchant_profile

  prompts_dir = _AGENT_DIR / "shopping_agent" / "prompts"
  prompt_files = [
      "consent_unified.md",
      "purchase_hp.md",
      "purchase_hnp.md",
      "monitoring_unified.md",
  ]

  for merchant_key, expected_currency in (("shoe", "USD"), ("flight", "USD")):
    os.environ["UNIFIED_MERCHANT"] = merchant_key
    profile = merchant_profile.get_merchant_profile(merchant_key)
    if profile.currency != expected_currency:
      raise SystemExit(
          f"{merchant_key}: expected currency {expected_currency}, got {profile.currency}"
      )
    for filename in prompt_files:
      template = (prompts_dir / filename).read_text(encoding="utf-8")
      rendered = profile.render_prompt(template)
      if "{{" in rendered:
        raise SystemExit(
            f"{merchant_key}/{filename}: unresolved template token in rendered prompt"
        )
    # purchase_hp must contain profile-specific examples
    hp = profile.render_prompt((prompts_dir / "purchase_hp.md").read_text())
    if profile.example_item_name not in hp:
      raise SystemExit(
          f"{merchant_key}/purchase_hp.md: missing example_item_name in rendered output"
      )
    if f'"currency":"{expected_currency}"' not in hp:
      raise SystemExit(
          f"{merchant_key}/purchase_hp.md: missing currency {expected_currency} in artifact example"
      )
    if merchant_key == "flight" and "8091" in hp:
      raise SystemExit("flight/purchase_hp.md must not contain port 8091")
    if merchant_key == "shoe" and "8091" not in hp:
      raise SystemExit("shoe/purchase_hp.md must retain port 8091 OOS section")

  os.environ.pop("UNIFIED_MERCHANT", None)
  print("OK  prompt templates render for shoe + flight profiles")


def check_flight_merchant_override() -> None:
  """Flight profile must override mandate merchant + currency."""
  os.environ["UNIFIED_MERCHANT"] = "flight"
  from shopping_agent import merchant_profile

  merchant_profile.set_active_merchant_key("flight")
  profile = merchant_profile.get_merchant_profile("flight")
  if profile.key != "flight":
    raise SystemExit(f"expected flight profile, got {profile.key}")
  merchant_profile.apply_mandate_overrides(profile)

  from shopping_agent import mandate_bridge
  import shopping_agent.mandate_tools_hp as mandate_tools_hp

  if mandate_bridge._mt_module.DEMO_MERCHANT.id != "heg-flight-mock":
    raise SystemExit("flight DEMO_MERCHANT not applied to mandate bridge")
  if mandate_bridge._mt_module._DEFAULT_CURRENCY != "USD":
    raise SystemExit("flight currency not applied to mandate bridge")
  if mandate_tools_hp.DEFAULT_CURRENCY != "USD":
    raise SystemExit("flight currency not applied to mandate_tools_hp")
  print("OK  flight merchant profile overrides (heg-flight-mock / USD)")


def check_session_id_filename_roundtrip() -> None:
  """Session files encode ``@`` as ``_``; scheduler must decode on scan."""
  from buyer_mcp_unified.session_store import (
      _session_path,
      session_id_from_filename,
  )

  sid = "smoke_uuid@im.wechat"
  path = _session_path(sid)
  decoded = session_id_from_filename(path.stem)
  if decoded != sid:
    raise SystemExit(
        f"session_id roundtrip failed: {sid!r} -> {path.name!r} -> {decoded!r}"
    )
  print("OK  session_id filename roundtrip (@im.wechat)")


def main() -> None:
  os.chdir(_AGENT_DIR)
  check_adk_schemas()
  check_payment_method_switch()
  check_matches_true_coercion()
  check_normalize_price_cap_from_constraints()
  check_mandate_hnp_chain()
  check_assemble_idempotency()
  check_assemble_reresign_on_payment_switch()
  check_clear_open_preserves_closed()
  check_session_id_filename_roundtrip()
  check_prompt_render_for_profiles()
  check_flight_merchant_override()
  print("All unified tool checks passed.")


if __name__ == "__main__":
  main()
