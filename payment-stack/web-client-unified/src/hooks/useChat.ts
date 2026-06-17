import {useCallback, useEffect, useMemo, useRef, useState} from 'react';

import {A2AClient} from '../a2aClient';
import {isAutoMode, isFixedMode, type Ap2ModeConfig} from '../components/ModePicker';
import {AGENT_URL, isFlightMerchant, MERCHANT_TRIGGER_URL, MONITOR_INTERVAL_MINUTES, type MerchantKey} from '../config';
import {fetchBackendMonitorStatus, registerBackendMonitor} from '../monitorScheduler';
import type {ChatMessage, ImmediateCheckoutRequest, InventoryMatch, InventoryOptionsArtifact, MandateApprovalData, MandateChainsFetched, MandateEntry, MandateRequest, MandatesSigned, MonitoringStatus, OutgoingDataPayload, Part, PurchaseComplete, ToolCallArtifact} from '../types';
import {isFunctionResponsePart, isToolCallArtifact} from '../types';
import {deriveMandateEntries} from '../utils/mandateEntries';
import {
  getCheckoutFlowState,
  hasAnyPurchaseComplete,
  immediateCheckoutKey,
} from '../utils/checkoutFlow';
import {devError, devLog, devWarn} from '../utils/devLog';
import {findItemNameForId} from '../utils/itemDisplay';
import {
  extractOpenMandateIds,
  isMandateId,
  latestApprovedHnpMandate,
  monitoringStatusFromBackend,
  normalizeSlugItemId,
} from '../utils/hnpMonitor';
import {
  extractMandateFromProseTable,
  hasAnyMandateApprovalInThread,
  mandateFromAssembleToolArgs,
  mandateRequestKey,
  shouldPromptMandateApproval,
} from '../utils/mandateFlow';
import {convertToStrictPart, extractErrorFromText, extractImmediateCheckoutFromText, extractInventoryOptionsFromText, extractMandateFromText, extractMonitoringFromText, extractMonitoringJsonFromText, extractProductPreviewUnavailableFromText, extractPurchaseCompleteFromText, parseInvocationParts, parseMainArtifactData, parseToolAndInventoryArtifacts, removeArtifactJsonFromText, stripAgentArtifactJson} from '../utils/parsing';

const a2aClient = new A2AClient(AGENT_URL);

function withMerchantPayload(
    text: string|OutgoingDataPayload,
    merchant: MerchantKey,
    fixedAp2Config?: {presence_mode: 'hp'|'hnp'; payment_method: 'card'|'x402'},
    ): string|OutgoingDataPayload {
  const ap2WithMerchant = (cfg: {
    presence_mode: 'hp'|'hnp';
    payment_method: 'card'|'x402';
  }) => ({...cfg, merchant});

  if (typeof text === 'string') {
    const payload: Record<string, unknown> = {message: text, merchant};
    if (fixedAp2Config) {
      payload.ap2_config = ap2WithMerchant(fixedAp2Config);
    }
    return JSON.stringify(payload);
  }

  const payload = {...text} as Record<string, unknown>;
  payload.merchant = merchant;
  if (payload.ap2_config && typeof payload.ap2_config === 'object') {
    payload.ap2_config = {
      ...(payload.ap2_config as Record<string, unknown>),
      merchant,
    };
  }
  return payload as unknown as OutgoingDataPayload;
}

/**
 * For short user replies (< 220 chars), prepend a thread recap with
 * instructions so the agent doesn't re-ask for product/budget.
 */
function augmentUserMessageForAgent(
    text: string,
    messages: ChatMessage[],
    ): string {
  if (text.length >= 220) return text;
  const lastUserMsgs = messages.filter((m) => m.role === 'user')
                           .slice(-8)
                           .map((m) => m.text ?? '')
                           .filter(Boolean);
  const lastAgentMsgs = messages.filter((m) => m.role === 'agent')
                            .slice(-4)
                            .map((m) => m.text ?? '')
                            .filter(Boolean);
  if (lastUserMsgs.length === 0 && lastAgentMsgs.length === 0) return text;
  const recap = [
    'Thread context (user last 8):',
    ...lastUserMsgs.map((m) => `  U: ${m.slice(0, 200)}`),
    'Agent last 4:',
    ...lastAgentMsgs.map((m) => `  A: ${m.slice(0, 300)}`),
    '',
    'Do not re-ask for product or budget. If user is confirming after product_preview_unavailable, build slug_0 item_id, call check_product with limited_drop=true, then emit mandate_request — do NOT call search_inventory.',
    'Plain-text like "1 and pay by card", "option 1", or a dollar budget is a budget/payment choice — NOT mandate_approved. Emit mandate_request JSON and wait for Trusted Surface; do NOT call assemble_and_sign_mandates_tool until the client sends structured mandate_approved.',
    '',
    `User says: ${text}`,
  ].join('\n');
  return recap;
}

/**
 * Update existing monitoring row in-place (by item_id, scanning backward)
 * or append a new one.
 */
function upsertMonitoringMessage(
    prev: ChatMessage[],
    monitoring: MonitoringStatus,
    text?: string,
    ): ChatMessage[] {
  const enriched: MonitoringStatus = {
    ...monitoring,
    item_name:
        monitoring.item_name?.trim() ||
        findItemNameForId(prev, monitoring.item_id),
  };
  const idx = [...prev].reverse().findIndex(
      (m) => m.artifactData &&
          (m.artifactData as {type?: string}).type === 'monitoring' &&
          (m.artifactData as MonitoringStatus).item_id === enriched.item_id,
  );
  if (idx >= 0) {
    const realIdx = prev.length - 1 - idx;
    const existing = prev[realIdx].artifactData as MonitoringStatus;
    const merged: MonitoringStatus = {
      ...existing,
      ...enriched,
      item_name: enriched.item_name || existing.item_name,
      current_price:
          enriched.current_price ?? existing.current_price,
      available: enriched.available ?? existing.available,
      meets_constraints:
          enriched.meets_constraints ?? existing.meets_constraints,
      message: enriched.message ?? existing.message,
      open_checkout_mandate:
          enriched.open_checkout_mandate ?? existing.open_checkout_mandate,
      open_payment_mandate:
          enriched.open_payment_mandate ?? existing.open_payment_mandate,
    };
    const updated = [...prev];
    updated[realIdx] = {
      ...updated[realIdx],
      artifactData: merged,
      text: text ?? updated[realIdx].text,
      timestamp: Date.now(),
    };
    return updated;
  }
  return [
    ...prev,
    {
      id: crypto.randomUUID(),
      role: 'agent' as const,
      artifactData: enriched,
      text,
      timestamp: Date.now(),
    },
  ];
}

