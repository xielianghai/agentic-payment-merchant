import type {A2APart, ActionChoice, ActionChoices, AgentArtifactData, ErrorArtifact, ImmediateCheckoutRequest, InventoryOptionsArtifact, MandateRequest, MerchantSelected, MonitoringStatus, Part, ProductPreviewUnavailable, PurchaseComplete, ToolCallArtifact} from '../types';
import {isInventoryOptionsArtifact, isToolCallArtifact} from '../types';

import {normalizeProductPreviewUnavailable} from './productPreviewUnavailable';

/**
 * Converts a loose A2APart object into a strict Part object.
 * This is used to normalize various incoming message part formats (text, data,
 * tool calls) into a standard structure used by the client.
 * @param p The message part to convert.
 * @returns A strict Part object, or undefined if the input is invalid or
 *     unsupported.
 */
export function convertToStrictPart(p: A2APart): Part|undefined {
  if (p.kind === 'text' && typeof p.text === 'string') {
    return {kind: 'text', text: p.text};
  }
  if (!p.kind && p.text) {
    return {kind: 'text', text: p.text};
  }
  if ((p.kind === 'data' || !p.kind) && p.data) {
    if (typeof p.data.name === 'string' && p.data.args) {
      return {
        kind: 'data',
        data: {
          ...p.data,
          name: p.data.name ?? p.name,
          args: p.data.args ?? p.data
        }
      };
    }
    return {kind: 'data', data: p.data};
  }
  if (p.name) {
    return {
      kind: 'tool_call',
      tool_call: {name: p.name, arguments: p.data ?? {}}
    };
  }
  return undefined;
}

/**
 * Extracts a JSON object from text that contains a specific type key/value
 * pair. Searches for a JSON object starting with `{"typeKey": "typeVal"`.
 * @param text The text to search.
 * @param typeKey The key to look for.
 * @param typeVal The value the key should have.
 * @returns The parsed object of type T, or undefined if not found or invalid.
 */
function extractJsonFromText(
    text: string,
    typeKey: string,
    typeVal: string,
    ): unknown {
  const match = text.match(
      new RegExp(`\\{\\s*"${typeKey}"\\s*:\\s*"${typeVal}"`),
  );
  if (!match || match.index == null) return undefined;
  const start = match.index;
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    if (text[i] === '{') {
      depth++;
    } else if (text[i] === '}') {
      depth--;
      if (depth === 0) {
        try {
          const parsed = JSON.parse(text.slice(start, i + 1));
          return parsed?.[typeKey] === typeVal ? parsed : undefined;
        } catch {
          return undefined;
        }
      }
    }
  }
  return undefined;
}

/**
 * Removes a JSON artifact from text by finding the matching type.
 */
function removeBalancedJsonFromIndex(text: string, start: number): string {
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    if (text[i] === '{') {
      depth++;
    } else if (text[i] === '}') {
      depth--;
      if (depth === 0) {
        return text.slice(0, start) + text.slice(i + 1);
      }
    }
  }
  return text;
}

/**
 * Removes a JSON artifact from text by finding the matching type.
 * Also strips surrounding ```json fences when the agent wraps the payload.
 */
export function removeArtifactJsonFromText(
    text: string,
    typeVal: string,
    ): string {
  const typePattern = `\\{\\s*"type"\\s*:\\s*"${typeVal}"`;
  const fenced = new RegExp(
      `\`\`\`(?:json)?\\s*\\n?\\s*${typePattern}[\\s\\S]*?\\}\\s*\\n?\`\`\``,
      'i',
  );
  const fencedMatch = text.match(fenced);
  if (fencedMatch && fencedMatch.index != null) {
    return (text.slice(0, fencedMatch.index) +
            text.slice(fencedMatch.index + fencedMatch[0].length))
        .replace(/\n{3,}/g, '\n\n')
        .trim();
  }

  const match = text.match(new RegExp(typePattern));
  if (!match || match.index == null) return text;
  return removeBalancedJsonFromIndex(text, match.index)
      .replace(/\n{3,}/g, '\n\n')
      .trim();
}

/**
 * Extract tool_call JSON embedded in text.
 */
function extractToolCallFromEmbeddedJson(
    text: string,
    ): ToolCallArtifact|undefined {
  const extracted = extractJsonFromText(text, 'type', 'tool_call');
  const toolCall = extracted as ToolCallArtifact | undefined;
  return toolCall?.tool && toolCall?.server ? toolCall : undefined;
}

