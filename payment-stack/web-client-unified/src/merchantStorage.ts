import {DEFAULT_MERCHANT, normalizeMerchantKey, type MerchantKey} from './config';

const STORAGE_KEY = 'ap2_unified_merchant';

export function loadMerchant(): MerchantKey {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_MERCHANT;
    return normalizeMerchantKey(raw);
  } catch {
    return DEFAULT_MERCHANT;
  }
}

export function saveMerchant(merchant: MerchantKey): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, merchant);
  } catch {
    // ignore quota / private mode
  }
}
