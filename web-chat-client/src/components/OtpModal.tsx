import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import './OtpModal.scss';

const MOCK_OTP = '123456';

type Props = {
  title?: string;
  subtitle?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function OtpModal({
  title = 'Enter verification code',
  subtitle = 'A one-time code has been sent. Enter it to continue.',
  onConfirm,
  onCancel,
}: Props) {
  const [code, setCode] = useState('');
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function handleConfirm() {
    if (code === MOCK_OTP) {
      onConfirm();
    } else {
      setError(true);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && code.length === 6) {
      handleConfirm();
    }
  }

  return createPortal(
    <div className="otp-modal-overlay">
      <div className="otp-modal-card">
        <div className="otp-modal-header">
          <span className="otp-modal-title">{title}</span>
          <span className="otp-modal-subtitle">{subtitle}</span>
        </div>
        <input
          ref={inputRef}
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          className={`otp-modal-input ${error ? 'error' : ''}`}
          maxLength={6}
          placeholder="123456"
          value={code}
          onChange={(e) => {
            const next = e.target.value.replace(/\D/g, '').slice(0, 6);
            setCode(next);
            if (error) setError(false);
          }}
          onKeyDown={handleKeyDown}
        />
        {error && (
          <div className="otp-modal-error">验证码错误，请输入 123456</div>
        )}
        <div className="otp-modal-actions">
          <button
            type="button"
            className="otp-modal-cancel"
            onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="otp-modal-confirm"
            onClick={handleConfirm}
            disabled={code.length !== 6}>
            Confirm
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
