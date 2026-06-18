import type {InventoryMatch} from '../types';

/** One row from an agent flight search table or MCP match. */
export interface FlightTableRow {
  flightNo: string;
  date: string;
  time: string;
  cabin: string;
  price: number;
  currency: string;
  seats?: string;
  itemId?: string;
}

export interface FlightRouteHint {
  from?: string;
  to?: string;
  fromLabel?: string;
  toLabel?: string;
}

export interface ParsedFlightTable {
  rows: FlightTableRow[];
  route: FlightRouteHint;
  proseBefore: string;
  proseAfter: string;
}

function splitTableRow(line: string): string[] {
  return line
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim());
}

function isSeparatorCell(cell: string): boolean {
  return /^:?-{2,}:?$/.test(cell.replace(/\s/g, ''));
}

function isSeparatorRow(cells: string[]): boolean {
  return cells.length > 0 && cells.every(isSeparatorCell);
}

function parsePrice(raw: string): {amount: number; currency: string} {
  const trimmed = raw.trim();
  const usd = trimmed.match(/^\$\s*([\d,]+(?:\.\d+)?)/);
  if (usd) {
    return {amount: Number(usd[1].replace(/,/g, '')), currency: 'USD'};
  }
  const generic = trimmed.match(/([\d,]+(?:\.\d+)?)/);
  return {
    amount: generic ? Number(generic[1].replace(/,/g, '')) : 0,
    currency: 'USD',
  };
}

function headerIndex(headers: string[], ...needles: string[]): number {
  const lower = headers.map((h) => h.toLowerCase());
  for (const needle of needles) {
    const idx = lower.findIndex((h) => h.includes(needle));
    if (idx >= 0) return idx;
  }
  return -1;
}

function rowFromCells(headers: string[], cells: string[]): FlightTableRow | undefined {
  if (cells.length < 3) return undefined;
  const flightIdx = headerIndex(headers, 'flight');
  const dateIdx = headerIndex(headers, 'date');
  const timeIdx = headerIndex(headers, 'time');
  const cabinIdx = headerIndex(headers, 'cabin', 'class');
  const priceIdx = headerIndex(headers, 'price');
  const seatsIdx = headerIndex(headers, 'seat');

  let flightNo = flightIdx >= 0 ? cells[flightIdx] : '';
  let date = dateIdx >= 0 ? cells[dateIdx] : '';
  let time = timeIdx >= 0 ? cells[timeIdx] : '';
  let cabin = cabinIdx >= 0 ? cells[cabinIdx] : '';
  let priceRaw = priceIdx >= 0 ? cells[priceIdx] : '';
  let seats = seatsIdx >= 0 ? cells[seatsIdx] : undefined;

  // Positional fallback when headers are missing or malformed.
  if (!flightNo || !/^[A-Z]{2}\d+/i.test(flightNo)) {
    const flightCell = cells.find((c) => /^[A-Z]{2}\d+/i.test(c));
    if (flightCell) flightNo = flightCell;
  }
  if (!flightNo) return undefined;

  if (!date) {
    date = cells.find((c) =>
        /\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b/i.test(c) ||
        /\d{4}-\d{2}-\d{2}/.test(c),
    ) ?? '';
  }
  if (!time) {
    time = cells.find((c) => /^\d{1,2}:\d{2}/.test(c)) ?? '';
  }
  if (!cabin) {
    cabin = cells.find((c) => /economy|business|first|\([A-Z]\)/i.test(c)) ?? '';
  }
  if (!priceRaw) {
    priceRaw = cells.find((c) => /\$|usd|\d+\.\d{2}/i.test(c)) ?? '';
  }
  if (!seats) {
    seats = cells.find((c) => /seat/i.test(c));
  }

  const {amount, currency} = parsePrice(priceRaw);
  return {
    flightNo: flightNo.replace(/\*+/g, '').trim(),
    date: date.replace(/\*+/g, '').trim(),
    time: time.replace(/\*+/g, '').trim(),
    cabin: cabin.replace(/\*+/g, '').trim(),
    price: amount,
    currency,
    seats: seats?.replace(/\*+/g, '').trim(),
  };
}

