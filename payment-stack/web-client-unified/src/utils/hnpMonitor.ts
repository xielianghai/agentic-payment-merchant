import type {ChatMessage, MandateRequest, MonitoringStatus} from '../types';
import {hasMandateApprovalForKey, mandateRequestKey} from './mandateFlow';

export interface OpenMandateIds {
  checkoutId: string;
  paymentId: string;
  openCheckoutHash?: string;
}

export function isMandateId(value: string): boolean {
  return value.startsWith('open_chk_') || value.startsWith('open_pay_');
}

/** Normalize LLM/slug item_id variants for merchant trigger + monitor register. */
export function normalizeSlugItemId(itemId: string): string {
  let s = itemId.trim().toLowerCase();
  if (s.startsWith('preview_')) s = s.slice('preview_'.length);
  s = s.replace(/-/g, '_');
  return s.replace(/\.(\d+)$/, '_$1');
}

/** Latest HNP mandate_request the user approved on Trusted Surface. */
export function latestApprovedHnpMandate(
    messages: ChatMessage[],
    ): MandateRequest|undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (data?.type !== 'mandate_request') continue;
    const mr = data as MandateRequest;
    if (hasMandateApprovalForKey(messages, mandateRequestKey(mr))) {
      return mr;
    }
  }
  return undefined;
}

/** Open mandate ids from mandates_signed / monitoring artifacts (newest first). */
export function extractOpenMandateIds(
    messages: ChatMessage[],
    ): OpenMandateIds|undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const raw = messages[i].artifactData as Record<string, unknown>|undefined;
    if (!raw?.type) continue;

    if (raw.type === 'mandates_signed') {
      const checkoutId =
          typeof raw.open_checkout_mandate_id === 'string' ?
              raw.open_checkout_mandate_id :
              typeof raw.open_checkout_mandate === 'string' &&
                  isMandateId(raw.open_checkout_mandate) ?
                  raw.open_checkout_mandate :
                  undefined;
      const paymentId =
          typeof raw.open_payment_mandate_id === 'string' ?
              raw.open_payment_mandate_id :
              typeof raw.open_payment_mandate === 'string' &&
                  isMandateId(raw.open_payment_mandate) ?
                  raw.open_payment_mandate :
                  undefined;
      if (checkoutId && paymentId) {
        return {
          checkoutId,
          paymentId,
          openCheckoutHash: typeof raw.open_checkout_hash === 'string' ?
              raw.open_checkout_hash :
              undefined,
        };
      }
    }

    if (raw.type === 'monitoring') {
      const ms = raw as unknown as MonitoringStatus;
      const checkoutId =
          ms.open_checkout_mandate && isMandateId(ms.open_checkout_mandate) ?
              ms.open_checkout_mandate :
              undefined;
      const paymentId =
          ms.open_payment_mandate && isMandateId(ms.open_payment_mandate) ?
              ms.open_payment_mandate :
              undefined;
      if (checkoutId && paymentId) {
        return {checkoutId, paymentId};
      }
    }
  }
  return undefined;
}

export function monitoringStatusFromBackend(
    tick: Partial<MonitoringStatus>,
    fallback: {
      item_id: string;
      price_cap: number;
      qty?: number;
      item_name?: string;
      open_checkout_mandate?: string;
      open_payment_mandate?: string;
    },
    ): MonitoringStatus {
  return {
    type: 'monitoring',
    item_id: tick.item_id ?? fallback.item_id,
    item_name: tick.item_name ?? fallback.item_name,
    price_cap: (tick.price_cap as number|undefined) ?? fallback.price_cap,
    qty: fallback.qty,
    current_price: tick.current_price as number|undefined,
    available: tick.available as boolean|undefined,
    meets_constraints: tick.meets_constraints as boolean|undefined,
    message: tick.message as string|undefined,
    open_checkout_mandate: fallback.open_checkout_mandate,
    open_payment_mandate: fallback.open_payment_mandate,
  };
}
