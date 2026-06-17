import {useState} from 'react';
import './ModePicker.scss';

/** Agent decides HP/HNP and card/x402 from conversation (default). */
export const AUTO_UNIFIED_CONFIG: Ap2ModeConfig = {entry_mode: 'auto'};

export type Ap2ModeConfig =
  | {entry_mode: 'auto'}
  | {
      entry_mode: 'fixed';
      presence_mode: 'hp' | 'hnp';
      payment_method: 'card' | 'x402';
    };

const STORAGE_KEY = 'ap2_unified_config';

export function isAutoMode(config: Ap2ModeConfig | null): boolean {
  return config?.entry_mode === 'auto';
}

export function isFixedMode(
    config: Ap2ModeConfig | null,
    ): config is Extract<Ap2ModeConfig, {entry_mode: 'fixed'}> {
  return config?.entry_mode === 'fixed';
}

export function loadAp2Config(): Ap2ModeConfig | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Ap2ModeConfig;
    if (parsed.entry_mode === 'auto') return {entry_mode: 'auto'};
    if (
      parsed.entry_mode === 'fixed' &&
      (parsed.presence_mode === 'hp' || parsed.presence_mode === 'hnp') &&
      (parsed.payment_method === 'card' || parsed.payment_method === 'x402')
    ) {
      return parsed;
    }
    // Legacy: { presence_mode, payment_method } without entry_mode
    const legacy = parsed as {
      presence_mode?: string;
      payment_method?: string;
    };
    if (
      (legacy.presence_mode === 'hp' || legacy.presence_mode === 'hnp') &&
      (legacy.payment_method === 'card' || legacy.payment_method === 'x402')
    ) {
      return {
        entry_mode: 'fixed',
        presence_mode: legacy.presence_mode,
        payment_method: legacy.payment_method,
      };
    }
  } catch {
    // ignore
  }
  return null;
}

export function saveAp2Config(config: Ap2ModeConfig) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

type Props = {
  onConfirm: (config: Ap2ModeConfig) => void;
  onClose?: () => void;
  /** When true, user can dismiss back to chat (already has a config). */
  allowClose?: boolean;
};

export function ModePicker({onConfirm, onClose, allowClose}: Props) {
  const saved = loadAp2Config();
  const [showAdvanced, setShowAdvanced] = useState(
      saved != null && isFixedMode(saved),
  );

  function startAuto() {
    saveAp2Config(AUTO_UNIFIED_CONFIG);
    onConfirm(AUTO_UNIFIED_CONFIG);
  }

  function handleFixedSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const config: Ap2ModeConfig = {
      entry_mode: 'fixed',
      presence_mode: fd.get('presence') as 'hp' | 'hnp',
      payment_method: fd.get('payment') as 'card' | 'x402',
    };
    saveAp2Config(config);
    onConfirm(config);
  }

  return (
    <div className="mode-picker-overlay">
      <div className="mode-picker-card">
        {allowClose && onClose && (
          <button type="button" className="close-btn" onClick={onClose}>
            ×
          </button>
        )}
        <h2>AP2 Demo</h2>
        <p>
          By default, enter the <strong>unified scenario</strong>: say in chat whether
          you want a timed drop (delegated) or buy now, card or x402 — the agent
          calls <code>set_ap2_session_config</code> then runs the matching flow.
        </p>

        <button type="button" className="primary-btn" onClick={startAuto}>
          Start unified scenario (recommended)
        </button>

        <button
          type="button"
          className="link-btn"
          onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ?
              'Hide preset mode' :
              'Preset HP/HNP and payment method (demo)'}
        </button>

        {showAdvanced && (
          <form className="advanced-form" onSubmit={handleFixedSubmit}>
            <label>
              Presence
              <select
                name="presence"
                defaultValue={
                  isFixedMode(saved) ? saved.presence_mode : 'hnp'
                }>
                <option value="hnp">Human Not Present (delegated drop)</option>
                <option value="hp">Human Present (immediate checkout)</option>
              </select>
            </label>
            <label>
              Payment
              <select
                name="payment"
                defaultValue={
                  isFixedMode(saved) ? saved.payment_method : 'card'
                }>
                <option value="card">Card (MPP)</option>
                <option value="x402">x402 (PSP)</option>
              </select>
            </label>
            <button type="submit" className="secondary-btn">
              Start with preset mode
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
