import { Radar } from 'lucide-react'
import { useState } from 'react'
import { api, describeError, formatNumber, formatTime, get, humanize } from '../api'
import type { Anomaly, Device } from '../api'
import { Badge, Empty, Loading, Notice, PageHeader } from '../components'
import { useData } from '../hooks'

const load = (signal: AbortSignal) => Promise.all([get<Anomaly[]>('/anomalies?limit=100', signal), get<Device[]>('/devices', signal)])
const algorithms: Record<string, string> = { zscore: 'Z-Score', ewma: 'EWMA', isolation_forest: 'Isolation Forest' }

export function Anomalies() {
  const results = useData(load)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [anomalousOnly, setAnomalousOnly] = useState(true)
  const [rows, devices] = results.data ?? [[], []]
  const shown = rows.filter(item => !anomalousOnly || item.is_anomaly)

  async function runScan() {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const { data } = await api.post<{ devices_scanned: number; results_saved: number; anomalies_detected: number }>('/anomalies/scan')
      setMessage(`Scanned ${data.devices_scanned} devices · ${data.anomalies_detected} anomalies detected · ${data.results_saved} new results saved.`)
      results.refresh()
    } catch (error) {
      setError(describeError(error))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <PageHeader title="Anomaly Detection" description="Inspect statistical deviations in device traffic and probe telemetry."
      action={<button className="button" disabled={busy} onClick={() => void runScan()}><Radar size={17} />{busy ? 'Scanning…' : 'Run Anomaly Scan'}</button>} />
    {(error || results.error) && <Notice error message={error || results.error} />}
    {message && <Notice message={message} />}
    <section className="card">
      <div className="card-heading"><div><h2>Anomaly results</h2><p>{shown.length} shown from the latest 100 evaluations</p></div>
        <label className="checkbox-label"><input type="checkbox" checked={anomalousOnly} onChange={event => setAnomalousOnly(event.target.checked)} />Anomalies only</label></div>
      {shown.length ? <div className="table-scroll"><table><thead><tr><th>Device and metric</th><th>Algorithm</th><th>Observed</th><th>Baseline ± σ</th><th>Score</th><th>Severity</th><th>Window end</th></tr></thead><tbody>
        {shown.map(item => <tr key={item.id}><td><strong>{devices.find(device => device.id === item.device_id)?.hostname ?? `Device #${item.device_id}`}</strong><div className="meta">{humanize(item.metric_name)}{item.explanation_json.synthetic ? ' · Synthetic' : ''}</div></td>
          <td>{algorithms[item.algorithm] ?? humanize(item.algorithm)}</td><td className="mono">{formatNumber(item.observed_value)}</td><td className="mono">{formatNumber(item.baseline_mean)} ± {formatNumber(item.baseline_std)}</td>
          <td className="mono">{formatNumber(item.anomaly_score)}</td><td><Badge value={item.is_anomaly ? item.severity : 'normal'} /></td><td>{formatTime(item.window_end)}</td></tr>)}
      </tbody></table></div> : results.loading ? <Loading /> : <Empty>{anomalousOnly ? 'No anomalies found in recent results.' : 'No evaluations yet.'}</Empty>}
    </section>
  </>
}
