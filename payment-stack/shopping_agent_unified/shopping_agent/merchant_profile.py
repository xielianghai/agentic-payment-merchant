"""Merchant profile for unified demo (shoe vs Singapore Airlines flight)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ap2.sdk.generated.types.merchant import Merchant

_ROLES_DIR = Path(__file__).resolve().parents[2]
_UNIFIED_SCENARIO = _ROLES_DIR
if str(_ROLES_DIR) not in __import__("sys").path:
  __import__("sys").path.insert(0, str(_ROLES_DIR))
from path_setup import resolve_heg_mcp_server  # noqa: E402

_DEFAULT_HEG_MCP = resolve_heg_mcp_server()

_SHOE_OOS_SECTION = """## Out of stock (demo trigger)
New drop products start with **stock 0**. They become available only after the user runs the trigger curl. When **search_inventory** or **check_product** shows unavailable / stock 0:

1. Use the exact **`item_id`** and **price** from tool results (`matches[0].item_id`, `matches[0].price`) — never invent a shorter id.
2. End your message with **`inventory_options`** JSON (copy exact fields from search `matches[0]`, including `available` and `stock`):
   `{"type":"inventory_options","matches":[{"item_id":"...","name":"...","price":299,"stock":0,"available":false}]}`
3. Include the **complete copy-paste curl** in a fenced code block (required — developers run this in terminal):

```
curl -X POST "http://localhost:8091/trigger-price-drop?item_id=ITEM_ID&price=PRICE&stock=10"
```

Replace `ITEM_ID` and `PRICE` with real values from search (price in dollars, e.g. `299`).

4. Tell the user: run the curl, then say **buy now** again (or you will re-check availability).

When the user asks **how to simulate a drop**, repeat the **same full curl line** with the real `item_id` / price from the conversation — do not describe a generic API.

**Never** mention `POST /trigger/drop`, JSON request bodies, port **8081**, or other invented endpoints — unified demo trigger is **8091** only.

## After user ran trigger curl
If the user says they dropped / stock is live / **go ahead** / **buy now** again:

1. **Do NOT** call **search_inventory** again if you already have `item_id` from the prior turn.
2. Call **check_product** with that exact `item_id`.
3. If `available: true` → continue HP workflow below.
4. If still unavailable, repeat the curl on port **8091** with the exact `item_id` from tool results.

If the user message includes `hp_drop_ready` with `item_id`, call **check_product** immediately and continue checkout when available."""

_FLIGHT_OOS_SECTION = """## Availability (flights)
Flights are **available** when seats exist — no trigger server and no out-of-stock simulation.
- Never emit **`inventory_options`** or out-of-stock messaging.
- Never show a trigger-price-drop curl or reference the shoe demo drop trigger.
- If **check_product** returns `available: true`, proceed directly to the HP workflow below.
- If no seats, tell the user and suggest another date or route — do not wait for a trigger.

