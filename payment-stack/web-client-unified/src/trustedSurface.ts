// Trusted Surface: H5 portal on port 8104 (non-agentic confirmation page).
import {TS_BASE_URL} from './config';
import {devLog, devWarn} from './utils/devLog';

export type PortalConfirmParams = {
  sessionId: string;
  priceCap: number;
  paymentMethod: 'card' | 'x402';
  itemId: string;
  itemName: string;
  presenceMode: 'hp' | 'hnp';
};

export type PortalConfirmOptions = {
  onPortalUrl?: (url: string) => void;
  timeoutMs?: number;
  pollIntervalMs?: number;
};

type TsSessionResponse = {
  ref?: string;
  portal_url?: string;
  error?: string;
  message?: string;
};

type TsStatusResponse = {
  status?: string;
  message?: string;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class TrustedSurface {
  /**
   * Create a TS session, open the H5 portal, poll until signed or timeout.
   * Returns true only when the user confirms on the portal.
   */
  async confirmViaPortal(
      params: PortalConfirmParams,
      options: PortalConfirmOptions = {},
  ): Promise<boolean> {
    const {
      onPortalUrl,
      timeoutMs = 300_000,
      pollIntervalMs = 1500,
    } = options;
    const base = TS_BASE_URL.replace(/\/$/, '');

    devLog('TrustedSurface', 'confirmViaPortal START', {
      session_id: params.sessionId.slice(0, 8),
      price_cap: params.priceCap,
      presence_mode: params.presenceMode,
    });

    let sessionResp: Response;
    try {
      sessionResp = await fetch(`${base}/ts/sessions`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          session_id: params.sessionId,
          price_cap: params.priceCap,
          payment_method: params.paymentMethod,
          item_id: params.itemId,
          item_name: params.itemName,
          presence_mode: params.presenceMode,
        }),
      });
    } catch (err) {
      devWarn('TrustedSurface', 'POST /ts/sessions failed', {error: String(err)});
      return false;
    }

    const sessionData = (await sessionResp.json()) as TsSessionResponse;
    if (!sessionResp.ok || sessionData.error || !sessionData.ref) {
      devWarn('TrustedSurface', 'TS session rejected', sessionData);
      return false;
    }

    const portalUrl = sessionData.portal_url ?? `${base}/ts/confirm?ref=${sessionData.ref}`;
    onPortalUrl?.(portalUrl);
    try {
      window.open(portalUrl, '_blank', 'noopener,noreferrer');
    } catch {
      // Popup blocked — user must click the link in the UI.
    }

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await sleep(pollIntervalMs);
      let statusResp: Response;
      try {
        statusResp = await fetch(
            `${base}/ts/status?ref=${encodeURIComponent(sessionData.ref!)}`,
        );
      } catch (err) {
        devWarn('TrustedSurface', 'GET /ts/status failed', {error: String(err)});
        continue;
      }
      const statusData = (await statusResp.json()) as TsStatusResponse;
      const status = statusData.status ?? '';
      if (status === 'signed') {
        devLog('TrustedSurface', 'portal signed', {ref: sessionData.ref});
        return true;
      }
      if (status === 'expired' || status === 'not_found') {
        devWarn('TrustedSurface', 'portal session ended', statusData);
        return false;
      }
    }

    devWarn('TrustedSurface', 'portal poll timeout', {ref: sessionData.ref});
    return false;
  }
}
