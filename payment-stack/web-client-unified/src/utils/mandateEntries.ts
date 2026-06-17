/**
 * Derivation of MandateEntry[] from the current chat message history.
 *
 * The agent surfaces mandate artifacts in a few different shapes:
 *   - `mandate_request` — user-facing mandate proposal (JSON object)
 *   - `monitoring` — carries `open_checkout_mandate` and `open_payment_mandate`
 *     as encoded SD-JWT strings
 *   - `purchase_complete` — may carry `closed_payment_mandate` (SD-JWT string)
 *     and `closed_payment_mandate_content` (JSON object), sometimes also
 *     `checkout_jwt` / `closed_checkout_mandate`.
 *   - Tool calls (`tool_call` artifacts) for `create_checkout_presentation`,
 *     `create_payment_presentation`, and `present_mandate_chain` — these
 *     don't return the raw SD-JWT to the client, but the tool arguments let
 *     us document that the operation happened (embedded checkout JWT, target
 *     audience for a presentation, etc.).
 *
 * We scan the message list once, deduplicate identical tokens, and return a
 * chronologically ordered list suitable for the Mandates tab.
 */

import type {ChatMessage, MandateChainsFetched, MandateEntry, MandateRequest, MandatesSigned, MonitoringStatus, PurchaseComplete,} from '../types';
import {hasMandateApprovalForKey, mandateRequestKey} from './mandateFlow';

type Draft = Omit<MandateEntry, 'id'>;

function pushOpenMandateDraft(
    drafts: Draft[],
    kind: 'open_checkout_mandate' | 'open_payment_mandate',
    token: string,
    timestamp: number,
    subtitle?: string,
    ): void {
  const title =
      kind === 'open_checkout_mandate' ?
          'Open Checkout Mandate' :
          'Open Payment Mandate';
  if (token.includes('~')) {
    drafts.push({kind, title, subtitle, timestamp, rawToken: token});
    return;
  }
  drafts.push({
    kind,
    title,
    subtitle: subtitle ?? token,
    timestamp,
    rawPayload: {mandate_id: token},
  });
}

/** Stable string key for dedup (same token OR same decoded JSON object). */
function entryKey(d: Draft): string {
  if (d.rawToken) return `${d.kind}:token:${d.rawToken}`;
  if (d.rawPayload) {
    // For tool-call-derived entries, identify by stable discriminators so we
    // don't emit duplicates if the stream replays the same tool invocation.
    const p = d.rawPayload;
    if (typeof p.checkout_hash === 'string') {
      return `${d.kind}:hash:${p.checkout_hash}`;
    }
    if (typeof p.transaction_id === 'string') {
      return `${d.kind}:tx:${p.transaction_id}`;
    }
    if (typeof p.mandate_chain_id === 'string' && typeof p.aud === 'string') {
      return `${d.kind}:${p.aud}:${p.mandate_chain_id}`;
    }
    return `${d.kind}:payload:${JSON.stringify(p)}`;
  }
  return `${d.kind}:${d.title}:${d.timestamp}`;
}

/**
 * Collapse the many representations of an open mandate to ONE card per kind.
 *
 * The same open checkout/payment mandate surfaces as a decoded SD-JWT (from
 * `monitoring` / `mandates_signed`) and as a bare `open_chk_*` / `open_pay_*`
 * id stub (from a later, asynchronously-injected `mandates_signed`). These
 * cannot be matched by id (the SD-JWT does not embed the short id), so we
 * collapse by kind: a purchase has exactly one open checkout + one open
 * payment. Prefer the richest representation (decoded SD-JWT), then the latest.
 */
