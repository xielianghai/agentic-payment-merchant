import {useState} from 'react';
import type {MerchantKey} from '../config';
import type {TrustedSurface} from '../trustedSurface';
import {defaultCurrencyFor} from '../config';
import {
  formatItemReferenceValue,
  itemReferenceLabel,
  shouldShowItemReferenceRow,
} from '../utils/itemDisplay';
import {formatPaymentDisplay} from '../utils/paymentDisplay';
import {devLog, devWarn} from '../utils/devLog';
import './ImmediateCheckoutApproval.scss';

export type ImmediateCheckoutRequest = {
  type: 'immediate_checkout_request';
  item_name?: string;
  item_id?: string;
  total_cents?: number;
  currency?: string;
  payment_method?: 'card' | 'x402';
  payment_method_description?: string;
};

type Props = {
  request: ImmediateCheckoutRequest;
  trustedSurface: TrustedSurface;
  sessionId: string;
  merchant?: MerchantKey;
  /** Session-resolved rail when agent JSON omits payment_method. */
  paymentMethod?: 'card' | 'x402';
  onApprove: () => void;
  onReject: () => void;
  alreadyConfirmed?: boolean;
};

export function ImmediateCheckoutApproval({
  request,
  trustedSurface,
  sessionId,
  merchant = 'shoe',
  paymentMethod = 'card',
  onApprove,
  onReject,
  alreadyConfirmed = false,
}: Props) {
  const [state, setState] = useState<'idle' | 'signing' | 'signed'>(
      alreadyConfirmed ? 'signed' : 'idle',
  );
  const [portalUrl, setPortalUrl] = useState<string | undefined>();
  const [portalError, setPortalError] = useState<string | undefined>();
  const total = request.total_cents != null ? request.total_cents / 100 : null;
  const currency = defaultCurrencyFor(merchant);
  const rail = request.payment_method ?? paymentMethod;
  const payment = formatPaymentDisplay(rail, request.payment_method_description);
  const showReference = shouldShowItemReferenceRow(
      merchant,
      request.item_id,
      request.item_name,
  );
  const itemId = request.item_id ?? '';
  const itemName = request.item_name || request.item_id || 'Purchase';
  const canConfirm = Boolean(itemId) && total != null && total > 0;

  async function handleSign() {
    if (!canConfirm || state !== 'idle') return;
    devLog('TrustedSurface', 'HP Confirm & pay START', {
      item_id: itemId,
      price_cap: total,
      payment_method: rail,
    });
    setPortalError(undefined);
    setPortalUrl(undefined);
    setState('signing');
    try {
      const signed = await trustedSurface.confirmViaPortal(
          {
            sessionId,
            priceCap: total!,
            paymentMethod: rail,
            itemId,
            itemName,
            presenceMode: 'hp',
          },
          {onPortalUrl: setPortalUrl},
      );
      if (!signed) {
        devWarn('TrustedSurface', 'HP portal not signed');
        setPortalError(
            'Trusted Surface confirmation failed or timed out. Open the portal link and confirm, then try again.',
        );
        setState('idle');
        return;
      }
      setState('signed');
      setPortalUrl(undefined);
      devLog('TrustedSurface', 'HP portal signed — dispatching checkout');
      setTimeout(onApprove, 300);
    } catch {
      setPortalError('Trusted Surface connection error.');
      setState('idle');
    }
  }

  return (
    <div className="msg-agent immediate-checkout-container">
      <div className="immediate-checkout-card">
        <div className="header">
          <span className="title">Confirm purchase (HP)</span>
          <span className="subtitle">Trusted Surface · User signs Closed Mandate</span>
        </div>
        <div className="body">
          <div className="row">
            <span className="label">Item</span>
            <span className="value">
              {request.item_name || request.item_id || '—'}
            </span>
          </div>
          {showReference && request.item_id && (
            <div className="row subtle">
              <span className="label">{itemReferenceLabel(merchant)}</span>
              <span className="value mono">
                {formatItemReferenceValue(
                    merchant,
                    request.item_id,
                    request.item_name,
                )}
              </span>
            </div>
          )}
          {total != null && (
            <div className="row">
              <span className="label">Total</span>
              <span className="amount">
                {currency} {total.toFixed(2)}
              </span>
            </div>
          )}
          <div className="row payment-row">
            <span className="label">Payment</span>
            <span className="payment-value">
              <span className="payment-label">{payment.label}</span>
              <span className="payment-badge">{payment.badge}</span>
            </span>
          </div>
        </div>
        {portalError && state === 'idle' && (
          <div className="portal-error">{portalError}</div>
        )}
        <div className="actions">
          {alreadyConfirmed || state === 'signed' ? (
            <div className="signed">Already confirmed — processing payment…</div>
          ) : state === 'idle' ? (
            <>
              <button type="button" className="reject" onClick={onReject}>
                Cancel
              </button>
              <button
                type="button"
                className="approve"
                onClick={handleSign}
                disabled={!canConfirm}>
                Confirm &amp; pay
              </button>
            </>
          ) : state === 'signing' ? (
            <div className="signing">
              Waiting for Trusted Surface confirmation…
              {portalUrl && (
                <p style={{marginTop: 8}}>
                  <a href={portalUrl} target="_blank" rel="noopener noreferrer">
                    Open Trusted Surface to confirm
                  </a>
                </p>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
