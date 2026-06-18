// Vite proxy forwards /a2a → unified agent (8090)
export const AGENT_URL =
  (import.meta as { env?: { VITE_AGENT_URL?: string } }).env?.VITE_AGENT_URL ??
  "/a2a/shopping_agent";

export const MERCHANT_TRIGGER_URL =
  (import.meta as { env?: { VITE_MERCHANT_TRIGGER_URL?: string } }).env
    ?.VITE_MERCHANT_TRIGGER_URL ?? "http://localhost:8091";

export type MerchantKey = "shoe" | "flight";

const ENV_MERCHANT_PROFILE =
  (import.meta as { env?: { VITE_MERCHANT_PROFILE?: string } }).env
    ?.VITE_MERCHANT_PROFILE ?? "shoe";

export function normalizeMerchantKey(value: string): MerchantKey {
  const key = value.trim().toLowerCase();
  if (key === "flight" || key === "heg" || key === "sq") {
    return "flight";
  }
  return "shoe";
}

export const DEFAULT_MERCHANT: MerchantKey = normalizeMerchantKey(
  ENV_MERCHANT_PROFILE,
);

export function isFlightMerchant(merchant: MerchantKey): boolean {
  return merchant === "flight";
}

/**
 * Deterministically infer the merchant from a user message so a clear request
 * (e.g. "book a flight", "buy SuperShoe sneakers") skips the conversational
 * "auto" selection round-trip and goes straight into the purchase flow.
 *
 * Returns null when the message is ambiguous or mentions both domains — in that
 * case we keep sending "auto" and let the agent ask which merchant to use.
 */
export function inferMerchantFromText(text: string): MerchantKey | null {
  const t = ` ${text.toLowerCase()} `;
  const flight =
    /\b(flight|flights|fly|flying|airline|airlines|airfare|airport|ticket|tickets|singapore airlines|economy|business class|first class|departure|round[- ]?trip|one[- ]?way|sin|pvg|iata)\b/.test(
      t,
    ) || /\bsq\s?\d/.test(t);
  const shoe =
    /\b(sneaker|sneakers|shoe|shoes|supershoe|super shoe|kicks|footwear|sneaker drop)\b/.test(
      t,
    );
  if (flight && !shoe) return "flight";
  if (shoe && !flight) return "shoe";
  return null;
}

/** Selectable merchants for the conversational picker (cards). */
export const MERCHANT_OPTIONS: ReadonlyArray<{
  key: MerchantKey;
  label: string;
  icon: string;
  tagline: string;
}> = [
  {
    key: "shoe",
    label: "SuperShoe",
    icon: "🛒",
    tagline: "Limited sneaker drops + buy now (HP / HNP, card / x402)",
  },
  {
    key: "flight",
    label: "Singapore Airlines",
    icon: "✈️",
    tagline: "Search + book flights (HP / HNP, card / x402)",
  },
] as const;

/** Greeting shown above the merchant cards before a merchant is chosen. */
export const MERCHANT_PICKER_GREETING =
  "Hi! I'm your AP2 shopping agent. Which merchant would you like to shop with? Pick one below, or just tell me what you want (e.g. \"buy SuperShoe sneakers\" or \"book a flight\").";

/** @deprecated Use isFlightMerchant(merchant) with runtime merchant state. */
export const IS_FLIGHT = isFlightMerchant(DEFAULT_MERCHANT);

export function defaultCurrencyFor(_merchant: MerchantKey): string {
  return "USD";
}

/** @deprecated Use defaultCurrencyFor(merchant). */
export const DEFAULT_CURRENCY = defaultCurrencyFor(DEFAULT_MERCHANT);

/** Format a major-unit amount with profile currency (no hardcoded $). */
export function formatMoney(
  amount: number,
  currency?: string,
  merchant: MerchantKey = DEFAULT_MERCHANT,
): string {
  const cur = currency ?? defaultCurrencyFor(merchant);
  return `${cur} ${amount.toFixed(2)}`;
}