function dedupeOpenMandateRepresentations(drafts: Draft[]): Draft[] {
  const isOpen = (d: Draft) =>
      d.kind === 'open_checkout_mandate' || d.kind === 'open_payment_mandate';
  const rank = (d: Draft) => (d.rawToken && d.rawToken.includes('~') ? 1 : 0);

  const bestByKind = new Map<string, Draft>();
  for (const draft of drafts) {
    if (!isOpen(draft)) continue;
    const existing = bestByKind.get(draft.kind);
    if (!existing) {
      bestByKind.set(draft.kind, draft);
      continue;
    }
    const better =
        rank(draft) > rank(existing) ||
        (rank(draft) === rank(existing) && draft.timestamp >= existing.timestamp);
    if (better) bestByKind.set(draft.kind, draft);
  }

  const out: Draft[] = [];
  for (const draft of drafts) {
    if (!isOpen(draft)) {
      out.push(draft);
      continue;
    }
    if (bestByKind.get(draft.kind) === draft) out.push(draft);
  }
  return out.sort((a, b) => a.timestamp - b.timestamp);
}

function purchaseEntries(msg: ChatMessage, pc: PurchaseComplete): Draft[] {
  const out: Draft[] = [];
  const extra = pc as unknown as Record<string, unknown>;

  // Closed payment mandate -- token form.
  const closedPaymentToken = extra.closed_payment_mandate;
  if (typeof closedPaymentToken === 'string' && closedPaymentToken.includes('~')) {
    out.push({
      kind: 'closed_payment_mandate',
      title: 'Closed Payment Mandate',
      subtitle: pc.order_id,
      timestamp: msg.timestamp,
      rawToken: closedPaymentToken,
    });
  }

  // Closed checkout mandate -- token form.
  const closedCheckoutToken = extra.closed_checkout_mandate;
  if (typeof closedCheckoutToken === 'string' && closedCheckoutToken.includes('~')) {
    out.push({
      kind: 'closed_checkout_mandate',
      title: 'Closed Checkout Mandate',
      subtitle: pc.order_id,
      timestamp: msg.timestamp,
      rawToken: closedCheckoutToken,
    });
  }

  // Checkout JWT (merchant-signed, not an SD-JWT).
  const checkoutJwt = extra.checkout_jwt;
  if (typeof checkoutJwt === 'string' && checkoutJwt.split('.').length === 3) {
    out.push({
      kind: 'checkout_jwt',
      title: 'Checkout JWT',
      subtitle: pc.order_id,
      timestamp: msg.timestamp,
      rawToken: checkoutJwt,
    });
  }

  return out;
}

function toolCallEntries(): Draft[] {
  return [];
}

/**
 * One open checkout+payment pair per purchase. Agent retries create extras;
 * keep the last open pair before each closed checkout, or the latest if still
 * in progress.
 */
function filterOpenMandateRetries(drafts: Draft[]): Draft[] {
  const isOpen = (d: Draft) =>
      d.kind === 'open_checkout_mandate' || d.kind === 'open_payment_mandate';

  const openCheckouts = drafts.filter((d) => d.kind === 'open_checkout_mandate');
  const completionTimes = drafts
      .filter(
          (d) => d.kind === 'closed_checkout_mandate' ||
              (d.kind === 'mandate_chain' &&
                  d.title === 'Checkout Mandate Chain'),
      )
      .map((d) => d.timestamp)
      .sort((a, b) => a - b);

  const keepTimestamps = new Set<number>();

  if (completionTimes.length === 0) {
    const last = openCheckouts[openCheckouts.length - 1];
    if (last) keepTimestamps.add(last.timestamp);
  } else {
    // One purchase → one closed checkout. Keep only the last open pair before the
    // final closed mandate (multiple mandate_chains_fetched messages must not
    // leave an earlier duplicate open pair visible).
    const lastCompleteTs = completionTimes[completionTimes.length - 1];
    const inWindow = openCheckouts.filter(
        (d) => d.timestamp <= lastCompleteTs,
    );
    const last = inWindow[inWindow.length - 1];
    if (last) keepTimestamps.add(last.timestamp);
    const pending = openCheckouts.filter((d) => d.timestamp > lastCompleteTs);
    const lastPending = pending[pending.length - 1];
    if (lastPending) keepTimestamps.add(lastPending.timestamp);
  }

  return drafts.filter((d) => !isOpen(d) || keepTimestamps.has(d.timestamp));
}

