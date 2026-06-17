import type {ChatMessage, ImmediateCheckoutRequest, ToolCallArtifact} from '../types';
import {extractPurchaseCompleteFromText} from './parsing';

export function immediateCheckoutKey(req: {
  item_id?: string;
  total_cents?: number;
  payment_method?: 'card' | 'x402';
}): string {
  return `${req.item_id ?? ''}:${req.total_cents ?? ''}:${req.payment_method ?? ''}`;
}

/** True when the user confirmed this specific checkout request. */
export function isCheckoutConfirmed(
    messages: ChatMessage[],
    checkoutMsgTimestamp: number,
    key: string,
): boolean {
  return messages.some(
      (m) =>
          m.role === 'user_action' &&
          m.userActionLabel === 'Confirmed checkout' &&
          m.checkoutKey === key &&
          m.timestamp > checkoutMsgTimestamp,
  );
}

export type CheckoutFlowPhase =
    'none'|'awaiting_confirm'|'processing'|'complete';

export function getCheckoutFlowState(messages: ChatMessage[]): {
  phase: CheckoutFlowPhase;
  request?: ImmediateCheckoutRequest;
  requestIndex?: number;
} {
  let lastReqIdx = -1;
  let lastReq: ImmediateCheckoutRequest|undefined;
  for (let i = 0; i < messages.length; i++) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (data?.type === 'immediate_checkout_request') {
      lastReqIdx = i;
      lastReq = data as ImmediateCheckoutRequest;
    }
  }
  if (!lastReq || lastReqIdx < 0) {
    return {phase: 'none'};
  }

  const key = immediateCheckoutKey(lastReq);
  const msgTs = messages[lastReqIdx].timestamp;
  if (!isCheckoutConfirmed(messages, msgTs, key)) {
    return {phase: 'awaiting_confirm', request: lastReq, requestIndex: lastReqIdx};
  }

  for (let i = lastReqIdx; i < messages.length; i++) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (data?.type === 'purchase_complete') {
      return {phase: 'complete', request: lastReq, requestIndex: lastReqIdx};
    }
    if (messages[i].text && extractPurchaseCompleteFromText(messages[i].text!)) {
      return {phase: 'complete', request: lastReq, requestIndex: lastReqIdx};
    }
    const tc = messages[i].artifactData as ToolCallArtifact|undefined;
    if (tc?.type === 'tool_call' && tc.tool === 'complete_checkout') {
      return {phase: 'complete', request: lastReq, requestIndex: lastReqIdx};
    }
  }

  return {phase: 'processing', request: lastReq, requestIndex: lastReqIdx};
}

export function hasAnyPurchaseComplete(messages: ChatMessage[]): boolean {
  for (const m of messages) {
    const data = m.artifactData as {type?: string}|undefined;
    if (data?.type === 'purchase_complete') return true;
    if (m.text && extractPurchaseCompleteFromText(m.text)) return true;
  }
  return false;
}
