import type {ChatMessage, ImmediateCheckoutRequest, PurchaseComplete, ToolCallArtifact} from '../types';
import type {MerchantKey} from '../config';
import {defaultCurrencyFor} from '../config';
import {getCheckoutFlowState} from './checkoutFlow';
import {formatPaymentDisplay} from './paymentDisplay';

function centsToDollars(cents: number): number {
  return cents / 100;
}

function paymentLabel(
    method?: 'card'|'x402',
    description?: string,
): string {
  if (!method) return description ?? 'Card';
  return formatPaymentDisplay(method, description).label;
}

/** Fill receipt gaps from thread context (HP often omits closed_payment_mandate_content). */
export function enrichPurchaseComplete(
    purchase: PurchaseComplete,
    messages: ChatMessage[],
    fallbackItemName?: string,
    merchant: MerchantKey = 'shoe',
): PurchaseComplete {
  const profileCurrency = defaultCurrencyFor(merchant);
  const flow = getCheckoutFlowState(messages);
  const checkoutReq = flow.request;

  const item_id = purchase.item_id ?? checkoutReq?.item_id;
  const item_name = purchase.item_name ?? checkoutReq?.item_name ?? fallbackItemName;
  let total_cents = purchase.total_cents ?? checkoutReq?.total_cents;
  let currency = purchase.currency ?? checkoutReq?.currency ?? profileCurrency;
  let payment_method = purchase.payment_method ?? checkoutReq?.payment_method;
  let payment_method_description =
      purchase.payment_method_description ?? checkoutReq?.payment_method_description;
  let status = purchase.status;

  const closed = purchase.closed_payment_mandate_content as
      Record<string, unknown>|undefined;
  if (closed) {
    const amountObj = closed.payment_amount as {amount?: number; currency?: string}|undefined;
    if (total_cents == null && typeof amountObj?.amount === 'number') {
      total_cents = amountObj.amount;
    }
    if (amountObj?.currency) currency = amountObj.currency;
    const instrument = closed.payment_instrument as
        {description?: string; type?: string}|undefined;
    if (!payment_method_description && instrument?.description) {
      payment_method_description = instrument.description;
    }
    if (!payment_method && instrument?.type === 'x402') payment_method = 'x402';
  }

  for (let i = messages.length - 1; i >= 0; i--) {
    const tc = messages[i].artifactData as ToolCallArtifact|undefined;
    if (tc?.type !== 'tool_call' || tc.tool !== 'complete_checkout') continue;
    const resp = tc.args?.response as Record<string, unknown>|undefined;
    if (!resp && tc.args) {
      // response may be on function response part, not stored on artifact — skip
    }
    if (typeof resp?.status === 'string') status = resp.status;
    if (typeof resp?.order_id === 'string' && !purchase.order_id) {
      purchase = {...purchase, order_id: resp.order_id};
    }
    break;
  }

  const receipt = purchase.receipt as Record<string, unknown>|undefined;
  if (receipt) {
    if (total_cents == null && typeof receipt.total_cents === 'number') {
      total_cents = receipt.total_cents;
    }
    if (total_cents == null && typeof receipt.amount_charged === 'number') {
      total_cents = receipt.amount_charged;
    }
    if (!status && typeof receipt.status === 'string') status = receipt.status;
  }

  if (typeof purchase.amount_charged === 'number' && total_cents == null) {
    total_cents = purchase.amount_charged;
  }

  return {
    ...purchase,
    item_id,
    item_name,
    total_cents,
    currency,
    payment_method,
    payment_method_description: paymentLabel(payment_method, payment_method_description),
    status: status ?? 'success',
  };
}

export function formatReceiptAmount(
    purchase: PurchaseComplete,
    merchant: MerchantKey = 'shoe',
): string {
  const profileCurrency = defaultCurrencyFor(merchant);
  if (purchase.total_cents != null) {
    const dollars = centsToDollars(purchase.total_cents);
    return `${profileCurrency} $${dollars.toFixed(2)}`;
  }
  const closed = purchase.closed_payment_mandate_content as
      Record<string, unknown>|undefined;
  const amountObj = closed?.payment_amount as {amount?: number}|undefined;
  if (typeof amountObj?.amount === 'number') {
    return `$${centsToDollars(amountObj.amount).toFixed(2)}`;
  }
  return '—';
}

export function checkoutRequestFromMessages(
    messages: ChatMessage[],
): ImmediateCheckoutRequest|undefined {
  return getCheckoutFlowState(messages).request;
}