## HNP (delegated flight booking)
HNP for flights means: **buy automatically when current price ≤ user's budget (`price_cap`)**.
- The user signs an Open Mandate with a **price ceiling** (e.g. USD 600), not a separate admin "ticket issuance" step.
- **monitoring_agent** polls **check_product** → **check_constraints_against_mandate**; when `meets_constraints` is true and seats exist, emit a **monitoring** artifact and stop — **backend scheduler (:8105) executes purchase**, do not transfer to purchase_hnp_agent.
- Do **not** ask the user to "issue tickets" in the admin console — checkout uses the normal HEG presale flow (`assemble_cart` → pay) same as HP.
- If current price is already ≤ budget, monitoring may succeed on the first check and purchase immediately."""


@dataclass(frozen=True)
class MerchantProfile:
  key: str
  display_name: str
  currency: str
  merchant: Merchant
  mcp_server: Path
  heg_backend_url: str | None
  instruction_preamble: str
  default_starter: str
  hnp_starter: str
  hp_starter: str
  trigger_port: int | None
  skip_trigger: bool
  example_item_name: str
  example_total_cents: int
  oos_section: str
  hnp_oos_hint: str

  def render_prompt(self, template: str) -> str:
    """Substitute {{TOKEN}} placeholders (not str.format — prompts contain JSON braces)."""
    text = template
    replacements = {
        "{{CURRENCY}}": self.currency,
        "{{EXAMPLE_ITEM_NAME}}": self.example_item_name,
        "{{EXAMPLE_TOTAL_CENTS}}": str(self.example_total_cents),
        "{{OOS_SECTION}}": self.oos_section,
        "{{HNP_OOS_HINT}}": self.hnp_oos_hint,
    }
    for token, value in replacements.items():
      text = text.replace(token, value)
    return text


SHOE_PROFILE = MerchantProfile(
    key="shoe",
    display_name="Demo Merchant (SuperShoe)",
    currency="USD",
    merchant=Merchant(
        id="merchant_1",
        name="Demo Merchant",
        website="https://demo-merchant.example",
    ),
    mcp_server=_ROLES_DIR / "merchant_unified" / "server.py",
    heg_backend_url=None,
    instruction_preamble=(
        "## Merchant profile: SuperShoe (physical goods)\n"
        "Currency: **USD**. Drop items start out of stock; trigger on port 8091 "
        "sets live price and stock."
    ),
    default_starter=(
        "When is the SuperShoe limited edition Gold sneaker drop? "
        "I need size 9 women's."
    ),
    hnp_starter=(
        "When is the SuperShoe limited edition Gold sneaker drop? "
        "I need size 9 women's, budget $200."
    ),
    hp_starter=(
        "Buy SuperShoe Gold size 9 women's in stock today — purchase now with card."
    ),
    trigger_port=8091,
    skip_trigger=False,
    example_item_name="SuperShoe Gold Womens 9",
    example_total_cents=1070,
    oos_section=_SHOE_OOS_SECTION,
    hnp_oos_hint=(
        "If inventory is **out of stock** (demo), the purchase agent must show the "
        "**full** `trigger-price-drop` curl (see purchase_hp prompt) — never a generic "
        "`POST /trigger/drop` JSON API."
    ),
)

FLIGHT_PROFILE = MerchantProfile(
    key="flight",
    display_name="Singapore Airlines (HEG Flight Mock)",
    currency="USD",
    merchant=Merchant(
        id="heg-flight-mock",
        name="HEG Flight Mock",
        website="https://heg-flight-mock.example",
    ),
    mcp_server=_DEFAULT_HEG_MCP,
    heg_backend_url=os.environ.get("HEG_FLIGHT_BACKEND_URL", "http://localhost:9000"),
    instruction_preamble=(
        "## Merchant profile: Singapore Airlines flights (HEG Flight Mock)\n"
        "Currency: **USD**. Use IATA codes + date in search; no trigger server."
    ),
    default_starter=(
        "Find Singapore Airlines flights from SIN to PVG economy on July 21 "
        "for 1 adult."
    ),
    hnp_starter=(
        "Book Singapore Airlines SIN to PVG economy July 21 for 1 adult — "
        "budget USD 600, buy for me when price is acceptable."
    ),
    hp_starter=(
        "Buy Singapore Airlines SIN to PVG economy July 21 for 1 adult now with card."
    ),
    trigger_port=None,
    skip_trigger=True,
    example_item_name="SQ830 SIN to PVG 2026-07-21",
    example_total_cents=130,
    oos_section=_FLIGHT_OOS_SECTION,
    hnp_oos_hint=(
        "HNP flights: user sets a **budget / price_cap**; monitoring buys when "
        "**current_price ≤ price_cap** and seats exist. No shoe trigger curl and "
        "no separate admin ticket-issuance step — presale runs at assemble_cart."
    ),
)


PROFILE_BY_KEY: dict[str, MerchantProfile] = {
    "shoe": SHOE_PROFILE,
    "flight": FLIGHT_PROFILE,
}

MERCHANT_NEUTRAL_PREAMBLE = (
    "## Active merchant — READ FIRST, EVERY TURN\n"
    "This shopping agent serves TWO merchants. The active one is given in each "
    "user message JSON as a top-level **`merchant`** field (`\"shoe\"` or "
    "`\"flight\"`), and authoritatively by **get_ap2_session_config** "
    "(`merchant`, `merchant_display_name`, `currency`, `merchant_instruction`).\n\n"
    "- **`merchant: \"flight\"`** → You ARE the **Singapore Airlines flight "
    "booking agent** (currency **USD**). You search and book flights. It is "
    "fully supported. **Never** say you only sell shoes or that you cannot book "
    "flights.\n"
    "- **`merchant: \"shoe\"`** → You ARE the **SuperShoe** store agent "
    "(currency **USD**) for limited drops and immediate purchases.\n\n"
    "ALWAYS adopt the active merchant's identity and never mention the other "
    "merchant unless the user asks to switch. A request that matches the active "
    "merchant's domain (flights when `merchant=flight`; sneakers/products when "
    "`merchant=shoe`) is always a **MATCH** — proceed; never refuse it.\n\n"
    "When the active merchant is **flight**: there is no out-of-stock trigger, "
    "no price-drop curl, and no `inventory_options`/`product_preview_unavailable` "
    "shoe messaging — flights are available when seats exist.\n\n"
    "Follow **merchant_instruction** from get_ap2_session_config for currency, "
    "availability rules, and examples. If unsure which merchant is active, call "
    "**get_ap2_session_config** before answering what you can do.\n\n"
    "User-visible responses must not narrate internal reasoning or tool plans. "
    "Do not say things like \"I need to call...\", \"let me emit...\", or "
    "\"now I need to...\". Just provide the customer-facing result and put any "
    "required JSON artifact as the final block."
)


def _selection_file() -> Path:
  temp_db = Path(os.environ.get("TEMP_DB_DIR", _UNIFIED_SCENARIO / ".temp-db"))
  return temp_db / "unified_merchant.json"


def normalize_merchant_key(key: str) -> str:
  normalized = key.strip().lower()
  if normalized in {"flight", "heg", "sq", "singapore_airlines"}:
    return "flight"
  return "shoe"


def get_active_merchant_key() -> str:
  """Active merchant for MCP router (session file, then env default)."""
  try:
    path = _selection_file()
    if path.is_file():
      data = json.loads(path.read_text(encoding="utf-8"))
      if isinstance(data, dict) and data.get("merchant"):
        return normalize_merchant_key(str(data["merchant"]))
  except (OSError, json.JSONDecodeError, TypeError):
    pass
  return normalize_merchant_key(os.environ.get("UNIFIED_MERCHANT", "shoe"))


def set_active_merchant_key(key: str) -> str:
  """Persist merchant selection for the MCP router subprocess."""
  normalized = normalize_merchant_key(key)
  path = _selection_file()
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(
      json.dumps({"merchant": normalized}, ensure_ascii=True),
      encoding="utf-8",
  )
  return normalized


def get_merchant_profile(key: str | None = None) -> MerchantProfile:
  resolved = normalize_merchant_key(key or get_active_merchant_key())
  return PROFILE_BY_KEY[resolved]


def merchant_instruction_block(profile: MerchantProfile) -> str:
  """Runtime merchant rules returned from get_ap2_session_config."""
  return (
      f"{profile.instruction_preamble}\n\n"
      f"Currency: **{profile.currency}**. "
      f"Example item: {profile.example_item_name} "
      f"(example total minor units: {profile.example_total_cents}).\n\n"
      f"{profile.oos_section}"
  )


def apply_mandate_overrides(profile: MerchantProfile) -> None:
  """Point v2 mandate tools at the active merchant + currency."""
  from shopping_agent import mandate_bridge
  import shopping_agent.mandate_tools_hp as mandate_tools_hp

  mandate_bridge._mt_module.DEMO_MERCHANT = profile.merchant
  mandate_bridge._mt_module._DEFAULT_CURRENCY = profile.currency
  mandate_tools_hp.DEMO_MERCHANT = profile.merchant
  mandate_tools_hp.DEFAULT_CURRENCY = profile.currency
