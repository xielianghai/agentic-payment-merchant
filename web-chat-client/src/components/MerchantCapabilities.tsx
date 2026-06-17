import {
  getMerchantDemo,
  getScenarioStarterHints,
  type MerchantKey,
} from '../config';
import {isAutoMode, isFixedMode, type Ap2ModeConfig} from './ModePicker';

/**
 * Presentational block describing a merchant's capabilities and example
 * prompts. Reused by the empty-chat state (after a merchant is chosen) and by
 * the in-chat merchant_selected card (free-text selection).
 */
export const MerchantCapabilities = ({
  merchant,
  ap2Config,
  onTryExample,
  showHeading = true,
}: {
  merchant: MerchantKey;
  ap2Config: Ap2ModeConfig | null;
  onTryExample: (text: string) => void;
  showHeading?: boolean;
}) => {
  const merchantDemo = getMerchantDemo(merchant);
  const scenarioHints = getScenarioStarterHints(merchant);
  const hints = isAutoMode(ap2Config)
    ? [scenarioHints.hnp, scenarioHints.hp]
    : isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp'
      ? [scenarioHints.hp]
      : [scenarioHints.hnp];

  return (
    <div className="merchant-capabilities">
      {showHeading && (
        <div className="merchant-capabilities-header">
          <span className="merchant-capabilities-icon">{merchantDemo.icon}</span>
          <span className="merchant-capabilities-label">
            {merchantDemo.label}
          </span>
        </div>
      )}
      <div className="merchant-capabilities-subtitle">
        {isAutoMode(ap2Config) ? (
          <>{merchantDemo.autoSubtitle}</>
        ) : (
          <>
            {isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp'
              ? merchantDemo.fixedHpSubtitle
              : merchantDemo.fixedHnpSubtitle}
            <br />
            Payment rail: {isFixedMode(ap2Config) && ap2Config.payment_method}
          </>
        )}
      </div>

      <div className="scenario-hints">
        {hints.map((hint) => (
          <div
            key={hint.tag}
            className={`scenario-hint scenario-hint--${hint.accent}`}>
            <div className="scenario-hint-header">
              <span className="scenario-tag">{hint.tag}</span>
              <span className="scenario-title">{hint.title}</span>
            </div>
            <div className="scenario-flow">{hint.flow}</div>
            <button
              type="button"
              className="scenario-example"
              onClick={() => onTryExample(hint.example)}
              title="Click to copy into the message box">
              &quot;{hint.example}&quot;
            </button>
          </div>
        ))}
      </div>

      {isAutoMode(ap2Config) && (
        <p className="payment-hint">{scenarioHints.payment}</p>
      )}
    </div>
  );
};
