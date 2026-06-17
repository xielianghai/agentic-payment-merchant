import {MERCHANT_TRIGGER_URL} from '../config';
import {normalizeSlugItemId} from './hnpMonitor';

/** Build merchant trigger curl for simulating a drop (price + stock). */
export function buildTriggerPriceDropCurl(
    itemId: string,
    price?: number,
    stock = 10,
): string {
  const dollars =
      price != null && price > 0 ? Math.round(price * 100) / 100 : 299;
  const params = new URLSearchParams({
    item_id: normalizeSlugItemId(itemId),
    price: String(dollars),
    stock: String(stock),
  });
  return `curl -X POST "${MERCHANT_TRIGGER_URL}/trigger-price-drop?${params.toString()}"`;
}

/** Agent prose indicating stock is not yet available (HP / HNP). */
export function isAwaitingStockMessage(text: string): boolean {
  const lower = text.toLowerCase();
  return (
      lower.includes('not available') ||
      lower.includes('not yet available') ||
      lower.includes('out of stock') ||
      lower.includes('stock = 0') ||
      lower.includes('stock=0') ||
      lower.includes('stock: 0') ||
      lower.includes('no inventory') ||
      lower.includes("hasn't been triggered") ||
      lower.includes('has not been triggered') ||
      lower.includes('drop has not') ||
      lower.includes('awaiting drop')
  );
}

/** Agent explaining how to fire the merchant trigger (HP / HNP). */
export function isTriggerHelpMessage(text: string): boolean {
  const lower = text.toLowerCase();
  return (
      lower.includes('simulate a drop') ||
      lower.includes('simulate drop') ||
      lower.includes('trigger server') ||
      lower.includes('trigger-price-drop') ||
      lower.includes('trigger/drop') ||
      lower.includes('how to trigger') ||
      lower.includes('price-drop curl') ||
      /run this curl/i.test(text)
  );
}

export function shouldShowTriggerCurl(text: string): boolean {
  return isAwaitingStockMessage(text) || isTriggerHelpMessage(text);
}

/** Pull item_id from agent text (backticks or explicit item_id). */
export function extractItemIdFromAgentText(text: string): string|undefined {
  const curlParam = text.match(/[?&]item_id=([a-z0-9_]+)/i);
  if (curlParam?.[1]) return curlParam[1];
  const idBold = text.match(/\*\*ID:\*\*\s*`([a-z0-9_]+)`/i);
  if (idBold?.[1]) return idBold[1];
  const idLabel = text.match(/\bID:\s*`([a-z0-9_]+)`/i);
  if (idLabel?.[1]) return idLabel[1];
  const backtick = text.match(/`([a-z0-9_]+)`/i);
  if (backtick?.[1]) return backtick[1];
  const labeled = text.match(/\bitem[_\s-]?id[:\s]+['"]?([a-z0-9_]+)/i);
  if (labeled?.[1]) return labeled[1];
  const productLine = text.match(
      /\*\*Product:\*\*[^\n]*\(([a-z0-9_]+)\)/i,
  );
  if (productLine?.[1]) return productLine[1];
  return undefined;
}
