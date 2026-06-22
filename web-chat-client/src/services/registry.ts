export interface RegistryMerchant {
  merchant_id: string;
  name: string;
  display_name_en: string;
  display_name_zh: string;
  protocols: string[];
  backend_base_url: string;
  capabilities: string[];
}

export const FLIGHT_REGISTRY_MERCHANT_ID = 'heg_flight';

const REGISTRY_URL =
  (import.meta as { env?: { VITE_REGISTRY_URL?: string } }).env
    ?.VITE_REGISTRY_URL ?? '/api/v1/registry/merchants';

let cachedMerchants: RegistryMerchant[] | null = null;
let cacheExpiresAt = 0;
const CACHE_TTL_MS = 5000;

export async function fetchRegistryMerchants(
  forceRefresh = false,
): Promise<RegistryMerchant[]> {
  const now = Date.now();
  if (!forceRefresh && cachedMerchants && now < cacheExpiresAt) {
    return cachedMerchants;
  }

  const response = await fetch(REGISTRY_URL);
  if (!response.ok) {
    throw new Error(`Registry fetch failed: ${response.status}`);
  }
  const payload = (await response.json()) as { data?: RegistryMerchant[] };
  const merchants = Array.isArray(payload.data) ? payload.data : [];
  cachedMerchants = merchants;
  cacheExpiresAt = now + CACHE_TTL_MS;
  return merchants;
}

export function isFlightMerchantRegistryActive(
  merchants: RegistryMerchant[],
): boolean {
  return merchants.some(
    (merchant) => merchant.merchant_id === FLIGHT_REGISTRY_MERCHANT_ID,
  );
}

export const FLIGHT_MERCHANT_UNAVAILABLE_MESSAGE =
  'No matching merchant products were found. Please try another merchant or product.';

export const FLIGHT_MERCHANT_UNAVAILABLE_MESSAGE_ZH =
  '当前没有找到对应的商家产品，请尝试其他商家或商品。';