/**
 * Searches for and returns the primary structured data payload from a list of
 * message parts. It looks for specific artifact types like 'mandate_request',
 * 'purchase_complete', 'error', or 'monitoring'.
 * @param parts The array of message parts to search.
 * @returns The first matching AgentArtifactData object found, or undefined if
 *     none match.
 */
export function parseMainArtifactData(
    parts: Part[],
    ): AgentArtifactData|undefined {
  const mainTypes = [
    'merchant_selected',
    'mandate_request',
    'immediate_checkout_request',
    'purchase_complete',
    'error',
    'monitoring',
    'product_preview_unavailable',
    'action_choices',
  ];
  for (const part of parts) {
    if (part.kind === 'data') {
      const d = part.data;
      if (d.type && typeof d.type === 'string' && mainTypes.includes(d.type)) {
        if (d.type === 'product_preview_unavailable') {
          return normalizeProductPreviewUnavailable(d) as AgentArtifactData;
        }
        if (d.type === 'immediate_checkout_request') {
          return normalizeImmediateCheckout(d) as AgentArtifactData;
        }
        if (d.type === 'action_choices') {
          const normalized = normalizeActionChoices(d);
          if (normalized) return normalized as AgentArtifactData;
          continue;
        }
        return d as unknown as AgentArtifactData;
      }
    } else if (part.kind === 'text') {
      for (const t of mainTypes) {
        const extracted = extractJsonFromText(part.text, 'type', t);
        if (extracted) {
          if (t === 'product_preview_unavailable') {
            return normalizeProductPreviewUnavailable(
                       extracted as Record<string, unknown>,
                       ) as AgentArtifactData;
          }
          if (t === 'immediate_checkout_request') {
            return normalizeImmediateCheckout(
                       extracted as Record<string, unknown>,
                       ) as AgentArtifactData;
          }
          if (t === 'action_choices') {
            const normalized = normalizeActionChoices(extracted);
            if (normalized) return normalized as AgentArtifactData;
            continue;
          }
          return extracted as AgentArtifactData;
        }
      }
    }
  }
  return undefined;
}

/**
 * Parses tool call and inventory option artifacts from a list of message parts.
 * It looks for both structured data and JSON embedded in text.
 * @param parts The array of message parts to search.
 * @returns An array of ToolCallArtifact and InventoryOptionsArtifact objects.
 */
export function parseToolAndInventoryArtifacts(
    parts: Part[],
    ): AgentArtifactData[] {
  const result: AgentArtifactData[] = [];
  for (const part of parts) {
    if (part.kind === 'data') {
      const d = part.data;
      if (isToolCallArtifact(d)) result.push(d);
      if (isInventoryOptionsArtifact(d)) result.push(d);
    } else if (part.kind === 'text') {
      try {
        const parsed = JSON.parse(part.text) as {type?: string};
        if (parsed?.type === 'tool_call') {
          result.push(parsed as ToolCallArtifact);
        }
        if (parsed?.type === 'inventory_options') {
          result.push(parsed as InventoryOptionsArtifact);
        }
      } catch {
        const embedded = extractToolCallFromEmbeddedJson(part.text);
        if (embedded) result.push(embedded);
      }
    }
  }
  return result;
}

/**
 * Parses tool invocation parts from a list of message parts.
 * It looks for structured data parts that represent tool calls and maps them
 * to ToolCallArtifact objects with their associated server.
 * @param parts The array of message parts to search.
 * @returns An array of ToolCallArtifact objects representing the tool
 *     invocations.
 */
export function parseInvocationParts(parts: Part[]): ToolCallArtifact[] {
  const result: ToolCallArtifact[] = [];
  const toolToServer = TOOL_SERVERS;
  for (const part of parts) {
    if (part.kind === 'data' && typeof part.data.name === 'string' &&
        part.data.args) {
      const name = part.data.name;
      const srv = toolToServer[name] ?? 'Unknown MCP';
      const msg = `Calling ${name.replace(/_/g, ' ')} via ${srv}`;
      const args = (part.data.args && typeof part.data.args === 'object') ?
          part.data.args as Record<string, unknown> :
          undefined;
      result.push({type: 'tool_call', tool: name, server: srv, message: msg, args});
    }
  }
  return result;
}

/**
 * Extracts a MandateRequest object from text.
 * Searches for a JSON object where "type" is "mandate_request".
 * @param text The text to search.
 * @returns The MandateRequest object, or undefined if not found.
 */
