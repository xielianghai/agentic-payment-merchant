import {MERCHANT_PICKER_GREETING} from '../config';

/**
 * Conversational merchant picker shown when no merchant has been chosen yet.
 * Pure natural-language entry: the user describes what they want and the agent
 * infers the merchant (handled via merchant: "auto").
 */
export const MerchantPicker = () => {
  return (
    <div className="merchant-picker">
      <div className="icon">🛍️</div>
      <div className="title">AP2 Demo</div>
      <div className="merchant-picker-greeting">{MERCHANT_PICKER_GREETING}</div>

      <p className="suggestion-enter-hint">
        Type what you want below to begin, e.g. &quot;buy SuperShoe sneakers&quot;
        or &quot;book a flight&quot;.
      </p>
    </div>
  );
};
