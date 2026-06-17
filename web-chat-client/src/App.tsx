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
  type MerchantKey,
} from './config';
import {MerchantCapabilities} from './components/MerchantCapabilities';
import {MerchantPicker} from './components/MerchantPicker';
import {type ChatState, useChat} from './hooks/useChat';

// ==========================================
// SUB-COMPONENTS
// ==========================================

const AppHeader = ({
  usedServers,
  ap2Config,
  merchant,
  onOpenModeSettings,
}: {
  usedServers: Set<string>;
  ap2Config: Ap2ModeConfig;
  merchant: MerchantKey | null;
  onOpenModeSettings: () => void;
}) => {
  const merchantDemo = merchant ? getMerchantDemo(merchant) : null;
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
        <span>{merchantDemo?.icon ?? '🛍️'}</span>
      </div>
      <div className="title-container">
        <div className="title">
          AP2 Demo
          <span className="flow-badge card">{presenceLabel}</span>
          <span className="flow-badge card">{paymentLabel}</span>
        </div>
        <div className="subtitle">
          {!merchantDemo
            ? 'Choose a merchant in the chat to begin'
            : isAutoMode(ap2Config)
              ? merchantDemo.autoSubtitle
              : `A2A · ${isFixedMode(ap2Config) && ap2Config.presence_mode === 'hp' ? 'Human Present' : 'Human Not Present'} · Merchant MCP · Credential Provider MCP`}
          {' · '}
          <button type="button" className="mode-settings-link" onClick={onOpenModeSettings}>
            Mode settings
          </button>
        </div>
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
  const enterExample = defaultChatStarterMessage(merchant);

  return (
    <div className="empty-state">
      <div className="icon">{merchantDemo.icon}</div>
      <div className="title">AP2 Demo</div>
      <div className="merchant-demo-label">{merchantDemo.label}</div>

      <MerchantCapabilities
        merchant={merchant}
        ap2Config={ap2Config}
        onTryExample={onTryExample}
        showHeading={false}
      />

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
  merchant: MerchantKey | null;
};

const ChatInput = ({input, setInput, handleSend, loading, merchant}: ChatInputProps) => {
  // No merchant yet: generic placeholder and no Enter-to-start fallback.
  const placeholder = merchant
    ? getMerchantDemo(merchant).inputPlaceholder
    : 'Tell me which merchant you want, e.g. "buy SuperShoe sneakers" or "book a flight".';
  const starter = merchant ? defaultChatStarterMessage(merchant) : undefined;
  return (
    <div className="input-area">
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) =>
          e.key === 'Enter' &&
          !loading &&
          handleSend(starter ? {fallbackIfEmpty: starter} : undefined)
        }
        placeholder={placeholder}
        disabled={loading}
        className="chat-input"
      />
      <button
        onClick={() =>
          handleSend(starter ? {fallbackIfEmpty: starter} : undefined)
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
  // Merchant is in-memory only: a browser refresh clears the chat thread, so it
  // also resets the merchant and returns to the conversational picker.
  const [merchant, setMerchant] = useState<MerchantKey | null>(null);
  const [showModePicker, setShowModePicker] = useState(false);

  function handleMerchantSelected(next: MerchantKey) {
    setMerchant(next);
  }

  const chatState: ChatState = useChat(
      ap2Config,
      merchant,
      handleMerchantSelected,
  );
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
                {merchant === null ? (
                  <MerchantPicker />
                ) : (
                  <EmptyChatState
                    ap2Config={ap2Config}
                    merchant={merchant}
                    onTryExample={chatState.setInput}
                  />
                )}
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
          <MandateViewer mandates={chatState.mandates} merchant={merchant ?? undefined} />
        </div>
      )}
    </div>
  );
}
