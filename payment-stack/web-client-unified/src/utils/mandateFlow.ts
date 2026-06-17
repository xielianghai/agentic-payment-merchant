import type {
  ChatMessage,
  InventoryOptionsArtifact,
  MandateRequest,
  ToolCallArtifact,
} from '../types';

function parseMandatePayload(
    raw: unknown,
    ): Record<string, unknown>|undefined {
  if (raw == null) return undefined;
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return typeof parsed === 'object' && parsed && !Array.isArray(parsed) ?
          parsed as Record<string, unknown> :
          undefined;
    } catch {
      return undefined;
    }
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return undefined;
}

/** Normalize agent / tool payloads into a mandate_request artifact. */
export function normalizeMandateRequestPayload(
    raw: Record<string, unknown>,
    ): MandateRequest|undefined {
  const item_id = String(raw.item_id ?? '').trim();
  if (!item_id) return undefined;

  const constraints =
      typeof raw.constraints === 'object' && raw.constraints ?
          raw.constraints as {price_lt?: number; price_cap?: number} :
          undefined;

  let price_cap: number|undefined;
  if (typeof raw.price_cap === 'number' && raw.price_cap > 0) {
    price_cap = raw.price_cap;
  } else if (constraints?.price_lt != null && constraints.price_lt > 0) {
    price_cap = constraints.price_lt;
  } else if (constraints?.price_cap != null && constraints.price_cap > 0) {
    price_cap = constraints.price_cap;
  }
  if (price_cap == null) return undefined;

  const current_price =
      typeof raw.current_price === 'number' ? raw.current_price :
      undefined;

  const payment_method =
      raw.payment_method === 'x402' ? 'x402' :
      raw.payment_method === 'card' ? 'card' :
      undefined;

  const matches = Array.isArray(raw.matches) ?
      raw.matches
          .filter((m): m is {item_id: string; name: string; price: number} =>
              typeof m === 'object' && m != null &&
              typeof (m as {item_id?: unknown}).item_id === 'string' &&
              typeof (m as {name?: unknown}).name === 'string' &&
              typeof (m as {price?: unknown}).price === 'number',
          )
          .map((m) => ({
            item_id: m.item_id,
            name: m.name,
            price: m.price,
          })) :
      undefined;

  return {
    type: 'mandate_request',
    item_id,
    item_name: typeof raw.item_name === 'string' ? raw.item_name : undefined,
    price_cap,
    qty: typeof raw.qty === 'number' ? raw.qty : undefined,
    constraint_focus:
        raw.constraint_focus === 'availability' ? 'availability' :
        raw.constraint_focus === 'price' ? 'price' :
        undefined,
    available: typeof raw.available === 'boolean' ? raw.available : undefined,
    constraints: constraints?.price_lt != null ?
        {price_lt: constraints.price_lt} :
        {price_lt: price_cap},
    instructions:
        typeof raw.instructions === 'string' ? raw.instructions : undefined,
    matches,
    current_price,
    payment_method,
    payment_method_description:
        typeof raw.payment_method_description === 'string' ?
            raw.payment_method_description :
            undefined,
  };
}

/** Stable key for a mandate the user must sign (budget + payment rail). */
export function mandateRequestKey(mandate: MandateRequest): string {
  const payment = mandate.payment_method === 'x402' ? 'x402' : 'card';
  const cap =
      mandate.price_cap ??
      mandate.constraints?.price_lt ??
      0;
  return `${cap}:${payment}`;
}

export function mandateFromAssembleToolArgs(
    args: Record<string, unknown>|undefined,
    ): MandateRequest|undefined {
  if (!args) return undefined;
  const payload = parseMandatePayload(args.mandate_request);
  if (!payload) return undefined;
  return normalizeMandateRequestPayload(payload);
}

function prosePrice(text: string, label: string): number|undefined {
  const re = new RegExp(
      `${label}[^|$\\d]*\\*{0,2}\\s*\\$?([\\d]+(?:\\.[\\d]+)?)`,
      'i',
  );
  const m = text.match(re);
  return m ? Number(m[1]) : undefined;
}

/** Match ``$100 budget`` / ``USD 100 budget`` where the amount precedes the label. */
function prosePriceBefore(text: string, label: string): number|undefined {
  const re = new RegExp(
      `(?:usd|us\\$)?\\s*\\$?([\\d]+(?:\\.[\\d]+)?)\\s*[^|$\\n]{0,24}?\\*{0,2}${label}\\b`,
      'i',
  );
  const m = text.match(re);
  return m ? Number(m[1]) : undefined;
}