/** Extract SIN → PVG style route hints from surrounding prose. */
export function extractRouteFromProse(text: string): FlightRouteHint {
  const labeled = text.match(
      /([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{3})\)\s*(?:->|→|to)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{3})\)/,
  );
  if (labeled) {
    return {
      fromLabel: labeled[1].trim(),
      from: labeled[2].toUpperCase(),
      toLabel: labeled[3].trim(),
      to: labeled[4].toUpperCase(),
    };
  }
  const arrow = text.match(/\b([A-Z]{3})→([A-Z]{3})\b/);
  if (arrow) {
    return {from: arrow[1], to: arrow[2]};
  }
  const codes = text.match(/\b([A-Z]{3})\s*(?:->|→|to)\s*([A-Z]{3})\b/);
  if (codes) {
    return {from: codes[1], to: codes[2]};
  }
  return {};
}

/** Parse HEG MCP match label: ``SQ830 SIN→PVG 2026-07-21 09:30 (Y)``. */
export function parseFlightMatchName(name: string): Partial<FlightTableRow> {
  const m = name.match(
      /^(\S+)\s+([A-Z]{3})→([A-Z]{3})\s+(\S+(?:\s+\S+)?)\s+\(([A-Z])\)$/i,
  );
  if (!m) return {};
  const [, flightNo, , , when, cabinCode] = m;
  const [datePart, timePart] = when.includes(' ')
      ? when.split(/\s+/, 2)
      : [when, ''];
  const cabinMap: Record<string, string> = {
    Y: 'Economy',
    C: 'Business',
    F: 'First',
    J: 'Business',
  };
  return {
    flightNo,
    date: datePart,
    time: timePart,
    cabin: `${cabinMap[cabinCode.toUpperCase()] ?? cabinCode} (${cabinCode.toUpperCase()})`,
  };
}

export function inventoryMatchToFlightRow(match: InventoryMatch): FlightTableRow {
  const parsed = parseFlightMatchName(match.name);
  return {
    flightNo: parsed.flightNo ?? match.name.split(/\s+/)[0] ?? 'Flight',
    date: parsed.date ?? '',
    time: parsed.time ?? '',
    cabin: parsed.cabin ?? '',
    price: match.price,
    currency: 'USD',
    seats:
        match.stock != null
            ? match.stock === 1
                ? '1 seat left'
                : `${match.stock} seats`
            : undefined,
    itemId: match.item_id,
  };
}

/** Detect and parse markdown flight tables embedded in agent prose. */
export function parseFlightTableFromText(text: string): ParsedFlightTable | undefined {
  const lines = text.split('\n');
  let tableStart = -1;
  let tableEnd = -1;
  let headers: string[] = [];
  const rows: FlightTableRow[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line.includes('|')) continue;

    // Some models collapse separator + first data row onto one line.
    const sublines = line.includes('||')
        ? line.split(/\|\|/).map((part, idx) => (idx === 0 ? `${part}|` : `|${part}`))
        : [line];

    for (const subline of sublines) {
      const cells = splitTableRow(subline);
      if (cells.length < 3) continue;

      if (tableStart < 0) {
        const joined = cells.join(' ').toLowerCase();
        if (!joined.includes('flight') && !joined.includes('cabin')) continue;
        headers = cells;
        tableStart = i;
        continue;
      }

      if (isSeparatorRow(cells)) continue;

      const row = rowFromCells(headers, cells);
      if (row) {
        rows.push(row);
        tableEnd = i;
      }
    }
  }

  if (rows.length === 0) return undefined;

  const proseBefore = lines.slice(0, tableStart).join('\n').trim();
  const proseAfter = lines.slice((tableEnd >= 0 ? tableEnd : tableStart) + 1)
      .join('\n')
      .trim();
  const route = extractRouteFromProse(text);

  return {rows, route, proseBefore, proseAfter};
}

/** True when text looks like a flight inventory answer (table or route prose). */
export function looksLikeFlightInventoryText(text: string): boolean {
  const lower = text.toLowerCase();
  if (parseFlightTableFromText(text)?.rows.length) return true;
  return (
      /\b([A-Z]{3})\s*(?:->|→|to)\s*([A-Z]{3})\b/.test(text) &&
      (lower.includes('flight') || lower.includes('economy') || /\b[A-Z]{2}\d{2,4}\b/.test(text))
  );
}
