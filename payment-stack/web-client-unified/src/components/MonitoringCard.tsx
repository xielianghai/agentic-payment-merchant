import type {MonitoringStatus, ChatMessage} from '../types';
import type {MerchantKey} from '../config';
import {shouldShowItemReferenceRow, resolveMonitoringDisplayName} from '../utils/itemDisplay';
import {TriggerCurlBox} from './TriggerCurlBox';
import './MonitoringCard.scss';

interface Props {
  status: MonitoringStatus;
  onCheckNow?: () => void;
  triggerCurl?: string;
  pollIntervalSeconds?: number;
  backendSchedulerMinutes?: number;
  itemName?: string;
  merchant?: MerchantKey;
  messages?: ChatMessage[];
}

export function MonitoringCard({
  status,
  onCheckNow,
  triggerCurl,
  pollIntervalSeconds,
  backendSchedulerMinutes,
  itemName,
  merchant = 'shoe',
  messages,
}: Props) {
  const current = status.current_price ?? status.price_cap;
  const available = status.available ?? false;
  const withinBudget =
      status.current_price != null && status.current_price <= status.price_cap;
  const constraintsMet = status.meets_constraints === true;
  const readyToBuy = constraintsMet && available;
  const pct =
    current > 0
      ? Math.min(100, Math.round((status.price_cap / current) * 100))
      : 100;
  const displayName = resolveMonitoringDisplayName(
      merchant,
      status,
      itemName,
      messages,
  );
  const showReference = shouldShowItemReferenceRow(
      merchant,
      status.item_id,
      displayName,
  );

  return (
    <div className="msg-agent monitoring-card-container">
      <div className="monitoring-card">
        <div className="monitoring-header">
          <div className="status-dot" />
          <span className="title">Monitoring Board</span>
        </div>
        <div className="item-name">
          {displayName}
          {showReference && (
            <span className="item-id">{status.item_id}</span>
          )}
        </div>

        <div className="status-grid">
          <div className="status-cell">
            <span className="cell-label">Price</span>
            <span
              className={`cell-value ${status.current_price != null ? 'has-price' : 'no-price'}`}>
              {status.current_price != null
                ? `$${current.toFixed(2)}`
                : '— checking'}
            </span>
          </div>
          <div className="status-cell">
            <span className="cell-label">Target</span>
            <span className="cell-value target">${status.price_cap}</span>
          </div>
          <div className="status-cell">
            <span className="cell-label">Available</span>
            <span
              className={`cell-value ${available ? 'available-yes' : 'available-no'}`}>
              {available ? '✓ In stock' : '✗ Not yet'}
            </span>
          </div>
          <div className="status-cell">
            <span className="cell-label">Constraints</span>
            <span
              className={`cell-value ${
                readyToBuy ? 'constraints-met' :
                constraintsMet ? 'constraints-partial' :
                withinBudget && available ? 'constraints-pending' :
                'constraints-no'
              }`}>
              {readyToBuy
                  ? '✓ Ready to buy'
                  : constraintsMet
                      ? '✓ Price OK'
                      : withinBudget && available
                          ? '⏳ Verifying'
                          : '✗ Not yet'}
            </span>
          </div>
        </div>

        <div className="progress-track">
          <div className="progress-bar" style={{width: `${pct}%`}} />
        </div>
        <div className="info-text">
          {readyToBuy
              ? 'Conditions met — backend scheduler will complete purchase on the next tick.'
              : withinBudget && available && !constraintsMet
                  ? 'Price is within budget and seats are available, but mandate constraints are still being verified. Backend scheduler checks every few seconds.'
                  : 'Purchase will execute automatically when the item is available and mandate constraints are satisfied.'}
        </div>
        {triggerCurl && (
          <TriggerCurlBox
            curl={triggerCurl}
            hint={
                backendSchedulerMinutes != null ?
                    'Run in a terminal to simulate a drop. Backend scheduler will detect the price change on its next tick.' :
                    'Run in a terminal, then say “check now” or wait for auto-poll.'
            }
          />
        )}
        {backendSchedulerMinutes != null && (
          <p className="poll-text">
            Backend scheduler checks every {backendSchedulerMinutes} min
            {pollIntervalSeconds ?
                ` (status refreshes every ${pollIntervalSeconds}s)` :
                ''}
          </p>
        )}
        {!backendSchedulerMinutes && pollIntervalSeconds && (
          <p className="poll-text">
            Auto-checking every {pollIntervalSeconds}s
          </p>
        )}
        {onCheckNow && (
          <button onClick={onCheckNow} className="check-button">
            Check now
          </button>
        )}
      </div>
    </div>
  );
}
