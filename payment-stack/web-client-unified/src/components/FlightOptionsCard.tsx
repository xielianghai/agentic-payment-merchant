import type {FlightRouteHint, FlightTableRow} from '../utils/flightTable';
import {formatMoney} from '../config';
import './FlightOptionsCard.scss';

interface Props {
  rows: FlightTableRow[];
  route?: FlightRouteHint;
  /** Short intro line above the cards (agent prose). */
  subtitle?: string;
}

function routeLabel(route?: FlightRouteHint): string | undefined {
  if (!route?.from && !route?.to) return undefined;
  const from = route.fromLabel
      ? `${route.fromLabel} (${route.from})`
      : route.from;
  const to = route.toLabel ? `${route.toLabel} (${route.to})` : route.to;
  if (from && to) return `${from} → ${to}`;
  return from ?? to;
}

function seatBadge(seats?: string): {label: string; low: boolean} | undefined {
  if (!seats?.trim()) return undefined;
  const low = /1 seat|only one|last seat/i.test(seats);
  return {label: seats, low};
}

function FlightRowCard({row}: {row: FlightTableRow}) {
  const badge = seatBadge(row.seats);
  const when = [row.date, row.time].filter(Boolean).join(' · ');

  return (
    <div className="flight-row-card">
      <div className="flight-main">
        <div className="flight-no">{row.flightNo}</div>
        <div className="flight-meta">
          {when && <div className="flight-when">{when}</div>}
          {row.cabin && <div className="flight-cabin">{row.cabin}</div>}
        </div>
      </div>
      <div className="flight-side">
        <div className="flight-price">
          {formatMoney(row.price, row.currency)}
        </div>
        {badge && (
          <div className={`flight-seats ${badge.low ? 'low' : ''}`}>
            {badge.label}
          </div>
        )}
      </div>
    </div>
  );
}

export function FlightOptionsCard({rows, route, subtitle}: Props) {
  const routeText = routeLabel(route);
  const count = rows.length;

  return (
    <div className="msg-agent flight-options-container">
      <div className="header-wrapper">
        <div className="icon-wrapper" aria-hidden="true">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <path
              d="M2 16l20-5-4 2 2 5-4-1-3 4-3-1 4-4-2z"
              stroke="#60a5fa"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="header-copy">
          <span className="tool-label">Flight search</span>
          {routeText && <span className="route-label">{routeText}</span>}
        </div>
      </div>

      {subtitle && <p className="subtitle">{subtitle}</p>}

      <div className="flight-list">
        {rows.map((row, idx) => (
          <FlightRowCard
            key={row.itemId ?? `${row.flightNo}-${row.date}-${idx}`}
            row={row}
          />
        ))}
      </div>

      <p className="info-text">
        {count === 1
            ? 'One flight matches your route — review details above before continuing.'
            : `${count} flights match your route — pick one to continue booking.`}
      </p>
    </div>
  );
}