/** Best-effort budget/price-cap extraction from prose (both word orders). */
export function extractBudgetFromText(text: string): number|undefined {
  return (
      prosePriceBefore(text, 'budget') ??
      prosePrice(text, 'budget') ??
      prosePriceBefore(text, 'price\\s*cap') ??
      prosePrice(text, 'price\\s*cap') ??
      prosePrice(text, 'ceiling')
  );
}

/** Latest explicit budget the user stated in chat (e.g. "budget USD 100"). */
export function extractBudgetFromThread(
    messages: ChatMessage[],
    ): number|undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role !== 'user') continue;
    const text = messages[i].text ?? '';
    const fromProse = extractBudgetFromText(text);
    if (fromProse != null && fromProse > 0) return fromProse;
  }
  return undefined;
}

/**
 * Fix agent slips such as using the travel day (June 10 → price_cap 10) instead
 * of the user's stated budget ($100).
 */
export function reconcileMandateBudget(
    mandate: MandateRequest,
    messages: ChatMessage[],
    agentText?: string,
    ): MandateRequest {
  const cap =
      mandate.price_cap ??
      mandate.constraints?.price_lt ??
      (mandate.constraints as {price_cap?: number}|undefined)?.price_cap;
  if (cap == null || cap <= 0) return mandate;

  const threadBudget = extractBudgetFromThread(messages);
  const proseBudget = agentText ? extractBudgetFromText(agentText) : undefined;
  const stated = Math.max(threadBudget ?? 0, proseBudget ?? 0);
  if (stated <= 0 || stated <= cap) return mandate;

  // Day-of-month confusion: cap is 1–31 while user clearly asked for more.
  const looksLikeDateConfusion = cap <= 31 && stated >= 50;
  const looksLikeTruncatedBudget = stated >= cap * 5;
  if (!looksLikeDateConfusion && !looksLikeTruncatedBudget) return mandate;

  return {
    ...mandate,
    price_cap: stated,
    constraints: {price_lt: stated},
  };
}