export function extractMandateFromText(text: string): MandateRequest|undefined {
  return extractJsonFromText(text, 'type', 'mandate_request') as
      MandateRequest |
      undefined;
}

export function normalizeImmediateCheckout(
    raw: Record<string, unknown>,
    ): ImmediateCheckoutRequest|undefined {
  if (raw.type !== 'immediate_checkout_request') return undefined;
  const rawTotal = raw.total_cents ?? raw.amount_cents;
  let total_cents: number|undefined;
  if (typeof rawTotal === 'number' && Number.isFinite(rawTotal)) {
    total_cents = rawTotal;
  } else if (typeof raw.total === 'number') {
    total_cents = Math.round(raw.total * 100);
  } else if (typeof raw.price === 'number') {
    total_cents =
        raw.price < 1000 ? Math.round(raw.price * 100) : Math.round(raw.price);
  }
  const item_name = String(
      raw.item_name ?? raw.product_name ?? raw.name ?? '',
  ).trim() || undefined;
  const item_id = String(raw.item_id ?? '').trim() || undefined;
  const payment_method =
      raw.payment_method === 'x402' ? 'x402' :
      raw.payment_method === 'card' ? 'card' :
      undefined;
  const payment_method_description =
      typeof raw.payment_method_description === 'string' ?
          raw.payment_method_description :
          undefined;
  return {
    type: 'immediate_checkout_request',
    item_id,
    item_name,
    total_cents,
    currency: typeof raw.currency === 'string' ? raw.currency : 'USD',
    payment_method,
    payment_method_description,
  };
}

export function extractImmediateCheckoutFromText(
    text: string,
    ): ImmediateCheckoutRequest|undefined {
  const extracted = extractJsonFromText(text, 'type', 'immediate_checkout_request');
  if (!extracted || typeof extracted !== 'object') return undefined;
  return normalizeImmediateCheckout(extracted as Record<string, unknown>);
}

/**
 * Extracts an ErrorArtifact object from text.
 * Searches for a JSON object where "type" is "error".
 * @param text The text to search.
 * @returns The ErrorArtifact object, or undefined if not found.
 */
export function extractErrorFromText(text: string): ErrorArtifact|undefined {
  return extractJsonFromText(text, 'type', 'error') as ErrorArtifact |
      undefined;
}

/**
 * Extracts a price value from text using regular expressions.
 * Looks for patterns like "price: $12.34" or just "$12.34".
 * @param text The text to search.
 * @returns The price as a number, or undefined if not found.
 */
export function extractCurrentPriceFromText(text: string): number|undefined {
  const m = text.match(/(?:current\s+)?price[:\s]*\$(\d+(?:\.\d+)?)/i);
  if (m) return Number(m[1]);
  const fallback = text.match(/\$(\d+(?:\.\d+)?)/);
  return fallback ? Number(fallback[1]) : undefined;
}

/**
 * Extracts a PurchaseComplete object from text.
 * Searches for a JSON object where "type" is "purchase_complete".
 * @param text The text to search.
 * @returns The PurchaseComplete object, or undefined if not found.
 */
export function extractPurchaseCompleteFromText(
    text: string,
    ): PurchaseComplete|undefined {
  return extractJsonFromText(text, 'type', 'purchase_complete') as
      PurchaseComplete |
      undefined;
}

/**
 * Validate and normalize an action_choices object into a clean options list.
 * Returns undefined when there are no usable options.
 */
export function normalizeActionChoices(
    raw: unknown,
    ): ActionChoices|undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const optsRaw = (raw as {options?: unknown}).options;
  if (!Array.isArray(optsRaw)) return undefined;
  const options: ActionChoice[] = [];
  for (const o of optsRaw) {
    if (!o || typeof o !== 'object') continue;
    const label = (o as {label?: unknown}).label;
    if (typeof label !== 'string' || !label.trim()) continue;
    const value = (o as {value?: unknown}).value;
    options.push({
      label: label.trim(),
      value: typeof value === 'string' && value.trim() ? value.trim() : undefined,
    });
  }
  if (options.length === 0) return undefined;
  return {type: 'action_choices', options};
}

/**
 * Extract action_choices JSON from text. Returns undefined when not present or
 * when no valid options exist.
 */
export function extractActionChoicesFromText(
    text: string,
    ): ActionChoices|undefined {
  return normalizeActionChoices(
      extractJsonFromText(text, 'type', 'action_choices'),
  );
}

/**
 * Extract merchant_selected JSON from text. Validates merchant is shoe|flight.
 */
