import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

export interface Merchant {
  id: string
  name: string
  display_name_en: string
  display_name_zh: string
  status: string
  protocols: string[]
  backend_base_url: string
  a2a_endpoint?: string
  ucp_profile_url?: string
  mcp_server_path?: string
  capabilities_json?: Record<string, unknown>
  jwks_url?: string
  onboarded_at?: string
}

export interface KybReview {
  id: number
  merchant_id: string
  legal_name: string
  registration_no: string
  country: string
  vertical: string
  contact_email: string
  documents_json?: Record<string, unknown>
  status: string
  reviewer?: string
  reject_reason?: string
  submitted_at: string
  reviewed_at?: string
}

export interface Contract {
  id: number
  merchant_id: string
  contract_type: string
  template_version: string
  status: string
  signed_by?: string
  signed_at?: string
  summary_json?: Record<string, unknown>
}

export interface OnboardingTask {
  id: number
  merchant_id: string
  step: string
  status: string
  detail_json?: Record<string, unknown>
  created_at: string
}

export interface OnboardingData {
  kyb: KybReview | null
  contract: Contract | null
  tasks: OnboardingTask[]
}

export interface Capability {
  id: number
  merchant_id: string
  capability_id: string
  version: string
  status: string
  descriptor?: string
  vertical?: string
  description_en?: string
  description_zh?: string
  schema_url?: string
  config_json?: Record<string, unknown>
  line_items_schema?: Record<string, unknown>
  registered_at?: string
  validated_at?: string
}

export interface TrustKey {
  id: number
  merchant_id: string
  kid: string
  alg: string
  public_jwk_json: Record<string, unknown>
  source: string
  status: string
  fingerprint: string
  expires_at?: string
  last_verified_at?: string
  alert_status?: string
}

export interface Certificate {
  id: number
  merchant_id: string
  serial_no: string
  subject_cn: string
  issuer_cn: string
  status: string
  not_before: string
  not_after: string
  alert_status: string
  revoked_at?: string
  revoke_reason?: string
}

export interface Transaction {
  id: number
  merchant_id: string
  order_id: string
  mandate_ref?: string
  receipt_ref?: string
  amount: number
  currency: string
  status: string
  vertical?: string
  descriptor?: string
  audit_index?: string
  detail_json?: Record<string, unknown>
  occurred_at: string
}

export interface ReconciliationRun {
  id: number
  merchant_id: string
  status: string
  total_items: number
  matched_items: number
  mismatch_items: number
  mandate_verify_fail_count: number
  file_summary_json?: Record<string, unknown>
  started_at: string
  completed_at?: string
  items?: ReconciliationItem[]
}

export interface ReconciliationItem {
  id: number
  run_id: number
  merchant_id: string
  order_id: string
  mandate_ref?: string
  receipt_ref?: string
  status: string
  mismatch_reason?: string
  detail_json?: Record<string, unknown>
}

export interface ExportJob {
  id: number
  merchant_id: string
  export_type: string
  status: string
  requested_by: string
  filters_json?: Record<string, unknown>
  artifact_summary_json?: Record<string, unknown>
  created_at: string
  completed_at?: string
}

export interface OperationLog {
  id: number
  merchant_id?: string
  action: string
  actor: string
  detail_json?: Record<string, unknown>
  created_at: string
}

export interface MonitoringOverview {
  merchant_id: string
  transaction_stats: Record<string, number>
  latest_reconciliation?: ReconciliationRun
  alerts: Array<{ type: string; count: number; severity: string }>
}

async function unwrap<T>(promise: Promise<{ data: { data: T } }>): Promise<T> {
  const { data } = await promise
  return data.data
}

export const getDashboard = () => unwrap<Record<string, number>>(api.get('/admin/dashboard'))
export const getMerchants = (status?: string) =>
  unwrap<Merchant[]>(api.get('/admin/merchants', { params: { status } }))
export const createMerchant = (payload: Partial<Merchant> & {
  name: string
  vertical?: string
  legal_name?: string
  registration_no?: string
  contact_email?: string
  country?: string
}) => unwrap<Merchant>(api.post('/admin/merchants', payload))
export const getMerchant = (id: string) => unwrap<Merchant>(api.get(`/admin/merchants/${id}`))
export const deleteMerchant = (id: string) => unwrap<null>(api.delete(`/admin/merchants/${id}`))
export const getOnboarding = (id: string) => unwrap<OnboardingData>(api.get(`/admin/merchants/${id}/onboarding`))
export const submitKyb = (id: string, payload: Partial<KybReview>) =>
  unwrap<KybReview>(api.post(`/admin/merchants/${id}/kyb`, payload))
export const reviewKyb = (id: string, approved: boolean, rejectReason?: string) =>
  unwrap<KybReview>(api.post(`/admin/merchants/${id}/kyb/review`, { approved, reject_reason: rejectReason }))
