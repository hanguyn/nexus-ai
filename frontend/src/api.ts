import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 125_000,
})

export function describeError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(item => item.msg).join('; ')
    if (error.response) return `Request failed (HTTP ${error.response.status}).`
  }
  return error instanceof Error ? error.message : 'Request failed.'
}

export type Site = { id: number; name: string; location: string | null; description: string | null }
export type DeviceType = 'router' | 'switch' | 'firewall' | 'server'
export type Device = {
  id: number; site_id: number; hostname: string; ip_address: string; device_type: DeviceType
  vendor: string | null; monitoring_enabled: boolean; status: string
}
export type Dependency = { id: number; upstream_device_id: number; downstream_device_id: number; dependency_type: string }
export type Alert = { id: number; alertname: string; instance: string; severity: string; status: string; starts_at: string; ends_at: string | null }
export type Incident = {
  id: number; site_id: number | null; title: string; status: string; severity: string
  created_at: string; updated_at: string; resolved_at: string | null
  alerts: Alert[]
  history: { id: number; action: string; note: string; created_at: string }[]
}
export type Evidence = { id: number; evidence_type: string; description: string; weight: number; observed_at: string }
export type Candidate = {
  id: number; rank: number; candidate_component: string; confidence_score: number
  verification_status: 'verified' | 'potential'; summary: string
  evidence: Evidence[]; missing_data_json: string[]
}
export type Recommendation = {
  id: number; executive_summary: string; technical_explanation: string; implications?: string
  impact_assessment: string; limitations_note: string; model_provider: string; model_name: string
  evidence_citations_json: { evidence_id: number; observed_at: string }[]
}
export type Run = { id: number; step_title: string; command_or_action: string; execution_mode: string; status: string; operator_note: string | null }
export type Verification = { is_recovered: boolean; results: { id: number; target_metric_or_probe: string; pre_fix_value: number | null; post_fix_value: number | null; is_recovered: boolean }[] }
export type Assistant = { recommendation: Recommendation | null; troubleshooting_runs: Run[]; verification: Verification | null }
export type Anomaly = {
  id: number; device_id: number; metric_name: string; algorithm: string; observed_value: number
  baseline_mean: number; baseline_std: number; anomaly_score: number; severity: string; is_anomaly: boolean
  window_end: string; explanation_json: { synthetic?: boolean }
}
export type HealthPoint = { at: string; online: number; offline: number; unknown: number }
export type NetworkHealth = {
  history: HealthPoint[]
  device_statuses: Record<string, 'online' | 'offline' | 'unknown'>
  active_anomalies: number
}
export const get = <T,>(path: string, signal?: AbortSignal) => api.get<T>(path, { signal }).then(response => response.data)
export const humanize = (value: string) => value.replaceAll('_', ' ').replace(/^./, first => first.toUpperCase())
export const formatTime = (value: string) => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
export const formatNumber = (value: number) => new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4 }).format(value)
