import type {ProductPreviewUnavailable} from '../types';
import {TriggerCurlBox} from './TriggerCurlBox';
import './ProductPreviewUnavailableCard.scss';

interface Props {
  preview: ProductPreviewUnavailable;
  triggerCurl?: string;
}

export function ProductPreviewUnavailableCard({preview, triggerCurl}: Props) {
  return (
    <div className="msg-agent product-preview-unavailable-container">
      <div className="product-preview-card">
        {/* Badge */}
        <div className="preview-badge">Preview · not purchasable yet</div>

        {/* Emoji visual */}
        {preview.image_emoji && (
          <div className="emoji-display">{preview.image_emoji}</div>
        )}

        {/* Product info */}
        <div className="product-name">{preview.product_name}</div>
        {preview.product_subtitle && (
          <div className="product-subtitle">{preview.product_subtitle}</div>
        )}

        {/* Metadata grid */}
        <div className="metadata-grid">
          {preview.typical_list_price != null && (
            <div className="meta-item">
              <div className="meta-label">Typical list price</div>
              <div className="meta-value price">
                ${preview.typical_list_price}
              </div>
            </div>
          )}
          {preview.drop_scheduled_hint && (
            <div className="meta-item">
              <div className="meta-label">Drop</div>
              <div className="meta-value drop">
                {preview.drop_scheduled_hint}
              </div>
            </div>
          )}
        </div>

        {/* Status bar */}
        <div className="status-bar">
          <div className="status-dot" />
          <span className="status-text">Awaiting drop</span>
        </div>
        {triggerCurl && (
          <TriggerCurlBox
            curl={triggerCurl}
            label="Simulate drop (HNP — for after mandate / monitoring):"
            hint="Save for later; monitoring card will show the same command once signed."
          />
        )}
      </div>
    </div>
  );
}