export function extractMerchantSelectedFromText(
    text: string,
    ): MerchantSelected|undefined {
  const raw = extractJsonFromText(text, 'type', 'merchant_selected');
  if (!raw || typeof raw !== 'object') return undefined;
  const merchant = (raw as Record<string, unknown>).merchant;
  if (merchant !== 'shoe' && merchant !== 'flight') return undefined;
  return {type: 'merchant_selected', merchant};
}

/**
 * Extracts an InventoryOptionsArtifact object from text.
 * Searches for a JSON object where "type" is "inventory_options".
 * @param text The text to search.
 * @returns The InventoryOptionsArtifact object, or undefined if not found.
 */
export function extractInventoryOptionsFromText(
    text: string,
    ): InventoryOptionsArtifact|undefined {
  return extractJsonFromText(text, 'type', 'inventory_options') as
      InventoryOptionsArtifact |
      undefined;
}

/**
 * Extract monitoring JSON from streamed text using brace-balanced parsing.
 * Validates item_id is a string and price_cap is a number.
 */
export function extractMonitoringJsonFromText(
    text: string,
    ): MonitoringStatus|undefined {
  const raw = extractJsonFromText(text, 'type', 'monitoring');
  if (!raw || typeof raw !== 'object') return undefined;
  const obj = raw as Record<string, unknown>;
  if (typeof obj.item_id !== 'string' || typeof obj.price_cap !== 'number')
    return undefined;
  return obj as unknown as MonitoringStatus;
}

/**
 * Extract product_preview_unavailable JSON from text.
 */
export function extractProductPreviewUnavailableFromText(
    text: string,
    ): ProductPreviewUnavailable|undefined {
  const raw = extractJsonFromText(text, 'type', 'product_preview_unavailable');
  if (!raw || typeof raw !== 'object') return undefined;
  return normalizeProductPreviewUnavailable(raw as Record<string, unknown>);
}

/**
 * Extracts a MonitoringStatus object from text using regular expressions.
 * Matches patterns indicating that an item is being monitored for a price cap.
 * @param text The text to search.
 * @returns A MonitoringStatus object, or undefined if no pattern matches.
 */
export function extractMonitoringFromText(text: string): MonitoringStatus|
    undefined {
  const jsonMon = extractMonitoringJsonFromText(text);
  if (jsonMon) return jsonMon;

  const m = text.match(
      /Monitoring\s+([^—]+)\s*—\s*will\s+purchase\s+when\s+price\s*[<≤]\s*\$(\d+(?:\.\d+)?)/i,
  );
  if (m) {
    return {
      type: 'monitoring',
      item_id: m[1].trim(),
      price_cap: Number(m[2]),
      message: text.split(/\n/)[0]?.trim(),
    };
  }
  const m2 = text.match(
      /Mandate\s+received\.\s+Monitoring\s+([^—.]+)\s*[—.]\s*will\s+purchase\s+when\s+price\s*[<≤=]\s*\$(\d+(?:\.\d+)?)/i,
  );
  if (m2) {
    return {
      type: 'monitoring',
      item_id: m2[1].trim(),
      price_cap: Number(m2[2]),
      message: text.split(/\n/)[0]?.trim(),
    };
  }
  return undefined;
}

const TOOL_SERVERS: Record<string, string> = {
  search_inventory: 'Merchant MCP',
  check_price: 'Merchant MCP',
  check_product: 'Merchant MCP',
  assemble_cart: 'Merchant MCP',
  create_checkout: 'Merchant MCP',
  complete_checkout: 'Merchant MCP',
  settle_with_psp: 'Merchant MCP',
  get_ap2_session_config: 'Shopping Agent',
  set_ap2_session_config: 'Shopping Agent',
  reset_temp_db: 'Shopping Agent',
  assemble_and_sign_mandates_tool: 'Shopping Agent',
  create_hp_open_mandates_tool: 'Shopping Agent',
  assemble_and_sign_immediate_mandates_tool: 'Shopping Agent',
  check_price_against_mandate: 'Shopping Agent',
  check_constraints_against_mandate: 'Shopping Agent',
  create_checkout_presentation: 'Shopping Agent',
  create_payment_presentation: 'Shopping Agent',
  verify_checkout_receipt: 'Shopping Agent',
  transfer_to_agent: 'Agent Handoff',
  issue_payment_credential: 'Credential Provider MCP',
  revoke_payment_credential: 'Credential Provider MCP',
  verify_payment_receipt: 'Credential Provider MCP',
};
