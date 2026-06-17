import type {ChatState} from '../hooks/useChat';
import {TrustedSurface} from '../trustedSurface';
import type {
  ChatMessage,
  ErrorArtifact,
  ImmediateCheckoutRequest,
  InventoryOptionsArtifact,
  MandateRequest,
  MonitoringStatus,
  ProductPreviewUnavailable,
  PurchaseComplete,
  ToolCallArtifact,
} from '../types';
import {
  extractCurrentPriceFromText,
  extractErrorFromText,
  extractImmediateCheckoutFromText,
  extractMandateFromText,
  extractMonitoringFromText,
  extractProductPreviewUnavailableFromText,
  removeArtifactJsonFromText,
  stripAgentArtifactJson,
} from '../utils/parsing';
import {
  extractMandateFromProseTable,
  isMandateAlreadyApproved,
  isMandateSuperseded,
  mandateFromAssembleToolArgs,
  normalizeMandateRequestPayload,
  reconcileMandateBudget,
  stripTrustedSurfaceProseHints,
} from '../utils/mandateFlow';
import {
  buildTriggerPriceDropCurl,
  extractItemIdFromAgentText,
  shouldShowTriggerCurl,
} from '../utils/triggerCurl';
import {normalizeSlugItemId} from '../utils/hnpMonitor';
import {
  immediateCheckoutKey,
  isCheckoutConfirmed,
} from '../utils/checkoutFlow';
import {enrichPurchaseComplete} from '../utils/purchaseReceipt';
import {
  parseFlightTableFromText,
} from '../utils/flightTable';
import {isFlightMerchant, MONITOR_INTERVAL_MINUTES} from '../config';
import {ImmediateCheckoutApproval} from './ImmediateCheckoutApproval';
import {AgentMarkdown} from './AgentMarkdown';
import {AgentProse} from './AgentProse';
import {ErrorCard} from './ErrorCard';
import {FlightOptionsCard} from './FlightOptionsCard';
import {InventoryOptionsCard} from './InventoryOptionsCard';
import {MandateApproval} from './MandateApproval';
import {MonitoringCard} from './MonitoringCard';
import {ProductPreviewUnavailableCard} from './ProductPreviewUnavailableCard';
import {ReceiptCard} from './ReceiptCard';
import {ToolCallCard} from './ToolCallCard';
import {TriggerCurlBox} from './TriggerCurlBox';
import {UserActionCard} from './UserActionCard';

const trustedSurface = new TrustedSurface();

function resolveTriggerItemId(
    messages: ChatMessage[],
    text?: string,
): string|undefined {
  const fromText = text ? extractItemIdFromAgentText(text) : undefined;
  if (fromText) return fromText;

  for (let i = messages.length - 1; i >= 0; i--) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (!data?.type) continue;
    if (data.type === 'monitoring') {
      return (data as MonitoringStatus).item_id;
    }
    if (data.type === 'mandate_request') {
      return (data as MandateRequest).item_id;
    }
    if (data.type === 'inventory_options') {
      const inv = data as InventoryOptionsArtifact;
      return inv.selected ?? inv.matches[0]?.item_id;
    }
    if (data.type === 'tool_call') {
      const tc = data as ToolCallArtifact;
      const argId = tc.args?.item_id;
      if (typeof argId === 'string' && argId) return argId;
    }
  }
  return undefined;
}

function resolveTriggerPrice(
    messages: ChatMessage[],
    itemId: string,
    text?: string,
): number|undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const data = messages[i].artifactData as {type?: string}|undefined;
    if (data?.type === 'monitoring') {
      const mon = data as MonitoringStatus;
      if (mon.item_id === itemId && mon.price_cap != null) {
        return Math.max(1, mon.price_cap - 1);
      }
    }
    if (data?.type === 'mandate_request') {
      const m = data as MandateRequest;
      if (m.item_id === itemId && m.price_cap != null) {
        return Math.max(1, m.price_cap - 1);
      }
    }
    if (data?.type === 'inventory_options') {
      const inv = data as InventoryOptionsArtifact;
      const match = inv.matches.find((x) => x.item_id === itemId) ??
          inv.matches[0];
      if (match?.price != null) return Math.max(1, match.price - 1);
    }
  }
  if (text) {
    const p = extractCurrentPriceFromText(text);
    if (p != null) return Math.max(1, p - 1);
  }
  return undefined;
}