/**
 * Custom hook to manage chat state and operations with the A2A Agent.
 *
 * It handles message history, sending messages to the agent, streaming
 * responses, and managing UI states for tool calls, inventory lists, and
 * mandates.
 *
 * @returns An object containing:
 *   - messages: Array of ChatMessage objects.
 *   - input: String for the current chat input.
 *   - setInput: Function to update the chat input.
 *   - loading: Boolean indicating if the agent is responding.
 *   - pendingTaskId: String or undefined for active task tracing.
 *   - lastSelectedItemName: Name of the last item selected in inventory.
 *   - lastInventoryMatches: List of matches from the last inventory lookup.
 *   - lastInventoryOptions: Options for the last inventory lookup (e.g. qty,
 * cap).
 *   - usedServers: Set of backend tools/servers used by the agent.
 *   - isMonitoring: Boolean indicating if a monitoring task is active.
 *   - handleSend: Function to submit the current input text.
 *   - handleMandateApprove: Handler for approving a payment mandate.
 *   - handleMandateReject: Handler for rejecting a mandate.
 *   - sendToAgent: Function to send a raw string or structured object to the
 * agent.
 */
export function useChat(ap2Config: Ap2ModeConfig | null, merchantKey: MerchantKey) {
  const sessionId = a2aClient.getSessionId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const configSentRef = useRef(false);

  useEffect(() => {
    configSentRef.current = false;
  }, [ap2Config, merchantKey]);

  const fetchMandate = useCallback(async(id: string): Promise<string> => {
    let lastErr: unknown;
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const resp = await fetch(`${AGENT_URL}/mandates/${encodeURIComponent(id)}`);
        if (!resp.ok) throw new Error(`Failed to fetch mandate ${id}: ${resp.status}`);
        return resp.text();
      } catch (e) {
        lastErr = e;
        if (attempt < 4) {
          await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
        }
      }
    }
    throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
  }, []);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [pendingTaskId, setPendingTaskId] = useState<string|undefined>();
  const [lastSelectedItemName, setLastSelectedItemName] =
      useState<string|undefined>();
  const [lastInventoryMatches, setLastInventoryMatches] =
      useState<InventoryMatch[]|undefined>();
  const [lastInventoryOptions, setLastInventoryOptions] =
      useState<InventoryOptionsArtifact|undefined>();

  const loadingRef = useRef(loading);
  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  const pendingTriggerNudgeRef = useRef<'hnp'|'hp'|false>(false);
  const hpDropItemIdRef = useRef<string|undefined>();
  const hpNudgeSentForRef = useRef<string|undefined>();
  const lastTriggerStateRef = useRef<string>('');
  const mandateApproveInFlightRef = useRef(false);
  const approvalRetrySentRef = useRef<string|undefined>();
  const backendMonitorRegisteredRef = useRef<string|undefined>();
  const backendPurchasePostedRef = useRef(false);
  const backendMandateChainsPostedRef = useRef<Set<string>>(new Set());
  const sessionDoneRef = useRef(false);
  const messagesRef = useRef<ChatMessage[]>([]);
  const pendingAssembleMandateRef = useRef<MandateRequest|undefined>();
  const pendingHnpApprovalRef = useRef<MandateApprovalData|undefined>();
  const lastInventoryOptionsRef = useRef(lastInventoryOptions);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  useEffect(() => {
    lastInventoryOptionsRef.current = lastInventoryOptions;
  }, [lastInventoryOptions]);

  const usedServers = useMemo(() => {
    const set = new Set<string>();
    for (const msg of messages) {
      if (msg.artifactData &&
          (msg.artifactData as {type?: string}).type === 'tool_call') {
        set.add((msg.artifactData as ToolCallArtifact).server);
      }
    }
    return set;
  }, [messages]);

  // Derive monitoring state from full thread scan (not just last message)
  const monitoringData = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.artifactData &&
          (m.artifactData as {type?: string}).type === 'monitoring') {
        return m.artifactData as MonitoringStatus;
      }
      if (m.text && m.role === 'agent') {
        const parsed = extractMonitoringFromText(m.text);
        if (parsed) return parsed;
      }
    }
    return undefined;
  }, [messages]);

  const checkoutFlow = useMemo(
      () => getCheckoutFlowState(messages),
      [messages],
  );

  const hasPurchaseComplete = useMemo(() => {
    if (checkoutFlow.phase === 'awaiting_confirm' ||
        checkoutFlow.phase === 'processing') {
      return false;
    }
    if (checkoutFlow.phase === 'complete') return true;
    return hasAnyPurchaseComplete(messages);
  }, [checkoutFlow, messages]);

  useEffect(() => {
    sessionDoneRef.current =
        checkoutFlow.phase === 'complete' ||
        (checkoutFlow.phase === 'none' && hasAnyPurchaseComplete(messages));
  }, [checkoutFlow, messages]);

  const hpCheckoutStarted = useMemo(() => {
    return checkoutFlow.phase === 'awaiting_confirm' ||
        checkoutFlow.phase === 'processing';
  }, [checkoutFlow]);

  // Derive mandate entries for the Mandates tab by scanning messages.
  const mandates: MandateEntry[] = useMemo(
      () => deriveMandateEntries(messages),
      [messages],
  );

  /** Item IDs whose mandate was already approved/signed in this session. */
  const approvedMandateItemIds = useMemo(() => {
    const ids = new Set<string>();
    for (const msg of messages) {
      if (msg.mandateItemId) {
        ids.add(msg.mandateItemId);
      }
      const data = msg.artifactData as {type?: string; item_id?: string}|undefined;
      if (!data?.type) continue;
      if (data.type === 'monitoring' && data.item_id) {
        ids.add(data.item_id);
      }
      if (data.type === 'mandates_signed') {
        for (const m of messages) {
          if (m.mandateItemId) ids.add(m.mandateItemId);
        }
      }
    }
    return ids;
  }, [messages]);

  const isHnpPresence =
      isFixedMode(ap2Config) && ap2Config.presence_mode === 'hnp';
  const hnpApprovedMandate = useMemo(
      () => latestApprovedHnpMandate(messages),
      [messages],
  );
  const openMandateIds = useMemo(
      () => extractOpenMandateIds(messages),
      [messages],
  );
  const isMonitoring =
      (isAutoMode(ap2Config) || isHnpPresence) && monitoringData != null &&
      !hasPurchaseComplete && !loading;
  const hnpBackendWatch = useMemo(() => {
    if (hasPurchaseComplete || loading) return false;
    if (!(isAutoMode(ap2Config) || isHnpPresence)) return false;
    return monitoringData != null || hnpApprovedMandate != null;
  }, [
    hasPurchaseComplete, loading, ap2Config, isHnpPresence, monitoringData,
    hnpApprovedMandate,
  ]);

  const hpAwaitingDrop = useMemo(() => {
    if (hasPurchaseComplete || isMonitoring) return undefined;
    for (let i = messages.length - 1; i >= 0; i--) {
      const data = messages[i].artifactData as
          Partial<InventoryOptionsArtifact>&{type?: string}|undefined;
      if (data?.type !== 'inventory_options' || !data.matches?.[0]) continue;
      const m = data.matches[0];
      if (m.available === true || (m.stock != null && m.stock > 0)) {
        return undefined;
      }
      return {item_id: m.item_id, name: m.name};
    }
    return undefined;
  }, [messages, hasPurchaseComplete, isMonitoring]);

  const triggerWatchItemId =
      monitoringData?.item_id ?? hpAwaitingDrop?.item_id ??
      hnpApprovedMandate?.item_id;
  const shouldPollTrigger =
      !isFlightMerchant(merchantKey) &&
      triggerWatchItemId != null && !hasPurchaseComplete && !hpCheckoutStarted &&
      (hpAwaitingDrop != null || hnpBackendWatch);

  const resolvedHpPayment = useMemo((): 'card'|'x402' => {
    if (isFixedMode(ap2Config)) return ap2Config.payment_method;
    for (let i = messages.length - 1; i >= 0; i--) {
      const t = (messages[i].text ?? '').toLowerCase();
      if (/\bx402\b|crypto|usdc/.test(t)) return 'x402';
      if (/\bcard\b|credit\s+card/.test(t)) return 'card';
    }
    return 'card';
  }, [messages, ap2Config]);

  const addMessage = useCallback((msg: Omit<ChatMessage, 'id'|'timestamp'>) => {
    setMessages((prev) => {
      const next = [
        ...prev,
        {...msg, id: crypto.randomUUID(), timestamp: Date.now()},
      ];
      messagesRef.current = next;
      return next;
    });
  }, []);

  const armBackendHnpMonitor = useCallback(async (params: {
    item_id: string;
    price_cap: number;
    qty?: number;
    item_name?: string;
    open_checkout_mandate: string;
    open_payment_mandate: string;
    open_checkout_hash?: string;
    payment_method: 'card'|'x402';
  }) => {
    const itemId = normalizeSlugItemId(params.item_id);
    if (
        !isMandateId(params.open_checkout_mandate) ||
        !isMandateId(params.open_payment_mandate)
    ) {
      devWarn('WebClient', 'backend monitor arm skipped — invalid mandate ids', {
        open_checkout: params.open_checkout_mandate?.slice(0, 40),
        open_payment: params.open_payment_mandate?.slice(0, 40),
      });
      return;
    }
    const registerKey = [
      sessionId,
      itemId,
      params.price_cap,
      params.open_checkout_mandate,
      params.open_payment_mandate,
    ].join(':');
    if (backendMonitorRegisteredRef.current === registerKey) return;
    const result = await registerBackendMonitor({
      session_id: sessionId,
      item_id: itemId,
      price_cap: params.price_cap,
      qty: params.qty ?? 1,
      item_name: params.item_name,
      merchant: merchantKey,
      interval_minutes: MONITOR_INTERVAL_MINUTES,
      open_checkout_mandate: params.open_checkout_mandate,
      open_payment_mandate: params.open_payment_mandate,
      open_checkout_hash: params.open_checkout_hash,
      payment_method: params.payment_method,
    });
    if (result.status === 'ok' || !result.error) {
      backendMonitorRegisteredRef.current = registerKey;
      devLog('WebClient', 'backend monitor armed', {
        sessionId,
        item_id: itemId,
      });
      pendingHnpApprovalRef.current = undefined;
      setMessages((prev) => {
        const next = upsertMonitoringMessage(prev, {
          type: 'monitoring',
          item_id: itemId,
          item_name: params.item_name,
          price_cap: params.price_cap,
          qty: params.qty ?? 1,
          open_checkout_mandate: params.open_checkout_mandate,
          open_payment_mandate: params.open_payment_mandate,
          message: 'Backend scheduler is monitoring this item.',
        });
        messagesRef.current = next;
        return next;
      });
    } else {
      devWarn('WebClient', 'backend monitor arm failed', {result});
      addMessage({
        role: 'system',
        text: `Monitor register failed: ${
            result.message ?? result.error ?? 'unknown error'
        }. Purchase will not run until this is fixed.`,
      });
    }
  }, [sessionId, merchantKey]);

  const postBackendMandateChains = useCallback(async (pc: PurchaseComplete) => {
    const checkoutId = pc.checkout_mandate_chain_id;
    const paymentId = pc.payment_mandate_chain_id;
    const posted = backendMandateChainsPostedRef.current;
    if (checkoutId && !posted.has(`chk:${checkoutId}`)) {
      posted.add(`chk:${checkoutId}`);
      try {
        const token = await fetchMandate(checkoutId);
        addMessage({
          role: 'agent',
          artifactData: {
            type: 'mandate_chains_fetched',
            checkout_mandate_chain: token,
          } as MandateChainsFetched,
        });
      } catch (e) {
        posted.delete(`chk:${checkoutId}`);
        devError('WebClient', 'fetch backend checkout chain failed', {
          error: String(e),
        });
      }
    }
    if (paymentId && !posted.has(`pay:${paymentId}`)) {
      posted.add(`pay:${paymentId}`);
      try {
        const token = await fetchMandate(paymentId);
        addMessage({
          role: 'agent',
          artifactData: {
            type: 'mandate_chains_fetched',
            payment_mandate_chain: token,
          } as MandateChainsFetched,
        });
      } catch (e) {
        posted.delete(`pay:${paymentId}`);
        devError('WebClient', 'fetch backend payment chain failed', {
          error: String(e),
        });
      }
    }
  }, [fetchMandate, addMessage]);

  const applyBackendMonitorStatus = useCallback(async () => {
    const mandate = monitoringData ?? hnpApprovedMandate;
    if (!mandate?.item_id || mandate.price_cap == null) return;
    const ids = openMandateIds;
    const fallbackItemId = normalizeSlugItemId(mandate.item_id);
    try {
      const status = await fetchBackendMonitorStatus(sessionId);
      const tick = status.monitoring;
      const backendActive =
          status.status === 'active' || status.status === 'purchasing';
      const tickItemId =
          typeof tick?.item_id === 'string' ? tick.item_id :
          typeof status.item_id === 'string' ? status.item_id :
          fallbackItemId;
      if (backendActive || tick) {
        setMessages((prev) => {
          const existingIdx = [...prev].reverse().findIndex(
              (m) => m.artifactData &&
                  (m.artifactData as {type?: string}).type === 'monitoring' &&
                  (m.artifactData as MonitoringStatus).item_id ===
                      fallbackItemId,
          );
          const existingTick = existingIdx >= 0 ?
              prev[prev.length - 1 - existingIdx].artifactData as
                  MonitoringStatus :
              undefined;
          const mergedTick = {
            ...(existingTick ?? {}),
            ...(tick ?? {}),
          };
          return upsertMonitoringMessage(
              prev,
              monitoringStatusFromBackend(mergedTick, {
                item_id: tickItemId,
                price_cap:
                    (typeof status.price_cap === 'number' ?
                         status.price_cap :
                         undefined) ?? mandate.price_cap,
                qty: monitoringData?.qty ?? mandate.qty,
                item_name:
                    (typeof status.item_name === 'string' ?
                         status.item_name :
                         undefined) ??
                    monitoringData?.item_name ?? mandate.item_name,
                open_checkout_mandate: ids?.checkoutId,
                open_payment_mandate: ids?.paymentId,
              }),
              status.status === 'purchasing' ?
                  'Completing purchase…' :
                  undefined,
          );
        });
      }
      if (status.status === 'purchased') {
        const pc = (status.purchase_complete ??
            status.purchase_result?.purchase_complete) as
            PurchaseComplete|undefined;
        if (pc?.type === 'purchase_complete') {
          if (!backendPurchasePostedRef.current) {
            backendPurchasePostedRef.current = true;
            addMessage({
              role: 'agent',
              artifactData: pc,
              text: status.message ??
                  'Purchase completed by backend scheduler.',
            });
          }
          void postBackendMandateChains(pc);
        } else if (
            !backendPurchasePostedRef.current && status.message
        ) {
          backendPurchasePostedRef.current = true;
          addMessage({role: 'system', text: status.message});
        }
      }
    } catch {
      // ignore transient fetch errors
    }
  }, [
    sessionId, monitoringData, hnpApprovedMandate, openMandateIds, addMessage,
    postBackendMandateChains,
  ]);

  const sendToAgent = useCallback(
      async (
          text: string|OutgoingDataPayload,
          taskId?: string,
          ) => {
        setLoading(true);
        const tid = taskId ?? crypto.randomUUID();
        setPendingTaskId(tid);
        let agentTextBuffer = '';
        const addedToolCallsInThisRun = new Set<string>();
        pendingAssembleMandateRef.current = undefined;
        let mandateUiFromAssembleTool = false;
        const injectedMandateSignKeys = new Set<string>();

        let outbound: string|OutgoingDataPayload = text;
        let extraMetadata: Record<string, unknown>|undefined;
        const includeFixedAp2 =
            isFixedMode(ap2Config) && !configSentRef.current;
        if (includeFixedAp2) {
          configSentRef.current = true;
          const fixedConfig = {
            presence_mode: ap2Config.presence_mode,
            payment_method: ap2Config.payment_method,
          };
          extraMetadata = {ap2_config: {...fixedConfig, merchant: merchantKey}};
        }
        outbound = withMerchantPayload(
            outbound,
            merchantKey,
            includeFixedAp2 && isFixedMode(ap2Config) ? {
              presence_mode: ap2Config.presence_mode,
              payment_method: ap2Config.payment_method,
            } : undefined,
        );

        // Build a dedup key that distinguishes multiple invocations of the same
        // tool with different arguments (e.g. present_mandate_chain called
        // once per audience).
        const toolCallKey = (tc: ToolCallArtifact): string =>
            tc.args ? `${tc.tool}:${JSON.stringify(tc.args)}` : tc.tool;

        try {
          devLog('WebClient', 'sendToAgent', {
            taskId: tid,
            payload: typeof outbound === 'string' ?
                outbound.slice(0, 120) :
                outbound,
          });
          for await (const event of a2aClient.sendMessage(
              outbound, tid, extraMetadata)) {
            if (event.type === 'status') {
              devLog('WebClient', 'A2A status', {
                state: event.status.state,
                message: event.status.message,
              });
              if (event.status.state === 'failed') {
                devError('WebClient', 'A2A failed', {
                  message: event.status.message,
                });
                addMessage({
                  role: 'system',
                  text: 'Agent error: ' + JSON.stringify(event.status.message),
                });
              }
              const statusParts = event.status.message?.parts ?? [];

              // Intercept tool responses to inject mandates and trigger fetches
              for (const rawPart of statusParts) {
                if (isFunctionResponsePart(rawPart)) {
                  const toolName = rawPart.data.name;
                  const resp = rawPart.data.response as Record<string, unknown>;

                  if (toolName === 'create_hp_open_mandates_tool' ||
                      toolName === 'assemble_and_sign_mandates_tool') {
                    if (
                        toolName === 'assemble_and_sign_mandates_tool' &&
                        !hasAnyMandateApprovalInThread(messagesRef.current) &&
                        !pendingHnpApprovalRef.current
                    ) {
                      devWarn(
                          'WebClient',
                          'assemble_and_sign before Trusted Surface approval — skipping mandates_signed',
                      );
                      continue;
                    }
                    if (typeof resp.open_checkout_mandate === 'string' &&
                        typeof resp.open_payment_mandate === 'string') {
                      const signKey =
                          `${resp.open_checkout_mandate}:${
                              resp.open_payment_mandate}`;
                      if (injectedMandateSignKeys.has(signKey)) {
                        continue;
                      }
                      injectedMandateSignKeys.add(signKey);
                      devLog('WebClient', 'mandates_signed intercept', {
                        tool: toolName,
                        open_checkout: resp.open_checkout_mandate,
                        open_payment: resp.open_payment_mandate,
                      });
                      const checkoutId =
                          typeof resp.open_checkout_mandate_id === 'string' &&
                          isMandateId(resp.open_checkout_mandate_id) ?
                          resp.open_checkout_mandate_id :
                          typeof resp.open_checkout_mandate === 'string' &&
                              isMandateId(resp.open_checkout_mandate) ?
                              resp.open_checkout_mandate :
                              '';
                      const paymentId =
                          typeof resp.open_payment_mandate_id === 'string' &&
                          isMandateId(resp.open_payment_mandate_id) ?
                          resp.open_payment_mandate_id :
                          typeof resp.open_payment_mandate === 'string' &&
                              isMandateId(resp.open_payment_mandate) ?
                              resp.open_payment_mandate :
                              '';
                      const checkoutHash =
                          typeof resp.open_checkout_hash === 'string' ?
                              resp.open_checkout_hash :
                              undefined;
                      const mr =
                          latestApprovedHnpMandate(messagesRef.current) ??
                          pendingAssembleMandateRef.current ??
                          (pendingHnpApprovalRef.current ?
                               {
                                 type: 'mandate_request' as const,
                                 item_id: pendingHnpApprovalRef.current.item_id,
                                 item_name: pendingHnpApprovalRef.current.item_name,
                                 price_cap: pendingHnpApprovalRef.current.price_cap,
                                 qty: pendingHnpApprovalRef.current.qty,
                                 payment_method:
                                     pendingHnpApprovalRef.current.payment_method,
                               } :
                               undefined);
                      const rail: 'card' | 'x402' =
                          typeof resp.payment_method === 'string' &&
                          (resp.payment_method === 'x402' ||
                              resp.payment_method === 'card') ?
                              resp.payment_method :
                          mr?.payment_method === 'x402' ? 'x402' :
                          resolvedHpPayment;
                      if (mr && checkoutId && paymentId) {
                        void armBackendHnpMonitor({
                          item_id: mr.item_id,
                          price_cap: mr.price_cap ?? 0,
                          qty: mr.qty,
                          item_name: mr.item_name,
                          open_checkout_mandate: checkoutId,
                          open_payment_mandate: paymentId,
                          open_checkout_hash: checkoutHash,
                          payment_method: rail,
                        });
                      } else if (checkoutId && paymentId) {
                        devWarn('WebClient', 'assemble ok but no mandate context for monitor', {
                          checkoutId,
                          paymentId,
                        });
                      }
                      Promise
                          .all([
                            fetchMandate(resp.open_checkout_mandate),
                            fetchMandate(resp.open_payment_mandate)
                          ])
                          .then(([openChkToken, openPayToken]) => {
                            if (sessionDoneRef.current) return;
                            const payRail =
                                typeof resp.payment_method === 'string' &&
                                (resp.payment_method === 'x402' ||
                                    resp.payment_method === 'card') ?
                                    resp.payment_method :
                                    rail;
                            addMessage({
                              role: 'agent',
                              artifactData: {
                                type: 'mandates_signed',
                                open_checkout_mandate: openChkToken,
                                open_payment_mandate: openPayToken,
                                open_checkout_mandate_id: checkoutId,
                                open_payment_mandate_id: paymentId,
                                open_checkout_hash: checkoutHash,
                                payment_method: payRail,
                              } as MandatesSigned,
                            });
                          })
                          .catch(
                              (e) => {
                                devError(
                                    'WebClient', 'fetch open mandates failed', {
                                      error: String(e),
                                    });
                                if (sessionDoneRef.current) return;
                                const rail =
                                    typeof resp.payment_method === 'string' &&
                                    (resp.payment_method === 'x402' ||
                                        resp.payment_method === 'card') ?
                                        resp.payment_method :
                                        undefined;
                                addMessage({
                                  role: 'agent',
                                  artifactData: {
                                    type: 'mandates_signed',
                                    open_checkout_mandate: checkoutId,
                                    open_payment_mandate: paymentId,
                                    open_checkout_mandate_id: checkoutId,
                                    open_payment_mandate_id: paymentId,
                                    open_checkout_hash: checkoutHash,
                                    payment_method: rail,
                                  } as MandatesSigned,
                                });
                              });
                    }
                  } else if (
                      toolName === 'assemble_and_sign_immediate_mandates_tool') {
                    if (typeof resp.checkout_mandate_chain_id === 'string') {
                      const chainKey =
                          `checkout:${resp.checkout_mandate_chain_id}`;
                      if (!injectedMandateSignKeys.has(chainKey)) {
                        injectedMandateSignKeys.add(chainKey);
                        devLog('WebClient', 'HP checkout chain intercept', {
                          chain_id: resp.checkout_mandate_chain_id,
                        });
                        fetchMandate(resp.checkout_mandate_chain_id)
                            .then((token) => {
                              if (sessionDoneRef.current) return;
                              addMessage({
                                role: 'agent',
                                artifactData: {
                                  type: 'mandate_chains_fetched',
                                  checkout_mandate_chain: token,
                                } as MandateChainsFetched,
                              });
                            })
                            .catch(
                                (e) => devError(
                                    'WebClient', 'fetch HP checkout chain failed',
                                    {error: String(e)},
                                ));
                      }
                    }
                    if (typeof resp.payment_mandate_chain_id === 'string') {
                      const chainKey =
                          `payment:${resp.payment_mandate_chain_id}`;
                      if (!injectedMandateSignKeys.has(chainKey)) {
                        injectedMandateSignKeys.add(chainKey);
                        devLog('WebClient', 'HP payment chain intercept', {
                          chain_id: resp.payment_mandate_chain_id,
                        });
                        fetchMandate(resp.payment_mandate_chain_id)
                            .then((token) => {
                              if (sessionDoneRef.current) return;
                              addMessage({
                                role: 'agent',
                                artifactData: {
                                  type: 'mandate_chains_fetched',
                                  payment_mandate_chain: token,
                                } as MandateChainsFetched,
                              });
                            })
                            .catch(
                                (e) => devError(
                                    'WebClient', 'fetch HP payment chain failed',
                                    {error: String(e)},
                                ));
                      }
                    }
                  } else if (
                      toolName === 'create_checkout_presentation' &&
                      typeof resp.checkout_mandate_chain_id === 'string') {
                    devLog('WebClient', 'checkout chain intercept', {
                      chain_id: resp.checkout_mandate_chain_id,
                    });
                    fetchMandate(resp.checkout_mandate_chain_id)
                        .then(token => {
                          if (sessionDoneRef.current) return;
                          addMessage({
                            role: 'agent',
                            artifactData: {
                              type: 'mandate_chains_fetched',
                              checkout_mandate_chain: token,
                            } as MandateChainsFetched,
                          });
                        })
                        .catch(
                            e => devError(
                                'WebClient', 'fetch checkout chain failed', {
                                  error: String(e),
                                }));
                  } else if (
                      toolName === 'create_payment_presentation' &&
                      typeof resp.payment_mandate_chain_id === 'string') {
                    devLog('WebClient', 'payment chain intercept', {
                      chain_id: resp.payment_mandate_chain_id,
                    });
                    fetchMandate(resp.payment_mandate_chain_id)
                        .then(token => {
                          if (sessionDoneRef.current) return;
                          addMessage({
                            role: 'agent',
                            artifactData: {
                              type: 'mandate_chains_fetched',
                              payment_mandate_chain: token,
                            } as MandateChainsFetched,
                          });
                        })
                        .catch(
                            e => devError(
                                'WebClient', 'fetch payment chain failed', {
                                  error: String(e),
                                }));
                  }
                }
              }

              if (statusParts.length > 0) {
                const strictStatusParts =
                    statusParts.map((p) => convertToStrictPart(p))
                        .filter((p): p is Part => p !== undefined);
                const explicit =
                    parseToolAndInventoryArtifacts(strictStatusParts);
                const invocations = parseInvocationParts(strictStatusParts);
                const toolCalls: ToolCallArtifact[] = [
                  ...explicit.filter(isToolCallArtifact),
                  ...invocations,
                ];
                for (const tc of toolCalls) {
                  const key = toolCallKey(tc);
                  if (!addedToolCallsInThisRun.has(key)) {
                    addMessage({role: 'agent', artifactData: tc});
                    addedToolCallsInThisRun.add(key);
                  }
                  if (tc.tool === 'assemble_and_sign_mandates_tool') {
                    const inferred = mandateFromAssembleToolArgs(tc.args);
                    if (inferred) {
                      pendingAssembleMandateRef.current = inferred;
                      mandateUiFromAssembleTool = true;
                    }
                  }
                }
              }
            } else if (event.type === 'artifact') {
              devLog('WebClient', 'artifact event', {parts: event.artifact.parts.length});
              const parts = event.artifact.parts;
              for (const p of parts) {
                if (p.text) agentTextBuffer += p.text;
              }

              const explicit = parseToolAndInventoryArtifacts(
                  parts.map((p) => convertToStrictPart(p))
                      .filter((p): p is Part => p !== undefined));
              const invocations = parseInvocationParts(
                  parts.map((p) => convertToStrictPart(p))
                      .filter((p): p is Part => p !== undefined));
              const toolCalls: ToolCallArtifact[] = [
                ...explicit.filter(isToolCallArtifact),
                ...invocations,
              ];
              const inventoryOpts = explicit.filter(
                  (a): a is InventoryOptionsArtifact =>
                      (a as {type?: string}).type === 'inventory_options',
              );

              for (const tc of toolCalls) {
                const key = toolCallKey(tc);
                if (!addedToolCallsInThisRun.has(key)) {
                  addMessage({role: 'agent', artifactData: tc});
                  addedToolCallsInThisRun.add(key);
                }
                if (tc.tool === 'assemble_and_sign_mandates_tool') {
                  const inferred = mandateFromAssembleToolArgs(tc.args);
                  if (inferred) {
                    pendingAssembleMandateRef.current = inferred;
                    mandateUiFromAssembleTool = true;
                  }
                }
              }
              for (const inv of inventoryOpts) {
                addMessage({role: 'agent', artifactData: inv});
                const sel = inv.matches.find((m) => m.item_id === inv.selected);
                if (sel) setLastSelectedItemName(sel.name);
                setLastInventoryMatches(inv.matches);
                setLastInventoryOptions(inv);
              }

              // Early monitoring extraction during streaming
              if (!event.artifact.lastChunk && agentTextBuffer) {
                const earlyMon = extractMonitoringJsonFromText(agentTextBuffer);
                if (earlyMon) {
                  setMessages(
                      (prev) => upsertMonitoringMessage(
                          prev, earlyMon, agentTextBuffer));
                }
              }

              let showedInventoryFromText = false;
              if (event.artifact.lastChunk && agentTextBuffer) {
                if (inventoryOpts.length === 0) {
                  const inv = extractInventoryOptionsFromText(agentTextBuffer);
                  if (inv) {
                    addMessage({role: 'agent', artifactData: inv});
                    showedInventoryFromText = true;
                    const sel =
                        inv.matches.find((m) => m.item_id === inv.selected);
                    if (sel) setLastSelectedItemName(sel.name);
                    setLastInventoryMatches(inv.matches);
                    setLastInventoryOptions(inv);
                  }
                }
              }

              if (event.artifact.lastChunk) {
                const strictParts =
                    parts.map((p) => convertToStrictPart(p))
                        .filter((p): p is Part => p !== undefined);
                const mandateFromText = agentTextBuffer ?
                    (extractMandateFromText(agentTextBuffer) ??
                     extractMandateFromProseTable(agentTextBuffer, {
                       messages: messagesRef.current,
                       inventory: lastInventoryOptionsRef.current,
                     })) :
                    undefined;
                const mandateFallback =
                    !mandateUiFromAssembleTool ?
                        pendingAssembleMandateRef.current :
                        undefined;
                const mainData = parseMainArtifactData(strictParts) ??
                    (agentTextBuffer ?
                         (mandateFromText ??
                          mandateFallback ??
                          extractImmediateCheckoutFromText(agentTextBuffer) ??
                          extractProductPreviewUnavailableFromText(
                              agentTextBuffer) ??
                          extractPurchaseCompleteFromText(agentTextBuffer) ??
                          extractErrorFromText(agentTextBuffer) ??
                          extractMonitoringFromText(agentTextBuffer)) :
                         mandateFallback ??
                         undefined);

                // For monitoring artifacts, upsert instead of append
                if (mainData &&
                    (mainData as {type?: string}).type === 'monitoring') {
                  setMessages(
                      (prev) => upsertMonitoringMessage(
                          prev,
                          mainData as MonitoringStatus,
                          agentTextBuffer || undefined,
                          ),
                  );
                } else if (mainData) {
                  const isMandateReq =
                      (mainData as {type?: string}).type === 'mandate_request';
                  const skipDuplicateMandate =
                      mandateUiFromAssembleTool && isMandateReq;
                  let displayText = agentTextBuffer || undefined;
                  const mainType = (mainData as {type?: string}).type;
                  if (displayText && isMandateReq) {
                    displayText = stripAgentArtifactJson(
                        displayText,
                        'mandate_request',
                        'product_preview_unavailable',
                    );
                  } else if (
                      displayText &&
                      mainType === 'product_preview_unavailable'
                  ) {
                    displayText = stripAgentArtifactJson(
                        displayText,
                        'product_preview_unavailable',
                        'mandate_request',
                    );
                  }
                  if (!skipDuplicateMandate) {
                    addMessage({
                      role: 'agent',
                      artifactData: mainData,
                      text: displayText,
                    });
                  } else if (agentTextBuffer) {
                    addMessage({role: 'agent', text: agentTextBuffer});
                  }
                } else if (
                    agentTextBuffer && inventoryOpts.length === 0 &&
                    !showedInventoryFromText) {
                  addMessage({role: 'agent', text: agentTextBuffer});
                }
                agentTextBuffer = '';
              }
            }
          }
        } catch (e) {
          addMessage({role: 'system', text: 'Connection error: ' + String(e)});
        } finally {
          setLoading(false);
        }
      },
      [addMessage, ap2Config, armBackendHnpMonitor, fetchMandate, merchantKey,
       resolvedHpPayment, sessionId]);

  useEffect(() => {
    if (loading || !hnpApprovedMandate) return;
    const last = messages[messages.length - 1];
    const data = last?.artifactData as Record<string, unknown>|undefined;
    const errorCode =
        typeof data?.error === 'string' ? data.error :
        typeof data?.code === 'string' ? data.code :
        undefined;
    const text = last?.text ?? '';
    const approvalRequired =
        errorCode === 'trusted_surface_approval_required' ||
        text.includes('trusted_surface_approval_required');
    if (!approvalRequired) return;

    const paymentMethod = hnpApprovedMandate.payment_method === 'x402' ?
        'x402' :
        'card';
    const retryKey = `${sessionId}:${hnpApprovedMandate.item_id}:${
        hnpApprovedMandate.price_cap}:${paymentMethod}`;
    if (approvalRetrySentRef.current === retryKey) return;
    approvalRetrySentRef.current = retryKey;
    devWarn('WebClient', 'resending mandate_approved after approval_required', {
      item_id: hnpApprovedMandate.item_id,
      payment_method: paymentMethod,
    });
    void sendToAgent(
        {
          type: 'mandate_approved',
          mandate_request: {
            session_id: sessionId,
            item_id: hnpApprovedMandate.item_id,
            item_name: hnpApprovedMandate.item_name,
            price_cap: hnpApprovedMandate.price_cap,
            qty: hnpApprovedMandate.qty ?? 1,
            constraints: {
              price_lt:
                  hnpApprovedMandate.constraints?.price_lt ??
                  hnpApprovedMandate.price_cap,
            },
            matches: Array.isArray(hnpApprovedMandate.matches) ?
                hnpApprovedMandate.matches.map((m) => ({
                  item_id: m.item_id,
                  name: m.name,
                })) :
                undefined,
            payment_method: paymentMethod,
          },
          ap2_config: {
            presence_mode: 'hnp',
            payment_method: paymentMethod,
            merchant: merchantKey,
          },
        },
        pendingTaskId,
    );
  }, [
    loading, messages, hnpApprovedMandate, sessionId, merchantKey, pendingTaskId,
    sendToAgent,
  ]);

  // Trigger-state polling while HNP monitoring (fast) or HP awaiting drop (slow)
  useEffect(() => {
    lastTriggerStateRef.current = '';
    hpNudgeSentForRef.current = undefined;
  }, [triggerWatchItemId]);

  useEffect(
      () => {
        if (!shouldPollTrigger || !triggerWatchItemId) return;
        const hpOnly = hpAwaitingDrop != null && !hnpBackendWatch;
        if (hpOnly && hpNudgeSentForRef.current === triggerWatchItemId) {
          return;
        }
        const pollMs = hnpBackendWatch ? 2000 : hpOnly ? 3000 : 3000;
        const interval = setInterval(async () => {
          if (hpOnly && hpNudgeSentForRef.current === triggerWatchItemId) {
            return;
          }
          try {
            const resp = await fetch(
                `${MERCHANT_TRIGGER_URL}/state?item_id=${
                    encodeURIComponent(triggerWatchItemId)}`,
            );
            if (!resp.ok) return;
            const json = await resp.json();
            const str = JSON.stringify(json);
            const entry = json.entry as {stock?: number; price?: number}|undefined;
            const stock =
                typeof entry === 'object' && entry != null ? entry.stock : undefined;
            const hasStock = typeof stock === 'number' && stock > 0;
            if (str !== lastTriggerStateRef.current &&
                lastTriggerStateRef.current !== '') {
              if (hnpBackendWatch) {
                devLog('WebClient', 'trigger changed — refresh backend monitor', {
                  item_id: triggerWatchItemId,
                  entry,
                });
                void applyBackendMonitorStatus();
              } else if (hasStock) {
                devLog('WebClient', 'trigger state changed', {
                  item_id: triggerWatchItemId,
                  entry: json.entry,
                  hp: true,
                });
                pendingTriggerNudgeRef.current = 'hp';
                hpDropItemIdRef.current = triggerWatchItemId;
              }
            }
            lastTriggerStateRef.current = str;
          } catch {
            // ignore fetch errors
          }
        }, pollMs);
        return () => clearInterval(interval);
      },
      [
        shouldPollTrigger, triggerWatchItemId, hnpBackendWatch, hpAwaitingDrop,
        applyBackendMonitorStatus,
      ],
  );

  // When loading clears and a trigger nudge is pending, nudge the agent
  useEffect(
      () => {
        if (loading || hasPurchaseComplete || !pendingTriggerNudgeRef.current) {
          return;
        }
        if (hpCheckoutStarted && pendingTriggerNudgeRef.current === 'hp') {
          pendingTriggerNudgeRef.current = false;
          return;
        }
        const kind = pendingTriggerNudgeRef.current;
        pendingTriggerNudgeRef.current = false;

        if (kind === 'hnp') {
          // Backend scheduler (:8105) drives HNP ticks; no agent nudge.
          return;
        }

        const hpItem = hpDropItemIdRef.current ?? hpAwaitingDrop?.item_id;
        if (kind === 'hp' && hpItem) {
          hpNudgeSentForRef.current = hpItem;
          devLog('WebClient', 'hp_drop_ready (trigger watch)', {item_id: hpItem});
          sendToAgent(
              JSON.stringify({
                hp_drop_ready: true,
                item_id: hpItem,
                message:
                    'Merchant drop is live. Call check_product then continue HP checkout.',
              }),
              pendingTaskId,
          );
        }
      },
      [
        loading, monitoringData, hasPurchaseComplete, sendToAgent, pendingTaskId,
        hpAwaitingDrop, hpCheckoutStarted,
      ]);

  // Backend HNP monitor (:8105): register once, poll status for UI updates only
  useEffect(() => {
    backendPurchasePostedRef.current = false;
    backendMandateChainsPostedRef.current = new Set();
    backendMonitorRegisteredRef.current = undefined;
  }, [sessionId]);

  useEffect(
      () => {
        if (!hnpBackendWatch) return;
        const mandate = monitoringData ?? hnpApprovedMandate;
        const ids = openMandateIds;
        if (!mandate?.item_id || mandate.price_cap == null || !ids) return;
        void armBackendHnpMonitor({
          item_id: mandate.item_id,
          price_cap: mandate.price_cap,
          qty: monitoringData?.qty ?? mandate.qty,
          item_name: monitoringData?.item_name ?? mandate.item_name,
          open_checkout_mandate: ids.checkoutId,
          open_payment_mandate: ids.paymentId,
          open_checkout_hash: ids.openCheckoutHash,
          payment_method: isFixedMode(ap2Config) ?
              ap2Config.payment_method :
              resolvedHpPayment,
        });
      },
      [
        hnpBackendWatch, monitoringData, hnpApprovedMandate, openMandateIds,
        ap2Config, resolvedHpPayment, armBackendHnpMonitor,
      ],
  );

  useEffect(
      () => {
        if (!hnpBackendWatch || hasPurchaseComplete) return;
        void applyBackendMonitorStatus();
        const interval = setInterval(() => {
          void applyBackendMonitorStatus();
        }, 5000);
        return () => clearInterval(interval);
      },
      [hnpBackendWatch, hasPurchaseComplete, applyBackendMonitorStatus],
  );

  async function handleSend(opts?: {fallbackIfEmpty?: string}) {
    const raw = input.trim();
    const text = raw || opts?.fallbackIfEmpty;
    if (!text) return;
    setInput('');
    const augmented = augmentUserMessageForAgent(text, messages);
    addMessage({role: 'user', text});
    await sendToAgent(augmented);
  }

  async function handleMandateApprove(mandateRequest: MandateApprovalData) {
    const paymentMethod = mandateRequest.payment_method ?? 'card';
    const alreadyApprovedSameRail = !shouldPromptMandateApproval(messages, {
      type: 'mandate_request',
      item_id: mandateRequest.item_id,
      price_cap: mandateRequest.price_cap,
      payment_method: paymentMethod,
    });
    if (mandateApproveInFlightRef.current || alreadyApprovedSameRail) {
      devWarn('WebClient', 'mandate approve skipped', {
        inFlight: mandateApproveInFlightRef.current,
        alreadyApprovedSameRail,
      });
      return;
    }
    mandateApproveInFlightRef.current = true;
    devLog('WebClient', 'mandate_approved', {
      item_id: mandateRequest.item_id,
      price_cap: mandateRequest.price_cap,
      payment_method: paymentMethod,
    });
    const requestKey = mandateRequestKey({
      type: 'mandate_request',
      item_id: mandateRequest.item_id,
      price_cap: mandateRequest.price_cap,
      payment_method: paymentMethod,
    });
    addMessage({
      role: 'user_action',
      userActionLabel: 'Approved mandate',
      userActionSublabel: 'User signed over the TS surface with agent provider key',
      mandateItemId: mandateRequest.item_id,
      mandatePaymentMethod: paymentMethod,
      mandateRequestKey: requestKey,
    });
    const approvedMandateRequest: MandateApprovalData = {
      ...mandateRequest,
      session_id: sessionId,
    };
    pendingHnpApprovalRef.current = approvedMandateRequest;
    try {
      await sendToAgent(
          {
            type: 'mandate_approved',
            mandate_request: approvedMandateRequest,
            ap2_config: {
              presence_mode: 'hnp',
              payment_method: paymentMethod,
              merchant: merchantKey,
            },
          },
          pendingTaskId,
      );
    } finally {
      mandateApproveInFlightRef.current = false;
    }
  }

  function handleMandateReject() {
    devLog('WebClient', 'mandate rejected');
    addMessage({role: 'system', text: 'Mandate rejected. Purchase cancelled.'});
  }

  async function handleImmediateCheckoutApprove(
      request: ImmediateCheckoutRequest,
      ) {
    const paymentMethod = request.payment_method ?? resolvedHpPayment;
    const checkoutKey = immediateCheckoutKey({
      item_id: request.item_id,
      total_cents: request.total_cents,
      payment_method: paymentMethod,
    });
    const alreadyConfirmed = messages.some(
        (m) =>
            m.role === 'user_action' &&
            m.userActionLabel === 'Confirmed checkout' &&
            m.checkoutKey === checkoutKey,
    );
    if (alreadyConfirmed) {
      devWarn('WebClient', 'checkout approve skipped (already confirmed)', {
        checkoutKey,
      });
      return;
    }
    devLog('WebClient', 'immediate_checkout_approved', {
      item_id: request.item_id,
      item_name: request.item_name,
      total_cents: request.total_cents,
      payment_method: request.payment_method ?? resolvedHpPayment,
    });
    addMessage({
      role: 'user_action',
      userActionLabel: 'Confirmed checkout',
      userActionSublabel: 'User signed Closed Mandate (HP)',
      checkoutKey,
    });
    await sendToAgent(
        {
          type: 'immediate_checkout_approved',
          item_id: request.item_id,
          item_name: request.item_name,
          total_cents: request.total_cents,
          currency: request.currency,
          ap2_config: {
            presence_mode: 'hp',
            payment_method: paymentMethod,
            merchant: merchantKey,
          },
        },
        pendingTaskId,
    );
  }

  function handleImmediateCheckoutReject() {
    devLog('WebClient', 'immediate checkout rejected');
    addMessage({role: 'system', text: 'Checkout cancelled.'});
  }

  return {
    messages,
    input,
    setInput,
    loading,
    pendingTaskId,
    lastSelectedItemName,
    setLastSelectedItemName,
    lastInventoryMatches,
    lastInventoryOptions,
    usedServers,
    isMonitoring,
    hnpBackendWatch,
    mandates,
    approvedMandateItemIds,
    handleSend,
    handleMandateApprove,
    handleMandateReject,
    handleImmediateCheckoutApprove,
    handleImmediateCheckoutReject,
    ap2Config,
    merchantKey,
    resolvedHpPayment,
    sendToAgent,
    sessionId,
  };
}

/**
 * Return shape of {@link useChat}; use this for props instead of duplicating
 * fields.
 */
export type ChatState = ReturnType<typeof useChat>;
