import {useEffect, useState} from 'react';
import {isFlightMerchant, type MerchantKey} from '../config';
import type {TrustedSurface} from '../trustedSurface';
import type {MandateApprovalData, MandateRequest} from '../types';
import {devLog, devWarn} from '../utils/devLog';
import {
  formatItemReferenceValue,
  shouldShowItemReferenceRow,
} from '../utils/itemDisplay';
import {formatPaymentDisplay} from '../utils/paymentDisplay';
import {TriggerCurlBox} from './TriggerCurlBox';
import './MandateApproval.scss';

interface Props {
  mandate: MandateRequest;
  trustedSurface: TrustedSurface;
  sessionId: string;
  onApprove: (mandateRequest: MandateApprovalData) => void;
  onReject: () => void;
  merchant?: MerchantKey;
  itemName?: string;
  currentPrice?: number;
  /** Mandate already approved in this session — show signed, hide actions. */
  alreadyApproved?: boolean;
  /** HNP: simulate drop before monitoring can purchase. */
  triggerCurl?: string;
}

export function MandateApproval({
  mandate,
  trustedSurface,
  sessionId,
  onApprove,
  onReject,
  merchant = 'shoe',
  itemName,
  currentPrice,
  alreadyApproved = false,
  triggerCurl,
}: Props) {
  const [state, setState] = useState<'idle' | 'signing' | 'signed'>(
      alreadyApproved ? 'signed' : 'idle',
  );
  const [signedHere, setSignedHere] = useState(false);
  const [portalUrl, setPortalUrl] = useState<string | undefined>();
  const [portalError, setPortalError] = useState<string | undefined>();

  useEffect(() => {
    if (alreadyApproved && !signedHere) {
      setState('signed');
    }
  }, [alreadyApproved, signedHere]);

  async function handleSign() {
    if (alreadyApproved || state !== 'idle') return;
    const priceCap =
        mandate.price_cap ??
        mandate.constraints?.price_lt ??
        (mandate.constraints as {price_cap?: number}|undefined)?.price_cap;
    if (!priceCap || priceCap <= 0) {
      devWarn('TrustedSurface', 'approve blocked — invalid price_cap', {
        item_id: mandate.item_id,
        price_cap: mandate.price_cap,
        price_lt: mandate.constraints?.price_lt,
      });
      return;
    }
    devLog('TrustedSurface', 'Approve & Sign START', {
      item_id: mandate.item_id,
      price_cap: priceCap,
      payment_method: mandate.payment_method ?? 'card',
    });
    setPortalError(undefined);
    setPortalUrl(undefined);
    setState('signing');
    try {
      const paymentMethod: 'card' | 'x402' =
        mandate.payment_method === 'x402' ? 'x402' : 'card';
      const displayName = itemName ?? mandate.item_name ?? mandate.item_id;
      const signed = await trustedSurface.confirmViaPortal(
          {
            sessionId,
            priceCap,
            paymentMethod,
            itemId: mandate.item_id,
            itemName: displayName,
            presenceMode: 'hnp',
          },
          {onPortalUrl: setPortalUrl},
      );
      if (!signed) {
        setPortalError(
            'Trusted Surface confirmation failed or timed out. Open the portal link and confirm, then try again.',
        );
        setState('idle');
        return;
      }
      const mandateRequest: MandateApprovalData = {
        item_id: mandate.item_id,
        item_name: mandate.item_name,
        price_cap: priceCap,
        qty: mandate.qty ?? 1,
        constraints: {
          price_lt: mandate.constraints?.price_lt ?? priceCap,
        },
        matches: Array.isArray(mandate.matches)
          ? mandate.matches.map((m) => ({
              item_id: m.item_id,
              name: m.name,
            }))
          : undefined,
        payment_method: paymentMethod,
      };
      setState('signed');
      setSignedHere(true);
      setPortalUrl(undefined);
      devLog('TrustedSurface', 'portal signed — dispatching mandate_approved');
      setTimeout(() => onApprove(mandateRequest), 300);
    } catch {
      setPortalError('Trusted Surface connection error.');
      setState('idle');
    }
  }

  const priceCap =
      mandate.price_cap ??
      mandate.constraints?.price_lt ??
      (mandate.constraints as {price_cap?: number}|undefined)?.price_cap ??
      0;
  const qty = mandate.qty ?? 1;
  const canApprove = priceCap > 0 && Boolean(mandate.item_id);
  const current = currentPrice ?? mandate.current_price;
  const hasCurrentPrice = current != null && current > 0;
  const gap = hasCurrentPrice ? current - priceCap : 0;
  const pct = hasCurrentPrice ? Math.round((priceCap / current) * 100) : 0;

  const availabilityMode =
    !isFlightMerchant(merchant) &&
    (mandate.constraint_focus === 'availability' ||
      (mandate.constraint_focus == null && mandate.available === false));
  const displayName = itemName ?? mandate.item_name ?? mandate.item_id;
  const showReference = shouldShowItemReferenceRow(
      merchant,
      mandate.item_id,
      displayName,
  );

  return (
    <div className="msg-agent mandate-approval-container">
      <div className="mandate-card">
        {/* Header */}
        <div className="mandate-header">
          <div className="icon-wrapper">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M8 2L10.5 6.5H14L10.5 9L12 13.5L8 11L4 13.5L5.5 9L2 6.5H5.5L8 2Z"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="title-container">
            <div className="title">Trusted Surface For Mandates</div>
            <div className="subtitle">AP2 · Open Mandates</div>
          </div>
        </div>

        {/* Body */}
        <div className="mandate-body">
          <div className="item-section">
            <div className="section-label">Item</div>
            <div className="item-name">{displayName}</div>
            {showReference && (
              <div className="item-id item-id-muted">
                {formatItemReferenceValue(
                    merchant,
                    mandate.item_id,
                    displayName,
                )}
              </div>
            )}
          </div>

          {availabilityMode ? (
            <>
              <div className="details-grid details-grid-availability">
                {[
                  {
                    label: 'Budget (max)',
                    value: `$${priceCap}`,
                    accent: '#60a5fa',
                  },
                  {
                    label: 'Availability',
                    value: mandate.available
                      ? 'In stock'
                      : 'Not yet — awaiting drop',
                    accent: mandate.available ? '#34d399' : '#fbbf24',
                  },
                  {label: 'Qty', value: String(qty), accent: '#94a3b8'},
                ].map((f) => (
                  <div key={f.label} className="grid-item">
                    <div className="item-label">{f.label}</div>
                    <div className="item-value" style={{color: f.accent}}>
                      {f.value}
                    </div>
                  </div>
                ))}
              </div>

              <div className="gap-indicator gap-indicator-availability">
                <div className="gap-header">
                  <span className="gap-label">Trigger condition</span>
                  <span className="gap-status pending">
                    Availability + budget
                  </span>
                </div>
                <p className="gap-prose">
                  Agent will purchase when the item becomes available and price
                  is within your <span className="highlight">${priceCap}</span>{' '}
                  budget.
                </p>
              </div>

              {hasCurrentPrice && (
                <div className="reference-price-note">
                  Reference price: ${current!.toFixed(2)} (list)
                </div>
              )}
            </>
          ) : (
            <>
              <div className="details-grid">
                {[
                  {
                    label: 'Max Price',
                    value: `$${priceCap}`,
                    accent: '#60a5fa',
                  },
                  {
                    label: 'Current',
                    value: hasCurrentPrice ? `$${current!.toFixed(2)}` : '—',
                    accent: '#f87171',
                  },
                  {label: 'Qty', value: String(qty), accent: '#94a3b8'},
                ].map((f) => (
                  <div key={f.label} className="grid-item">
                    <div className="item-label">{f.label}</div>
                    <div className="item-value" style={{color: f.accent}}>
                      {f.value}
                    </div>
                  </div>
                ))}
              </div>

              {hasCurrentPrice && (
                <div className="gap-indicator">
                  <div className="gap-header">
                    <span className="gap-label">Price gap to trigger</span>
                    <span
                      className={`gap-status ${gap <= 0 ? 'met' : 'pending'}`}>
                      {gap <= 0
                        ? `✓ condition met`
                        : `-$${gap.toFixed(2)} needed`}
                    </span>
                  </div>
                  <div className="progress-track">
                    <div
                      className={`progress-bar ${gap <= 0 ? 'met' : 'pending'}`}
                      style={{width: `${Math.min(Math.max(pct, 0), 100)}%`}}
                    />
                  </div>
                </div>
              )}
            </>
          )}

          {/* Payment method row */}
          <div className="fop-row">
            <svg width="32" height="20" viewBox="0 0 32 20" fill="none">
              <rect
                width="32"
                height="20"
                rx="3"
                fill="#1a1f3c"
                stroke="#2d3555"
                strokeWidth="0.5"
              />
              <rect
                x="0"
                y="4"
                width="32"
                height="3"
                fill="#ca8a04"
                opacity="0.6"
              />
              <rect
                x="4"
                y="11"
                width="10"
                height="2"
                rx="0.5"
                fill="#4b5563"
              />
              <rect
                x="4"
                y="14.5"
                width="6"
                height="1.5"
                rx="0.5"
                fill="#374151"
              />
            </svg>
            <div className="fop-details">
              <span className="fop-name">
                {formatPaymentDisplay(
                    mandate.payment_method === 'x402' ? 'x402' : 'card',
                    mandate.payment_method_description,
                ).label}
              </span>
              <span className="fop-badge">
                {formatPaymentDisplay(
                    mandate.payment_method === 'x402' ? 'x402' : 'card',
                    mandate.payment_method_description,
                ).badge}
              </span>
            </div>
          </div>

          <div className="info-banner">
            Approving opens the H5 Trusted Surface portal. Confirm the frozen
            mandate there; the agent will purchase autonomously when{' '}
            {availabilityMode ? 'the item is available and within' : 'price ≤'}{' '}
            <span className="highlight">${priceCap}</span>
            {availabilityMode ? ' budget' : ''}.
          </div>

          {portalError && state === 'idle' && (
            <div className="info-banner" style={{borderColor: '#f87171'}}>
              {portalError}
            </div>
          )}

          {triggerCurl && availabilityMode && (
            <TriggerCurlBox
              curl={triggerCurl}
              label="Simulate drop (HNP — after approve, before purchase):"
              hint="Optional before signing; required before monitoring can auto-buy."
            />
          )}

          {!canApprove && state === 'idle' && (
            <div className="info-banner" style={{borderColor: '#f87171'}}>
              Budget is missing or invalid — ask the agent to set a price cap
              before approving.
            </div>
          )}

          {state === 'idle' && (
            <div className="action-buttons">
              <button
                type="button"
                className="approve-button"
                onClick={handleSign}
                disabled={!canApprove}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M7 1L8.8 4.8L13 5.3L10 8.2L10.7 12.4L7 10.5L3.3 12.4L4 8.2L1 5.3L5.2 4.8L7 1Z"
                    stroke="white"
                    strokeWidth="1.2"
                    fill="rgba(255,255,255,.2)"
                    strokeLinejoin="round"
                  />
                </svg>
                Approve & Sign
              </button>
              <button type="button" className="reject-button" onClick={onReject}>
                Reject
              </button>
            </div>
          )}

          {state === 'signing' && (
            <div className="signing-state">
              <div className="spinner" />
              Waiting for Trusted Surface confirmation…
              {portalUrl && (
                <p style={{marginTop: 12}}>
                  <a
                    href={portalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="highlight">
                    Open Trusted Surface to confirm
                  </a>
                </p>
              )}
            </div>
          )}

          {state === 'signed' && (
            <div className="signed-state">
              <div className="success-badge">
                <svg width="10" height="10" viewBox="0 0 10 10">
                  <path
                    d="M2 5l2 2 4-4"
                    stroke="white"
                    strokeWidth="1.5"
                    fill="none"
                    strokeLinecap="round"
                    strokeDasharray="24"
                    strokeDashoffset="0"
                  />
                </svg>
              </div>
              <span className="status-text">
                {signedHere ? 'Mandate signed' : 'Mandate already signed'}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
