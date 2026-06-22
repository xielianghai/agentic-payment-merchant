export const DEFAULT_CAPABILITY_VERSION = '2026-01-23'

const SCHEMA_URLS: Record<string, string> = {
  'dev.ucp.shopping.catalog.search': 'https://ucp.dev/2026-01-23/schemas/shopping/catalog_lookup.json',
  'dev.ucp.shopping.cart': 'https://ucp.dev/2026-01-23/schemas/shopping/cart.json',
  'dev.ucp.shopping.checkout': 'https://ucp.dev/2026-01-23/schemas/shopping/checkout.json',
  'dev.ucp.shopping.order': 'https://ucp.dev/2026-01-23/schemas/shopping/order.json',
  'dev.ucp.shopping.ap2_mandate': 'https://ucp.dev/2026-01-23/schemas/shopping/ap2_mandate.json',
}

export function resolveSchemaUrl(
  capabilityId: string,
  version: string = DEFAULT_CAPABILITY_VERSION,
): string | undefined {
  if (SCHEMA_URLS[capabilityId]) return SCHEMA_URLS[capabilityId]
  if (capabilityId.startsWith('dev.ucp.travel.hotel.')) {
    const suffix = capabilityId.replace('dev.ucp.travel.hotel.', '')
    return `https://ucp.dev/${version}/schemas/travel/hotel_${suffix}.json`
  }
  return undefined
}

export function defaultLineItemsSchema(vertical?: string): Record<string, unknown> {
  if (vertical === 'airline') {
    return { type: 'flight', fields: ['route', 'cabin', 'passenger_count'] }
  }
  if (vertical === 'hotel') {
    return {
      type: 'hotel',
      fields: ['hotel_id', 'room_type', 'check_in', 'check_out', 'guest_count'],
    }
  }
  if (vertical === 'travel') {
    return {
      type: 'travel_package',
      fields: ['package_id', 'destination', 'start_date', 'end_date', 'travelers'],
    }
  }
  return {}
}

export function defaultConfigJson(capabilityId: string): Record<string, unknown> {
  if (capabilityId === 'dev.ucp.shopping.ap2_mandate') {
    return { extends: 'dev.ucp.shopping.checkout' }
  }
  return {}
}

export function stringifyJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2)
}

export function parseJsonField(
  raw: string | undefined,
  fallback: Record<string, unknown> = {},
): Record<string, unknown> {
  if (!raw?.trim()) return fallback
  const parsed = JSON.parse(raw) as unknown
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('invalid_json_object')
  }
  return parsed as Record<string, unknown>
}
