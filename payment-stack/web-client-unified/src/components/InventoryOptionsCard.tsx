import {useState} from 'react';
import type {InventoryMatch, InventoryOptionsArtifact} from '../types';
import {isFlightMerchant, type MerchantKey} from '../config';
import {
  extractRouteFromProse,
  inventoryMatchToFlightRow,
} from '../utils/flightTable';
import {FlightOptionsCard} from './FlightOptionsCard';
import {TriggerCurlBox} from './TriggerCurlBox';
import './InventoryOptionsCard.scss';

interface Props {
  inventory: InventoryOptionsArtifact;
  onSelect?: (itemId: string) => void;
  /** Dev helper: simulate drop before HP purchase can continue. */
  triggerCurl?: string;
  hpFlow?: boolean;
  merchantKey?: MerchantKey;
}

function ItemRow({
  item,
  selected,
  onClick,
}: {
  item: InventoryMatch;
  selected: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      className={`item-card ${onClick ? 'clickable' : ''} ${selected ? 'selected' : ''}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onClick?.()}>
      <div className="row-content">
        {selected && (
          <div className="selected-icon">
            <svg width="8" height="8" viewBox="0 0 8 8">
              <path
                d="M1.5 4l2 2 3-3"
                stroke="white"
                strokeWidth="1.5"
                fill="none"
                strokeLinecap="round"
              />
            </svg>
          </div>
        )}
        {!selected && <div className="unselected-circle" />}
        <div className="item-details">
          <div className="item-name">{item.name}</div>
          <div className="item-id">{item.item_id}</div>
        </div>
      </div>
      <div className="price-wrapper">
        <div className="item-price">${item.price.toFixed(2)}</div>
        {item.stock != null && (
          <div className="item-stock">{item.stock} in stock</div>
        )}
      </div>
    </div>
  );
}

export function InventoryOptionsCard({
  inventory,
  onSelect,
  triggerCurl,
  hpFlow = false,
  merchantKey = 'shoe',
}: Props) {
  const [userSelected, setUserSelected] = useState<string | undefined>(
    inventory.selected,
  );
  const [hasConfirmed, setHasConfirmed] = useState(false);
  const selected = userSelected ?? inventory.selected ?? '';
  const canConfirm = !!onSelect && !!selected && !hasConfirmed;

  if (isFlightMerchant(merchantKey)) {
    const rows = inventory.matches.map(inventoryMatchToFlightRow);
    const first = inventory.matches[0];
    const route = extractRouteFromProse(first?.name ?? '');
    return (
      <div className="inventory-options-container flight-inventory-wrap">
        <FlightOptionsCard rows={rows} route={route} />
        {canConfirm && (
          <button
            onClick={() => {
              setHasConfirmed(true);
              onSelect?.(selected);
            }}
            className="confirm-button">
            Confirm selection
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="msg-agent inventory-options-container">
      <div className="header-wrapper">
        <div className="icon-wrapper">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path
              d="M2 5l2 2 4-4"
              stroke="#34d399"
              strokeWidth="1.5"
              fill="none"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <span className="tool-label">Merchant MCP · search_inventory</span>
      </div>
      <div className="item-list">
        {inventory.matches.map((item) => (
          <ItemRow
            key={item.item_id}
            item={item}
            selected={item.item_id === selected}
            onClick={onSelect ? () => setUserSelected(item.item_id) : undefined}
          />
        ))}
      </div>
      <p className="info-text">
        {hpFlow ? (
          inventory.matches.some((m) => m.available) ? (
            <>
              Drop is live — {inventory.matches.find((m) => m.available)?.stock ??
                inventory.matches[0]?.stock ?? '?'}{' '}
              in stock. Say <em>buy now</em> to continue checkout.
            </>
          ) : (
            <>
              Found {inventory.matches.length} SKU via Merchant MCP. Stock is 0
              until you simulate a drop (curl below — port <strong>8091</strong>
              ), then say <em>buy now</em> again or wait for the agent to
              re-check.
            </>
          )
        ) : (
          <>
            I&apos;ve queried the merchant inventory via Merchant MCP and found{' '}
            {inventory.matches.length} option
            {inventory.matches.length === 1 ? '' : 's'} above. Please select
            which item you want, then I&apos;ll create the purchase mandate and
            start monitoring the price.
          </>
        )}
      </p>
      {triggerCurl && !inventory.matches.some((m) => m.available) && (
        <TriggerCurlBox
          curl={triggerCurl}
          label="Run in terminal (unified demo port 8091):"
          hint="Copy and run exactly — not port 8081. Then say buy now again."
        />
      )}
      <div className="status-text">
        {onSelect ? (
          selected ? (
            <>
              Selected <span className="selected-item-id">{selected}</span>
              {hasConfirmed
                ? '. Creating mandate…'
                : '. Click &quot;Confirm selection&quot; to create the mandate.'}
            </>
          ) : (
            'Choose an option above.'
          )
        ) : (
          <>
            Selected <span className="selected-item-id">{selected || '—'}</span>
          </>
        )}
      </div>
      {canConfirm && (
        <button
          onClick={() => {
            setHasConfirmed(true);
            onSelect?.(selected);
          }}
          className="confirm-button">
          Confirm selection
        </button>
      )}
    </div>
  );
}