const getArtifactType = (artifactData: unknown): string | undefined => {
  if (
    artifactData &&
    typeof artifactData === 'object' &&
    'type' in artifactData
  ) {
    return (artifactData as {type: string}).type;
  }
  return undefined;
};

type MessageRendererChatState = Pick<
  ChatState,
  | 'approvedMandateItemIds'
  | 'handleImmediateCheckoutApprove'
  | 'handleImmediateCheckoutReject'
  | 'handleMandateApprove'
  | 'handleMandateReject'
  | 'hnpBackendWatch'
  | 'isMonitoring'
  | 'lastInventoryMatches'
  | 'lastInventoryOptions'
  | 'lastSelectedItemName'
  | 'merchantKey'
  | 'messages'
  | 'pendingTaskId'
  | 'resolvedHpPayment'
  | 'sendToAgent'
  | 'sessionId'
  | 'setLastSelectedItemName'
>;

export const MessageRenderer = ({
  msg,
  chatState,
}: {
  msg: ChatMessage;
  chatState: MessageRendererChatState;
}) => {
  const {
    lastInventoryOptions,
    pendingTaskId,
    setLastSelectedItemName,
    sendToAgent,
    lastSelectedItemName,
    lastInventoryMatches,
    messages,
    handleMandateApprove,
    handleMandateReject,
    handleImmediateCheckoutApprove,
    handleImmediateCheckoutReject,
    isMonitoring,
    hnpBackendWatch,
    resolvedHpPayment,
    merchantKey,
    sessionId,
  } = chatState;

  const showShoeTriggerUi = !isFlightMerchant(merchantKey);

  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';
  const artifactType = getArtifactType(msg.artifactData);

  // Skip rendering for internal state artifacts that have no accompanying text
  const hiddenArtifactTypes = [
    'mandates_signed',
    'mandates_created',
    'mandate_presented',
    'mandate_chains_fetched',
  ];
  if (artifactType && hiddenArtifactTypes.includes(artifactType) && !msg.text) {
    return null;
  }

  // 1. User Action
  if (msg.role === 'user_action') {
    return (
      <UserActionCard
        label={msg.userActionLabel ?? 'Action'}
        sublabel={msg.userActionSublabel}
      />
    );
  }

  // 2. Tool Call
  const toolCall =
    artifactType === 'tool_call'
      ? (msg.artifactData as ToolCallArtifact)
      : undefined;

  if (toolCall) {
    if (toolCall.tool === 'assemble_and_sign_mandates_tool') {
      const inferred = mandateFromAssembleToolArgs(toolCall.args);
      if (inferred) {
        const normalized = normalizeMandateRequestPayload(
            inferred as unknown as Record<string, unknown>,
        ) ?? inferred;
        const reconciled = reconcileMandateBudget(
            normalized,
            messages,
            msg.text,
        );
        const mandateWithName = {
          ...reconciled,
          item_name: reconciled.item_name ?? lastSelectedItemName,
          matches: reconciled.matches ?? lastInventoryMatches,
          ...(isFlightMerchant(merchantKey) ?
              {
                constraint_focus: 'price' as const,
                available: reconciled.available ?? true,
              } :
              {}),
        };
        const alreadyApproved =
            isMandateAlreadyApproved(messages, mandateWithName) ||
            isMandateSuperseded(messages, mandateWithName, msg.timestamp);
        return (
          <div className="agent-composite-msg">
            <ToolCallCard
              call={{
                type: 'tool_call',
                tool: toolCall.tool,
                server: toolCall.server,
                message: toolCall.message,
              }}
            />
            <MandateApproval
              mandate={mandateWithName}
              trustedSurface={trustedSurface}
              sessionId={sessionId}
              onApprove={handleMandateApprove}
              onReject={handleMandateReject}
              merchant={merchantKey}
              itemName={lastSelectedItemName}
              currentPrice={mandateWithName.current_price}
              alreadyApproved={alreadyApproved}
            />
          </div>
        );
      }
    }
    return (
      <ToolCallCard
        call={{
          type: 'tool_call',
          tool: toolCall.tool,
          server: toolCall.server,
          message: toolCall.message,
        }}
      />
    );
  }

  // 2.5. Product Preview Unavailable (skip when mandate_request is in same message)
  const mandateInSameMessage =
      artifactType === 'mandate_request' ||
      (msg.text && msg.role === 'agent' && !!extractMandateFromText(msg.text));
  const productPreview =
      !mandateInSameMessage &&
      (artifactType === 'product_preview_unavailable'
        ? (msg.artifactData as ProductPreviewUnavailable)
        : msg.text && msg.role === 'agent'
          ? extractProductPreviewUnavailableFromText(msg.text)
          : undefined);

  if (productPreview) {
    const proseText = msg.text
      ? stripAgentArtifactJson(
          msg.text,
          'product_preview_unavailable',
          'mandate_request',
      )
      : undefined;
    const previewCurl =
        showShoeTriggerUi && productPreview.sku_preview_id
            ? buildTriggerPriceDropCurl(
                normalizeSlugItemId(productPreview.sku_preview_id),
                productPreview.typical_list_price,
            )
            : undefined;
    return (
      <div className="agent-composite-msg">
        {proseText && proseText.trim() && <AgentProse text={proseText} />}
        <ProductPreviewUnavailableCard
          preview={productPreview}
          triggerCurl={previewCurl}
        />
      </div>
    );
  }

  // 3. Inventory Options
  if (artifactType === 'inventory_options') {
    const inv = msg.artifactData as InventoryOptionsArtifact;
    const opts = lastInventoryOptions ?? inv;
    const price_cap = opts?.price_cap;
    const qty = opts?.qty;

    const handleSelect =
      price_cap != null && qty != null && pendingTaskId
        ? (itemId: string) => {
            setLastSelectedItemName(
              inv.matches.find((m) => m.item_id === itemId)?.name,
            );
            sendToAgent(
              {
                type: 'item_selected',
                item_id: itemId,
                price_cap: price_cap,
                qty: qty,
              },
              pendingTaskId,
            );
          }
        : undefined;

    const primaryItemId =
        inv.selected ?? inv.matches[0]?.item_id ?? '';
    const triggerCurl =
        showShoeTriggerUi && primaryItemId
            ? buildTriggerPriceDropCurl(
                primaryItemId,
                inv.matches.find((m) => m.item_id === primaryItemId)?.price,
            )
            : undefined;

    return (
      <InventoryOptionsCard
        inventory={inv}
        onSelect={handleSelect}
        triggerCurl={triggerCurl}
        hpFlow
        merchantKey={merchantKey}
      />
    );
  }

  // 3.5 HP immediate checkout
  const immediateCheckout =
    artifactType === 'immediate_checkout_request'
      ? (msg.artifactData as ImmediateCheckoutRequest)
      : msg.text && msg.role === 'agent'
        ? extractImmediateCheckoutFromText(msg.text)
        : undefined;

  if (immediateCheckout) {
    const proseText = msg.text
      ? removeArtifactJsonFromText(msg.text, 'immediate_checkout_request')
      : undefined;
    const invMatch =
        lastInventoryOptions?.matches.find(
            (m) => m.item_id === immediateCheckout.item_id,
        ) ?? lastInventoryOptions?.matches[0];
    const prosePrice = msg.text ?
        extractCurrentPriceFromText(msg.text) :
        undefined;
    const checkoutRequest = {
      ...immediateCheckout,
      item_id:
          immediateCheckout.item_id ||
          invMatch?.item_id ||
          lastInventoryOptions?.selected,
      item_name:
          immediateCheckout.item_name ||
          lastSelectedItemName ||
          invMatch?.name,
      total_cents:
          immediateCheckout.total_cents ??
          (invMatch?.price != null ?
              Math.round(invMatch.price * 100) :
              prosePrice != null ?
                  Math.round(prosePrice * 100) :
                  undefined),
      payment_method: immediateCheckout.payment_method ?? resolvedHpPayment,
    };
    const checkoutKey = immediateCheckoutKey({
      item_id: checkoutRequest.item_id,
      total_cents: checkoutRequest.total_cents,
      payment_method: checkoutRequest.payment_method ?? resolvedHpPayment,
    });
    const checkoutAlreadyConfirmed = isCheckoutConfirmed(
        messages,
        msg.timestamp,
        checkoutKey,
    );
    return (
      <div className="agent-composite-msg">
        {proseText && proseText.trim() && <AgentProse text={proseText} />}
        <ImmediateCheckoutApproval
          key={checkoutKey}
          request={checkoutRequest}
          trustedSurface={trustedSurface}
          sessionId={sessionId}
          merchant={merchantKey}
          paymentMethod={resolvedHpPayment}
          onApprove={() => handleImmediateCheckoutApprove(checkoutRequest)}
          onReject={handleImmediateCheckoutReject}
          alreadyConfirmed={checkoutAlreadyConfirmed}
        />
      </div>
    );
  }

  // 4. Mandate Request
  const rawMandate =
    artifactType === 'mandate_request'
      ? (msg.artifactData as MandateRequest)
      : msg.text && msg.role === 'agent'
        ? extractMandateFromText(msg.text) ??
          extractMandateFromProseTable(msg.text, {
            messages,
            inventory: lastInventoryOptions,
            paymentMethod: resolvedHpPayment,
          })
        : undefined;
  const mandate = rawMandate ?
      reconcileMandateBudget(
          normalizeMandateRequestPayload(
              rawMandate as unknown as Record<string, unknown>,
          ) ?? rawMandate,
          messages,
          msg.text,
      ) :
      undefined;

  if (mandate) {
    const currentPrice =
      mandate.current_price ??
      (msg.text ? extractCurrentPriceFromText(msg.text) : undefined);
    const mandateWithName = {
      ...mandate,
      item_name: mandate.item_name ?? lastSelectedItemName,
      matches: mandate.matches ?? lastInventoryMatches,
      price_cap:
          mandate.price_cap ??
          mandate.constraints?.price_lt ??
          (mandate.constraints as {price_cap?: number}|undefined)?.price_cap,
      ...(isFlightMerchant(merchantKey) ?
          {
            constraint_focus: 'price' as const,
            available: mandate.available ?? true,
          } :
          {}),
    };
    let proseText = msg.text
      ? stripAgentArtifactJson(
          msg.text,
          'mandate_request',
          'product_preview_unavailable',
      )
      : undefined;
    if (proseText) {
      proseText = stripTrustedSurfaceProseHints(proseText) ?? proseText;
    }

    const mandateSuperseded = isMandateSuperseded(
        messages,
        mandateWithName,
        msg.timestamp,
    );
    const mandateAlreadyApproved =
        !mandateSuperseded &&
        isMandateAlreadyApproved(messages, mandateWithName);

    if (mandateSuperseded) {
      return proseText && proseText.trim() ? (
        <div className="agent-composite-msg">
          <AgentProse text={proseText} />
        </div>
      ) : null;
    }

    const mandateTriggerCurl =
        showShoeTriggerUi &&
        mandateWithName.item_id &&
        (mandateWithName.available === false ||
            (mandateWithName.constraint_focus === 'availability' &&
                mandateWithName.available !== true))
            ? buildTriggerPriceDropCurl(
                mandateWithName.item_id,
                mandateWithName.price_cap != null
                    ? Math.max(1, mandateWithName.price_cap - 1)
                    : undefined,
            )
            : undefined;

    return (
      <div className="agent-composite-msg">
        {proseText && proseText.trim() && <AgentProse text={proseText} />}
        <MandateApproval
          mandate={mandateWithName}
          trustedSurface={trustedSurface}
          sessionId={sessionId}
          onApprove={handleMandateApprove}
          onReject={handleMandateReject}
          merchant={merchantKey}
          itemName={lastSelectedItemName}
          currentPrice={currentPrice}
          alreadyApproved={mandateAlreadyApproved}
          triggerCurl={mandateTriggerCurl}
        />
      </div>
    );
  }

  // 5. Error or Monitoring
  const error =
    artifactType === 'error'
      ? (msg.artifactData as ErrorArtifact)
      : msg.text && msg.role === 'agent'
        ? extractErrorFromText(msg.text)
        : undefined;

  const monitoring =
    artifactType === 'monitoring'
      ? (msg.artifactData as MonitoringStatus)
      : msg.text && msg.role === 'agent'
        ? extractMonitoringFromText(msg.text)
        : undefined;

  if (error || monitoring) {
    const handleCheckNow =
      !error && monitoring && !hnpBackendWatch
        ? () => {
            sendToAgent(
              {
                type: 'check_product_now',
                item_id: monitoring.item_id,
                price_cap: monitoring.price_cap,
                qty: monitoring.qty ?? 1,
                open_checkout_mandate: monitoring.open_checkout_mandate,
                open_payment_mandate: monitoring.open_payment_mandate,
                message: 'Check product now',
                source: 'manual',
              },
              pendingTaskId,
            );
          }
        : undefined;

    return (
      <div className="error-monitoring-wrapper">
        {monitoring && (
          <MonitoringCard
            status={monitoring}
            onCheckNow={handleCheckNow}
            triggerCurl={
              showShoeTriggerUi
                  ? buildTriggerPriceDropCurl(
                      monitoring.item_id,
                      monitoring.price_cap != null
                          ? Math.max(1, monitoring.price_cap - 1)
                          : undefined,
                  )
                  : undefined
            }
            pollIntervalSeconds={
                !error && hnpBackendWatch ? 5 :
                !error && isMonitoring ? 15 :
                undefined
            }
            backendSchedulerMinutes={
                !error && hnpBackendWatch ? MONITOR_INTERVAL_MINUTES : undefined
            }
            itemName={lastSelectedItemName}
            messages={messages}
            merchant={merchantKey}
          />
        )}
        {error && <ErrorCard error={error} />}
      </div>
    );
  }

  // 6. Purchase Complete
  if (artifactType === 'purchase_complete') {
    const enriched = enrichPurchaseComplete(
        msg.artifactData as PurchaseComplete,
        messages,
        lastSelectedItemName,
        merchantKey,
    );
    const hadHpCheckout = messages.some(
        (m) =>
            (m.artifactData as {type?: string}|undefined)?.type ===
            'immediate_checkout_request',
    );
    return (
      <ReceiptCard
        purchase={enriched}
        itemName={lastSelectedItemName}
        merchant={merchantKey}
        presenceMode={hadHpCheckout ? 'hp' : 'hnp'}
      />
    );
  }

  // 7. Standard Text Message Fallback
  const showTriggerCurl =
      showShoeTriggerUi && !isUser && !isSystem && msg.text && shouldShowTriggerCurl(msg.text);
  const stockItemId = showTriggerCurl
      ? resolveTriggerItemId(messages, msg.text)
      : undefined;
  const stockTriggerCurl =
      stockItemId
          ? buildTriggerPriceDropCurl(
              stockItemId,
              resolveTriggerPrice(messages, stockItemId, msg.text),
          )
          : undefined;

  const flightTable =
      !isUser && !isSystem && isFlightMerchant(merchantKey) && msg.text
          ? parseFlightTableFromText(msg.text)
          : undefined;

  if (flightTable?.rows.length) {
    return (
      <div className="agent-composite-msg">
        {flightTable.proseBefore && (
          <AgentProse text={flightTable.proseBefore} />
        )}
        <FlightOptionsCard
          rows={flightTable.rows}
          route={flightTable.route}
        />
        {flightTable.proseAfter && (
          <AgentProse text={flightTable.proseAfter} />
        )}
        {stockTriggerCurl && (
          <TriggerCurlBox
            curl={stockTriggerCurl}
            label="Run this in your terminal (simulate drop):"
            hint="Copy the full curl, run it, then say buy now again."
          />
        )}
      </div>
    );
  }

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'agent'}`}>
      <div
        className={`message-content ${isUser ? 'user' : isSystem ? 'system' : 'agent'}`}>
        {isUser ? (
          msg.text
        ) : (
          <>
            <AgentMarkdown text={msg.text ?? ''} className="message-markdown" />
            {stockTriggerCurl && (
              <TriggerCurlBox
                curl={stockTriggerCurl}
                label="Run this in your terminal (simulate drop):"
                hint="Copy the full curl, run it, then say buy now again."
              />
            )}
          </>
        )}
      </div>
    </div>
  );
};