/** Format minor units (cents) with profile currency. */
export function formatMoneyMinor(
  minorUnits: number,
  currency?: string,
  merchant: MerchantKey = DEFAULT_MERCHANT,
): string {
  return formatMoney(minorUnits / 100, currency, merchant);
}

export function defaultChatStarterMessage(merchant: MerchantKey): string {
  return isFlightMerchant(merchant)
    ? "Find Singapore Airlines flights from SIN to PVG economy on July 21 for 1 adult."
    : 'When is the SuperShoe limited edition Gold sneaker drop? I need size 9 women\'s.';
}

/** @deprecated Use defaultChatStarterMessage(merchant). */
export const DEFAULT_CHAT_STARTER_MESSAGE = defaultChatStarterMessage(
  DEFAULT_MERCHANT,
);

export function getScenarioStarterHints(merchant: MerchantKey) {
  const flight = isFlightMerchant(merchant);
  return {
    hnp: {
      tag: "HNP",
      title: flight ? "Delegated flight booking" : "Timed drop (Human Not Present)",
      flow: flight
        ? "search → Approve & Sign → monitoring → autonomous purchase when price ≤ budget"
        : "product preview → Approve & Sign → monitoring → autonomous purchase",
      example: flight
        ? "Book Singapore Airlines SIN to PVG economy July 21 for 1 adult — budget USD 600."
        : 'When is the SuperShoe limited edition Gold sneaker drop? I need size 9 women\'s, budget $200.',
      accent: "hnp" as const,
    },
    hp: {
      tag: "HP",
      title: flight ? "Book flight now" : "Buy now (Human Present)",
      flow: flight
        ? "search → checkout → Confirm & pay → ticket issued"
        : "search → checkout → Confirm & pay → pay at checkout",
      example: flight
        ? "Buy Singapore Airlines SIN to PVG economy July 21 for 1 adult now with card."
        : 'Buy SuperShoe Gold size 9 women\'s in stock today — purchase now with card.',
      accent: "hp" as const,
    },
    payment: flight
      ? "Payment: say card or x402 / crypto in chat. Prices are in USD. After switching payment rails, Approve & Sign again."
      : "Payment: say card (credit card) or x402 / crypto (on-chain USDC) in chat. After switching payment rails, Approve & Sign again.",
  } as const;
}

/** @deprecated Use getScenarioStarterHints(merchant). */
export const SCENARIO_STARTER_HINTS = getScenarioStarterHints(DEFAULT_MERCHANT);

/** Demo page copy for the active merchant profile. */
export function getMerchantDemo(merchant: MerchantKey) {
  const flight = isFlightMerchant(merchant);
  return {
    label: flight
      ? "Singapore Airlines · HEG Flight Mock"
      : "SuperShoe · Demo Merchant",
    icon: flight ? "✈️" : "🛒",
    autoSubtitle: flight
      ? "Book Singapore Airlines flights — try an example below (HP buy now or HNP delegate with budget). The agent infers HP / HNP and card / x402 from your message."
      : "Unified scenario: start with an example below. The agent will infer HP / HNP and card / x402 and configure the flow.",
    fixedHpSubtitle: flight
      ? "Human Present: search flights → checkout → confirm & pay → ticket issued"
      : "Human Present: search → checkout → confirm & pay",
    fixedHnpSubtitle: flight
      ? "Human Not Present: search → mandate → monitoring → autonomous booking when price ≤ budget"
      : "Human Not Present: product preview → mandate → monitoring → autonomous purchase",
    inputPlaceholder: flight
      ? "e.g. Buy Singapore Airlines SIN to PVG economy July 21 for 1 adult now with card."
      : "e.g. When is the SuperShoe limited edition Gold sneaker drop? I need size 9 women's.",
    enterKeySuffix: flight
      ? " to start (defaults to Singapore Airlines flight search)"
      : " to start (defaults to HNP drop demo)",
  } as const;
}

/** @deprecated Use getMerchantDemo(merchant). */
export const MERCHANT_DEMO = getMerchantDemo(DEFAULT_MERCHANT);
