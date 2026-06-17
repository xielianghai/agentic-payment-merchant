import type {ProductPreviewUnavailable} from '../types';

const parsePrice = (v: unknown): number|undefined => {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const cleaned = v.replace(/[$,]/g, '').trim();
    const n = Number(cleaned);
    return Number.isNaN(n) ? undefined : n;
  }
  return undefined;
};

const emptyToUndef = (v: unknown): string|undefined =>
    typeof v === 'string' && v.trim() ? v.trim() : undefined;

const firstString = (...values: unknown[]): string|undefined => {
  for (const v of values) {
    const s = emptyToUndef(v);
    if (s) return s;
  }
  return undefined;
};

const slugToSubtitle = (slug: string): string =>
    slug.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/**
 * Coerce loose LLM-emitted JSON into a typed ProductPreviewUnavailable.
 * Accepts alternate field names (item_name, budget, slug) common in agent output.
 */
export function normalizeProductPreviewUnavailable(
    raw: Record<string, unknown>,
    ): ProductPreviewUnavailable|undefined {
  if (raw?.type !== 'product_preview_unavailable') return undefined;

  const product =
      typeof raw.product === 'object' && raw.product != null &&
          !Array.isArray(raw.product) ?
          raw.product as Record<string, unknown> :
          undefined;

  const productName = firstString(
      raw.product_name,
      raw.item_name,
      raw.name,
      product?.name,
      product?.item_name,
  );
  if (!productName) return undefined;

  const itemId = firstString(product?.item_id, raw.item_id);
  const slug = firstString(raw.slug, itemId);

  const productSubtitle =
      firstString(raw.product_subtitle, raw.subtitle, raw.description) ??
      (slug ? slugToSubtitle(slug.replace(/-/g, '_')) : undefined);

  return {
    type: 'product_preview_unavailable',
    product_name: productName,
    product_subtitle: productSubtitle,
    image_emoji: firstString(raw.image_emoji),
    typical_list_price: parsePrice(
        raw.typical_list_price ?? raw.budget ?? raw.price ?? raw.list_price ??
            product?.price ?? product?.typical_list_price,
    ),
    drop_scheduled_hint: firstString(
        raw.drop_scheduled_hint,
        raw.drop_hint,
        raw.drop,
    ),
    sku_preview_id:
        firstString(raw.sku_preview_id, itemId) ??
        (slug ? `preview_${slug}` : undefined),
  };
}
