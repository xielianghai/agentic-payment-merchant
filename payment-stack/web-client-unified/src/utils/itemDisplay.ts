import {isFlightMerchant, type MerchantKey} from '../config';
import type {ChatMessage, MonitoringStatus} from '../types';

/** HEG routing keys slugged for MCP (e.g. rt_1_1_ff16fd912e_0). */
export function isInternalFlightItemId(itemId: string): boolean {
  return /^rt_\d/i.test(itemId.trim());
}

/** Human-readable slug (sin_pvg_20260610_y_0) vs opaque routing key. */
export function isReadableFlightItemId(itemId: string): boolean {
  const id = itemId.trim().toLowerCase();
  if (isInternalFlightItemId(id)) return false;
  return /^[a-z]{3}_[a-z]{3}_\d{8}_[a-z]_\d+$/.test(id);
}

const CABIN_LABELS: Record<string, string> = {
  y: 'Economy',
  c: 'Business',
  f: 'First',
  j: 'Business',
};

/** Turn sin_pvg_20260610_y_0 into a short route label. */
export function formatReadableFlightSlug(itemId: string): string | undefined {
  const id = itemId.trim().toLowerCase();
  const m = id.match(/^([a-z]{3})_([a-z]{3})_(\d{8})_([a-z])_\d+$/);
  if (!m) return undefined;
  const [, dep, arr, ymd, cabin] = m;
  const date = `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;
  const cabinLabel = CABIN_LABELS[cabin] ?? cabin.toUpperCase();
  return `${dep.toUpperCase()} → ${arr.toUpperCase()} · ${date} · ${cabinLabel}`;
}

/** Scan chat artifacts for a display name tied to item_id. */
export function findItemNameForId(
    messages: ChatMessage[],
    itemId: string,
): string | undefined {
  if (!itemId.trim()) return undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    const data = messages[i].artifactData as {type?: string} | undefined;
    if (!data?.type) continue;
    if (data.type === 'mandate_request') {
      const m = data as {item_id?: string; item_name?: string};
      if (m.item_id === itemId && m.item_name?.trim()) return m.item_name.trim();
    }
    if (data.type === 'monitoring') {
      const mon = data as MonitoringStatus;
      if (mon.item_id === itemId && mon.item_name?.trim()) return mon.item_name.trim();
    }
    if (data.type === 'inventory_options') {
      const inv = data as {
        matches?: Array<{item_id: string; name: string}>;
      };
      const match = inv.matches?.find((x) => x.item_id === itemId);
      if (match?.name?.trim()) return match.name.trim();
    }
    if (data.type === 'purchase_complete') {
      const p = data as {item_id?: string; item_name?: string};
      if (p.item_id === itemId && p.item_name?.trim()) return p.item_name.trim();
    }
  }
  return undefined;
}

/** Best label for Monitoring Board (hide opaque HEG routing keys when possible). */
export function resolveMonitoringDisplayName(
    merchant: MerchantKey,
    status: MonitoringStatus,
    fallbackName?: string,
    messages?: ChatMessage[],
): string {
  const candidates = [
    status.item_name?.trim(),
    fallbackName?.trim(),
    messages ? findItemNameForId(messages, status.item_id) : undefined,
  ].filter((v): v is string => Boolean(v && v !== status.item_id));

  if (candidates.length > 0) return candidates[0];

  if (isFlightMerchant(merchant)) {
    const fromSlug = formatReadableFlightSlug(status.item_id);
    if (fromSlug) return fromSlug;
    if (isInternalFlightItemId(status.item_id)) {
      return 'Flight booking';
    }
  }

  return status.item_id;
}

export function itemReferenceLabel(merchant: MerchantKey): string {
  return isFlightMerchant(merchant) ? 'Reference' : 'SKU';
}

/** Whether to show a second row with item_id under the display name. */
export function shouldShowItemReferenceRow(
    _merchant: MerchantKey,
    itemId?: string,
    itemName?: string,
): boolean {
  if (!itemId?.trim()) return false;
  if (!itemName?.trim()) return true;
  if (itemId === itemName) return false;
  return true;
}

export function formatItemReferenceValue(
    merchant: MerchantKey,
    itemId: string,
    itemName?: string,
): string {
  if (isFlightMerchant(merchant) && isReadableFlightItemId(itemId)) {
    return formatReadableFlightSlug(itemId) ?? itemId.replace(/_/g, ' ').toUpperCase();
  }
  if (isFlightMerchant(merchant) && itemName) {
    const flightNo = itemName.match(/\b([A-Z]{2}\d+)\b/)?.[1];
    if (flightNo) return flightNo;
  }
  return itemId;
}
