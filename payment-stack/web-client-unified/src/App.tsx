import {useEffect, useRef, useState} from 'react';
import './App.scss';
import {MandateViewer} from './components/MandateViewer';
import {MessageRenderer} from './components/MessageRenderer';
import {
  AUTO_UNIFIED_CONFIG,
  isAutoMode,
  isFixedMode,
  loadAp2Config,
  ModePicker,
  saveAp2Config,
  type Ap2ModeConfig,
} from './components/ModePicker';
import {TypingIndicator} from './components/TypingIndicator';
import {
  defaultChatStarterMessage,
  getMerchantDemo,
  getScenarioStarterHints,
  type MerchantKey,
} from './config';
import {type ChatState, useChat} from './hooks/useChat';
import {loadMerchant, saveMerchant} from './merchantStorage';

// ==========================================
// SUB-COMPONENTS
// ==========================================

const AppHeader = ({
  usedServers,
  ap2Config,
  merchant,
  onMerchantChange,
  onOpenModeSettings,
}: {
  usedServers: Set<string>;
  ap2Config: Ap2ModeConfig;
  merchant: MerchantKey;
  onMerchantChange: (merchant: MerchantKey) => void;
  onOpenModeSettings: () => void;
}) => {
  const merchantDemo = getMerchantDemo(merchant);
  const presenceLabel = isAutoMode(ap2Config)
    ? 'Auto'
    : isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp'
      ? 'HP'
      : 'HNP';
  const paymentLabel = isAutoMode(ap2Config)
    ? 'Agent picks'
    : isFixedMode(ap2Config) && ap2Config.payment_method === 'x402'
      ? 'x402'
      : 'Card';
  const servers = [
    {
      label: 'Shopping Agent',
      key: 'Shopping Agent',
      className: 'server-shopping',
    },
    {label: 'Merchant MCP', key: 'Merchant MCP', className: 'server-merchant'},
    {
      label: 'Credential Provider MCP',
      key: 'Credential Provider MCP',
      className: 'server-credential',
    },
  ];

  return (
    <div className="app-header">
      <div className="logo-container">
        <span>{merchantDemo.icon}</span>
      </div>
      <div className="title-container">
        <div className="title">
          AP2 Demo
          <span className="flow-badge card">{presenceLabel}</span>
          <span className="flow-badge card">{paymentLabel}</span>
        </div>
        <div className="subtitle">
          {isAutoMode(ap2Config)
            ? merchantDemo.autoSubtitle
            : `A2A · ${isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp' ? 'Human Present' : 'Human Not Present'} · Merchant MCP · Credential Provider MCP`}
          {' · '}
          <button type="button" className="mode-settings-link" onClick={onOpenModeSettings}>
            Mode settings
          </button>
        </div>
      </div>
      <div className="merchant-switch">
        <label className="merchant-switch-label" htmlFor="merchant-select">
          Merchant
        </label>
        <select
          id="merchant-select"
          className="merchant-select"
          value={merchant}
          onChange={(e) => onMerchantChange(e.target.value as MerchantKey)}>
          <option value="shoe">SuperShoe</option>
          <option value="flight">Singapore Airlines</option>
        </select>
      </div>
      <div className="server-badges">
        {servers.map((b) => (
          <div
            key={b.key}
            className={`server-badge ${usedServers.has(b.key) ? 'active' : ''} ${b.className}`}>
            <div className="dot" />
            <span className="label">{b.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

type TabKey = 'chat' | 'mandates';

const TabBar = ({
  activeTab,
  onChange,
  mandateCount,
}: {
  activeTab: TabKey;
  onChange: (t: TabKey) => void;
  mandateCount: number;
}) => (
  <div className="tab-bar">
    <button
      className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
      onClick={() => onChange('chat')}>
      Chat
    </button>
    <button
      className={`tab ${activeTab === 'mandates' ? 'active' : ''}`}
      onClick={() => onChange('mandates')}>
      Mandates
      {mandateCount > 0 && <span className="tab-count">{mandateCount}</span>}
    </button>
  </div>
);

const EmptyChatState = ({
  ap2Config,
  merchant,
  onTryExample,
}: {
  ap2Config: Ap2ModeConfig;
  merchant: MerchantKey;
  onTryExample: (text: string) => void;
}) => {
  const merchantDemo = getMerchantDemo(merchant);
  const scenarioHints = getScenarioStarterHints(merchant);
  const hints =
      isAutoMode(ap2Config)
          ? [scenarioHints.hnp, scenarioHints.hp]
          : isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp'
              ? [scenarioHints.hp]
              : [scenarioHints.hnp];
  const enterExample = hints[0]?.example ?? defaultChatStarterMessage(merchant);

  return (
    <div className="empty-state">
      <div className="icon">{merchantDemo.icon}</div>
      <div className="title">AP2 Demo</div>
      <div className="merchant-demo-label">{merchantDemo.label}</div>
      <div className="subtitle">
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
          <div key={hint.tag} className={`scenario-hint scenario-hint--${hint.accent}`}>
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

      <p className="suggestion">
        Try: <em>&quot;{enterExample}&quot;</em>
      </p>
      <p className="suggestion-enter-hint">
        or just press <kbd>Enter</kbd>
        {merchantDemo.enterKeySuffix}
      </p>
    </div>
  );
};

type ChatInputProps = Pick<
  ChatState,
  'handleSend' | 'input' | 'loading' | 'setInput'
> & {
  merchant: MerchantKey;
};

const ChatInput = ({input, setInput, handleSend, loading, merchant}: ChatInputProps) => {
  const merchantDemo = getMerchantDemo(merchant);
  const starter = defaultChatStarterMessage(merchant);
  return (
    <div className="input-area">
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) =>
          e.key === 'Enter' &&
          !loading &&
          handleSend({fallbackIfEmpty: starter})
        }
        placeholder={merchantDemo.inputPlaceholder}
        disabled={loading}
        className="chat-input"
      />
      <button
        onClick={() =>
          handleSend({fallbackIfEmpty: starter})
        }
        disabled={loading}
        className="send-button">
        Send
      </button>
    </div>
  );
};

// ==========================================
// MAIN APP COMPONENT
// ==========================================

export default function App() {
  const [ap2Config, setAp2Config] = useState<Ap2ModeConfig>(
      () => loadAp2Config() ?? AUTO_UNIFIED_CONFIG,
  );
  const [merchant, setMerchant] = useState<MerchantKey>(() => loadMerchant());
  const [showModePicker, setShowModePicker] = useState(false);
  const chatState: ChatState = useChat(ap2Config, merchant);
  const [activeTab, setActiveTab] = useState<TabKey>('chat');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeTab === 'chat') {
      bottomRef.current?.scrollIntoView({behavior: 'smooth'});
    }
  }, [chatState.messages, activeTab]);

  function handleModeConfirm(config: Ap2ModeConfig) {
    saveAp2Config(config);
    setAp2Config(config);
    setShowModePicker(false);
  }

  function handleMerchantChange(next: MerchantKey) {
    saveMerchant(next);
    setMerchant(next);
  }

  return (
    <div className="app-container">
      {showModePicker && (
        <ModePicker
          allowClose
          onClose={() => setShowModePicker(false)}
          onConfirm={handleModeConfirm}
        />
      )}
      <AppHeader
        usedServers={chatState.usedServers}
        ap2Config={ap2Config}
        merchant={merchant}
        onMerchantChange={handleMerchantChange}
        onOpenModeSettings={() => setShowModePicker(true)}
      />
      <TabBar
        activeTab={activeTab}
        onChange={setActiveTab}
        mandateCount={chatState.mandates.length}
      />

      {activeTab === 'chat' ? (
        <>
          <div className="messages-container">
            {chatState.messages.length > 0 ? (
              <div className="messages-list">
                {chatState.messages.map((msg) => (
                  <MessageRenderer
                    key={msg.id}
                    msg={msg}
                    chatState={chatState}
                  />
                ))}
                {chatState.loading && (
                  <div className="msg-agent">
                    <TypingIndicator />
                  </div>
                )}
              </div>
            ) : (
              <>
                <EmptyChatState
                  ap2Config={ap2Config}
                  merchant={merchant}
                  onTryExample={chatState.setInput}
                />
                {chatState.loading && (
                  <div className="msg-agent">
                    <TypingIndicator />
                  </div>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>

          <ChatInput
            input={chatState.input}
            setInput={chatState.setInput}
            handleSend={chatState.handleSend}
            loading={chatState.loading}
            merchant={merchant}
          />
        </>
      ) : (
        <div className="mandate-tab-container">
          <MandateViewer mandates={chatState.mandates} merchant={merchant} />
        </div>
      )}
    </div>
  );
}