/** Scan the message list and produce a deduplicated, chronological list. */
export function deriveMandateEntries(messages: ChatMessage[]): MandateEntry[] {
  const drafts: Draft[] = [];
  for (const msg of messages) {
    const data = msg.artifactData as {type?: string} | undefined;
    if (!data) continue;

    switch (data.type) {
      case 'mandate_request': {
        const mr = data as unknown as MandateRequest;
        const payment =
            mr.payment_method === 'x402' ? 'x402' :
            mr.payment_method === 'card' ? 'card' :
            'card';
        if (hasMandateApprovalForKey(messages, mandateRequestKey(mr))) {
          drafts.push({
            kind: 'mandate_request',
            title: 'Signed Mandate Request',
            subtitle: payment,
            timestamp: msg.timestamp,
            rawPayload: {
              item_id: mr.item_id,
              item_name: mr.item_name,
              price_cap: mr.price_cap,
              qty: mr.qty ?? 1,
              payment_method: payment,
              constraints: mr.constraints,
            },
          });
        }
        break;
      }
      case 'monitoring': {
        const ms = data as unknown as MonitoringStatus;
        if (ms.open_checkout_mandate) {
          pushOpenMandateDraft(
              drafts,
              'open_checkout_mandate',
              ms.open_checkout_mandate,
              msg.timestamp,
          );
        }
        if (ms.open_payment_mandate) {
          pushOpenMandateDraft(
              drafts,
              'open_payment_mandate',
              ms.open_payment_mandate,
              msg.timestamp,
          );
        }
        break;
      }
      case 'mandates_signed': {
        const ms = data as unknown as MandatesSigned;
        const railLabel =
            ms.payment_method === 'x402' ? 'x402' :
            ms.payment_method === 'card' ? 'card' :
            undefined;
        if (ms.open_checkout_mandate) {
          pushOpenMandateDraft(
              drafts,
              'open_checkout_mandate',
              ms.open_checkout_mandate,
              msg.timestamp,
              railLabel,
          );
        }
        if (ms.open_payment_mandate) {
          pushOpenMandateDraft(
              drafts,
              'open_payment_mandate',
              ms.open_payment_mandate,
              msg.timestamp,
              railLabel,
          );
        }
        break;
      }
      case 'purchase_complete':
        drafts.push(...purchaseEntries(msg, data as unknown as PurchaseComplete));
        break;
      case 'tool_call':
        drafts.push(...toolCallEntries());
        break;
      case 'mandate_chains_fetched': {
        const mcf = data as unknown as MandateChainsFetched;
        if (mcf.payment_mandate_chain) {
          drafts.push({
            kind: 'mandate_chain',
            title: 'Payment Mandate Chain',
            timestamp: msg.timestamp,
            rawToken: mcf.payment_mandate_chain,
          });

          // Extract closed payment mandate
          const parts = mcf.payment_mandate_chain.split('~~');
          const closedToken = parts[parts.length - 1];
          drafts.push({
            kind: 'closed_payment_mandate',
            title: 'Closed Payment Mandate',
            timestamp: msg.timestamp,
            rawToken: closedToken,
          });
        }
        if (mcf.checkout_mandate_chain) {
          drafts.push({
            kind: 'mandate_chain',
            title: 'Checkout Mandate Chain',
            timestamp: msg.timestamp,
            rawToken: mcf.checkout_mandate_chain,
          });

          // Extract closed checkout mandate
          const parts = mcf.checkout_mandate_chain.split('~~');
          const closedToken = parts[parts.length - 1];
          drafts.push({
            kind: 'closed_checkout_mandate',
            title: 'Closed Checkout Mandate',
            timestamp: msg.timestamp,
            rawToken: closedToken,
          });
        }
        break;
      }
      default:
        break;
    }
  }



  const seen = new Set<string>();
  const result: MandateEntry[] = [];
  for (const d of dedupeOpenMandateRepresentations(filterOpenMandateRetries(drafts))) {
    const key = entryKey(d);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({...d, id: `mandate_${result.length}_${d.timestamp}`});
  }
  return result;
}