export function resolveItemIdFromThread(
    messages: ChatMessage[],
    text?: string,
    inventory?: InventoryOptionsArtifact,
    ): string|undefined {
  if (inventory?.selected) return inventory.selected;
  const invMatch = inventory?.matches?.[0]?.item_id;
  if (invMatch) return invMatch;

  for (let i = messages.length - 1; i >= 0; i--) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (!data?.type) continue;
    if (data.type === 'mandate_request') {
      return (data as MandateRequest).item_id;
    }
    if (data.type === 'monitoring') {
      return (data as {item_id?: string}).item_id;
    }
    if (data.type === 'inventory_options') {
      const inv = data as InventoryOptionsArtifact;
      return inv.selected ?? inv.matches[0]?.item_id;
    }
    if (data.type === 'tool_call') {
      const tc = data as ToolCallArtifact;
      const fromAssemble = mandateFromAssembleToolArgs(tc.args)?.item_id;
      if (fromAssemble) return fromAssemble;
      const argId = tc.args?.item_id;
      if (typeof argId === 'string' && argId) return argId;
    }
  }

  if (text) {
    const curlParam = text.match(/[?&]item_id=([a-z0-9_]+)/i);
    if (curlParam?.[1]) return curlParam[1];
    const labeled = text.match(/\bitem[_\s-]?id[:\s]+['"]?([a-z0-9_]+)/i);
    if (labeled?.[1]) return labeled[1];
  }
  return undefined;
}

/**
 * Fallback when the agent describes a mandate in prose/markdown instead of
 * emitting mandate_request JSON (common LLM slip).
 */
export function extractMandateFromProseTable(
    text: string,
    context: {
      messages: ChatMessage[];
      inventory?: InventoryOptionsArtifact;
      paymentMethod?: 'card'|'x402';
      paymentDescription?: string;
    },
    ): MandateRequest|undefined {
  const lower = text.toLowerCase();
  if (
      !lower.includes('mandate') &&
      !lower.includes('price cap') &&
      !lower.includes('approve') &&
      !lower.includes('trusted surface')
  ) {
    return undefined;
  }

  const price_cap =
      extractBudgetFromText(text) ??
      prosePrice(text, 'price\\s*cap') ??
      prosePrice(text, 'budget') ??
      prosePrice(text, 'ceiling');
  const current_price =
      prosePrice(text, 'current\\s*price') ??
      prosePrice(text, 'quoted\\s*price');
  if (price_cap == null) return undefined;

  const item_id = resolveItemIdFromThread(
      context.messages,
      text,
      context.inventory,
  );
  if (!item_id) return undefined;

  let item_name: string|undefined;
  const flightRow = text.match(/\*\*Flight\*\*\s*\|\s*([^|]+)/i);
  if (flightRow?.[1]) {
    item_name = flightRow[1].replace(/\*+/g, '').trim();
  }
  const productRow = text.match(/\*\*Product\*\*\s*\|\s*([^|]+)/i);
  if (productRow?.[1]) {
    item_name = productRow[1].replace(/\*+/g, '').trim();
  }

  const cardHint = /card|•••\d{4}/i.test(text);
  const x402Hint = /x402|crypto|usdc/i.test(text);
  const payment_method =
      context.paymentMethod ??
      (x402Hint && !cardHint ? 'x402' : cardHint ? 'card' : 'card');

  return {
    type: 'mandate_request',
    item_id,
    item_name,
    price_cap,
    current_price,
    qty: 1,
    constraint_focus: 'availability',
    available: false,
    constraints: {price_lt: price_cap},
    payment_method,
    payment_method_description: context.paymentDescription,
  };
}

export function hasMandateApprovalForKey(
    messages: ChatMessage[],
    key: string,
    ): boolean {
  return messages.some(
      (m) =>
          m.role === 'user_action' &&
          m.userActionLabel === 'Approved mandate' &&
          m.mandateRequestKey === key,
  );
}

export function hasMandateApprovalInThread(
    messages: ChatMessage[],
    itemId: string,
    paymentMethod: 'card'|'x402' = 'card',
    ): boolean {
  return messages.some(
      (m) =>
          m.role === 'user_action' &&
          m.userActionLabel === 'Approved mandate' &&
          m.mandateItemId === itemId &&
          (m.mandatePaymentMethod ?? 'card') === paymentMethod,
  );
}

export function hasAnyMandateApprovalInThread(messages: ChatMessage[]): boolean {
  return messages.some(
      (m) =>
          m.role === 'user_action' &&
          m.userActionLabel === 'Approved mandate',
  );
}

export function hasMandatesSignedInThread(messages: ChatMessage[]): boolean {
  return messages.some(
      (m) =>
          (m.artifactData as {type?: string}|undefined)?.type ===
          'mandates_signed',
  );
}

/**
 * Whether the Trusted Surface should show Approve & Sign for this mandate.
 * Each distinct budget (price_cap) + payment rail requires its own approval.
 */
export function shouldPromptMandateApproval(
    messages: ChatMessage[],
    mandate: MandateRequest,
    ): boolean {
  const key = mandateRequestKey(mandate);
  if (hasMandateApprovalForKey(messages, key)) {
    return false;
  }
  return true;
}

export function isMandateAlreadyApproved(
    messages: ChatMessage[],
    mandate: MandateRequest,
    ): boolean {
  return !shouldPromptMandateApproval(messages, mandate);
}

/**
 * A mandate_request card is superseded once a *later* mandate_request with a
 * different budget/rail exists (e.g. the user switched card → x402). Approving
 * a stale card would record an approval for the wrong rail and trigger a
 * trusted_surface_approval_mismatch, so such cards must lock.
 */
export function isMandateSuperseded(
    messages: ChatMessage[],
    mandate: MandateRequest,
    cardTimestamp: number,
    ): boolean {
  const key = mandateRequestKey(mandate);
  return messages.some((m) => {
    if (m.timestamp <= cardTimestamp) return false;
    const data = m.artifactData as {type?: string}|undefined;
    if (data?.type !== 'mandate_request') return false;
    return mandateRequestKey(data as MandateRequest) !== key;
  });
}

/** Strip agent instructions that duplicate the Trusted Surface UI. */
export function stripTrustedSurfaceProseHints(text: string): string|undefined {
  const stripped = text
      .replace(
          /please\s+\*{0,2}approve\s*&\s*sign\*{0,2}[^\n.]*/gi,
          '',
      )
      .replace(/on your trusted surface[^\n.]*/gi, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  return stripped.length > 0 ? stripped : undefined;
}
