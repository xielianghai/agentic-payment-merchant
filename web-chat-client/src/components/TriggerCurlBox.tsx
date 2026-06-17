import {useState} from 'react';
import './TriggerCurlBox.scss';

interface Props {
  curl: string;
  label?: string;
  hint?: string;
}

export function TriggerCurlBox({
  curl,
  label = 'Simulate drop (price + stock):',
  hint,
}: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(curl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore — user can still select the code block */
    }
  };

  return (
    <div className="trigger-curl-box">
      <div className="trigger-curl-header">
        <div className="trigger-curl-label">{label}</div>
        <button
          type="button"
          className="trigger-curl-copy"
          onClick={handleCopy}
          aria-label="Copy curl command">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {hint && <div className="trigger-curl-hint">{hint}</div>}
      <code className="trigger-curl-code">{curl}</code>
    </div>
  );
}
