import {MONITOR_SCHEDULER_URL} from './config';
import type {MonitoringStatus, PurchaseComplete} from './types';

export interface MonitorRegisterParams {
  session_id: string;
  item_id: string;
  price_cap: number;
  interval_minutes?: number;
  currency?: string;
  item_name?: string;
  merchant?: string;
  qty?: number;
  open_checkout_mandate?: string;
  open_payment_mandate?: string;
  open_checkout_hash?: string;
  payment_method?: 'card' | 'x402';
}

export interface MonitorStatusResponse {
  status?: string;
  item_id?: string;
  price_cap?: number;
  item_name?: string;
  monitoring?: Partial<MonitoringStatus>;
  purchase_complete?: PurchaseComplete;
  purchase_result?: {purchase_complete?: PurchaseComplete};
  message?: string;
  should_stop?: boolean;
  error?: string;
}

export async function registerBackendMonitor(
    params: MonitorRegisterParams,
    ): Promise<MonitorStatusResponse> {
  const resp = await fetch(`${MONITOR_SCHEDULER_URL}/monitor/register`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(params),
  });
  return resp.json() as Promise<MonitorStatusResponse>;
}

export async function fetchBackendMonitorStatus(
    sessionId: string,
    ): Promise<MonitorStatusResponse> {
  const url =
      `${MONITOR_SCHEDULER_URL}/monitor/status?session_id=${
          encodeURIComponent(sessionId)}`;
  const resp = await fetch(url);
  return resp.json() as Promise<MonitorStatusResponse>;
}