export const signContract = (id: string, signedBy: string) =>
  unwrap<Contract>(api.post(`/admin/merchants/${id}/contract/sign`, { signed_by: signedBy }))
export const onboardMerchant = (id: string) => unwrap<Merchant>(api.post(`/admin/merchants/${id}/onboard`))
export const disableMerchant = (id: string) => unwrap<Merchant>(api.post(`/admin/merchants/${id}/disable`))
export const enableMerchant = (id: string) => unwrap<Merchant>(api.post(`/admin/merchants/${id}/enable`))
export const getCapabilities = (id: string) =>
  unwrap<Capability[]>(api.get(`/admin/merchants/${id}/capabilities`))
export const createCapability = (id: string, payload: Partial<Capability>) =>
  unwrap<Capability>(api.post(`/admin/merchants/${id}/capabilities`, payload))
export const updateCapability = (id: string, capId: string, payload: Partial<Capability>) =>
  unwrap<Capability>(api.put(`/admin/merchants/${id}/capabilities/${capId}`, payload))
export const deleteCapability = (id: string, capId: string) =>
  unwrap<null>(api.delete(`/admin/merchants/${id}/capabilities/${encodeURIComponent(capId)}`))
export const validateCapability = (id: string, capId: string) =>
  unwrap<Capability>(api.post(`/admin/merchants/${id}/capabilities/${capId}/validate`))
export const publishCapability = (id: string, capId: string) =>
  unwrap<Capability>(api.post(`/admin/merchants/${id}/capabilities/${capId}/publish`))
export const offlineCapability = (id: string, capId: string) =>
  unwrap<Capability>(api.post(`/admin/merchants/${id}/capabilities/${capId}/offline`))
export const getTrustKeys = (id: string) => unwrap<TrustKey[]>(api.get(`/admin/merchants/${id}/trust/keys`))
export const registerTrustKey = (id: string) => unwrap<TrustKey>(api.post(`/admin/merchants/${id}/trust/keys`))
export const rotateTrustKey = (id: string, actor = 'merchant') =>
  unwrap<TrustKey>(api.post(`/admin/merchants/${id}/trust/keys/rotate`, null, { params: { actor } }))
export const verifyTrustKey = (id: string, kid: string) =>
  unwrap<TrustKey>(api.post(`/admin/merchants/${id}/trust/keys/${encodeURIComponent(kid)}/verify`))
export const deleteTrustKey = (id: string, kid: string) =>
  unwrap<null>(api.delete(`/admin/merchants/${id}/trust/keys/${encodeURIComponent(kid)}`))
export const getExpiryAlerts = (merchantId?: string) =>
  unwrap<TrustKey[]>(api.get('/admin/trust/expiry-alerts', { params: { merchant_id: merchantId } }))
export const getCertificates = (id: string) =>
  unwrap<Certificate[]>(api.get(`/admin/merchants/${id}/certificates`))
export const issueCertificate = (id: string, subjectCn?: string) =>
  unwrap<Certificate>(api.post(`/admin/merchants/${id}/certificates/issue`, { subject_cn: subjectCn }))
export const revokeCertificate = (id: string, serialNo: string, reason?: string) =>
  unwrap<Certificate>(api.post(`/admin/merchants/${id}/certificates/${encodeURIComponent(serialNo)}/revoke`, { reason }))
export const deleteCertificate = (id: string, serialNo: string) =>
  unwrap<null>(api.delete(`/admin/merchants/${id}/certificates/${encodeURIComponent(serialNo)}`))
export const refreshCertAlerts = (merchantId?: string) =>
  unwrap<Certificate[]>(api.post('/admin/certificates/refresh-alerts', null, { params: { merchant_id: merchantId } }))
export const getTransactions = (id: string, params?: Record<string, string | number>) =>
  unwrap<Transaction[]>(api.get(`/admin/merchants/${id}/transactions`, { params }))
export const getTransactionStats = (id: string) =>
  unwrap<Record<string, number>>(api.get(`/admin/merchants/${id}/transactions/stats`))
export const getMonitoring = (id: string) => unwrap<MonitoringOverview>(api.get(`/admin/merchants/${id}/monitoring`))
export const getReconciliationRuns = (id: string) =>
  unwrap<ReconciliationRun[]>(api.get(`/admin/merchants/${id}/reconciliation/runs`))
export const runReconciliation = (id: string) =>
  unwrap<ReconciliationRun>(api.post(`/admin/merchants/${id}/reconciliation/run`))
export const getExports = (id: string) => unwrap<ExportJob[]>(api.get(`/admin/merchants/${id}/exports`))
export const createDisputeExport = (id: string, requestedBy = 'merchant') =>
  unwrap<ExportJob>(api.post(`/admin/merchants/${id}/exports/dispute`, { requested_by: requestedBy }))
export const getOperationLogs = (params?: { merchant_id?: string; action?: string; limit?: number }) =>
  unwrap<OperationLog[]>(api.get('/admin/operation-logs', { params }))
