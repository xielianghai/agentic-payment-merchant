import {useState} from 'react';
import type {MerchantKey} from '../config';
import {defaultCurrencyFor} from '../config';
import {
  formatItemReferenceValue,
  itemReferenceLabel,
  shouldShowItemReferenceRow,
} from '../utils/itemDisplay';
import {formatPaymentDisplay} from '../utils/paymentDisplay';
import {OtpModal} from './OtpModal';
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
  merchant?: MerchantKey;
  /** Session-resolved rail when agent JSON omits payment_method. */
  paymentMethod?: 'card' | 'x402';
  onApprove: () => void;
  onReject: () => void;
  alreadyConfirmed?: boolean;
};

export function ImmediateCheckoutApproval({
  request,
  merchant = 'shoe',
  paymentMethod = 'card',
  onApprove,
  onReject,
  alreadyConfirmed = false,
}: Props) {
  const [state, setState] = useState<'idle' | 'signing' | 'signed'>(
      alreadyConfirmed ? 'signed' : 'idle',
  );
  const [showOtp, setShowOtp] = useState(false);
  const total = request.total_cents != null ? request.total_cents / 100 : null;
  const currency = defaultCurrencyFor(merchant);
  const rail = request.payment_method ?? paymentMethod;
  const payment = formatPaymentDisplay(rail, request.payment_method_description);
  const showReference = shouldShowItemReferenceRow(
      merchant,
      request.item_id,
      request.item_name,
  );

  async function handleSign() {
    setState('signing');
    await new Promise((r) => setTimeout(r, 600));
    setState('signed');
    setTimeout(onApprove, 300);
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
                onClick={() => setShowOtp(true)}>
                Confirm &amp; pay
              </button>
            </>
          ) : state === 'signing' ? (
            <div className="signing">Signing mandate…</div>
          ) : null}
        </div>
      </div>
      {showOtp && (
        <OtpModal
          onConfirm={() => {
            setShowOtp(false);
            handleSign();
          }}
          onCancel={() => setShowOtp(false)}
        />
      )}
    </div>
  );
}
