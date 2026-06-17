import type { PurchaseComplete } from '../types';
import type { MerchantKey } from '../config';
import {
  formatItemReferenceValue,
  itemReferenceLabel,
  shouldShowItemReferenceRow,
} from '../utils/itemDisplay';
import { formatPaymentDisplay } from '../utils/paymentDisplay';
import { formatReceiptAmount } from '../utils/purchaseReceipt';
import './ReceiptCard.scss';

interface Props {
  purchase: PurchaseComplete;
  itemName?: string;
  merchant?: MerchantKey;
  presenceMode?: 'hp' | 'hnp';
}

export function ReceiptCard({purchase, itemName, merchant = 'shoe', presenceMode}: Props) {
  const displayName =
      purchase.item_name ?? itemName ?? 'Order';
  const amountLabel = formatReceiptAmount(purchase, merchant);
  const paymentMethod = formatPaymentDisplay(
      purchase.payment_method ?? 'card',
      purchase.payment_method_description,
  ).label;
  const status = (purchase.status ?? 'success').toLowerCase();
  const subtitle =
      presenceMode === 'hp' ?
          'Human Present · user confirmed checkout' :
          'Autonomous · mandate-authorized';

  const showReference = shouldShowItemReferenceRow(
      merchant,
      purchase.item_id,
      purchase.item_name ?? itemName,
  );

  return (
    <div className="msg-agent receipt-card-container">
      <div className="receipt-card">
        <div className="success-header">
          <div className="success-badge">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path
                d="M4 9l3.5 3.5 6.5-7"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="24"
                strokeDashoffset="0"
              />
            </svg>
          </div>
          <div className="title-container">
            <div className="title">Purchase Complete</div>
            <div className="subtitle">{subtitle}</div>
          </div>
        </div>

        <div className="receipt-body">
          <div className="display-name">{displayName}</div>
          {showReference && purchase.item_id && (
            <div className="sku-line">
              {itemReferenceLabel(merchant)} ·{' '}
              {formatItemReferenceValue(
                  merchant,
                  purchase.item_id,
                  purchase.item_name ?? itemName,
              )}
            </div>
          )}
          <div className="order-id">Order · {purchase.order_id}</div>

          <div className="info-grid info-grid--wide">
            <div className="grid-item">
              <div className="item-label">Charged</div>
              <div className="item-value">{amountLabel}</div>
            </div>
            <div className="grid-item">
              <div className="item-label">Payment</div>
              <div className="item-value payment-method">{paymentMethod}</div>
            </div>
            <div className="grid-item">
              <div className="item-label">Status</div>
              <div className={`item-value status-${status}`}>{status}</div>
            </div>
          </div>

          <div className="detail-rows">
            {purchase.currency && (
              <div className="detail-row">
                <span className="detail-label">Currency</span>
                <span className="detail-value">{purchase.currency}</span>
              </div>
            )}
            {purchase.payment_method && (
              <div className="detail-row">
                <span className="detail-label">Rail</span>
                <span className="detail-value">{purchase.payment_method}</span>
              </div>
            )}
            {presenceMode && (
              <div className="detail-row">
                <span className="detail-label">Flow</span>
                <span className="detail-value">
                  {presenceMode === 'hp' ? 'Human Present (HP)' : 'Human Not Present (HNP)'}
                </span>
              </div>
            )}
          </div>

          <div className="chain-box">
            <div className="chain-label">Transaction chain</div>
            {[
              {
                label: 'Merchant MCP',
                steps: 'check_product → cart → checkout → complete',
              },
              {
                label: 'Credential Provider MCP',
                steps: 'issue_payment_credential (verify + issue)',
              },
            ].map((s) => (
              <div key={s.label} className="chain-row">
                <span className="row-label">{s.label}</span>
                <span className="row-value">{s.steps}</span>
              </div>
            ))}
          </div>

          <div className="timestamp">
            {new Date().toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
              timeZoneName: 'short',
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
